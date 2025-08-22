"""
基于JSON配置的轻量路由引擎
"""
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from .config_models import Channel
from .utils.capability_mapper import get_capability_mapper
from .utils.channel_cache_manager import get_channel_cache_manager
from .utils.local_model_capabilities import get_capability_detector
from .utils.model_analyzer import get_model_analyzer
from .utils.parameter_comparator import get_parameter_comparator
from .utils.request_cache import RequestFingerprint, get_request_cache
from .yaml_config import YAMLConfigLoader, get_yaml_config_loader

logger = logging.getLogger(__name__)

class TagNotFoundError(Exception):
    """标签未找到错误"""
    def __init__(self, tags: list[str], message: str = None):
        self.tags = tags
        if message is None:
            if len(tags) == 1:
                message = f"没有找到匹配标签 '{tags[0]}' 的模型"
            else:
                message = f"没有找到同时匹配标签 {tags} 的模型"
        super().__init__(message)

class ParameterComparisonError(Exception):
    """参数量比较错误"""
    def __init__(self, query: str, message: str = None):
        self.query = query
        if message is None:
            message = f"没有找到满足参数量比较 '{query}' 的模型"
        super().__init__(message)

@dataclass
class SizeFilter:
    """大小过滤器"""
    operator: str  # >, <, >=, <=, =
    value: float
    unit: str  # b, m, k for parameters; ki, ko, mi, mo for context
    type: str  # 'params', 'input_context', 'output_context'

    def matches(self, target_value: float) -> bool:
        """检查目标值是否匹配过滤条件"""
        if self.operator == ">":
            return target_value > self.value
        elif self.operator == "<":
            return target_value < self.value
        elif self.operator == ">=":
            return target_value >= self.value
        elif self.operator == "<=":
            return target_value <= self.value
        elif self.operator == "=":
            return target_value == self.value
        return False

def parse_size_filter(tag: str) -> Optional[SizeFilter]:
    """解析大小过滤标签

    Args:
        tag: 标签字符串，如 ">20b", "<8ko", ">=10ki"

    Returns:
        SizeFilter 对象，如果解析失败则返回 None
    """
    # 参数大小过滤模式：>20b, <7b, >=1.5b
    param_pattern = r'^([><=]+)(\d+\.?\d*)([bmk])$'
    # 上下文大小过滤模式：>10ki, <8ko, >=32mi
    context_pattern = r'^([><=]+)(\d+\.?\d*)([kK]?[iI]|[mM]?[oO])$'

    # 先尝试参数大小过滤
    match = re.match(param_pattern, tag, re.IGNORECASE)
    if match:
        operator, value_str, unit = match.groups()
        try:
            value = float(value_str)
            # 转换单位到基本单位
            if unit.lower() == 'b':
                pass  # 1b = 1 billion parameters
            elif unit.lower() == 'm':
                pass  # 1m = 1 million parameters
            elif unit.lower() == 'k':
                pass  # 1k = 1 thousand parameters
            else:
                return None

            return SizeFilter(
                operator=operator,
                value=value,
                unit=unit,
                type='params'
            )
        except ValueError:
            return None

    # 再尝试上下文大小过滤
    match = re.match(context_pattern, tag, re.IGNORECASE)
    if match:
        operator, value_str, unit = match.groups()
        try:
            value = float(value_str)
            # 转换单位到基本单位 (tokens)
            unit_lower = unit.lower()
            if unit_lower in ['ki', 'i']:
                pass  # 1ki = 1000 tokens
            elif unit_lower in ['ko', 'o']:
                pass  # 1ko = 1000 tokens
            elif unit_lower in ['mi', 'm']:
                pass  # 1mi = 1M tokens
            elif unit_lower in ['mo']:
                pass  # 1mo = 1M tokens
            else:
                return None

            context_type = 'input_context' if unit_lower in ['ki', 'i', 'mi', 'm'] else 'output_context'

            return SizeFilter(
                operator=operator,
                value=value,
                unit=unit,
                type=context_type
            )
        except ValueError:
            return None

    return None


def apply_size_filters(candidates: list['ChannelCandidate'], size_filters: list[SizeFilter]) -> list['ChannelCandidate']:
    """应用大小过滤器到候选渠道

    Args:
        candidates: 候选渠道列表
        size_filters: 大小过滤器列表

    Returns:
        过滤后的候选渠道列表
    """
    if not size_filters:
        return candidates

    filtered_candidates = []
    model_analyzer = get_model_analyzer()

    logger.info(f"SIZE FILTERS: Applying {len(size_filters)} filters to {len(candidates)} candidates")

    for candidate in candidates:
        match = True
        model_name = candidate.matched_model
        logger.info(f"SIZE FILTER DEBUG: Processing candidate {candidate.channel.id} -> {model_name}")

        # 获取模型详细信息
        config_loader = get_yaml_config_loader()
        channel_id = candidate.channel.id
        model_data = None

        # 🔥 修复：使用API Key级别缓存查找方法
        discovered_info = config_loader.get_model_cache_by_channel(channel_id)
        if isinstance(discovered_info, dict):
            # 首先尝试从 models_data 获取模型详情（新格式）
            models_data = discovered_info.get("models_data", {})
            if model_name in models_data:
                model_data = models_data[model_name]
                logger.info(f"SIZE FILTER DEBUG: Found model_data for {model_name} in models_data")
            else:
                # 🔥 修复：如果 models_data 为空，从 response_data.data 查找（OpenRouter格式）
                response_data = discovered_info.get("response_data", {})
                data_list = response_data.get("data", [])
                model_data = None
                for model_info in data_list:
                    if model_info.get("id") == model_name:
                        model_data = model_info
                        logger.info(f"SIZE FILTER DEBUG: Found model_data for {model_name} in response_data: context_length={model_info.get('context_length')}")
                        break
                if not model_data:
                    logger.info(f"SIZE FILTER DEBUG: No model_data found for {model_name} in channel {channel_id}")
                    logger.info(f"SIZE FILTER DEBUG: Available models in models_data: {list(models_data.keys())[:5]}")
                    logger.info(f"SIZE FILTER DEBUG: Available models in response_data: {len(data_list)} models")
        else:
            logger.info(f"SIZE FILTER DEBUG: No discovered_info found for channel {channel_id}")

        # 使用模型分析器分析模型
        try:
            specs = model_analyzer.analyze_model(model_name, model_data)
            if specs:
                logger.info(f"SIZE FILTER DEBUG: Model analysis for {model_name}: context_length={specs.context_length}, parameter_count={specs.parameter_count}")
            else:
                logger.info(f"SIZE FILTER DEBUG: Model analysis returned None for {model_name}")
        except Exception as e:
            logger.warning(f"Failed to analyze model {model_name}: {e}")
            specs = None

        # 应用每个过滤器
        for size_filter in size_filters:
            if size_filter.type == 'params':
                # 参数大小过滤
                if specs and specs.parameter_count:
                    # parameter_count 以百万为单位，需要转换为 billion 进行比较
                    param_count_billions = specs.parameter_count / 1000.0
                    logger.debug(f"Model {model_name}: {specs.parameter_count}M params = {param_count_billions}B")

                    if not size_filter.matches(param_count_billions):
                        logger.debug(f"SIZE FILTER: {model_name} filtered out - {param_count_billions}B params does not match {size_filter.operator}{size_filter.value}b")
                        match = False
                        break
                else:
                    logger.debug(f"SIZE FILTER: {model_name} filtered out - no parameter count available")
                    match = False
                    break

            elif size_filter.type == 'input_context':
                # 输入上下文大小过滤
                context_size = None
                if specs and specs.context_length:
                    context_size = specs.context_length
                elif model_data and model_data.get("max_input_tokens"):
                    context_size = model_data["max_input_tokens"]
                elif model_data and model_data.get("context_length"):
                    context_size = model_data["context_length"]

                if context_size:
                    # 转换为千为单位进行比较
                    context_size_k = context_size / 1000.0
                    logger.info(f"SIZE FILTER DEBUG: Model {model_name}: {context_size} input tokens = {context_size_k}k")

                    if not size_filter.matches(context_size_k):
                        logger.info(f"SIZE FILTER DEBUG: {model_name} filtered out - {context_size_k}ki does not match {size_filter.operator}{size_filter.value}ki")
                        match = False
                        break
                    else:
                        logger.info(f"SIZE FILTER DEBUG: {model_name} PASSED - {context_size_k}ki matches {size_filter.operator}{size_filter.value}ki")
                else:
                    logger.info(f"SIZE FILTER DEBUG: {model_name} filtered out - no input context size available")
                    match = False
                    break

            elif size_filter.type == 'output_context':
                # 输出上下文大小过滤
                context_size = None
                if model_data and model_data.get("max_output_tokens"):
                    context_size = model_data["max_output_tokens"]
                elif specs and specs.context_length:
                    # 如果没有专门的输出限制，使用总上下文长度作为近似
                    context_size = specs.context_length
                elif model_data and model_data.get("context_length"):
                    context_size = model_data["context_length"]

                if context_size:
                    # 转换为千为单位进行比较
                    context_size_k = context_size / 1000.0
                    logger.debug(f"Model {model_name}: {context_size} output tokens = {context_size_k}k")

                    if not size_filter.matches(context_size_k):
                        logger.debug(f"SIZE FILTER: {model_name} filtered out - {context_size_k}ko does not match {size_filter.operator}{size_filter.value}ko")
                        match = False
                        break
                else:
                    logger.debug(f"SIZE FILTER: {model_name} filtered out - no output context size available")
                    match = False
                    break

        if match:
            filtered_candidates.append(candidate)
            logger.debug(f"SIZE FILTER: {model_name} passed all filters")

    logger.info(f"SIZE FILTERS: Filtered from {len(candidates)} to {len(filtered_candidates)} candidates")
    return filtered_candidates

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
    # 性能优化：预计算层次排序所需的额外评分
    parameter_score: float = 0.0
    context_score: float = 0.0
    free_score: float = 0.0

