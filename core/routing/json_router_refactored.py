# -*- coding: utf-8 -*-
"""
重构的JSON路由器
使用模块化组件，大幅减少代码复杂度
"""
import logging
import threading
from typing import Optional, List

from .candidate_finder import CandidateFinder
from .channel_scorer import ChannelScorer
from .models import RoutingRequest, RoutingScore, ChannelCandidate
from ..exceptions import TagNotFoundError, ParameterComparisonError, handle_errors, ErrorCode, RoutingException
from ..yaml_config import YAMLConfigLoader, get_yaml_config_loader
from ..utils.parameter_comparator import get_parameter_comparator
from ..utils.model_analyzer import get_model_analyzer
from ..utils.request_cache import get_request_cache

logger = logging.getLogger(__name__)


class RefactoredJSONRouter:
    """重构的JSON路由器 - 模块化设计"""
    
    def __init__(self, config_loader: Optional[YAMLConfigLoader] = None):
        self.config_loader = config_loader or get_yaml_config_loader()
        self.config = self.config_loader.config
        
        # 初始化模块化组件
        self.candidate_finder = CandidateFinder(
            self.config_loader, 
            get_parameter_comparator()
        )
        self.channel_scorer = ChannelScorer(
            self.config_loader,
            get_model_analyzer()
        )
        
        # 缓存
        self._available_models_cache: Optional[List[str]] = None
        self._available_tags_cache: Optional[set] = None
        
        logger.info("重构的JSON路由器初始化完成")
    
    @handle_errors(attempt_recovery=True, reraise=True)
    async def route(self, request: RoutingRequest) -> List[RoutingScore]:
        """主要路由方法 - 简化的流程"""
        try:
            logger.info(f"🚀 ROUTING START: Processing model '{request.model}'")
            
            # 检查缓存
            cache = get_request_cache()
            cached_result = await self._check_cache(cache, request)
            if cached_result:
                return cached_result
            
            # 第一步：查找候选渠道
            candidates = self.candidate_finder.find_candidates(request)
            if not candidates:
                logger.warning(f"No candidates found for model '{request.model}'")
                return []
            
            logger.info(f"Found {len(candidates)} candidate channels")
            
            # 第二步：过滤渠道
            filtered_candidates = self._filter_channels(candidates, request)
            if not filtered_candidates:
                logger.warning(f"No channels available after filtering for model '{request.model}'")
                return []
            
            logger.info(f"Filtered to {len(filtered_candidates)} available channels")
            
            # 第三步：评分和排序
            scored_channels = await self.channel_scorer.score_channels(filtered_candidates, request)
            if not scored_channels:
                logger.warning(f"Failed to score any channels for model '{request.model}'")
                return []
            
            logger.info(f"🎉 ROUTING SUCCESS: Scored {len(scored_channels)} channels for '{request.model}'")
            
            # 缓存结果
            await self._cache_result(cache, request, scored_channels)
            
            return scored_channels
            
        except (TagNotFoundError, ParameterComparisonError):
            # 让特定异常传播
            raise
        except Exception as e:
            logger.error(f"ROUTING ERROR: {e}", exc_info=True)
            return []
    
    def _filter_channels(self, channels: List[ChannelCandidate], request: RoutingRequest) -> List[ChannelCandidate]:
        """过滤渠道 - 简化版本"""
        filtered = []
        
        for candidate in channels:
            channel = candidate.channel
            
            # 基本检查
            if not channel.enabled or not channel.api_key:
                continue
            
            # 健康状态检查
            health_scores = self.config_loader.runtime_state.health_scores
            health_score = health_scores.get(channel.id, 1.0)
            if health_score < 0.3:
                continue
            
            filtered.append(candidate)
        
        return filtered
    
    async def _check_cache(self, cache, request: RoutingRequest) -> Optional[List[RoutingScore]]:
        """检查缓存"""
        try:
            # 简化的缓存检查
            return None  # 暂时禁用缓存
        except Exception as e:
            logger.debug(f"Cache check failed: {e}")
            return None
    
    async def _cache_result(self, cache, request: RoutingRequest, scored_channels: List[RoutingScore]) -> None:
        """缓存结果"""
        try:
            # 简化的缓存保存
            pass  # 暂时禁用缓存
        except Exception as e:
            logger.debug(f"Cache save failed: {e}")
    
    def get_available_models(self) -> List[str]:
        """获取可用模型列表"""
        if self._available_models_cache is not None:
            return self._available_models_cache
        
        try:
            models = set()
            
            # 从配置获取
            for channel in self.config_loader.get_enabled_channels():
                if channel.model_name:
                    models.add(channel.model_name)
            
            # 从缓存获取
            model_cache = self.config_loader.get_model_cache()
            for channel_id, cache_data in model_cache.items():
                if isinstance(cache_data, dict) and 'models' in cache_data:
                    models.update(cache_data['models'])
            
            self._available_models_cache = sorted(list(models))
            logger.info(f"Available models: {len(self._available_models_cache)}")
            return self._available_models_cache
            
        except Exception as e:
            logger.error(f"Failed to get available models: {e}")
            return []
    
    def get_all_available_tags(self) -> List[str]:
        """获取所有可用标签"""
        if self._available_tags_cache is not None:
            return sorted(list(self._available_tags_cache))
        
        try:
            tags = set()
            
            # 从渠道标签获取
            for channel in self.config_loader.get_enabled_channels():
                if hasattr(channel, 'tags') and channel.tags:
                    tags.update(tag.lower() for tag in channel.tags)
            
            self._available_tags_cache = tags
            logger.info(f"Available tags: {len(tags)}")
            return sorted(list(tags))
            
        except Exception as e:
            logger.error(f"Failed to get available tags: {e}")
            return []
    
    def clear_cache(self):
        """清除缓存"""
        self._available_models_cache = None
        self._available_tags_cache = None
        logger.info("Router cache cleared")
    
    def update_channel_health(self, channel_id: str, success: bool, latency: Optional[float] = None):
        """更新渠道健康状态"""
        self.config_loader.update_channel_health(channel_id, success, latency)


# 全局路由器实例（线程安全）
_refactored_router: Optional[RefactoredJSONRouter] = None
_router_lock = threading.Lock()


def get_refactored_router() -> RefactoredJSONRouter:
    """获取重构的路由器实例（线程安全）"""
    global _refactored_router
    if _refactored_router is None:
        with _router_lock:
            if _refactored_router is None:
                _refactored_router = RefactoredJSONRouter()
    return _refactored_router