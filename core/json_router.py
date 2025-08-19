"""
基于JSON配置的轻量路由引擎
"""
import random
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import time
import logging

from .yaml_config import YAMLConfigLoader, get_yaml_config_loader
from .config_models import Channel
from .utils.model_analyzer import get_model_analyzer
from .utils.channel_cache_manager import get_channel_cache_manager
from .utils.request_cache import get_request_cache, RequestFingerprint

logger = logging.getLogger(__name__)

class TagNotFoundError(Exception):
    """标签未找到错误"""
    def __init__(self, tags: List[str], message: str = None):
        self.tags = tags
        if message is None:
            if len(tags) == 1:
                message = f"没有找到匹配标签 '{tags[0]}' 的模型"
            else:
                message = f"没有找到同时匹配标签 {tags} 的模型"
        super().__init__(message)

@dataclass
class RoutingScore:
    """路由评分结果"""
    channel: Channel
    total_score: float
    cost_score: float
    speed_score: float
    quality_score: float
    reliability_score: float
    reason: str
    matched_model: Optional[str] = None  # 对于标签路由，记录实际匹配的模型

@dataclass
class ChannelCandidate:
    """候选渠道信息"""
    channel: Channel
    matched_model: Optional[str] = None  # 对于标签路由，记录实际匹配的模型

@dataclass
class RoutingRequest:
    """路由请求"""
    model: str
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    functions: Optional[List[Dict[str, Any]]] = None
    required_capabilities: List[str] = None