@dataclass
class ChannelCandidate:
    """候选渠道信息"""
    channel: Channel
    matched_model: Optional[str] = None  # 对于标签路由，记录实际匹配的模型

@dataclass
class RoutingRequest:
    """路由请求"""
    model: str
    messages: list[dict[str, Any]]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    functions: Optional[list[dict[str, Any]]] = None
    required_capabilities: list[str] = None
    data: Optional[dict[str, Any]] = None  # 完整的请求数据，用于能力检测

class JSONRouter:
    """基于Pydantic验证后配置的路由器"""

    def __init__(self, config_loader: Optional[YAMLConfigLoader] = None):
        self.config_loader = config_loader or get_yaml_config_loader()
        self.config = self.config_loader.config

        # 标签缓存，避免重复计算
        self._tag_cache: dict[str, list[str]] = {}
        self._available_tags_cache: Optional[set] = None
        self._available_models_cache: Optional[list[str]] = None

        # 模型分析器、缓存管理器和参数量比较器
        self.model_analyzer = get_model_analyzer()
        self.cache_manager = get_channel_cache_manager()
        self.parameter_comparator = get_parameter_comparator()

        # 能力检测器和映射器
        self.capability_detector = get_capability_detector()
        self.capability_mapper = get_capability_mapper()

    async def route_request(self, request: RoutingRequest) -> list[RoutingScore]:
        """
        路由请求，返回按评分排序的候选渠道列表。

        支持请求级缓存以提高性能：
        - 缓存TTL: 60秒
        - 基于请求指纹的智能缓存键生成
        - 自动故障转移和缓存失效
        """
        logger.info(f"ROUTING START: Processing request for model '{request.model}'")

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
        cache_key = fingerprint.to_cache_key()
        logger.debug(f"CACHE LOOKUP: Key={cache_key}, Model={request.model}")

        cached_result = await cache.get_cached_selection(fingerprint)

        if cached_result:
            # 缓存命中，转换为RoutingScore列表
            logger.info(f"CACHE HIT: Using cached selection for '{request.model}' "
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
        logger.info(f"CACHE MISS: Computing fresh routing for '{request.model}'")
        try:
            # 第一步：获取候选渠道
            logger.info("STEP 1: Finding candidate channels...")
            candidates = self._get_candidate_channels(request)
            if not candidates:
                logger.warning(f"ROUTING FAILED: No suitable channels found for model '{request.model}'")
                return []

            logger.info(f"STEP 1 COMPLETE: Found {len(candidates)} candidate channels")

            # 第二步：过滤渠道
            logger.info("STEP 2: Filtering channels by health and availability...")
            filtered_candidates = self._filter_channels(candidates, request)
            if not filtered_candidates:
                logger.warning(f"ROUTING FAILED: No available channels after filtering for model '{request.model}'")
                return []

            # 第2.5步：能力检测过滤（仅对本地模型）
            logger.info("STEP 2.5: Checking model capabilities...")
            capability_filtered = await self._filter_by_capabilities(filtered_candidates, request)
            if not capability_filtered:
                logger.warning(f"ROUTING FAILED: No channels with required capabilities for model '{request.model}'")
                return []

            logger.info(f"STEP 2.5 COMPLETE: {len(capability_filtered)} channels passed capability check (filtered out {len(filtered_candidates) - len(capability_filtered)})")
            filtered_candidates = capability_filtered

            # 第2.7步：预筛选（性能优化）- 限制参与详细评分的渠道数量
            if len(filtered_candidates) > 20:  # 仅在渠道数量过多时预筛选
                logger.info(f"STEP 2.7: Pre-filtering {len(filtered_candidates)} channels to reduce scoring overhead...")
                pre_filtered = await self._pre_filter_channels(filtered_candidates, request, max_channels=20)
                logger.info(f"STEP 2.7 COMPLETE: Pre-filtered to {len(pre_filtered)} channels for detailed scoring")
                filtered_candidates = pre_filtered

            # 第三步：评分和排序
            logger.info("🎯 STEP 3: Scoring and ranking channels...")
            scored_channels = await self._score_channels(filtered_candidates, request)
            if not scored_channels:
                logger.warning(f"ROUTING FAILED: Failed to score any channels for model '{request.model}'")
                return []

            logger.info(f"STEP 3 COMPLETE: Scored {len(scored_channels)} channels")

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
        except ParameterComparisonError:
            # 让ParameterComparisonError传播出去，以便上层处理
            raise
        except Exception as e:
            logger.error(f"ROUTING ERROR: Request failed for model '{request.model}': {e}", exc_info=True)
            return []

    def _get_candidate_channels(self, request: RoutingRequest) -> list[ChannelCandidate]:
        """获取候选渠道，支持按标签集合、物理模型或参数量比较进行智能路由"""

        # 1. 检查是否为参数量比较查询（qwen3->8b, qwen3-<72b 等）
        if self.parameter_comparator.is_parameter_comparison(request.model):
            logger.info(f"🔢 PARAMETER COMPARISON: Processing query '{request.model}'")
            comparison = self.parameter_comparator.parse_comparison(request.model)
            if not comparison:
                logger.error(f"PARAM PARSE FAILED: Could not parse parameter comparison '{request.model}'")
                raise ParameterComparisonError(request.model)

            # 获取所有模型缓存
            model_cache = self.config_loader.get_model_cache()
            if not model_cache:
                logger.error("NO MODEL CACHE: Model cache is empty for parameter comparison")
                raise ParameterComparisonError(request.model, "模型缓存为空，无法进行参数量比较")

            # 按参数量比较筛选模型
            matching_models = self.parameter_comparator.filter_models_by_comparison(comparison, model_cache)
            if not matching_models:
                logger.error(f"PARAM COMPARISON FAILED: No models found matching '{request.model}'")
                raise ParameterComparisonError(request.model)
            else:
                logger.info("📝 First 5 matched models:")
                for i, (channel_id, model_name, model_params) in enumerate(matching_models[:5]):
                    logger.info(f"  {i+1}. {channel_id} -> {model_name} ({model_params:.3f}B)")

            # 转换为候选渠道列表
            candidates = []
            disabled_count = 0
            not_found_count = 0

            logger.debug(f"Processing {len(matching_models)} matching models for channel lookup...")

            for channel_id, model_name, model_params in matching_models:
                # 从 API key-level cache key 中提取真实的 channel ID
                # 格式: "channel_id_apikeyash" -> "channel_id"
                real_channel_id = channel_id
                if '_' in channel_id:
                    # 尝试去掉 API key hash 后缀
                    parts = channel_id.split('_')
                    if len(parts) >= 2:
                        # 检查最后一部分是否为 hash 格式（长度为8的十六进制字符串）
                        potential_hash = parts[-1]
                        if len(potential_hash) == 8 and all(c in '0123456789abcdef' for c in potential_hash.lower()):
                            real_channel_id = '_'.join(parts[:-1])

                logger.debug(f"Channel ID mapping: '{channel_id}' -> '{real_channel_id}'")

                # 查找对应的渠道对象
                channel = self.config_loader.get_channel_by_id(real_channel_id)
                if channel:
                    if channel.enabled:
                        candidates.append(ChannelCandidate(
                            channel=channel,
                            matched_model=model_name
                        ))
                        logger.debug(f"Added channel: {channel.name} -> {model_name} ({model_params:.3f}B)")
                    else:
                        disabled_count += 1
                        logger.debug(f"Disabled channel: {real_channel_id} -> {model_name}")
                else:
                    not_found_count += 1
                    logger.debug(f"Channel not found: {real_channel_id} (from {channel_id}) -> {model_name}")

            logger.info(f"CHANNEL LOOKUP: Found {len(candidates)} enabled channels, "
                       f"disabled: {disabled_count}, not_found: {not_found_count}")

            logger.info(f"PARAMETER COMPARISON: Found {len(candidates)} candidate channels "
                       f"for '{comparison.model_prefix}' models {comparison.operator} {comparison.target_params}B")

            # 显示前几个匹配的渠道
            if candidates:
                logger.info("📝 Top matched channels:")
                for i, candidate in enumerate(candidates[:5]):
                    logger.info(f"  {i+1}. {candidate.channel.name} -> {candidate.matched_model}")
            return candidates

        # 2. 检查是否为标签查询
        if request.model.startswith("tag:") or request.model.startswith("tags:"):
            # 统一处理 tag: 和 tags: 前缀
            prefix = "tag:" if request.model.startswith("tag:") else "tags:"
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
                        # 检查是否为大小过滤标签
                        size_filter = parse_size_filter(tag_part)
                        if size_filter:
                            # 这是大小过滤标签，但也要当作正标签处理查找候选者
                            pass  # Size filter will be applied later
                        else:
                            # 正标签：free, qwen3
                            positive_tags.append(tag_part.lower())

                logger.info(f"TAG ROUTING: Processing multi-tag query '{request.model}' -> positive: {positive_tags}, negative: {negative_tags} (prefix: {prefix})")
                candidates = self._get_candidate_channels_by_auto_tags(positive_tags, negative_tags)
                if not candidates:
                    logger.error(f"TAG NOT FOUND: No models found matching tags {positive_tags} excluding {negative_tags}")
                    raise TagNotFoundError(positive_tags + [f"!{tag}" for tag in negative_tags])

                # 提取并应用大小过滤器
                size_filters = []
                for tag_part in tag_parts:
                    if not tag_part.startswith("!"):
                        size_filter = parse_size_filter(tag_part)
                        if size_filter:
                            size_filters.append(size_filter)

                if size_filters:
                    logger.info(f"SIZE FILTERS: Applying {len(size_filters)} size filters: {[f'{sf.operator}{sf.value}{sf.unit}' for sf in size_filters]}")
                    filtered_candidates = apply_size_filters(candidates, size_filters)
                    logger.info(f"SIZE FILTERS: Filtered from {len(candidates)} to {len(filtered_candidates)} candidates")
                    candidates = filtered_candidates

                if not candidates:
                    logger.error("SIZE FILTERS: No candidates left after applying size filters")
                    raise TagNotFoundError(positive_tags + [f"!{tag}" for tag in negative_tags])

                logger.info(f"TAG ROUTING: Multi-tag query found {len(candidates)} candidate channels")
                return candidates
            else:
                # 单标签查询 - 支持负标签：tag:!local
                tag_part = tag_query.strip()
                if tag_part.startswith("!"):
                    # 负标签单独查询：tag:!local (匹配所有不包含local的模型)
                    negative_tag = tag_part[1:].lower()
                    logger.info(f"TAG ROUTING: Processing negative tag query '{request.model}' -> excluding: '{negative_tag}' (prefix: {prefix})")
                    candidates = self._get_candidate_channels_by_auto_tags([], [negative_tag])
                else:
                    # 检查是否为大小过滤标签
                    size_filter = parse_size_filter(tag_part)
                    if size_filter:
                        # 这是大小过滤标签，需要特殊处理
                        logger.info(f"TAG ROUTING: Processing size filter query '{request.model}' -> filter: '{tag_part}' (prefix: {prefix})")
                        # 获取所有候选渠道，然后应用大小过滤器
                        candidates = self._get_candidate_channels_by_auto_tags([], [])
                        filtered_candidates = apply_size_filters(candidates, [size_filter])
                        logger.info(f"SIZE FILTERS: Filtered from {len(candidates)} to {len(filtered_candidates)} candidates")
                        candidates = filtered_candidates
                    else:
                        # 正常单标签查询
                        tag = tag_part.lower()
                        logger.info(f"TAG ROUTING: Processing single tag query '{request.model}' -> tag: '{tag}' (prefix: {prefix})")
                        candidates = self._get_candidate_channels_by_auto_tags([tag], [])

                if not candidates:
                    logger.error(f"TAG NOT FOUND: No models found for query '{request.model}'")
                    raise TagNotFoundError([tag_query])
                logger.info(f"TAG ROUTING: Found {len(candidates)} candidate channels")
                return candidates

        # 非tag:前缀的模型名称 - 精确匹配用户输入的完整名称
        all_enabled_channels = self.config_loader.get_enabled_channels()
        model_cache = self.config_loader.get_model_cache()

        # 1. 首先尝试作为物理模型查找（精确匹配）
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

                    logger.debug(f"PHYSICAL MODEL: Found '{request.model}' -> '{real_model_id}' in channel '{channel.name}'")
                    physical_candidates.append(ChannelCandidate(
                        channel=channel,
                        matched_model=real_model_id  # 使用真实的模型ID
                    ))

        # 2. 尝试完整子段标签匹配（不拆分用户输入）
        complete_segment_candidates = []
        logger.info(f"COMPLETE SEGMENT MATCHING: Searching for exact match of '{request.model}' as complete segment")

        # 使用用户输入作为完整标签进行匹配
        complete_segment_candidates = self._get_candidate_channels_by_complete_segment([request.model.lower()])
        if complete_segment_candidates:
            logger.info(f"COMPLETE SEGMENT MATCHING: Found {len(complete_segment_candidates)} candidate channels using complete segment match")
        else:
            logger.info(f"COMPLETE SEGMENT MATCHING: No channels found for complete segment '{request.model}'")

        # 3. 合并物理模型和完整子段匹配的结果，去重
        all_candidates = physical_candidates.copy()

        # 添加完整子段匹配的候选，避免重复
        for segment_candidate in complete_segment_candidates:
            # 检查是否已经存在相同的 channel + model 组合
            duplicate_found = False
            for existing in all_candidates:
                if (existing.channel.id == segment_candidate.channel.id and
                    existing.matched_model == segment_candidate.matched_model):
                    duplicate_found = True
                    break

            if not duplicate_found:
                all_candidates.append(segment_candidate)

        if all_candidates:
            physical_count = len(physical_candidates)
            segment_count = len(complete_segment_candidates)
            total_count = len(all_candidates)
            logger.info(f"COMPREHENSIVE SEARCH: Found {total_count} total candidates "
                       f"(physical: {physical_count}, complete-segment: {segment_count}, merged without duplicates)")
            return all_candidates

        # 4. 最后尝试从配置中查找
        config_channels = self.config_loader.get_channels_by_model(request.model)
        if config_channels:
            logger.info(f"CONFIG FALLBACK: Found {len(config_channels)} channels in configuration for model '{request.model}'")
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
        logger.warning(f"NO MATCH: No channels found for model '{request.model}' (tried physical, auto-tag, and config)")
        return []

    def _filter_channels(self, channels: list[ChannelCandidate], request: RoutingRequest) -> list[ChannelCandidate]:
        """过滤渠道，包含能力检测"""
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

            # 🚀 优化健康分数检查（避免重复访问）
            if not hasattr(self, '_cached_health_scores'):
                self._cached_health_scores = self.config_loader.runtime_state.health_scores.copy()

            health_score = self._cached_health_scores.get(channel.id, 1.0)
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

    async def _score_channels(self, channels: list[ChannelCandidate], request: RoutingRequest) -> list[RoutingScore]:
        """计算渠道评分 - 批量优化版本，支持慢查询检测"""
        start_time = time.time()
        channel_count = len(channels)

        logger.info(f"📊 SCORING: Evaluating {channel_count} candidate channels for model '{request.model}'")

        # 如果渠道数量较少，使用原有的单个评分方式
        if channel_count < 5:
            result = await self._score_channels_individual(channels, request)
            elapsed_ms = (time.time() - start_time) * 1000
            self._log_performance_metrics(channel_count, elapsed_ms, "individual")
            return result

        # 使用批量评分器进行优化
        if not hasattr(self, '_batch_scorer'):
            from core.utils.batch_scorer import BatchScorer
            self._batch_scorer = BatchScorer(self)

        # 批量计算所有评分，获取性能指标
        batch_result, metrics = await self._batch_scorer.batch_score_channels(channels, request)


        # 构建评分结果
        scored_channels = []
        strategy = self._get_routing_strategy(request.model)

        logger.info(f"📊 SCORING: Using routing strategy with {len(strategy)} rules")
        for rule in strategy:
            logger.debug(f"📊 SCORING: Strategy rule: {rule['field']} (weight: {rule['weight']}, order: {rule['order']})")

        for candidate in channels:
            # 从批量结果中获取评分
            scores = self._batch_scorer.get_score_for_channel(batch_result, candidate)

            total_score = self._calculate_total_score(
                strategy,
                scores['cost_score'], scores['speed_score'], scores['quality_score'],
                scores['reliability_score'], scores['parameter_score'], scores['context_score'],
                scores['free_score'], scores['local_score']
            )

            # 简化日志输出
            model_display = candidate.matched_model or candidate.channel.model_name
            # 只在调试模式记录详细评分，生产模式减少日志噪音
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"📊 SCORE: '{candidate.channel.name}' -> '{model_display}' = {total_score:.3f} (Q:{scores['quality_score']:.2f})")

            scored_channels.append(RoutingScore(
                channel=candidate.channel, total_score=total_score,
                cost_score=scores['cost_score'], speed_score=scores['speed_score'],
                quality_score=scores['quality_score'], reliability_score=scores['reliability_score'],
                reason=f"cost:{scores['cost_score']:.2f} speed:{scores['speed_score']:.2f} quality:{scores['quality_score']:.2f} reliability:{scores['reliability_score']:.2f}",
                matched_model=candidate.matched_model,
                # 预计算层次排序所需的额外评分
                parameter_score=scores['parameter_score'],
                context_score=scores['context_score'],
                free_score=scores['free_score']
            ))

        # 使用分层优先级排序
        scored_channels = self._hierarchical_sort(scored_channels)

        # 记录性能指标
        total_elapsed_ms = (time.time() - start_time) * 1000
        self._log_performance_metrics(channel_count, total_elapsed_ms, "batch", metrics)

        logger.info(f"🏆 SCORING RESULT: Channels ranked by score (computed in {total_elapsed_ms:.1f}ms):")
        for i, scored in enumerate(scored_channels[:5]):  # 只显示前5个
            logger.info(f"🏆   #{i+1}: '{scored.channel.name}' (Score: {scored.total_score:.3f})")

        return scored_channels

    async def _score_channels_individual(self, channels: list[ChannelCandidate], request: RoutingRequest) -> list[RoutingScore]:
        """单个渠道评分方式（用于小数量渠道）"""
        logger.info(f"📊 SCORING: Using individual scoring for {len(channels)} channels")

        scored_channels = []
        strategy = self._get_routing_strategy(request.model)

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

            model_display = candidate.matched_model or channel.model_name
            # 只在调试模式记录详细评分，生产模式减少日志噪音
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"📊 SCORE: '{channel.name}' -> '{model_display}' = {total_score:.3f} (Q:{quality_score:.2f})")

            scored_channels.append(RoutingScore(
                channel=channel, total_score=total_score, cost_score=cost_score,
                speed_score=speed_score, quality_score=quality_score,
                reliability_score=reliability_score,
                reason=f"cost:{cost_score:.2f} speed:{speed_score:.2f} quality:{quality_score:.2f} reliability:{reliability_score:.2f}",
                matched_model=candidate.matched_model,
                # 预计算层次排序所需的额外评分
                parameter_score=parameter_score,
                context_score=context_score,
                free_score=free_score
            ))

        scored_channels = self._hierarchical_sort(scored_channels)

        # 记录评分结果摘要
        logger.info(f"🏆 INDIVIDUAL SCORING RESULT: Processed {len(scored_channels)} channels")
        for i, scored in enumerate(scored_channels[:3]):  # 只显示前3个
            logger.info(f"🏆   #{i+1}: '{scored.channel.name}' (Score: {scored.total_score:.3f})")

        return scored_channels

    def _get_routing_strategy(self, model: str) -> list[dict[str, Any]]:
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

    def _get_model_specs(self, channel_id: str, model_name: str) -> Optional[dict[str, Any]]:
        """获取模型规格信息（内存索引优化版）"""
        try:
            # 🚀 优先使用内存索引（消除文件I/O瓶颈）
            from core.utils.memory_index import get_memory_index
            memory_index = get_memory_index()
            specs = memory_index.get_model_specs(channel_id, model_name)
            if specs:
                return specs

        except Exception as e:
            logger.debug(f"Memory index specs lookup failed for {model_name}: {e}")

        try:
            # 回退：从渠道缓存中获取
            channel_cache = self.cache_manager.load_channel_models(channel_id)
            if channel_cache and 'models' in channel_cache:
                return channel_cache['models'].get(model_name)
        except Exception as e:
            logger.debug(f"Failed to load model specs for {model_name}: {e}")

        # 最后回退到分析器分析
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
        """计算可靠性评分（完全后台化：只使用缓存结果）"""
        # 🚀 完全依赖后台任务维护的缓存数据，主线程不执行任何健康检查
        # 1. 优先从内存索引获取缓存的健康评分
        try:
            from core.utils.memory_index import get_memory_index
            memory_index = get_memory_index()
            cached_health = memory_index.get_health_score(channel.id, cache_ttl=300.0)  # 5分钟TTL
            if cached_health is not None:
                return cached_health
        except Exception:
            pass

        # 2. 回退到运行时状态缓存（由后台健康检查任务更新）
        health_score = self.config_loader.runtime_state.health_scores.get(channel.id, 1.0)

        # 3. 🚀 异步更新内存缓存（非阻塞）
        try:
            from core.utils.memory_index import get_memory_index
            memory_index = get_memory_index()
            memory_index.set_health_score(channel.id, health_score)
        except Exception:
            pass  # 静默失败，不影响主路由性能

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

    def _calculate_total_score(self, strategy: list[dict[str, Any]],
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

    def _hierarchical_sort(self, scored_channels: list[RoutingScore]) -> list[RoutingScore]:
        """分层优先级排序：使用6位数字评分系统 (成本|上下文|参数|速度|质量|可靠性)

        注意：移除了自动本地优先逻辑，只有在用户明确指定 local 标签或 local_first 策略时才会优先本地
        """
        def sorting_key(score: RoutingScore):
            # 使用预计算的评分信息（性能优化）
            free_score = score.free_score
            parameter_score = score.parameter_score
            context_score = score.context_score

            # 将每个维度的评分转换为0-9的整数评分
            # 第1位：成本优化程度 (9=完全免费, 8=很便宜, 0=很昂贵)
            if free_score >= 0.9:
                cost_tier = 9  # 免费模型固定为9分
            else:
                cost_tier = min(8, int(score.cost_score * 8))  # 付费模型最高8分

            # 第2位：上下文长度程度 (9=很长, 0=很短) - 优先级高于参数量
            context_tier = min(9, int(context_score * 9))

            # 第3位：参数量程度 (9=很大, 0=很小) - 在参数量比较查询中关键
            parameter_tier = min(9, int(parameter_score * 9))

            # 第4位：速度程度 (9=很快, 0=很慢)
            speed_tier = min(9, int(score.speed_score * 9))

            # 第5位：质量程度 (9=很高, 0=很低)
            quality_tier = min(9, int(score.quality_score * 9))

            # 第6位：可靠性程度 (9=很可靠, 0=很不可靠)
            reliability_tier = min(9, int(score.reliability_score * 9))

            # 组成6位数字，数字越大排序越靠前
            hierarchical_score = (
                cost_tier * 100000 +        # 第1位：成本(免费=9,付费最高=8)
                context_tier * 10000 +      # 第2位：上下文(优先级高于参数量)
                parameter_tier * 1000 +     # 第3位：参数量(在参数量比较查询中关键)
                speed_tier * 100 +          # 第4位：速度
                quality_tier * 10 +         # 第5位：质量
                reliability_tier            # 第6位：可靠性
            )

            return (-hierarchical_score, score.channel.name)

        logger.info("HIERARCHICAL SORTING: 6-digit scoring system (Cost|Context|Param|Speed|Quality|Reliability)")

        # 按分层评分排序
        sorted_channels = sorted(scored_channels, key=sorting_key)

        # 打印排序结果用于调试
        for i, scored in enumerate(sorted_channels[:5]):
            # 使用预计算的评分（性能优化）
            free_score = scored.free_score
            parameter_score = scored.parameter_score
            context_score = scored.context_score

            # 计算6位数字评分
            if free_score >= 0.9:
                cost_tier = 9  # 免费模型固定为9分
            else:
                cost_tier = min(8, int(scored.cost_score * 8))  # 付费模型最高8分

            context_tier = min(9, int(context_score * 9))
            parameter_tier = min(9, int(parameter_score * 9))
            speed_tier = min(9, int(scored.speed_score * 9))
            quality_tier = min(9, int(scored.quality_score * 9))
            reliability_tier = min(9, int(scored.reliability_score * 9))

            hierarchical_score = (
                cost_tier * 100000 + context_tier * 10000 + parameter_tier * 1000 +
                speed_tier * 100 + quality_tier * 10 + reliability_tier
            )

            score_display = f"{cost_tier}{context_tier}{parameter_tier}{speed_tier}{quality_tier}{reliability_tier}"
            is_free = "FREE" if free_score >= 0.9 else "PAID"
            logger.info(f"   #{i+1}: '{scored.channel.name}' [{is_free}] Score: {score_display} (Total: {hierarchical_score:,})")

        return sorted_channels

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """智能估算prompt tokens"""
        try:
            # 尝试使用tiktoken库
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4使用的编码

            total_tokens = 0
            for message in messages:
                content = message.get("content", "")
                if isinstance(content, str):
                    # 加上角色标记的开销
                    role_overhead = 4  # 每条消息的role等结构开销
                    content_tokens = len(encoding.encode(content))
                    total_tokens += content_tokens + role_overhead

            return max(1, total_tokens)

        except ImportError:
            # tiktoken不可用时的智能回退
            logger.debug("tiktoken不可用，使用改进的字符估算方法")

        # 改进的字符计算方法
        total_chars = 0
        all_content = ""
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                # 角色标记开销
                total_chars += len(f"role: {message.get('role', 'user')}")
                # 内容字符数
                total_chars += len(content)
                all_content += content

        # 改进的字符到token转换比率（更准确）
        # 中文字符通常1个字符=1个token，英文约4个字符=1个token
        chinese_chars = sum(1 for char in all_content if '\u4e00' <= char <= '\u9fff')
        english_chars = len(all_content) - chinese_chars
        estimated_tokens = chinese_chars + (english_chars // 4) + (len(messages) * 4)  # 添加消息结构开销

        return max(1, estimated_tokens)

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

    def _extract_tags_from_model_name(self, model_name: str) -> list[str]:
        """从模型名称中提取标签（带缓存）- 支持多颗粒度匹配

        例如: "qwen/qwen3-235b-a22b:free" ->
        - 拆分标签: ["qwen", "qwen3", "235b", "a22b", "free"]
        - 完整子段: ["qwen3-235b-a22b"] (去掉前缀和后缀的核心名称)
        - 合并结果: ["qwen", "qwen3", "235b", "a22b", "free", "qwen3-235b-a22b"]
        """
        if not model_name or not isinstance(model_name, str):
            return []

        # 检查缓存
        if model_name in self._tag_cache:
            return self._tag_cache[model_name]

        import re

        # 1. 提取完整子段（核心模型名称）
        complete_segments = self._extract_complete_segments(model_name)

        # 2. 使用多种分隔符进行拆分: :, /, @, -, _, ,
        separators = r'[/:@\-_,]'
        parts = re.split(separators, model_name.lower())

        # 3. 清理和过滤拆分标签
        split_tags = []
        for part in parts:
            part = part.strip()
            if part and len(part) > 1:  # 忽略单字符和空标签
                split_tags.append(part)

        # 4. 合并拆分标签和完整子段标签，去重
        all_tags = list(dict.fromkeys(split_tags + complete_segments))  # 保持顺序去重

        # 缓存结果
        self._tag_cache[model_name] = all_tags
        return all_tags

    def _extract_complete_segments(self, model_name: str) -> list[str]:
        """从模型名称中提取完整子段（核心模型名称）

        例如:
        - "qwen/qwen3-235b-a22b:free" -> ["qwen3-235b-a22b"]
        - "deepseek/deepseek-v3-1:pro" -> ["deepseek-v3-1"]
        - "anthropic/claude-3-haiku@free" -> ["claude-3-haiku"]
        - "anthropic/claude-3-haiku-20240307:free" -> ["claude-3-haiku-20240307", "claude-3-haiku"]
        """
        if not model_name or not isinstance(model_name, str):
            return []

        import re

        # 使用主要分隔符（/, :, @）分割，保留中间部分的完整性
        main_separators = r'[/:@]'
        segments = re.split(main_separators, model_name)

        complete_segments = []
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue

            # 跳过明显的前缀（提供商名称）和后缀（价格标签等）
            segment_lower = segment.lower()

            # 跳过常见的提供商前缀
            provider_prefixes = [
                'openai', 'anthropic', 'qwen', 'deepseek', 'google', 'meta',
                'mistral', 'cohere', 'groq', 'together', 'fireworks',
                'siliconflow', 'moonshot', 'ollama', 'lmstudio'
            ]
            if segment_lower in provider_prefixes:
                continue

            # 跳过常见的后缀标签
            suffix_tags = [
                'free', 'pro', 'premium', 'paid', 'api', 'chat', 'instruct',
                'base', 'tuned', 'finetune', 'ft', 'sft', 'rlhf', 'dpo'
            ]
            if segment_lower in suffix_tags:
                continue

            # 跳过单字符段
            if len(segment) <= 1:
                continue

            # 保留可能是模型核心名称的段（长度>=3，包含字母数字组合）
            if len(segment) >= 3 and re.search(r'[a-zA-Z]', segment) and re.search(r'[\d\-]', segment):
                # 首先添加完整的段名
                complete_segments.append(segment.lower())
                
                # 检查是否有日期后缀（格式: -YYYYMMDD 或 -YYYYMMDD 变种）
                # 支持多种日期格式: -20240307, -202403, -2024-03-07 等
                date_pattern = r'-(\d{8}|\d{6}|\d{4}-\d{2}-\d{2}|\d{4}\d{2}\d{2})$'
                match = re.search(date_pattern, segment_lower)
                
                if match:
                    # 如果找到日期后缀，生成去掉日期的版本
                    segment_without_date = segment_lower[:match.start()]
                    if len(segment_without_date) >= 3 and segment_without_date not in complete_segments:
                        complete_segments.append(segment_without_date)
                        logger.debug(f"DATE EXTRACTION: '{segment}' -> added both '{segment.lower()}' and '{segment_without_date}'")

        return complete_segments

    def _resolve_model_aliases(self, model_name: str, channel) -> str:
        """解析模型别名映射
        
        将标准模型名称转换为渠道特定的模型名称
        
        Args:
            model_name: 标准模型名称（如 "deepseek-v3.1", "doubao-1.5-pro-256k"）
            channel: 渠道配置对象
            
        Returns:
            str: 渠道特定的模型名称，如果没有别名则返回原名称
        """
        if not hasattr(channel, 'model_aliases') or not channel.model_aliases:
            return model_name
            
        # 直接匹配
        if model_name in channel.model_aliases:
            resolved_name = channel.model_aliases[model_name]
            logger.debug(f"ALIAS RESOLVED: '{model_name}' -> '{resolved_name}' for channel {channel.id}")
            return resolved_name
        
        # 尝试匹配不区分大小写
        model_lower = model_name.lower()
        for alias_key, alias_value in channel.model_aliases.items():
            if alias_key.lower() == model_lower:
                logger.debug(f"ALIAS RESOLVED (case-insensitive): '{model_name}' -> '{alias_value}' for channel {channel.id}")
                return alias_value
        
        # 尝试前缀匹配（用于带provider前缀的情况）
        # 例如 "doubao/deepseek-v3" 匹配 "deepseek-v3"
        if '/' in model_name:
            _, base_name = model_name.rsplit('/', 1)
            if base_name in channel.model_aliases:
                resolved_name = channel.model_aliases[base_name]
                logger.debug(f"ALIAS RESOLVED (prefix): '{model_name}' -> '{resolved_name}' for channel {channel.id}")
                return resolved_name
        
        # 没有找到别名，返回原名称
        return model_name

    def _extract_tags_with_aliases(self, model_name: str, channel) -> list[str]:
        """提取模型标签，包括来自渠道别名配置的标签
        
        Args:
            model_name: 模型名称
            channel: 渠道配置对象
            
        Returns:
            list[str]: 包含原始标签和别名标签的完整标签列表
        """
        # 获取基础标签
        base_tags = self._extract_tags_from_model_name(model_name)
        
        if not hasattr(channel, 'model_aliases') or not channel.model_aliases:
            return base_tags
        
        # 收集别名标签：遍历别名映射，如果当前模型名称是映射的目标值，则将标准名称作为标签添加
        alias_tags = []
        
        for standard_name, channel_specific_name in channel.model_aliases.items():
            # 如果当前模型名称匹配渠道特定名称，将标准名称作为标签添加
            if model_name.lower() == channel_specific_name.lower():
                # 从标准名称中提取标签
                standard_tags = self._extract_tags_from_model_name(standard_name)
                alias_tags.extend(standard_tags)
                logger.debug(f"ALIAS TAGS: '{model_name}' matched '{channel_specific_name}', adding tags from '{standard_name}': {standard_tags}")
                
            # 也支持反向匹配：如果模型名称包含标准名称的标签，也添加标准名称作为标签
            elif any(tag in model_name.lower() for tag in self._extract_tags_from_model_name(standard_name)):
                standard_tags = self._extract_tags_from_model_name(standard_name) 
                alias_tags.extend(standard_tags)
                logger.debug(f"ALIAS TAGS (reverse): '{model_name}' contains tags from '{standard_name}', adding: {standard_tags}")
        
        # 合并所有标签并去重
        all_tags = list(dict.fromkeys(base_tags + alias_tags))
        
        if alias_tags:
            logger.debug(f"ALIAS ENRICHED TAGS: '{model_name}' -> base: {base_tags}, aliases: {alias_tags}, total: {all_tags}")
        
        return all_tags

    def _get_candidate_channels_by_auto_tags(self, positive_tags: list[str], negative_tags: list[str] = None) -> list[ChannelCandidate]:
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

        logger.info(f"TAG MATCHING: Searching for channels with positive tags: {normalized_positive}, excluding: {normalized_negative}")

        model_cache = self.config_loader.get_model_cache()
        if not model_cache:
            logger.warning("TAG MATCHING: Model cache is empty, cannot perform tag routing")
            return []

        # 🚀 性能优化：检查缓存是否包含API Key级别的格式
        # API Key级别缓存格式示例: {"channel_id_apikeyhash": {...}}
        # 旧格式: {"channel_id": {...}}
        has_api_key_format = any('_' in key and len(key.split('_')[-1]) == 8 for key in model_cache.keys())
        if has_api_key_format:
            logger.info(f"TAG MATCHING: Using API key-level cache format with {len(model_cache)} entries")
            # API Key级别缓存格式需要特殊处理，但可以继续路由
        else:
            logger.info(f"TAG MATCHING: Using legacy cache format with {len(model_cache)} entries")

        logger.info(f"TAG MATCHING: Searching through {len(model_cache)} cached channels")

        # 🚀 性能优化：使用内存索引进行超高速标签查询
        try:
            from core.utils.memory_index import (
                get_memory_index,
                rebuild_index_if_needed,
            )

            # 🚀 智能检查：仅在必要时重建内存索引
            memory_index = get_memory_index()
            current_stats = memory_index.get_stats()
            cache_size = len(model_cache)

            logger.debug(f"🔍 INDEX CHECK: Current index has {current_stats.total_models} models, {current_stats.total_channels} channels")
            logger.debug(f"🔍 INDEX CHECK: Cache has {cache_size} entries")

            needs_rebuild = current_stats.total_models == 0 or memory_index.needs_rebuild(model_cache)
            if needs_rebuild:
                logger.info(f"🔨 REBUILDING MEMORY INDEX: Cache structure changed or index empty (cache: {cache_size}, indexed: {current_stats.total_channels})")
                stats = rebuild_index_if_needed(model_cache, force_rebuild=True)
                logger.info(f"INDEX REBUILT: {stats.total_models} models, {stats.total_tags} tags in {stats.build_time_ms:.1f}ms")
            else:
                logger.debug("MEMORY INDEX: Using existing index (no rebuild needed)")

            # 使用内存索引进行超高速查询
            start_time = time.time()
            matching_models = memory_index.find_models_by_tags(normalized_positive, normalized_negative)
            index_time_ms = (time.time() - start_time) * 1000

            logger.info(f"MEMORY INDEX QUERY: Found {len(matching_models)} models in {index_time_ms:.2f}ms")

            # 将结果转换为 ChannelCandidate 格式
            memory_candidates = []
            for channel_id, model_name in matching_models:
                # 查找对应的渠道对象
                channel = self.config_loader.get_channel_by_id(channel_id)
                if channel and channel.enabled:
                    memory_candidates.append(ChannelCandidate(
                        channel=channel, matched_model=model_name
                    ))
                    logger.debug(f"FOUND: {channel.name} -> {model_name}")

            logger.info(f"🎯 MEMORY INDEX RESULT: {len(memory_candidates)} enabled channels found")
            return memory_candidates

        except Exception as e:
            logger.warning(f"⚠️ MEMORY INDEX FAILED: {e}, falling back to legacy file-based search")
            # 继续使用原有的文件搜索逻辑作为后备

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

        logger.warning(f"NO MATCH: No channels found matching positive: {normalized_positive}, excluding: {normalized_negative}")
        return []

    def _get_candidate_channels_by_complete_segment(self, complete_segments: list[str]) -> list[ChannelCandidate]:
        """根据完整子段（不拆分）获取候选渠道

        Args:
            complete_segments: 完整子段标签列表（例如：["qwen3-30b-a3b"]）
        """
        if not complete_segments:
            return []

        # 标准化输入
        normalized_segments = [segment.lower().strip() for segment in complete_segments if segment and isinstance(segment, str)]

        logger.info(f"COMPLETE SEGMENT MATCHING: Searching for exact segments: {normalized_segments}")

        model_cache = self.config_loader.get_model_cache()
        if not model_cache:
            logger.warning("COMPLETE SEGMENT MATCHING: Model cache is empty")
            return []

        candidates = []

        # 遍历所有缓存的渠道
        for channel_id, discovery_data in model_cache.items():
            if not isinstance(discovery_data, dict):
                continue

            # 处理API Key级别的缓存格式
            real_channel_id = channel_id
            if '_' in channel_id:
                # 尝试去掉 API key hash 后缀
                parts = channel_id.split('_')
                if len(parts) >= 2:
                    # 检查最后一部分是否为 hash 格式（长度为8的十六进制字符串）
                    potential_hash = parts[-1]
                    if len(potential_hash) == 8 and all(c in '0123456789abcdef' for c in potential_hash.lower()):
                        real_channel_id = '_'.join(parts[:-1])

            # 查找渠道对象
            channel = self.config_loader.get_channel_by_id(real_channel_id)
            if not channel or not channel.enabled:
                continue

            # 检查渠道中的模型
            models = discovery_data.get("models", [])
            models_data = discovery_data.get("models_data", {})

            for model_name in models:
                # 为每个模型提取完整子段标签
                model_tags = self._extract_tags_from_model_name(model_name)

                # 检查是否包含我们要查找的完整子段
                for segment in normalized_segments:
                    if segment in [tag.lower() for tag in model_tags]:
                        logger.debug(f"COMPLETE SEGMENT MATCH: Found '{segment}' in model '{model_name}' from channel '{channel.name}'")

                        # 获取真实的模型ID
                        real_model_id = model_name
                        if models_data and model_name in models_data:
                            model_info = models_data[model_name]
                            real_model_id = model_info.get("id", model_name)

                        candidates.append(ChannelCandidate(
                            channel=channel,
                            matched_model=real_model_id
                        ))
                        break  # 找到一个匹配就够了，避免重复添加同一个模型

        logger.info(f"COMPLETE SEGMENT MATCHING: Found {len(candidates)} candidates for segments {normalized_segments}")
        return candidates

    def _find_channels_with_all_tags(self, tags: list[str], model_cache: dict) -> list[ChannelCandidate]:
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

            logger.debug(f"TAG MATCHING: Checking channel {channel.id} ({channel.name}) with {len(models)} models")

            # 统一的标签合并匹配：渠道标签 + 模型标签
            channel_tags = getattr(channel, 'tags', []) or []
            channel_matches = 0

            for model_name in models:
                if not model_name:
                    continue

                # 从模型名称提取标签（包括别名标签）
                model_tags = self._extract_tags_with_aliases(model_name, channel)

                # 合并渠道标签和模型标签，并规范化为小写
                combined_tags = list(set([tag.lower() for tag in channel_tags] + [tag.lower() for tag in model_tags]))

                # 验证所有查询标签都在合并后的标签中（case-insensitive匹配）
                normalized_query_tags = [tag.lower() for tag in tags]
                if all(tag in combined_tags for tag in normalized_query_tags):
                    # 🔥 严格验证 free 标签 - 确保渠道真的免费
                    if has_free_tag:
                        free_score = self._calculate_free_score(channel, model_name)
                        # 只有真正免费的渠道才会被匹配 (free_score >= 0.9)
                        if free_score < 0.9:
                            logger.debug(f"FREE TAG VALIDATION FAILED: Channel '{channel.name}' model '{model_name}' has free_score={free_score:.2f} < 0.9, not truly free")
                            continue
                        else:
                            logger.debug(f"FREE TAG VALIDATED: Channel '{channel.name}' model '{model_name}' confirmed as truly free (score={free_score:.2f})")

                    # 过滤掉不适合chat的模型类型
                    if self._is_suitable_for_chat(model_name):
                        candidate_channels.append(ChannelCandidate(
                            channel=channel,
                            matched_model=model_name
                        ))
                        matched_models.append(model_name)
                        channel_matches += 1
                        logger.debug(f"MERGED TAG MATCH: Channel '{channel.name}' model '{model_name}' -> tags: {combined_tags}")
                    else:
                        logger.debug(f"⚠️ FILTERED: Model '{model_name}' not suitable for chat (appears to be embedding/vision model)")

            if channel_matches > 0:
                logger.info(f"🎯 CHANNEL SUMMARY: Found {channel_matches} matching models in channel '{channel.name}' via merged channel+model tags")

        if matched_models:
            logger.info(f"🎯 TOTAL MATCHED MODELS: {len(matched_models)} models found: {matched_models[:5]}{'...' if len(matched_models) > 5 else ''}")

        return candidate_channels

    def _find_channels_with_positive_negative_tags(self, positive_tags: list[str], negative_tags: list[str], model_cache: dict) -> list[ChannelCandidate]:
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

            logger.debug(f"POSITIVE/NEGATIVE TAG MATCHING: Checking channel {channel.id} ({channel.name}) with {len(models)} models")

            # 统一的标签合并匹配：渠道标签 + 模型标签
            channel_tags = getattr(channel, 'tags', []) or []
            channel_matches = 0

            for model_name in models:
                if not model_name:
                    continue

                # 从模型名称提取标签（包括别名标签）
                model_tags = self._extract_tags_with_aliases(model_name, channel)

                # 合并渠道标签和模型标签，并规范化为小写
                combined_tags = list(set([tag.lower() for tag in channel_tags] + [tag.lower() for tag in model_tags]))

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
                        logger.debug(f"POSITIVE/NEGATIVE TAG MATCH: Channel '{channel.name}' model '{model_name}' -> tags: {combined_tags}")
                    else:
                        logger.debug(f"⚠️ FILTERED: Model '{model_name}' not suitable for chat (appears to be embedding/vision model)")
                else:
                    if not positive_match:
                        logger.debug(f"POSITIVE MISMATCH: Model '{model_name}' missing required tags from {positive_tags}")
                    if not negative_match:
                        logger.debug(f"NEGATIVE MISMATCH: Model '{model_name}' contains excluded tags from {negative_tags}")

            if channel_matches > 0:
                logger.info(f"🎯 CHANNEL SUMMARY: Found {channel_matches} matching models in channel '{channel.name}' via positive/negative tag filtering")

        if matched_models:
            logger.info(f"🎯 TOTAL MATCHED MODELS: {len(matched_models)} models found: {matched_models[:5]}{'...' if len(matched_models) > 5 else ''}")

        return candidate_channels

    def get_available_models(self) -> list[str]:
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
            for _channel_id, cache_info in model_cache.items():
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
        result = sorted(models | all_tags)
        self._available_models_cache = result
        return result

    def get_all_available_tags(self) -> list[str]:
        """获取所有可用的标签（不带tag:前缀）"""
        models = self.get_available_models()
        tags = [model[4:] for model in models if model.startswith("tag:")]
        return sorted(tags)

    async def _filter_by_capabilities(self, channels: list[ChannelCandidate], request: RoutingRequest) -> list[ChannelCandidate]:
        """基于模型能力过滤渠道"""
        if not hasattr(request, 'data') or not request.data:
            # 没有请求数据，跳过能力检测
            return channels

        # 分析请求需要的能力
        capability_requirements = self.capability_mapper.get_capability_requirements(request.data)

        # 如果请求不需要特殊能力，跳过检测
        if not any(capability_requirements.values()):
            logger.debug("Request doesn't require special capabilities, skipping capability check")
            return channels

        logger.info(f"CAPABILITY REQUIREMENTS: {capability_requirements}")

        capability_filtered = []
        fallback_channels = []

        for candidate in channels:
            channel = candidate.channel
            model_name = candidate.matched_model or channel.model_name

            try:
                # 检测模型能力
                capabilities = await self.capability_detector.detect_model_capabilities(
                    model_name=model_name,
                    provider=channel.provider,
                    base_url=channel.base_url or "",
                    api_key=channel.api_key
                )

                # 检查是否能处理当前请求
                can_handle = self.capability_detector.can_handle_request(capabilities, request.data)

                if can_handle:
                    capability_filtered.append(candidate)
                    logger.debug(f"CAPABILITY MATCH: {channel.name} can handle request")
                else:
                    # 如果是本地模型不支持，记录为备用选项
                    if capabilities.is_local:
                        fallback_channels.append((candidate, capabilities))
                        logger.debug(f"⚠️ LOCAL LIMITATION: {channel.name} lacks required capabilities, marked for fallback")
                    else:
                        logger.debug(f"CAPABILITY MISMATCH: {channel.name} cannot handle request")

            except Exception as e:
                logger.warning(f"Error checking capabilities for {channel.name}: {e}")
                # 检测失败时，保留渠道（保守策略）
                capability_filtered.append(candidate)

        # 如果没有合适的渠道且有本地模型无法处理，尝试添加云端备用渠道
        if not capability_filtered and fallback_channels:
            logger.info("FALLBACK SEARCH: Looking for cloud alternatives for local model limitations...")

            # 获取所有可用渠道进行备用搜索
            all_channels = []
            for provider_config in self.config.providers:
                for channel_config in provider_config.channels:
                    if channel_config.enabled:
                        all_channels.append({
                            "id": channel_config.id,
                            "name": channel_config.name,
                            "provider": provider_config.name,
                            "model_name": channel_config.model_name,
                            "base_url": channel_config.base_url or provider_config.base_url,
                            "api_key": channel_config.api_key,
                            "priority": getattr(channel_config, 'priority', 1)
                        })

            # 对每个失败的本地模型，寻找备用渠道
            for failed_candidate, _failed_capabilities in fallback_channels[:1]:  # 只为第一个失败的本地模型寻找备用
                fallback_candidates = await self.capability_detector.get_fallback_channels(
                    original_channel=failed_candidate.channel.id,
                    request_data=request.data,
                    available_channels=all_channels
                )

                if fallback_candidates:
                    logger.info(f"FOUND FALLBACK: {len(fallback_candidates)} alternative channels for {failed_candidate.channel.name}")

                    # 将前3个备用渠道转换为ChannelCandidate
                    for fallback_channel_config in fallback_candidates[:3]:
                        # 创建Channel对象
                        fallback_channel = Channel(
                            id=fallback_channel_config["id"],
                            name=fallback_channel_config["name"],
                            provider=fallback_channel_config["provider"],
                            model_name=fallback_channel_config["model_name"],
                            api_key=fallback_channel_config["api_key"],
                            base_url=fallback_channel_config["base_url"],
                            enabled=True,
                            priority=fallback_channel_config.get("priority", 1)
                        )

                        fallback_candidate = ChannelCandidate(
                            channel=fallback_channel,
                            matched_model=fallback_channel_config["model_name"]
                        )

                        capability_filtered.append(fallback_candidate)
                    break  # 只为第一个失败的渠道寻找备用

        return capability_filtered

    async def _pre_filter_channels(self, channels: list[ChannelCandidate], request: RoutingRequest, max_channels: int = 20) -> list[ChannelCandidate]:
        """
        性能优化：使用快速启发式方法预筛选渠道，减少详细评分的开销

        Args:
            channels: 候选渠道列表
            request: 路由请求
            max_channels: 最大保留渠道数量

        Returns:
            预筛选后的渠道列表
        """
        if len(channels) <= max_channels:
            return channels

        logger.info(f"PRE-FILTER: Fast pre-filtering {len(channels)} channels to top {max_channels}")

        # 使用快速启发式评分
        channel_scores = []
        for candidate in channels:
            channel = candidate.channel

            # 快速评分因子（避免复杂计算）
            score = 0.0

            # 1. 免费优先（最重要）
            if self._is_free_channel(channel, candidate.matched_model):
                score += 1000  # 免费渠道获得最高优先级

            # 2. 可靠性评分（基于简单指标）
            if hasattr(channel, 'priority') and channel.priority:
                score += (10 - channel.priority) * 10  # 优先级越高分数越高

            # 3. 本地模型优先
            if self._is_local_channel(channel):
                score += 100

            # 4. 健康状态
            if getattr(channel, 'enabled', True):
                score += 50

            # 5. 随机因子（避免总是选择相同渠道）
            score += random.uniform(0, 10)

            channel_scores.append((score, candidate))

        # 按评分排序并选择top N
        channel_scores.sort(key=lambda x: x[0], reverse=True)
        selected = [candidate for score, candidate in channel_scores[:max_channels]]

        # 记录预筛选结果
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("PRE-FILTER RESULTS:")
            for i, (score, candidate) in enumerate(channel_scores[:max_channels]):
                logger.debug(f"  #{i+1}: {candidate.channel.name} (score: {score:.1f})")

        logger.info(f"PRE-FILTER COMPLETE: Selected {len(selected)}/{len(channels)} channels for detailed scoring")
        return selected

    def _is_free_channel(self, channel: Channel, model_name: str) -> bool:
        """快速判断是否为免费渠道"""
        # 简单的免费判断规则
        if hasattr(channel, 'cost') and channel.cost == 0:
            return True
        if model_name and 'free' in model_name.lower():
            return True
        if hasattr(channel, 'name') and 'free' in channel.name.lower():
            return True
        return False

    def _is_local_channel(self, channel: Channel) -> bool:
        """快速判断是否为本地渠道"""
        if hasattr(channel, 'base_url') and channel.base_url:
            url = channel.base_url.lower()
            return any(local_indicator in url for local_indicator in [
                'localhost', '127.0.0.1', ':11434', ':1234', 'ollama', 'lmstudio'
            ])
        return False

    def clear_cache(self):
        """清除所有缓存"""
        self._tag_cache.clear()
        self._available_tags_cache = None
        self._available_models_cache = None
        logger.info("Router cache cleared")

    def update_channel_health(self, channel_id: str, success: bool, latency: Optional[float] = None):
        """更新渠道健康状态"""
        self.config_loader.update_channel_health(channel_id, success, latency)

    def _log_performance_metrics(self, channel_count: int, elapsed_ms: float,
                                scoring_type: str, metrics=None):
        """记录性能指标和慢查询检测"""
        avg_time_per_channel = elapsed_ms / max(channel_count, 1)

        # 慢查询检测阈值
        slow_threshold_ms = 1000  # 1秒
        very_slow_threshold_ms = 2000  # 2秒

        if elapsed_ms > very_slow_threshold_ms:
            logger.warning(f"🐌 VERY SLOW SCORING: {channel_count} channels took {elapsed_ms:.1f}ms "
                          f"(avg: {avg_time_per_channel:.1f}ms/channel) - Consider optimization")
        elif elapsed_ms > slow_threshold_ms:
            logger.warning(f"⚠️ SLOW SCORING: {channel_count} channels took {elapsed_ms:.1f}ms "
                          f"(avg: {avg_time_per_channel:.1f}ms/channel)")
        else:
            logger.info(f"SCORING PERFORMANCE: {channel_count} channels in {elapsed_ms:.1f}ms "
                       f"(avg: {avg_time_per_channel:.1f}ms/channel)")

        # 如果是批量评分且有性能指标
        if metrics and scoring_type == "batch":
            if metrics.slow_threshold_exceeded:
                logger.warning(f"BATCH SCORER ANALYSIS: {metrics.optimization_applied}")

            if metrics.cache_hit:
                logger.info("💾 CACHE HIT: Scoring completed with cached results")

        # 优化建议
        if channel_count > 50 and elapsed_ms > 1500:
            logger.info(f"💡 OPTIMIZATION TIP: Consider implementing channel pre-filtering for {channel_count}+ channels")
        elif channel_count > 20 and elapsed_ms > 800:
            logger.info("💡 OPTIMIZATION TIP: Performance could benefit from caching strategies")

# 全局路由器实例
_router: Optional[JSONRouter] = None

def get_router() -> JSONRouter:
    """获取全局路由器实例"""
    global _router
    if _router is None:
        _router = JSONRouter()
    return _router
