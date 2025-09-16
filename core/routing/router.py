"""
核心路由引擎（DEPRECATED/遗留） - 从原 json_router.py 拆分出来的主要路由逻辑

默认运行路径为 YAML + 标签路由（JSONRouter + services）。
本模块仅为向后兼容而保留，不建议用于新代码。
"""
import logging
from typing import Optional

from .exceptions import TagNotFoundError, ParameterComparisonError
from .filters import parse_size_filter, apply_size_filters  
from .models import RoutingScore, ChannelCandidate, RoutingRequest
from ..yaml_config import YAMLConfigLoader, get_yaml_config_loader
from ..utils.unified_model_registry import get_unified_model_registry
from ..utils.model_analyzer import get_model_analyzer
from ..utils.channel_cache_manager import get_channel_cache_manager
from ..utils.parameter_comparator import get_parameter_comparator
from ..utils.local_model_capabilities import get_capability_detector
from ..utils.capability_mapper import get_capability_mapper
from ..utils.request_cache import RequestFingerprint, get_request_cache
from ..utils.thread_safe_singleton import get_or_create_global

logger = logging.getLogger(__name__)


class JSONRouter:
    """基于Pydantic验证后配置的路由器 - 重构版本"""

    def __init__(self, config_loader: Optional[YAMLConfigLoader] = None):
        self.config_loader = config_loader or get_yaml_config_loader()
        self.config = self.config_loader.config

        # 标签缓存，避免重复计算
        self._tag_cache: dict[str, list[str]] = {}
        self._available_tags_cache: Optional[set] = None
        self._available_models_cache: Optional[list[str]] = None

        # 初始化各种服务组件
        self.unified_registry = get_unified_model_registry()
        self.model_analyzer = get_model_analyzer()
        self.cache_manager = get_channel_cache_manager()
        self.parameter_comparator = get_parameter_comparator()
        self.capability_detector = get_capability_detector()
        self.capability_mapper = get_capability_mapper()

    async def route_request(self, request: RoutingRequest) -> list[RoutingScore]:
        """
        路由请求，返回按评分排序的候选渠道列表
        
        这是一个精简版本的实现，主要逻辑保持不变但代码更清晰
        """
        logger.info(f"ROUTING START: Processing request for model '{request.model}'")
        
        try:
            # 1. 解析请求模型
            candidates = await self._find_matching_candidates(request)
            
            if not candidates:
                logger.warning(f"No candidates found for model '{request.model}'")
                return []
            
            # 2. 应用过滤器
            candidates = await self._apply_filters(candidates, request)
            
            # 3. 计算评分
            scored_candidates = await self._score_candidates(candidates, request)
            
            # 4. 排序和返回
            return await self._sort_and_format_results(scored_candidates, request)
            
        except Exception as e:
            logger.error(f"Routing failed for model '{request.model}': {e}")
            raise

    async def _find_matching_candidates(self, request: RoutingRequest) -> list[ChannelCandidate]:
        """查找匹配的候选渠道"""
        model_query = request.model.lower()
        candidates = []
        
        # 检查是否是标签查询 (tag:xxx格式)
        if model_query.startswith('tag:'):
            tags_str = model_query[4:]  # 移除'tag:'前缀
            tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
            candidates = await self._find_by_tags(tags)
        else:
            # 直接模型名查询
            candidates = await self._find_by_model_name(model_query)
        
        return candidates

    async def _find_by_tags(self, tags: list[str]) -> list[ChannelCandidate]:
        """根据标签查找候选渠道"""
        candidates = []
        
        # 从统一注册表获取所有可用模型
        try:
            all_models = await self.unified_registry.get_all_models()
        except Exception as e:
            logger.error(f"Failed to get models from registry: {e}")
            return []
        
        # 解析大小过滤器
        size_filters = []
        search_tags = []
        
        for tag in tags:
            size_filter = parse_size_filter(tag)
            if size_filter:
                size_filters.append(size_filter)
            else:
                search_tags.append(tag.lower())
        
        # 查找匹配的模型
        for channel_id, models in all_models.items():
            for model_name, model_info in models.items():
                model_tags = self._extract_tags_from_model_name(model_name)
                
                # 检查是否包含所有搜索标签
                if all(tag in model_tags for tag in search_tags):
                    # 获取渠道对象
                    channel = await self._get_channel_by_id(channel_id)
                    if channel and channel.enabled:
                        candidate = ChannelCandidate(
                            channel=channel,
                            model_name=model_name
                        )
                        candidates.append(candidate)
        
        # 应用大小过滤器
        if size_filters:
            candidates = apply_size_filters(candidates, size_filters)
        
        return candidates

    async def _find_by_model_name(self, model_name: str) -> list[ChannelCandidate]:
        """根据模型名查找候选渠道"""
        candidates = []
        
        try:
            all_models = await self.unified_registry.get_all_models()
        except Exception as e:
            logger.error(f"Failed to get models from registry: {e}")
            return []
        
        # 精确匹配和模糊匹配
        for channel_id, models in all_models.items():
            for available_model, model_info in models.items():
                if (model_name == available_model.lower() or 
                    model_name in available_model.lower() or
                    available_model.lower() in model_name):
                    
                    channel = await self._get_channel_by_id(channel_id)
                    if channel and channel.enabled:
                        candidate = ChannelCandidate(
                            channel=channel,
                            model_name=available_model
                        )
                        candidates.append(candidate)
        
        return candidates

    async def _apply_filters(self, candidates: list[ChannelCandidate], request: RoutingRequest) -> list[ChannelCandidate]:
        """应用各种过滤器"""
        filtered_candidates = candidates
        
        # 排除指定渠道
        if request.exclude_channels:
            filtered_candidates = [
                c for c in filtered_candidates 
                if c.channel.id not in request.exclude_channels
            ]
        
        # 能力过滤
        if request.required_capabilities:
            filtered_candidates = await self._filter_by_capabilities(
                filtered_candidates, request.required_capabilities
            )
        
        return filtered_candidates

    async def _filter_by_capabilities(self, candidates: list[ChannelCandidate], 
                                    required_capabilities: list[str]) -> list[ChannelCandidate]:
        """根据能力需求过滤候选渠道"""
        filtered = []
        
        for candidate in candidates:
            try:
                # 检查渠道是否支持所需能力
                channel_capabilities = await self._get_channel_capabilities(candidate)
                
                if all(cap in channel_capabilities for cap in required_capabilities):
                    filtered.append(candidate)
            except Exception as e:
                logger.warning(f"Failed to check capabilities for {candidate.channel.id}: {e}")
                continue
        
        return filtered

    async def _score_candidates(self, candidates: list[ChannelCandidate], 
                               request: RoutingRequest) -> list[ChannelCandidate]:
        """为候选渠道计算评分"""
        for candidate in candidates:
            try:
                score = await self._calculate_routing_score(candidate, request)
                candidate.score = score
            except Exception as e:
                logger.warning(f"Failed to score candidate {candidate.channel.id}: {e}")
                # 给一个默认的低分
                candidate.score = RoutingScore(
                    final_score=10.0,
                    cost_score=10.0,
                    speed_score=10.0, 
                    quality_score=10.0,
                    reliability_score=10.0,
                    capabilities_score=10.0
                )
        
        return candidates

    async def _calculate_routing_score(self, candidate: ChannelCandidate, 
                                     request: RoutingRequest) -> RoutingScore:
        """计算路由评分 - 简化版本"""
        
        # 基础分数
        cost_score = 50.0
        speed_score = 50.0
        quality_score = 50.0
        reliability_score = 50.0
        capabilities_score = 50.0
        
        try:
            # 成本评分 - 免费的给高分
            if 'free' in candidate.model_name.lower():
                cost_score = 90.0
            elif candidate.channel.cost_per_token:
                # 成本越低分数越高
                input_cost = candidate.channel.cost_per_token.get('input', 0.001)
                cost_score = max(10.0, 100.0 - (input_cost * 100000))
            
            # 速度评分 - 本地服务给高分
            if 'localhost' in str(candidate.channel.base_url) or 'local' in candidate.model_name.lower():
                speed_score = 95.0
            else:
                speed_score = 70.0
            
            # 质量评分 - 基于模型大小和类型
            model_analysis = self.model_analyzer.get_model_analysis(
                candidate.channel.id, candidate.model_name
            )
            if model_analysis:
                param_count = model_analysis.get('parameter_count', 0)
                if param_count > 70e9:  # 70B+参数
                    quality_score = 90.0
                elif param_count > 7e9:  # 7B+参数
                    quality_score = 80.0
                else:
                    quality_score = 60.0
            
            # 可靠性评分 - 基于渠道健康状态
            if hasattr(candidate.channel, 'health_score'):
                reliability_score = candidate.channel.health_score * 100
            else:
                reliability_score = 80.0
            
            # 能力评分 - 基于支持的功能
            capabilities_score = 70.0  # 默认值
            
        except Exception as e:
            logger.warning(f"Error calculating detailed scores for {candidate.channel.id}: {e}")
        
        # 根据策略计算最终分数
        if request.strategy == "cost_first":
            final_score = cost_score * 0.6 + speed_score * 0.2 + quality_score * 0.1 + reliability_score * 0.1
        elif request.strategy == "speed_first":
            final_score = speed_score * 0.6 + cost_score * 0.2 + quality_score * 0.1 + reliability_score * 0.1
        elif request.strategy == "quality_first":
            final_score = quality_score * 0.6 + reliability_score * 0.2 + speed_score * 0.1 + cost_score * 0.1
        else:  # balanced
            final_score = (cost_score + speed_score + quality_score + reliability_score + capabilities_score) / 5
        
        return RoutingScore(
            final_score=final_score,
            cost_score=cost_score,
            speed_score=speed_score,
            quality_score=quality_score,
            reliability_score=reliability_score,
            capabilities_score=capabilities_score
        )

    async def _sort_and_format_results(self, candidates: list[ChannelCandidate], 
                                      request: RoutingRequest) -> list[RoutingScore]:
        """排序并格式化结果"""
        # 过滤掉没有评分的候选者
        scored_candidates = [c for c in candidates if c.score is not None]
        
        # 按评分排序（降序）
        scored_candidates.sort(key=lambda c: c.score.final_score, reverse=True)
        
        # 返回评分列表
        return [c.score for c in scored_candidates[:10]]  # 限制返回前10个结果

    def _extract_tags_from_model_name(self, model_name: str) -> list[str]:
        """从模型名称提取标签"""
        if model_name in self._tag_cache:
            return self._tag_cache[model_name]
        
        # 使用多种分隔符拆分
        import re
        separators = r'[:\/@\-_,]+'
        parts = re.split(separators, model_name.lower())
        
        # 清理和过滤标签
        tags = []
        for part in parts:
            part = part.strip()
            if part and len(part) > 1:  # 忽略单字符标签
                tags.append(part)
        
        # 缓存结果
        self._tag_cache[model_name] = tags
        return tags

    async def _get_channel_by_id(self, channel_id: str):
        """根据ID获取渠道对象"""
        # 这里应该从配置或数据库中获取渠道信息
        # 简化实现
        try:
            for channel in self.config.channels:
                if channel.id == channel_id:
                    return channel
        except Exception as e:
            logger.error(f"Error getting channel {channel_id}: {e}")
        return None

    async def _get_channel_capabilities(self, candidate: ChannelCandidate) -> list[str]:
        """获取渠道能力列表"""
        # 简化实现 - 返回基本能力
        capabilities = ['text']
        
        try:
            if hasattr(candidate.channel, 'capabilities') and candidate.channel.capabilities:
                capabilities.extend(candidate.channel.capabilities)
        except Exception as e:
            logger.warning(f"Error getting capabilities for {candidate.channel.id}: {e}")
        
        return capabilities


def get_router() -> JSONRouter:
    """获取全局路由器实例"""
    def _create_router():
        return JSONRouter()
    
    return get_or_create_global("_router", _create_router)