class JSONRouter:
    """基于Pydantic验证后配置的路由器"""
    
    def __init__(self, config_loader: Optional[YAMLConfigLoader] = None):
        self.config_loader = config_loader or get_yaml_config_loader()
        self.config = self.config_loader.config
        
        # 标签缓存，避免重复计算
        self._tag_cache: Dict[str, List[str]] = {}
        self._available_tags_cache: Optional[set] = None
        self._available_models_cache: Optional[List[str]] = None
        
        # 模型分析器和缓存管理器
        self.model_analyzer = get_model_analyzer()
        self.cache_manager = get_channel_cache_manager()
        
    async def route_request(self, request: RoutingRequest) -> List[RoutingScore]:
        """
        路由请求，返回按评分排序的候选渠道列表。
        
        支持请求级缓存以提高性能：
        - 缓存TTL: 60秒
        - 基于请求指纹的智能缓存键生成
        - 自动故障转移和缓存失效
        """
        logger.info(f"🚀 ROUTING START: Processing request for model '{request.model}'")
        
        # 生成请求指纹用于缓存
        fingerprint = RequestFingerprint(
            model=request.model,
            routing_strategy=getattr(request, 'routing_strategy', 'balanced'),
            required_capabilities=getattr(request, 'required_capabilities', None),
            min_context_length=getattr(request, 'min_context_length', None),
            max_cost_per_1k=getattr(request, 'max_cost_per_1k', None),
            prefer_local=getattr(request, 'prefer_local', False),
            exclude_providers=getattr(request, 'exclude_providers', None),
            # 新增影响路由的参数
            max_tokens=getattr(request, 'max_tokens', None),
            temperature=getattr(request, 'temperature', None),
            stream=getattr(request, 'stream', False),
            has_functions=bool(getattr(request, 'functions', None) or getattr(request, 'tools', None))
        )
        
        # 检查缓存
        cache = get_request_cache()
        cached_result = await cache.get_cached_selection(fingerprint)
        
        if cached_result:
            # 缓存命中，转换为RoutingScore列表
            logger.info(f"⚡ CACHE HIT: Using cached selection for '{request.model}' "
                       f"(cost: ${cached_result.cost_estimate:.4f})")
            
            # 构建RoutingScore列表
            scores = []
            
            # 主要渠道
            primary_score = RoutingScore(
                channel=cached_result.primary_channel,
                total_score=1.0,  # 缓存的结果优先级最高
                cost_score=1.0 if cached_result.cost_estimate == 0.0 else 0.8,
                speed_score=0.9,  # 缓存访问很快
                quality_score=0.8,
                reliability_score=0.9,
                reason=f"CACHED: {cached_result.selection_reason}",
                matched_model=cached_result.primary_matched_model or request.model  # 使用缓存中的真实模型名
            )
            scores.append(primary_score)
            
            # 备选渠道  
            for i, backup_channel in enumerate(cached_result.backup_channels):
                # 获取对应的备选模型名
                backup_matched_model = None
                if cached_result.backup_matched_models and i < len(cached_result.backup_matched_models):
                    backup_matched_model = cached_result.backup_matched_models[i]
                
                backup_score = RoutingScore(
                    channel=backup_channel,
                    total_score=0.9 - i * 0.1,  # 递减优先级
                    cost_score=0.7,
                    speed_score=0.8,
                    quality_score=0.7,
                    reliability_score=0.8,
                    reason=f"CACHED_BACKUP_{i+1}",
                    matched_model=backup_matched_model or request.model  # 使用缓存中的真实模型名
                )
                scores.append(backup_score)
            
            return scores
        
        # 缓存未命中，执行正常路由逻辑
        logger.info(f"⏱️  CACHE MISS: Computing fresh routing for '{request.model}'")
        try:
            # 第一步：获取候选渠道
            logger.info(f"🔍 STEP 1: Finding candidate channels...")
            candidates = self._get_candidate_channels(request)
            if not candidates:
                logger.warning(f"❌ ROUTING FAILED: No suitable channels found for model '{request.model}'")
                return []
            
            logger.info(f"✅ STEP 1 COMPLETE: Found {len(candidates)} candidate channels")
            
            # 第二步：过滤渠道
            logger.info(f"🔧 STEP 2: Filtering channels by health and availability...")
            filtered_candidates = self._filter_channels(candidates, request)
            if not filtered_candidates:
                logger.warning(f"❌ ROUTING FAILED: No available channels after filtering for model '{request.model}'")
                return []
            
            logger.info(f"✅ STEP 2 COMPLETE: {len(filtered_candidates)} channels passed filtering (filtered out {len(candidates) - len(filtered_candidates)})")
            
            # 第三步：评分和排序
            logger.info(f"🎯 STEP 3: Scoring and ranking channels...")
            scored_channels = self._score_channels(filtered_candidates, request)
            if not scored_channels:
                logger.warning(f"❌ ROUTING FAILED: Failed to score any channels for model '{request.model}'")
                return []
            
            logger.info(f"✅ STEP 3 COMPLETE: Scored {len(scored_channels)} channels")
            
            # 缓存结果（异步执行，不阻塞主流程）
            if scored_channels:
                primary_channel = scored_channels[0].channel
                backup_channels = [score.channel for score in scored_channels[1:6]]  # 最多5个备选
                selection_reason = scored_channels[0].reason
                cost_estimate = self._estimate_cost_for_channel(primary_channel, request)
                
                # 提取真实的匹配模型名
                primary_matched_model = scored_channels[0].matched_model
                backup_matched_models = [score.matched_model for score in scored_channels[1:6]]
                
                try:
                    # 异步保存到缓存
                    cache_key = await cache.cache_selection(
                        fingerprint=fingerprint,
                        primary_channel=primary_channel,
                        backup_channels=backup_channels,
                        selection_reason=selection_reason,
                        cost_estimate=cost_estimate,
                        ttl_seconds=60,  # 1分钟TTL
                        primary_matched_model=primary_matched_model,
                        backup_matched_models=backup_matched_models
                    )
                    logger.debug(f"💾 CACHED RESULT: {cache_key} -> {primary_channel.name}")
                except Exception as cache_error:
                    logger.warning(f"⚠️  CACHE SAVE FAILED: {cache_error}, continuing without caching")
            
            logger.info(f"🎉 ROUTING SUCCESS: Ready to attempt {len(scored_channels)} channels in ranked order for model '{request.model}'")
            
            return scored_channels
            
        except TagNotFoundError:
            # 让TagNotFoundError传播出去，以便上层处理
            raise
        except Exception as e:
            logger.error(f"❌ ROUTING ERROR: Request failed for model '{request.model}': {e}", exc_info=True)
            return []
    
    def _get_candidate_channels(self, request: RoutingRequest) -> List[ChannelCandidate]:
        """获取候选渠道，支持按标签集合或物理模型进行智能路由"""
        
        if request.model.startswith("tag:"):
            tag_query = request.model.split(":", 1)[1]
            
            # 支持多标签查询，用逗号分隔：tag:qwen,free,!local
            if "," in tag_query:
                tag_parts = [tag.strip() for tag in tag_query.split(",")]
                positive_tags = []
                negative_tags = []
                
                for tag_part in tag_parts:
                    if tag_part.startswith("!"):
                        # 负标签：!local
                        negative_tags.append(tag_part[1:].lower())
                    else:
                        # 正标签：free, qwen3
                        positive_tags.append(tag_part.lower())
                
                logger.info(f"🏷️  TAG ROUTING: Processing multi-tag query '{request.model}' -> positive: {positive_tags}, negative: {negative_tags}")
                candidates = self._get_candidate_channels_by_auto_tags(positive_tags, negative_tags)
                if not candidates:
                    logger.error(f"❌ TAG NOT FOUND: No models found matching tags {positive_tags} excluding {negative_tags}")
                    raise TagNotFoundError(positive_tags + [f"!{tag}" for tag in negative_tags])
                logger.info(f"🏷️  TAG ROUTING: Multi-tag query found {len(candidates)} candidate channels")
                return candidates
            else:
                # 单标签查询 - 支持负标签：tag:!local
                tag_part = tag_query.strip()
                if tag_part.startswith("!"):
                    # 负标签单独查询：tag:!local (匹配所有不包含local的模型)
                    negative_tag = tag_part[1:].lower()
                    logger.info(f"🏷️  TAG ROUTING: Processing negative tag query '{request.model}' -> excluding: '{negative_tag}'")
                    candidates = self._get_candidate_channels_by_auto_tags([], [negative_tag])
                else:
                    # 正常单标签查询
                    tag = tag_part.lower()
                    logger.info(f"🏷️  TAG ROUTING: Processing single tag query '{request.model}' -> tag: '{tag}'")
                    candidates = self._get_candidate_channels_by_auto_tags([tag], [])
                
                if not candidates:
                    logger.error(f"❌ TAG NOT FOUND: No models found for query '{request.model}'")
                    raise TagNotFoundError([tag_query])
                logger.info(f"🏷️  TAG ROUTING: Found {len(candidates)} candidate channels")
                return candidates
        
        # 非tag:前缀的模型名称 - 首先尝试物理模型，然后尝试自动标签化
        candidate_channels = []
        all_enabled_channels = self.config_loader.get_enabled_channels()
        model_cache = self.config_loader.get_model_cache()

        # 1. 首先尝试作为物理模型查找
        physical_candidates = []
        for channel in all_enabled_channels:
            if channel.id in model_cache:
                discovered_info = model_cache[channel.id]
                models_data = discovered_info.get("models_data", {}) if isinstance(discovered_info, dict) else {}
                
                # 检查是否存在精确匹配的模型
                if request.model in discovered_info.get("models", []):
                    # 获取真实的模型ID - 可能与请求的不同（别名映射）
                    real_model_id = request.model
                    if models_data and request.model in models_data:
                        model_info = models_data[request.model]
                        real_model_id = model_info.get("id", request.model)
                    
                    logger.debug(f"🔍 PHYSICAL MODEL: Found '{request.model}' -> '{real_model_id}' in channel '{channel.name}'")
                    physical_candidates.append(ChannelCandidate(
                        channel=channel,
                        matched_model=real_model_id  # 使用真实的模型ID
                    ))
        
        # 2. 同时尝试自动标签化查找（免费模型优先考虑）
        auto_tag_candidates = []
        logger.info(f"🔄 AUTO TAGGING: Extracting tags from model name '{request.model}' for comprehensive search")
        auto_tags = self._extract_tags_from_model_name(request.model)
        if auto_tags:
            logger.info(f"🏷️  AUTO TAGGING: Extracted tags {auto_tags} from model name '{request.model}'")
            auto_tag_candidates = self._get_candidate_channels_by_auto_tags(auto_tags)
            if auto_tag_candidates:
                logger.info(f"🏷️  AUTO TAGGING: Found {len(auto_tag_candidates)} candidate channels using auto-extracted tags")
            else:
                logger.warning(f"🏷️  AUTO TAGGING: No channels found for auto-extracted tags {auto_tags}")
        
        # 3. 合并物理模型和自动标签化的结果，去重
        all_candidates = physical_candidates.copy()
        
        # 添加自动标签化的候选，避免重复
        for tag_candidate in auto_tag_candidates:
            # 检查是否已经存在相同的 channel + model 组合
            duplicate_found = False
            for existing in all_candidates:
                if (existing.channel.id == tag_candidate.channel.id and 
                    existing.matched_model == tag_candidate.matched_model):
                    duplicate_found = True
                    break
            
            if not duplicate_found:
                all_candidates.append(tag_candidate)
        
        if all_candidates:
            physical_count = len(physical_candidates)
            tag_count = len(auto_tag_candidates)
            total_count = len(all_candidates)
            logger.info(f"🔍 COMPREHENSIVE SEARCH: Found {total_count} total candidates "
                       f"(physical: {physical_count}, auto-tag: {tag_count}, merged without duplicates)")
            return all_candidates
        
        # 4. 最后尝试从配置中查找
        config_channels = self.config_loader.get_channels_by_model(request.model)
        if config_channels:
            logger.info(f"📋 CONFIG FALLBACK: Found {len(config_channels)} channels in configuration for model '{request.model}'")
            # 对于配置查找，尝试获取真实的模型ID
            config_candidates = []
            for ch in config_channels:
                real_model_id = request.model
                if ch.id in model_cache:
                    discovered_info = model_cache[ch.id]
                    models_data = discovered_info.get("models_data", {}) if isinstance(discovered_info, dict) else {}
                    if models_data and request.model in models_data:
                        model_info = models_data[request.model]
                        real_model_id = model_info.get("id", request.model)
                
                config_candidates.append(ChannelCandidate(channel=ch, matched_model=real_model_id))
            return config_candidates
        
        # 如果都没找到，返回空列表
        logger.warning(f"❌ NO MATCH: No channels found for model '{request.model}' (tried physical, auto-tag, and config)")
        return []
    
    def _filter_channels(self, channels: List[ChannelCandidate], request: RoutingRequest) -> List[ChannelCandidate]:
        """过滤渠道"""
        filtered = []
        
        # 获取路由配置中的过滤条件
        routing_config = self.config.routing if hasattr(self.config, 'routing') else None
        if routing_config and hasattr(routing_config, 'model_filters'):
            model_filters = routing_config.model_filters or {}
        else:
            model_filters = {}
        
        # 安全获取model_filters中的值
        min_context_length = getattr(model_filters, 'min_context_length', 0) if hasattr(model_filters, 'min_context_length') else model_filters.get('min_context_length', 0) if isinstance(model_filters, dict) else 0
        min_parameter_count = getattr(model_filters, 'min_parameter_count', 0) if hasattr(model_filters, 'min_parameter_count') else model_filters.get('min_parameter_count', 0) if isinstance(model_filters, dict) else 0
        exclude_embedding = getattr(model_filters, 'exclude_embedding_models', True) if hasattr(model_filters, 'exclude_embedding_models') else model_filters.get('exclude_embedding_models', True) if isinstance(model_filters, dict) else True
        exclude_vision_only = getattr(model_filters, 'exclude_vision_only_models', True) if hasattr(model_filters, 'exclude_vision_only_models') else model_filters.get('exclude_vision_only_models', True) if isinstance(model_filters, dict) else True
        
        for candidate in channels:
            channel = candidate.channel
            if not channel.enabled or not channel.api_key:
                continue
            
            health_score = self.config_loader.runtime_state.health_scores.get(channel.id, 1.0)
            if health_score < 0.3:
                continue
            
            # 模型规格过滤
            if candidate.matched_model and (min_context_length > 0 or min_parameter_count > 0 or exclude_embedding or exclude_vision_only):
                model_name = candidate.matched_model
                
                # 检查是否为embedding模型
                if exclude_embedding and self._is_embedding_model(model_name):
                    logger.debug(f"Filtered out embedding model: {model_name}")
                    continue
                
                # 检查是否为纯视觉模型
                if exclude_vision_only and self._is_vision_only_model(model_name):
                    logger.debug(f"Filtered out vision-only model: {model_name}")
                    continue
                
                # 获取模型规格
                model_specs = self._get_model_specs(channel.id, model_name)
                
                # 上下文长度过滤
                if min_context_length > 0:
                    context_length = model_specs.get('context_length', 0) if model_specs else 0
                    if context_length < min_context_length:
                        logger.debug(f"Filtered out model {model_name}: context {context_length} < {min_context_length}")
                        continue
                
                # 参数数量过滤
                if min_parameter_count > 0:
                    param_count = model_specs.get('parameter_count', 0) if model_specs else 0
                    if param_count < min_parameter_count:
                        logger.debug(f"Filtered out model {model_name}: params {param_count}M < {min_parameter_count}M")
                        continue
            
            # TODO: Add capability filtering when needed
            # if request.required_capabilities:
            #     if not all(cap in channel.capabilities for cap in request.required_capabilities):
            #         continue
            
            filtered.append(candidate)
        return filtered
    
    def _score_channels(self, channels: List[ChannelCandidate], request: RoutingRequest) -> List[RoutingScore]:
        """计算渠道评分"""
        logger.info(f"📊 SCORING: Evaluating {len(channels)} candidate channels for model '{request.model}'")
        
        scored_channels = []
        strategy = self._get_routing_strategy(request.model)
        
        logger.info(f"📊 SCORING: Using routing strategy with {len(strategy)} rules")
        for rule in strategy:
            logger.debug(f"📊 SCORING: Strategy rule: {rule['field']} (weight: {rule['weight']}, order: {rule['order']})")
        
        for candidate in channels:
            channel = candidate.channel
            cost_score = self._calculate_cost_score(channel, request)
            speed_score = self._calculate_speed_score(channel)
            quality_score = self._calculate_quality_score(channel, candidate.matched_model)
            reliability_score = self._calculate_reliability_score(channel)
            parameter_score = self._calculate_parameter_score(channel, candidate.matched_model)
            context_score = self._calculate_context_score(channel, candidate.matched_model)
            free_score = self._calculate_free_score(channel, candidate.matched_model)
            local_score = self._calculate_local_score(channel, candidate.matched_model)
            
            total_score = self._calculate_total_score(
                strategy, cost_score, speed_score, quality_score, reliability_score, 
                parameter_score, context_score, free_score, local_score
            )
            
            # 为了减少日志冗余，只显示模型名称和总分
            model_display = candidate.matched_model or channel.model_name
            logger.info(f"📊 SCORE: '{channel.name}' -> '{model_display}' = {total_score:.3f} (Q:{quality_score:.2f})")
            
            scored_channels.append(RoutingScore(
                channel=channel, total_score=total_score, cost_score=cost_score,
                speed_score=speed_score, quality_score=quality_score,
                reliability_score=reliability_score, 
                reason=f"cost:{cost_score:.2f} speed:{speed_score:.2f} quality:{quality_score:.2f} reliability:{reliability_score:.2f}",
                matched_model=candidate.matched_model
            ))
        
        # 使用分层优先级排序，而不是简单的总分排序
        scored_channels = self._hierarchical_sort(scored_channels)
        
        logger.info(f"🏆 SCORING RESULT: Channels ranked by score:")
        for i, scored in enumerate(scored_channels[:5]):  # 只显示前5个
            logger.info(f"🏆   #{i+1}: '{scored.channel.name}' (Score: {scored.total_score:.3f})")
        
        return scored_channels
    
    def _get_routing_strategy(self, model: str) -> List[Dict[str, Any]]:
        """获取并解析路由策略，始终返回规则列表"""
        routing_config = self.config.routing if hasattr(self.config, 'routing') else None
        if routing_config and hasattr(routing_config, 'default_strategy'):
            strategy_name = routing_config.default_strategy or 'balanced'
        else:
            strategy_name = 'balanced'
        
        # 尝试从配置中获取自定义策略
        if routing_config and hasattr(routing_config, 'sorting_strategies'):
            custom_strategies = routing_config.sorting_strategies or {}
        else:
            custom_strategies = {}
        if strategy_name in custom_strategies:
            return custom_strategies[strategy_name]

        # 回退到预定义策略
        predefined_strategies = {
            "cost_first": [
                {"field": "cost_score", "order": "desc", "weight": 0.4},
                {"field": "parameter_score", "order": "desc", "weight": 0.25},
                {"field": "context_score", "order": "desc", "weight": 0.2},
                {"field": "speed_score", "order": "desc", "weight": 0.15}
            ],
            "free_first": [
                {"field": "free_score", "order": "desc", "weight": 0.5},
                {"field": "cost_score", "order": "desc", "weight": 0.3},
                {"field": "speed_score", "order": "desc", "weight": 0.15},
                {"field": "reliability_score", "order": "desc", "weight": 0.05}
            ],
            "local_first": [
                {"field": "local_score", "order": "desc", "weight": 0.6},
                {"field": "speed_score", "order": "desc", "weight": 0.25},
                {"field": "cost_score", "order": "desc", "weight": 0.1},
                {"field": "reliability_score", "order": "desc", "weight": 0.05}
            ],
            "cost_optimized": [
                {"field": "cost_score", "order": "desc", "weight": 0.7},
                {"field": "reliability_score", "order": "desc", "weight": 0.2},
                {"field": "speed_score", "order": "desc", "weight": 0.1}
            ],
            "speed_optimized": [
                {"field": "speed_score", "order": "desc", "weight": 0.4},
                {"field": "cost_score", "order": "desc", "weight": 0.3},
                {"field": "parameter_score", "order": "desc", "weight": 0.2},
                {"field": "context_score", "order": "desc", "weight": 0.1}
            ],
            "quality_optimized": [
                {"field": "parameter_score", "order": "desc", "weight": 0.4},
                {"field": "context_score", "order": "desc", "weight": 0.3},
                {"field": "quality_score", "order": "desc", "weight": 0.2},
                {"field": "cost_score", "order": "desc", "weight": 0.1}
            ],
            "balanced": [
                {"field": "cost_score", "order": "desc", "weight": 0.3},
                {"field": "parameter_score", "order": "desc", "weight": 0.25},
                {"field": "context_score", "order": "desc", "weight": 0.2},
                {"field": "speed_score", "order": "desc", "weight": 0.15},
                {"field": "reliability_score", "order": "desc", "weight": 0.1}
            ]
        }
        
        return predefined_strategies.get(strategy_name, predefined_strategies["cost_first"])

    def _calculate_cost_score(self, channel: Channel, request: RoutingRequest) -> float:
        """计算成本评分(0-1，越低成本越高分)"""
        pricing = channel.pricing
        if not pricing:
            return 0.5
        
        # 估算token数量
        input_tokens = self._estimate_tokens(request.messages)
        max_output_tokens = request.max_tokens or 1000
        
        # 计算成本
        input_cost = pricing.get("input_cost_per_1k", 0.001) * input_tokens / 1000
        output_cost = pricing.get("output_cost_per_1k", 0.002) * max_output_tokens / 1000
        total_cost = (input_cost + output_cost) * pricing.get("effective_multiplier", 1.0)
        
        # 转换为评分 (成本越低分数越高)
        # 假设最高成本为0.1美元
        max_cost = 0.1
        score = max(0, 1 - (total_cost / max_cost))
        
        return min(1.0, score)
    
    # 内置模型质量排名 (分数越高越好, 满分100)
    MODEL_QUALITY_RANKING = {
        # OpenAI 系列
        "gpt-4o": 98, "gpt-4-turbo": 95, "gpt-4": 90, "gpt-4o-mini": 85, "gpt-3.5-turbo": 70,
        # Anthropic 系列
        "claude-3-5-sonnet": 99, "claude-3-opus": 97, "claude-3-sonnet": 92, "claude-3-haiku": 80,
        # Meta Llama 系列
        "llama-3.1-70b": 93, "llama-3.1-8b": 82, "llama-3-70b": 90, "llama-3-8b": 80,
        # Qwen 系列
        "qwen2.5-72b-instruct": 91, "qwen2-72b-instruct": 90, "qwen2-7b-instruct": 78,
        "qwen3-coder": 88, "qwen3-30b": 85, "qwen3-14b": 82, "qwen3-8b": 80, "qwen3-4b": 75, 
        "qwen3-1.7b": 65, "qwen3-0.6b": 60,
        # DeepSeek 系列
        "deepseek-r1": 89, "deepseek-v3": 87, "deepseek-coder": 85,
        # Moonshot 系列
        "moonshot-v1-128k": 88, "moonshot-v1-32k": 87, "moonshot-v1-8k": 86,
        # 01.AI 系列
        "yi-large": 89, "yi-lightning": 75,
        # Google 系列
        "gemma-3-12b": 78, "gemma-3-9b": 75, "gemma-3-270m": 55,
    }

    def _calculate_quality_score(self, channel: Channel, matched_model: Optional[str] = None) -> float:
        """根据内置排名和模型规格动态计算质量评分"""
        # 优先使用匹配的模型，如果没有则使用渠道默认模型
        model_name = matched_model or channel.model_name
        model_name_lower = model_name.lower()
        simple_model_name = model_name_lower.split('/')[-1]
        
        # 1. 基础质量评分（从内置排名）
        base_quality_score = self.MODEL_QUALITY_RANKING.get(simple_model_name)
        
        if base_quality_score is None:
            for key, score in self.MODEL_QUALITY_RANKING.items():
                if key in model_name_lower:
                    base_quality_score = score
                    break
        
        # 2. 获取模型规格信息
        model_specs = None
        try:
            # 从渠道缓存中获取模型详细信息
            channel_cache = self.cache_manager.load_channel_models(channel.id)
            if channel_cache and 'models' in channel_cache:
                model_specs = channel_cache['models'].get(model_name)
        except Exception as e:
            logger.debug(f"Failed to load model specs for {model_name}: {e}")
        
        # 如果缓存中没有，使用分析器分析模型名称
        if not model_specs:
            analyzed_specs = self.model_analyzer.analyze_model(model_name)
            model_specs = {
                'parameter_count': analyzed_specs.parameter_count,
                'context_length': analyzed_specs.context_length
            }
        
        # 3. 根据参数数量调整评分
        param_multiplier = 1.0
        if model_specs and 'parameter_count' in model_specs:
            param_count = model_specs['parameter_count']
            if param_count:
                # 参数数量评分曲线（越大越好，但有边际递减效应）
                if param_count >= 100000:      # 100B+
                    param_multiplier = 1.3
                elif param_count >= 70000:     # 70B+
                    param_multiplier = 1.25
                elif param_count >= 30000:     # 30B+
                    param_multiplier = 1.2
                elif param_count >= 8000:      # 8B+
                    param_multiplier = 1.1
                elif param_count >= 4000:      # 4B+
                    param_multiplier = 1.05
                elif param_count >= 1000:      # 1B+
                    param_multiplier = 1.0
                elif param_count >= 500:       # 500M+
                    param_multiplier = 0.9
                else:                          # <500M
                    param_multiplier = 0.8
                
                logger.debug(f"Model {model_name}: {param_count}M params -> multiplier {param_multiplier}")
        
        # 4. 根据上下文长度调整评分
        context_bonus = 0.0
        if model_specs and 'context_length' in model_specs:
            context_length = model_specs['context_length']
            if context_length:
                # 上下文长度奖励（更长的上下文在同等条件下更好）
                if context_length >= 200000:     # 200k+
                    context_bonus = 15
                elif context_length >= 128000:   # 128k+
                    context_bonus = 10
                elif context_length >= 32000:    # 32k+
                    context_bonus = 5
                elif context_length >= 16000:    # 16k+
                    context_bonus = 2
                
                logger.debug(f"Model {model_name}: {context_length} context -> bonus {context_bonus}")
        
        # 5. 计算最终评分
        final_score = (base_quality_score or 70) * param_multiplier + context_bonus
        
        # 6. 归一化到0-1范围，最高分设为120分
        normalized_score = min(1.0, final_score / 120.0)
        
        logger.debug(f"Quality scoring for {model_name}: base={base_quality_score}, "
                    f"param_mult={param_multiplier}, context_bonus={context_bonus}, "
                    f"final={final_score}, normalized={normalized_score:.3f}")
        
        return normalized_score
    
    def _calculate_parameter_score(self, channel: Channel, matched_model: Optional[str] = None) -> float:
        """计算参数数量评分"""
        model_name = matched_model or channel.model_name
        model_specs = self._get_model_specs(channel.id, model_name)
        
        if not model_specs or not model_specs.get('parameter_count'):
            return 0.5  # 默认中等评分
        
        param_count = model_specs['parameter_count']
        
        # 参数数量评分曲线（对数式递增，有边际递减效应）
        if param_count >= 500000:      # 500B+
            score = 1.0
        elif param_count >= 100000:    # 100B+
            score = 0.95
        elif param_count >= 70000:     # 70B+
            score = 0.9
        elif param_count >= 30000:     # 30B+
            score = 0.85
        elif param_count >= 8000:      # 8B+
            score = 0.8
        elif param_count >= 4000:      # 4B+
            score = 0.75
        elif param_count >= 1000:      # 1B+
            score = 0.7
        elif param_count >= 500:       # 500M+
            score = 0.6
        else:                          # <500M
            score = 0.4
        
        logger.debug(f"Parameter score for {model_name}: {param_count}M -> {score}")
        return score
    
    def _calculate_context_score(self, channel: Channel, matched_model: Optional[str] = None) -> float:
        """计算上下文长度评分"""
        model_name = matched_model or channel.model_name
        model_specs = self._get_model_specs(channel.id, model_name)
        
        if not model_specs or not model_specs.get('context_length'):
            return 0.5  # 默认中等评分
        
        context_length = model_specs['context_length']
        
        # 上下文长度评分曲线
        if context_length >= 1000000:    # 1M+
            score = 1.0
        elif context_length >= 200000:   # 200k+
            score = 0.95
        elif context_length >= 128000:   # 128k+
            score = 0.9
        elif context_length >= 32000:    # 32k+
            score = 0.8
        elif context_length >= 16000:    # 16k+
            score = 0.7
        elif context_length >= 8000:     # 8k+
            score = 0.6
        elif context_length >= 4000:     # 4k+
            score = 0.5
        else:                            # <4k
            score = 0.3
        
        logger.debug(f"Context score for {model_name}: {context_length} -> {score}")
        return score
    
    def _get_model_specs(self, channel_id: str, model_name: str) -> Optional[Dict[str, Any]]:
        """获取模型规格信息"""
        try:
            # 从渠道缓存中获取
            channel_cache = self.cache_manager.load_channel_models(channel_id)
            if channel_cache and 'models' in channel_cache:
                return channel_cache['models'].get(model_name)
        except Exception as e:
            logger.debug(f"Failed to load model specs for {model_name}: {e}")
        
        # 回退到分析器分析
        analyzed_specs = self.model_analyzer.analyze_model(model_name)
        return {
            'parameter_count': analyzed_specs.parameter_count,
            'context_length': analyzed_specs.context_length
        }
    
    def _is_embedding_model(self, model_name: str) -> bool:
        """检查是否为embedding模型"""
        name_lower = model_name.lower()
        embedding_keywords = ['embedding', 'embed', 'text-embedding', 'bge-', 'gte-', 'e5-']
        return any(keyword in name_lower for keyword in embedding_keywords)
    
    def _is_vision_only_model(self, model_name: str) -> bool:
        """检查是否为纯视觉模型"""
        name_lower = model_name.lower()
        vision_keywords = ['vision-only', 'image-only', 'ocr-only']
        return any(keyword in name_lower for keyword in vision_keywords)

    def _calculate_speed_score(self, channel: Channel) -> float:
        """根据平均延迟动态计算速度评分"""
        channel_stats = self.config_loader.runtime_state.channel_stats.get(channel.id)
        if channel_stats and "avg_latency_ms" in channel_stats:
            avg_latency = channel_stats["avg_latency_ms"]
            base_latency = 2000.0
            score = max(0.0, 1.0 - (avg_latency / base_latency))
            return 0.1 + score * 0.9
        return channel.performance.get("speed_score", 0.8)

    def _calculate_reliability_score(self, channel: Channel) -> float:
        """计算可靠性评分"""
        health_score = self.config_loader.runtime_state.health_scores.get(channel.id, 1.0)
        return health_score

    def _calculate_free_score(self, channel: Channel, model_name: str = None) -> float:
        """计算免费优先评分 - 严格验证真正免费的渠道"""
        free_tags = {"free", "免费", "0cost", "nocost", "trial"}
        
        # 🔥 优先检查模型级别的定价信息（从缓存中获取）
        if model_name:
            model_specs = self._get_model_specs(channel.id, model_name)
            if model_specs and 'raw_data' in model_specs:
                raw_data = model_specs['raw_data']
                if 'pricing' in raw_data:
                    pricing = raw_data['pricing']
                    prompt_cost = float(pricing.get('prompt', '0'))
                    completion_cost = float(pricing.get('completion', '0'))
                    if prompt_cost == 0.0 and completion_cost == 0.0:
                        logger.debug(f"FREE SCORE: Model '{model_name}' confirmed free via model-level pricing (prompt={prompt_cost}, completion={completion_cost})")
                        return 1.0
                    else:
                        logger.debug(f"FREE SCORE: Model '{model_name}' has non-zero costs (prompt={prompt_cost}, completion={completion_cost}), not free")
                        return 0.1
        
        # 🔥 检查模型名称模式 - 对于明确的免费模型后缀
        if model_name:
            model_lower = model_name.lower()
            # 明确的免费模型标识
            if (":free" in model_lower or 
                "-free" in model_lower or 
                "_free" in model_lower):
                logger.debug(f"FREE SCORE: Model '{model_name}' has explicit :free suffix, assumed free")
                return 1.0
            
            # 检查其他免费模型模式
            model_tags = self._extract_tags_from_model_name(model_name)
            model_tags_lower = [tag.lower() for tag in model_tags]
            if any(tag in free_tags for tag in model_tags_lower):
                # 开源模型通常免费
                if ("oss" in model_lower or 
                    "huggingface" in model_lower or
                    "hf" in model_lower):
                    logger.debug(f"FREE SCORE: Model '{model_name}' is open source model, assumed free")
                    return 1.0
                else:
                    # 模型名称包含free但需要进一步验证
                    logger.debug(f"FREE SCORE: Model '{model_name}' has 'free' in name, needs verification")
                    # 继续检查渠道级别信息
        
        # 🔥 检查渠道级别的定价信息
        cost_per_token = getattr(channel, 'cost_per_token', None)
        if cost_per_token:
            input_cost = cost_per_token.get("input", 0.0)
            output_cost = cost_per_token.get("output", 0.0)
            if input_cost <= 0.0 and output_cost <= 0.0:
                logger.debug(f"FREE SCORE: Channel '{channel.name}' confirmed free via cost_per_token (input={input_cost}, output={output_cost})")
                return 1.0
            # 对于有cost_per_token但非零的情况，如果模型名明确包含:free，仍认为该特定模型免费
            elif model_name and (":free" in model_name.lower() or "-free" in model_name.lower()):
                logger.debug(f"FREE SCORE: Channel '{channel.name}' has costs but model '{model_name}' explicitly marked as free")
                return 1.0
            else:
                # 渠道有成本且模型未明确标记为免费
                logger.debug(f"FREE SCORE: Channel '{channel.name}' has non-zero costs (input={input_cost}, output={output_cost}), not free")
                return 0.1
        
        # 检查传统的pricing配置
        pricing = getattr(channel, 'pricing', None)
        if pricing:
            input_cost = pricing.get("input_cost_per_1k", 0.001)
            output_cost = pricing.get("output_cost_per_1k", 0.002)
            avg_cost = (input_cost + output_cost) / 2
            if avg_cost <= 0.0001:  # 极低成本
                logger.debug(f"FREE SCORE: Channel '{channel.name}' very low cost (avg={avg_cost:.6f}), scored as near-free")
                return 0.9
            elif avg_cost <= 0.001:  # 低成本
                logger.debug(f"FREE SCORE: Channel '{channel.name}' low cost (avg={avg_cost:.6f}), scored as affordable")
                return 0.7
            else:
                # 有明确pricing且不便宜的，但如果模型明确标记为:free，仍认为免费
                if model_name and (":free" in model_name.lower() or "-free" in model_name.lower()):
                    logger.debug(f"FREE SCORE: Channel has costs but model '{model_name}' explicitly marked as free")
                    return 1.0
                else:
                    logger.debug(f"FREE SCORE: Channel '{channel.name}' has significant costs (avg={avg_cost:.6f}), not free")
                    return 0.1
        
        # 🔥 检查渠道标签
        channel_tags_lower = [tag.lower() for tag in getattr(channel, 'tags', [])]
        if any(tag in free_tags for tag in channel_tags_lower):
            logger.debug(f"FREE SCORE: Channel '{channel.name}' has free tag in channel tags, assumed free")
            return 1.0
        
        # 默认情况 - 没有免费证据
        logger.debug(f"FREE SCORE: Channel '{channel.name}' no evidence of being free")
        return 0.1

    def _calculate_local_score(self, channel: Channel, model_name: str = None) -> float:
        """计算本地优先评分"""
        # 检查渠道标签中是否包含本地相关标签
        local_tags = {"local", "本地", "localhost", "127.0.0.1", "offline", "edge"}
        
        # 从渠道标签检查
        channel_tags_lower = [tag.lower() for tag in channel.tags]
        if any(tag in local_tags for tag in channel_tags_lower):
            return 1.0
        
        # 从模型名称提取标签检查
        if model_name:
            model_tags = self._extract_tags_from_model_name(model_name)
            model_tags_lower = [tag.lower() for tag in model_tags]
            if any(tag in local_tags for tag in model_tags_lower):
                return 1.0
        
        # 检查base_url是否指向本地地址
        base_url = getattr(channel, 'base_url', None)
        if base_url:
            base_url_lower = base_url.lower()
            local_indicators = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
            if any(indicator in base_url_lower for indicator in local_indicators):
                return 1.0
        
        # 检查provider是否指向本地地址
        provider_config = None
        if hasattr(self.config, 'providers'):
            provider_config = next((p for p in self.config.providers.values() if p.name == channel.provider), None)
        
        if provider_config and hasattr(provider_config, 'base_url'):
            provider_url_lower = provider_config.base_url.lower()
            local_indicators = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
            if any(indicator in provider_url_lower for indicator in local_indicators):
                return 1.0
        
        # 检查是否是常见本地模型名称
        if model_name:
            local_model_patterns = ["ollama", "llama.cpp", "local", "自己的", "私有"]
            model_lower = model_name.lower()
            if any(pattern in model_lower for pattern in local_model_patterns):
                return 0.8
        
        return 0.1  # 默认较低评分
    
    def _calculate_total_score(self, strategy: List[Dict[str, Any]], 
                             cost_score: float, speed_score: float, 
                             quality_score: float, reliability_score: float,
                             parameter_score: float = 0.5, context_score: float = 0.5,
                             free_score: float = 0.1, local_score: float = 0.1) -> float:
        """根据策略计算总评分"""
        total_score = 0.0
        score_map = {
            "cost_score": cost_score, "speed_score": speed_score,
            "quality_score": quality_score, "reliability_score": reliability_score,
            "parameter_score": parameter_score, "context_score": context_score,
            "free_score": free_score, "local_score": local_score
        }
        
        total_weight = sum(rule.get("weight", 0.0) for rule in strategy)
        if total_weight == 0: 
            return 0.5

        for rule in strategy:
            field = rule.get("field", "")
            if field in score_map:
                score = score_map[field]
                if rule.get("order") == "asc": 
                    score = 1.0 - score
                total_score += score * rule.get("weight", 0.0)
        
        return total_score / total_weight
    
    def _hierarchical_sort(self, scored_channels: List[RoutingScore]) -> List[RoutingScore]:
        """分层优先级排序：使用7位数字评分系统 (成本|本地|上下文|参数|速度|质量|可靠性)"""
        def sorting_key(score: RoutingScore):
            # 获取额外的评分信息
            channel = score.channel
            free_score = self._calculate_free_score(channel, score.matched_model)
            local_score = self._calculate_local_score(channel, score.matched_model)
            parameter_score = self._calculate_parameter_score(channel, score.matched_model)
            context_score = self._calculate_context_score(channel, score.matched_model)
            
            # 将每个维度的评分转换为0-9的整数评分
            # 第1位：成本优化程度 (9=完全免费, 8=很便宜, 0=很昂贵)
            # 优先使用免费评分，如果不免费则使用成本评分
            if free_score >= 0.9:
                cost_tier = 9  # 免费模型固定为9分
            else:
                cost_tier = min(8, int(score.cost_score * 8))  # 付费模型最高8分
            
            # 第2位：本地优先程度 (9=本地, 0=远程)
            local_tier = min(9, int(local_score * 9))
            
            # 第3位：上下文长度程度 (9=很长, 0=很短)
            context_tier = min(9, int(context_score * 9))
            
            # 第4位：参数量程度 (9=很大, 0=很小)
            parameter_tier = min(9, int(parameter_score * 9))
            
            # 第5位：速度程度 (9=很快, 0=很慢)
            speed_tier = min(9, int(score.speed_score * 9))
            
            # 第6位：质量程度 (9=很高, 0=很低)
            quality_tier = min(9, int(score.quality_score * 9))
            
            # 第7位：可靠性程度 (9=很可靠, 0=不可靠)
            reliability_tier = min(9, int(score.reliability_score * 9))
            
            # 组成7位数字，数字越大排序越靠前
            hierarchical_score = (
                cost_tier * 1000000 +       # 第1位：成本(免费=9,付费最高=8)
                local_tier * 100000 +       # 第2位：本地
                context_tier * 10000 +      # 第3位：上下文
                parameter_tier * 1000 +     # 第4位：参数量
                speed_tier * 100 +          # 第5位：速度
                quality_tier * 10 +         # 第6位：质量
                reliability_tier            # 第7位：可靠性
            )
            
            # 返回负数实现降序排列（分数越高排名越前）
            return -hierarchical_score
        
        sorted_channels = sorted(scored_channels, key=sorting_key)
        
        # 记录分层排序的详细信息
        logger.info("🏆 HIERARCHICAL SORTING: 7-digit scoring system (Cost|Local|Context|Param|Speed|Quality|Reliability)")
        for i, scored in enumerate(sorted_channels[:5]):
            free_score = self._calculate_free_score(scored.channel, scored.matched_model)
            local_score = self._calculate_local_score(scored.channel, scored.matched_model)
            parameter_score = self._calculate_parameter_score(scored.channel, scored.matched_model)
            context_score = self._calculate_context_score(scored.channel, scored.matched_model)
            
            # 计算7位数字评分
            if free_score >= 0.9:
                cost_tier = 9  # 免费模型固定为9分
            else:
                cost_tier = min(8, int(scored.cost_score * 8))  # 付费模型最高8分
            
            local_tier = min(9, int(local_score * 9))
            context_tier = min(9, int(context_score * 9))
            parameter_tier = min(9, int(parameter_score * 9))
            speed_tier = min(9, int(scored.speed_score * 9))
            quality_tier = min(9, int(scored.quality_score * 9))
            reliability_tier = min(9, int(scored.reliability_score * 9))
            
            hierarchical_score = (
                cost_tier * 1000000 + local_tier * 100000 + context_tier * 10000 + 
                parameter_tier * 1000 + speed_tier * 100 + quality_tier * 10 + reliability_tier
            )
            
            score_display = f"{cost_tier}{local_tier}{context_tier}{parameter_tier}{speed_tier}{quality_tier}{reliability_tier}"
            is_free = "FREE" if free_score >= 0.9 else "PAID"
            is_local = "LOCAL" if local_score >= 0.7 else "REMOTE"
            logger.info(f"🏆   #{i+1}: '{scored.channel.name}' [{is_free}/{is_local}] "
                       f"Score: {score_display} (Total: {hierarchical_score:,})")
        
        return sorted_channels
    
    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """使用tiktoken估算prompt tokens"""
        try:
            # 尝试从main模块获取已经初始化的encoder
            import main
            if hasattr(main, 'estimate_prompt_tokens'):
                return main.estimate_prompt_tokens(messages)
        except (ImportError, AttributeError):
            pass

        # 如果获取失败，使用简单回退方法
        logger.warning("无法从main模块获取tiktoken编码器, token计算将使用简单方法")
        total_chars = 0
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
        return max(1, total_chars // 4)
    
    def _estimate_cost_for_channel(self, channel: Channel, request: RoutingRequest) -> float:
        """估算特定渠道的请求成本"""
        try:
            # 估算token数量
            input_tokens = self._estimate_tokens(request.messages)
            estimated_output_tokens = max(50, input_tokens // 4)  # 预估输出token
            
            # 获取渠道的定价信息
            model_cache = self.config_loader.get_model_cache()
            if channel.id in model_cache:
                discovered_info = model_cache[channel.id]
                models_pricing = discovered_info.get("models_pricing", {})
                
                # 查找模型的定价信息
                model_pricing = None
                for model_name, pricing in models_pricing.items():
                    if model_name == request.model or request.model in model_name:
                        model_pricing = pricing
                        break
                
                if model_pricing:
                    input_cost = model_pricing.get("input_cost_per_token", 0.0)
                    output_cost = model_pricing.get("output_cost_per_token", 0.0)
                    
                    total_cost = (input_tokens * input_cost + 
                                estimated_output_tokens * output_cost)
                    
                    return total_cost
            
            # 如果没有找到定价信息，使用免费评分来估算
            free_score = self._calculate_free_score(channel, request.model)
            if free_score >= 0.9:
                return 0.0  # 免费模型
            else:
                return 0.001  # 默认估算为很低的成本
                
        except Exception as e:
            logger.warning(f"成本估算失败: {e}")
            return 0.001
    
    def _is_suitable_for_chat(self, model_name: str) -> bool:
        """检查模型是否适合chat对话任务"""
        if not model_name:
            return False
            
        model_lower = model_name.lower()
        
        # 过滤embedding模型
        embedding_keywords = ['embedding', 'embed', 'text-embedding']
        if any(keyword in model_lower for keyword in embedding_keywords):
            return False
            
        # 过滤纯vision模型
        vision_only_keywords = ['vision-only', 'image-only']
        if any(keyword in model_lower for keyword in vision_only_keywords):
            return False
            
        # 过滤工具类模型
        tool_keywords = ['tokenizer', 'classifier', 'detector']
        if any(keyword in model_lower for keyword in tool_keywords):
            return False
            
        return True

    def _extract_tags_from_model_name(self, model_name: str) -> List[str]:
        """从模型名称中提取标签（带缓存）
        
        例如: "qwen/qwen3-30b-a3b:free" -> ["qwen", "qwen3", "30b", "a3b", "free"]
        """
        if not model_name or not isinstance(model_name, str):
            return []
        
        # 检查缓存
        if model_name in self._tag_cache:
            return self._tag_cache[model_name]
        
        import re
        
        # 使用多种分隔符进行拆分: :, /, @, -, _, ,
        separators = r'[/:@\-_,]'
        parts = re.split(separators, model_name.lower())
        
        # 清理和过滤标签
        tags = []
        for part in parts:
            part = part.strip()
            if part and len(part) > 1:  # 忽略单字符和空标签
                # 进一步分解数字和字母组合，如 "30b" -> ["30b"]
                tags.append(part)
        
        # 缓存结果
        self._tag_cache[model_name] = tags
        return tags

    def _get_candidate_channels_by_auto_tags(self, positive_tags: List[str], negative_tags: List[str] = None) -> List[ChannelCandidate]:
        """根据正负标签获取候选渠道（严格匹配）
        
        Args:
            positive_tags: 必须包含的标签列表
            negative_tags: 必须排除的标签列表
        """
        if negative_tags is None:
            negative_tags = []
            
        # 如果没有任何标签条件，返回空（避免返回所有模型）
        if not positive_tags and not negative_tags:
            return []
        
        # 标准化标签
        normalized_positive = [tag.lower().strip() for tag in positive_tags if tag and isinstance(tag, str)]
        normalized_negative = [tag.lower().strip() for tag in negative_tags if tag and isinstance(tag, str)]
        
        logger.info(f"🔍 TAG MATCHING: Searching for channels with positive tags: {normalized_positive}, excluding: {normalized_negative}")
        
        model_cache = self.config_loader.get_model_cache()
        if not model_cache:
            logger.warning("🔍 TAG MATCHING: Model cache is empty, cannot perform tag routing")
            return []
        
        logger.info(f"🔍 TAG MATCHING: Searching through {len(model_cache)} cached channels")
        
        # 严格匹配：支持正负标签的严格匹配
        if not normalized_negative:
            # 如果没有负标签，使用原有的方法
            exact_candidates = self._find_channels_with_all_tags(normalized_positive, model_cache)
        else:
            # 有负标签，使用新的正负标签匹配方法
            exact_candidates = self._find_channels_with_positive_negative_tags(normalized_positive, normalized_negative, model_cache)
        
        if exact_candidates:
            logger.info(f"🎯 STRICT MATCH: Found {len(exact_candidates)} channels matching positive: {normalized_positive}, excluding: {normalized_negative}")
            return exact_candidates
        
        logger.warning(f"❌ NO MATCH: No channels found matching positive: {normalized_positive}, excluding: {normalized_negative}")
        return []
    
    def _find_channels_with_all_tags(self, tags: List[str], model_cache: dict) -> List[ChannelCandidate]:
        """查找包含所有指定标签的渠道和模型组合
        
        标签匹配规则：
        1. 首先检查渠道级别的标签 (channel.tags)
        2. 如果渠道标签匹配，该渠道下所有模型都被视为匹配
        3. 否则检查从模型名称提取的标签
        4. 对于 'free' 标签，需要严格验证渠道是否真的免费
        """
        candidate_channels = []
        matched_models = []
        
        # 检查是否包含free标签 - 需要严格验证
        has_free_tag = any(tag.lower() in {"free", "免费", "0cost", "nocost"} for tag in tags)
        
        # 遍历所有有效渠道
        for channel in self.config_loader.get_enabled_channels():
            # 🔥 修复：使用API Key级别缓存查找方法
            discovered_info = self.config_loader.get_model_cache_by_channel(channel.id)
            if not isinstance(discovered_info, dict):
                continue
                
            models = discovered_info.get("models", [])
            if not models:
                continue
            
            logger.debug(f"🔍 TAG MATCHING: Checking channel {channel.id} ({channel.name}) with {len(models)} models")
            
            # 统一的标签合并匹配：渠道标签 + 模型标签
            channel_tags = getattr(channel, 'tags', []) or []
            channel_matches = 0
            
            for model_name in models:
                if not model_name:
                    continue
                    
                # 从模型名称提取标签（已经转为小写）
                model_tags = self._extract_tags_from_model_name(model_name)
                
                # 合并渠道标签和模型标签，并规范化为小写
                combined_tags = list(set([tag.lower() for tag in channel_tags] + model_tags))
                
                # 验证所有查询标签都在合并后的标签中（case-insensitive匹配）
                normalized_query_tags = [tag.lower() for tag in tags]
                if all(tag in combined_tags for tag in normalized_query_tags):
                    # 🔥 严格验证 free 标签 - 确保渠道真的免费
                    if has_free_tag:
                        free_score = self._calculate_free_score(channel, model_name)
                        # 只有真正免费的渠道才会被匹配 (free_score >= 0.9)
                        if free_score < 0.9:
                            logger.debug(f"❌ FREE TAG VALIDATION FAILED: Channel '{channel.name}' model '{model_name}' has free_score={free_score:.2f} < 0.9, not truly free")
                            continue
                        else:
                            logger.debug(f"✅ FREE TAG VALIDATED: Channel '{channel.name}' model '{model_name}' confirmed as truly free (score={free_score:.2f})")
                    
                    # 过滤掉不适合chat的模型类型
                    if self._is_suitable_for_chat(model_name):
                        candidate_channels.append(ChannelCandidate(
                            channel=channel,
                            matched_model=model_name
                        ))
                        matched_models.append(model_name)
                        channel_matches += 1
                        logger.debug(f"✅ MERGED TAG MATCH: Channel '{channel.name}' model '{model_name}' -> tags: {combined_tags}")
                    else:
                        logger.debug(f"⚠️ FILTERED: Model '{model_name}' not suitable for chat (appears to be embedding/vision model)")
            
            if channel_matches > 0:
                logger.info(f"🎯 CHANNEL SUMMARY: Found {channel_matches} matching models in channel '{channel.name}' via merged channel+model tags")
        
        if matched_models:
            logger.info(f"🎯 TOTAL MATCHED MODELS: {len(matched_models)} models found: {matched_models[:5]}{'...' if len(matched_models) > 5 else ''}")
        
        return candidate_channels

    def _find_channels_with_positive_negative_tags(self, positive_tags: List[str], negative_tags: List[str], model_cache: dict) -> List[ChannelCandidate]:
        """查找匹配正标签但排除负标签的渠道和模型组合
        
        Args:
            positive_tags: 必须包含的标签列表
            negative_tags: 必须排除的标签列表
            model_cache: 模型缓存
            
        Returns:
            符合条件的候选渠道列表
        """
        candidate_channels = []
        matched_models = []
        
        # 遍历所有有效渠道
        for channel in self.config_loader.get_enabled_channels():
            # 🔥 修复：使用API Key级别缓存查找方法
            discovered_info = self.config_loader.get_model_cache_by_channel(channel.id)
            if not isinstance(discovered_info, dict):
                continue
                
            models = discovered_info.get("models", [])
            if not models:
                continue
            
            logger.debug(f"🔍 POSITIVE/NEGATIVE TAG MATCHING: Checking channel {channel.id} ({channel.name}) with {len(models)} models")
            
            # 统一的标签合并匹配：渠道标签 + 模型标签
            channel_tags = getattr(channel, 'tags', []) or []
            channel_matches = 0
            
            for model_name in models:
                if not model_name:
                    continue
                    
                # 从模型名称提取标签（已经转为小写）
                model_tags = self._extract_tags_from_model_name(model_name)
                
                # 合并渠道标签和模型标签，并规范化为小写
                combined_tags = list(set([tag.lower() for tag in channel_tags] + model_tags))
                
                # 检查正标签：所有正标签都必须在合并后的标签中（case-insensitive）
                positive_match = True
                if positive_tags:
                    normalized_positive = [tag.lower() for tag in positive_tags]
                    positive_match = all(tag in combined_tags for tag in normalized_positive)
                
                # 检查负标签：任何负标签都不能在合并后的标签中（case-insensitive）
                negative_match = True
                if negative_tags:
                    normalized_negative = [tag.lower() for tag in negative_tags]
                    negative_match = not any(tag in combined_tags for tag in normalized_negative)
                
                # 只有同时满足正标签和负标签条件的模型才被选中
                if positive_match and negative_match:
                    # 过滤掉不适合chat的模型类型
                    if self._is_suitable_for_chat(model_name):
                        candidate_channels.append(ChannelCandidate(
                            channel=channel,
                            matched_model=model_name
                        ))
                        matched_models.append(model_name)
                        channel_matches += 1
                        logger.debug(f"✅ POSITIVE/NEGATIVE TAG MATCH: Channel '{channel.name}' model '{model_name}' -> tags: {combined_tags}")
                    else:
                        logger.debug(f"⚠️ FILTERED: Model '{model_name}' not suitable for chat (appears to be embedding/vision model)")
                else:
                    if not positive_match:
                        logger.debug(f"❌ POSITIVE MISMATCH: Model '{model_name}' missing required tags from {positive_tags}")
                    if not negative_match:
                        logger.debug(f"❌ NEGATIVE MISMATCH: Model '{model_name}' contains excluded tags from {negative_tags}")
            
            if channel_matches > 0:
                logger.info(f"🎯 CHANNEL SUMMARY: Found {channel_matches} matching models in channel '{channel.name}' via positive/negative tag filtering")
        
        if matched_models:
            logger.info(f"🎯 TOTAL MATCHED MODELS: {len(matched_models)} models found: {matched_models[:5]}{'...' if len(matched_models) > 5 else ''}")
        
        return candidate_channels

    def get_available_models(self) -> List[str]:
        """获取用户可直接请求的、在配置中定义的模型列表（带缓存）"""
        # 检查缓存
        if self._available_models_cache is not None:
            return self._available_models_cache
        
        models = set()
        all_tags = set()
        
        # 添加物理模型名称
        for ch in self.config.channels:
            if ch.enabled and ch.model_name:
                models.add(ch.model_name)
                
                # 从配置的tags中添加
                for tag in ch.tags:
                    if tag:
                        all_tags.add(f"tag:{tag}")
        
        # 从模型缓存中提取自动标签
        model_cache = self.config_loader.get_model_cache()
        if model_cache:
            for channel_id, cache_info in model_cache.items():
                if not isinstance(cache_info, dict):
                    continue
                
                models_list = cache_info.get("models", [])
                if not isinstance(models_list, list):
                    continue
                    
                for model_name in models_list:
                    if model_name:
                        models.add(model_name)
                        # 提取自动标签
                        auto_tags = self._extract_tags_from_model_name(model_name)
                        for tag in auto_tags:
                            if tag:
                                all_tags.add(f"tag:{tag}")
        
        # 缓存结果
        result = sorted(list(models | all_tags))
        self._available_models_cache = result
        return result
    
    def clear_cache(self):
        """清除所有缓存"""
        self._tag_cache.clear()
        self._available_tags_cache = None
        self._available_models_cache = None
        logger.info("Router cache cleared")
    
    def update_channel_health(self, channel_id: str, success: bool, latency: Optional[float] = None):
        """更新渠道健康状态"""
        self.config_loader.update_channel_health(channel_id, success, latency)

# 全局路由器实例
_router: Optional[JSONRouter] = None

def get_router() -> JSONRouter:
    """获取全局路由器实例"""
    global _router
    if _router is None:
        _router = JSONRouter()
    return _router