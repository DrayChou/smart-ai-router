"""
内存索引系统 - 消除文件I/O性能瓶颈
构建高性能的标签→模型映射索引
"""

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """模型信息"""

    channel_id: str
    model_name: str
    provider: str
    tags: set[str]
    pricing: Optional[dict] = None
    capabilities: Optional[dict] = None
    specs: Optional[dict] = None  # 模型规格信息（参数量、上下文长度等）
    # 健康状态缓存
    health_score: Optional[float] = None
    health_cached_at: Optional[float] = None  # Unix时间戳


@dataclass
class IndexStats:
    """索引统计信息"""

    total_models: int
    total_channels: int
    total_tags: int
    build_time_ms: float
    memory_usage_mb: float


class MemoryModelIndex:
    """内存模型索引 - 高性能标签查询"""

    def __init__(self):
        self._lock = threading.RLock()

        # 核心索引结构
        self._tag_to_models: dict[str, set[tuple[str, str]]] = defaultdict(
            set
        )  # tag -> {(channel_id, model_name)}
        self._channel_to_models: dict[str, set[str]] = defaultdict(
            set
        )  # channel_id -> {model_names}
        self._model_info: dict[tuple[str, str], ModelInfo] = (
            {}
        )  # (channel_id, model_name) -> ModelInfo

        # 性能统计
        self._stats = IndexStats(0, 0, 0, 0.0, 0.0)

        # 智能重建控制
        self._last_build_time = 0.0
        self._last_build_hash = None
        self._min_rebuild_interval = 30  # 最小重建间隔30秒
        self._build_count = 0
        self._incremental_updates_count = 0

        logger.info(
            "🚀 MemoryModelIndex initialized - ready for high-performance tag queries"
        )

    def build_index_from_cache(
        self, model_cache: dict[str, dict], channel_configs: Optional[list[dict]] = None
    ) -> IndexStats:
        """
        从模型缓存构建内存索引，支持智能重建控制

        Args:
            model_cache: 原始模型缓存数据
            channel_configs: 渠道配置信息列表

        Returns:
            索引构建统计信息
        """
        current_time = time.time()

        # 计算缓存数据的哈希值来检测变化
        import hashlib

        cache_str = str(sorted(model_cache.items()))
        cache_hash = hashlib.sha256(cache_str.encode()).hexdigest()

        # 智能重建判断
        if self._should_skip_rebuild(current_time, cache_hash):
            logger.info(
                f"⚡ INDEX SKIP: Using existing index ({self._stats.total_models} models, {self._stats.total_tags} tags)"
            )
            return self._stats

        start_time = time.time()

        with self._lock:
            # 清空现有索引
            self._tag_to_models.clear()
            self._channel_to_models.clear()
            self._model_info.clear()

            # 构建渠道标签映射
            self._channel_tag_map = {}
            if channel_configs:
                logger.info(
                    f"🏷️ CHANNEL TAG MAPPING: Processing {len(channel_configs)} channel configs"
                )
                for channel_config in channel_configs:
                    # 处理不同格式的渠道配置
                    if hasattr(channel_config, "id"):  # Pydantic对象
                        channel_id = channel_config.id
                        tags = getattr(channel_config, "tags", [])
                        logger.debug(f"PYDANTIC CHANNEL: {channel_id} -> {tags}")
                    elif isinstance(channel_config, dict):  # 字典格式
                        channel_id = channel_config.get("id")
                        tags = channel_config.get("tags", [])
                        logger.debug(f"DICT CHANNEL: {channel_id} -> {tags}")
                    else:
                        logger.debug(f"UNKNOWN CHANNEL TYPE: {type(channel_config)}")
                        continue

                    if channel_id and tags:
                        self._channel_tag_map[channel_id] = set(tags)
                        logger.info(f"✅ CHANNEL TAGS MAPPED: {channel_id} -> {tags}")
                    elif channel_id:
                        # 🚀 自动推断渠道标签（基于渠道名称）
                        inferred_tags = self._infer_channel_tags(channel_id)
                        if inferred_tags:
                            self._channel_tag_map[channel_id] = inferred_tags
                            logger.info(
                                f"🏷️ INFERRED CHANNEL TAGS: {channel_id} -> {inferred_tags}"
                            )
                        else:
                            logger.warning(
                                f"⚠️ CHANNEL NO TAGS: {channel_id} has no tags"
                            )

                logger.info(
                    f"🏷️ CHANNEL TAG MAP BUILT: {len(self._channel_tag_map)} channels with tags"
                )
            else:
                logger.warning("⚠️ NO CHANNEL CONFIGS PROVIDED for tag mapping")

            logger.info(
                f"🔨 INDEX BUILD: Processing {len(model_cache)} cache entries..."
            )

            total_models = 0
            processed_channels = set()

            # 🚀 多Provider免费策略：收集所有模型的定价信息
            global_model_pricing = (
                {}
            )  # {model_name: [{'provider': provider, 'is_free': bool, 'channel_id': str}]}

            for cache_key, cache_data in model_cache.items():
                if not isinstance(cache_data, dict):
                    continue

                # 提取渠道ID（处理API Key级别的缓存键）
                channel_id = self._extract_channel_id(cache_key)
                if not channel_id:
                    continue

                processed_channels.add(channel_id)

                # 处理模型列表
                models = cache_data.get("models", [])
                models_data = cache_data.get("models_data", {})  # 模型详细规格数据
                models_pricing = cache_data.get(
                    "models_pricing", {}
                )  # 🚀 新增：模型定价数据
                provider = cache_data.get("provider", "unknown")

                # 🚀 收集定价信息用于多Provider免费策略
                for model_name in models:
                    if model_name not in global_model_pricing:
                        global_model_pricing[model_name] = []

                    # 添加此Provider/Channel的定价信息
                    pricing_info = models_pricing.get(model_name, {})
                    is_free = pricing_info.get("is_free", False)

                    global_model_pricing[model_name].append(
                        {
                            "provider": provider,
                            "channel_id": channel_id,
                            "is_free": is_free,
                            "pricing": pricing_info,
                        }
                    )

                for model_name in models:
                    if not isinstance(model_name, str):
                        continue

                    # 生成基础标签
                    tags = self._generate_model_tags(model_name, provider)

                    # 🚀 多Provider免费策略：检查是否有任何Provider提供免费
                    if model_name in global_model_pricing:
                        provider_infos = global_model_pricing[model_name]
                        has_free_provider = any(
                            info.get("is_free", False) for info in provider_infos
                        )

                        if has_free_provider:
                            tags.add("free")
                            logger.debug(
                                f"🆓 模型 {model_name} 标记为免费 (跨Provider检测)"
                            )

                    # 🚀 动态价格检测：检查当前渠道的定价信息
                    if model_name in models_pricing:
                        pricing_info = models_pricing[model_name]
                        is_free_by_pricing = pricing_info.get("is_free", False)
                        prompt_price = pricing_info.get("prompt", 0)
                        completion_price = pricing_info.get("completion", 0)

                        # 如果当前渠道价格为0，添加临时free标签
                        if is_free_by_pricing or (
                            prompt_price == 0 and completion_price == 0
                        ):
                            tags.add("free")
                            logger.debug(
                                f"🆓 模型 {model_name} 标记为免费 (当前渠道 {channel_id} 定价为0)"
                            )

                    # 🚀 渠道级别价格检测：检查渠道配置的cost_per_token
                    try:
                        channel_cost = cache_data.get("cost_per_token", {})
                        if isinstance(channel_cost, dict):
                            input_cost = channel_cost.get("input", 0)
                            output_cost = channel_cost.get("output", 0)
                            if input_cost == 0 and output_cost == 0:
                                tags.add("free")
                                logger.debug(
                                    f"🆓 模型 {model_name} 标记为免费 (渠道 {channel_id} 配置cost_per_token为0)"
                                )
                    except Exception as e:
                        logger.debug(f"渠道价格检测失败 {channel_id}: {e}")

                    # 🚀 合并渠道级别的标签
                    channel_tags = self._get_channel_tags(channel_id)
                    if channel_tags:
                        tags = tags.union(channel_tags)

                    # 🏷️ 添加渠道商标签 (提取渠道ID的第一部分作为渠道商标签)
                    provider_tag = self._extract_provider_tag(channel_id)
                    if provider_tag:
                        tags.add(provider_tag)

                    # 获取模型详细规格
                    model_specs = models_data.get(model_name, {}) if models_data else {}

                    # 🚀 确保包含关键规格信息
                    if not model_specs:
                        # 尝试从其他位置获取规格信息
                        model_specs = self._ensure_model_specs(model_name, cache_data)

                    # 创建模型信息
                    model_key = (channel_id, model_name)
                    model_info = ModelInfo(
                        channel_id=channel_id,
                        model_name=model_name,
                        provider=provider,
                        tags=tags,
                        pricing=cache_data.get("models_pricing", {}).get(model_name),
                        capabilities=self._extract_capabilities(cache_data, model_name),
                    )

                    # 添加模型规格到ModelInfo（扩展用于健康检查优化）
                    if model_specs:
                        model_info.specs = model_specs
                    else:
                        # 即使没有详细规格，也确保包含基本分析结果
                        model_info.specs = self._get_basic_model_specs(model_name)

                    # 更新索引
                    self._model_info[model_key] = model_info
                    self._channel_to_models[channel_id].add(model_name)

                    # 更新标签索引
                    for tag in tags:
                        self._tag_to_models[tag].add(model_key)

                    total_models += 1

            # 构建统计信息
            build_time_ms = (time.time() - start_time) * 1000
            self._stats = IndexStats(
                total_models=total_models,
                total_channels=len(processed_channels),
                total_tags=len(self._tag_to_models),
                build_time_ms=build_time_ms,
                memory_usage_mb=self._estimate_memory_usage(),
            )

            self._last_build_time = current_time
            self._last_build_hash = cache_hash
            self._build_count += 1

            # 🚀 统计多Provider免费策略的效果
            free_models_count = len(self._tag_to_models.get("free", set()))
            multi_provider_free = 0

            for _model_name, provider_infos in global_model_pricing.items():
                if len(provider_infos) > 1:  # 多Provider
                    has_free = any(
                        info.get("is_free", False) for info in provider_infos
                    )
                    if has_free:
                        multi_provider_free += 1

            logger.info(
                f"✅ INDEX BUILT: {total_models} models, {len(processed_channels)} channels, "
                f"{len(self._tag_to_models)} tags in {build_time_ms:.1f}ms"
            )
            logger.info(
                f"🆓 FREE MODELS: {free_models_count} models tagged as free, {multi_provider_free} from multi-provider analysis"
            )

            return self._stats

    def find_models_by_tags(
        self, include_tags: list[str], exclude_tags: list[str] = None
    ) -> list[tuple[str, str]]:
        """
        根据标签查找模型（超高速）

        Args:
            include_tags: 必须包含的标签
            exclude_tags: 必须排除的标签

        Returns:
            匹配的模型列表 [(channel_id, model_name), ...]
        """
        if not include_tags:
            return []

        with self._lock:
            # 开始从最小的标签集合进行交集运算
            tag_sets = [self._tag_to_models.get(tag, set()) for tag in include_tags]
            if not all(tag_sets):
                return []  # 如果任何标签都没有匹配，直接返回空

            # 找到最小的集合作为起点（性能优化）
            result_set = min(tag_sets, key=len)

            # 计算交集
            for tag_set in tag_sets:
                if tag_set is not result_set:  # 避免自己和自己求交集
                    result_set = result_set.intersection(tag_set)
                    if not result_set:  # 如果交集为空，提前退出
                        break

            # 排除不需要的标签
            if exclude_tags and result_set:
                exclude_set = set()
                for tag in exclude_tags:
                    exclude_set.update(self._tag_to_models.get(tag, set()))
                result_set = result_set - exclude_set

            return list(result_set)

    def get_model_info(self, channel_id: str, model_name: str) -> Optional[ModelInfo]:
        """获取模型详细信息"""
        with self._lock:
            return self._model_info.get((channel_id, model_name))

    def get_model_specs(self, channel_id: str, model_name: str) -> Optional[dict]:
        """获取模型规格（优化版，替代文件I/O）"""
        with self._lock:
            model_info = self._model_info.get((channel_id, model_name))
            return model_info.specs if model_info else None

    def get_channel_models(self, channel_id: str) -> set[str]:
        """获取渠道下的所有模型"""
        with self._lock:
            return self._channel_to_models.get(channel_id, set()).copy()

    def get_health_score(
        self, channel_id: str, cache_ttl: float = 60.0
    ) -> Optional[float]:
        """获取健康评分（带缓存TTL检查）"""
        current_time = time.time()

        with self._lock:
            # 查找该渠道下的任意模型来获取健康状态
            models = self._channel_to_models.get(channel_id, set())
            if not models:
                return None

            # 使用第一个模型的健康状态（渠道级别）
            first_model = next(iter(models))
            model_info = self._model_info.get((channel_id, first_model))

            if (
                model_info
                and model_info.health_score is not None
                and model_info.health_cached_at is not None
                and (current_time - model_info.health_cached_at) < cache_ttl
            ):
                return model_info.health_score

            return None

    def set_health_score(self, channel_id: str, health_score: float):
        """设置健康评分（更新所有该渠道下的模型）"""
        current_time = time.time()

        with self._lock:
            models = self._channel_to_models.get(channel_id, set())
            for model_name in models:
                model_info = self._model_info.get((channel_id, model_name))
                if model_info:
                    model_info.health_score = health_score
                    model_info.health_cached_at = current_time

    def get_tag_stats(self) -> dict[str, int]:
        """获取标签统计信息"""
        with self._lock:
            return {tag: len(models) for tag, models in self._tag_to_models.items()}

    def get_stats(self) -> IndexStats:
        """获取索引统计信息"""
        with self._lock:
            return self._stats

    def is_stale(self, cache_update_time: float) -> bool:
        """检查索引是否过期"""
        return cache_update_time > self._last_build_time

    def needs_rebuild(self, model_cache: dict[str, dict]) -> bool:
        """检查是否需要重建索引"""
        # 🚀 修复：只有在索引为空时才强制重建
        if self._stats.total_models == 0:
            logger.debug("INDEX REBUILD: Index is empty, needs rebuild")
            return True

        # 🚀 修复：更智能的缓存大小检查
        current_cache_size = len(model_cache)
        cached_channels = self._stats.total_channels

        # 🚀 容忍缓存迁移造成的大小变化（从legacy格式到API Key格式）
        if current_cache_size < cached_channels:
            # 如果缓存减少超过30%，可能是迁移导致的清理，需要重建
            reduction_ratio = current_cache_size / cached_channels
            if reduction_ratio < 0.7:  # 减少超过30%
                logger.debug(
                    f"INDEX REBUILD: Cache size reduced significantly ({current_cache_size} vs {cached_channels})"
                )
                return True
        elif current_cache_size > cached_channels:
            # 🚀 缓存增加了，仅当增加超过50%时才重建（更宽松）
            growth_ratio = current_cache_size / cached_channels
            if growth_ratio > 1.5:  # 增长超过50%才重建
                logger.debug(
                    f"INDEX REBUILD: Cache size increased significantly ({current_cache_size} vs {cached_channels})"
                )
                return True

        # 🚀 更稳定的哈希检查：基于模型总数而非缓存键结构
        try:
            total_models_in_cache = sum(
                len(cache_data.get("models", []))
                for cache_data in model_cache.values()
                if isinstance(cache_data, dict)
            )
            if (
                abs(total_models_in_cache - self._stats.total_models)
                > self._stats.total_models * 0.1
            ):  # 模型数量变化超过10%
                logger.debug(
                    f"INDEX REBUILD: Model count changed significantly ({total_models_in_cache} vs {self._stats.total_models})"
                )
                return True
        except Exception as e:
            logger.debug(f"INDEX REBUILD: Error checking model count: {e}")
            pass

        logger.debug(
            f"INDEX REBUILD: No rebuild needed (cache: {current_cache_size}, indexed: {cached_channels})"
        )
        return False  # 默认不重建

    def _extract_channel_id(self, cache_key: str) -> Optional[str]:
        """从缓存键提取渠道ID"""
        if not cache_key:
            return None

        # 处理API Key级别的缓存键格式: "channel_id_apikeyash"
        if "_" in cache_key:
            parts = cache_key.split("_")
            if len(parts) >= 2:
                # 检查最后一部分是否为hash格式（8位十六进制）
                potential_hash = parts[-1]
                if len(potential_hash) == 8 and all(
                    c in "0123456789abcdef" for c in potential_hash.lower()
                ):
                    return "_".join(parts[:-1])

        # 直接返回作为渠道ID
        return cache_key

    def _generate_model_tags(self, model_name: str, provider: str) -> set[str]:
        """为模型生成标签集合"""
        tags = set()

        if not model_name:
            return tags

        model_lower = model_name.lower()

        # 添加提供商标签
        if provider:
            tags.add(provider.lower())

        # 使用多种分隔符分割模型名称生成标签
        separators = [":", "/", "@", "-", "_", ",", ".", " "]
        tokens = [model_lower]

        for sep in separators:
            new_tokens = []
            for token in tokens:
                new_tokens.extend(token.split(sep))
            tokens = [t.strip() for t in new_tokens if t.strip()]

        # 添加所有有效的token作为标签
        for token in tokens:
            if len(token) >= 2:  # 过滤太短的标签
                tags.add(token)

        # 特殊标签识别
        if any(
            free_indicator in model_lower
            for free_indicator in ["free", "gratis", "免费"]
        ):
            tags.add("free")

        if any(
            vision_indicator in model_lower
            for vision_indicator in ["vision", "visual", "image", "multimodal"]
        ):
            tags.add("vision")

        if any(
            code_indicator in model_lower
            for code_indicator in ["code", "coder", "coding", "program"]
        ):
            tags.add("code")

        return tags

    def _extract_provider_tag(self, channel_id: str) -> Optional[str]:
        """从渠道ID中提取渠道商标签"""
        if not channel_id:
            return None

        # 提取渠道ID的第一部分作为渠道商标签
        # 例如: groq -> groq, openrouter_1 -> openrouter, burn.hair -> burn
        provider_name = channel_id.split(".")[0].lower()

        # 过滤掉一些无意义的标签
        if provider_name and len(provider_name) > 2:
            return provider_name

        return None

    def _get_channel_tags(self, channel_id: str) -> Optional[set[str]]:
        """获取渠道级别的标签"""
        try:
            # 优先使用动态构建的渠道标签映射
            if hasattr(self, "_channel_tag_map") and self._channel_tag_map:
                tags = self._channel_tag_map.get(channel_id)
                if tags:
                    return tags

            # 回退到硬编码映射（兼容性）
            fallback_map = {
                "ollama_local": {"free", "local", "ollama"},
                "lmstudio_local": {"free", "local", "lmstudio"},
            }
            return fallback_map.get(channel_id)
        except Exception as e:
            logger.debug(f"Failed to get channel tags for {channel_id}: {e}")
        return None

    def _extract_capabilities(
        self, cache_data: dict, model_name: str
    ) -> Optional[dict]:
        """提取模型能力信息"""
        capabilities_data = cache_data.get("models_capabilities", {})
        return capabilities_data.get(model_name) if capabilities_data else None

    def _ensure_model_specs(self, model_name: str, cache_data: dict) -> dict:
        """确保模型规格信息存在"""
        specs = {}

        # 尝试从不同位置获取规格信息
        if "models" in cache_data and isinstance(cache_data["models"], dict):
            specs = cache_data["models"].get(model_name, {})

        # 如果仍然没有规格信息，使用模型分析器
        if not specs.get("parameter_count") or not specs.get("context_length"):
            try:
                from core.utils.model_analyzer import get_model_analyzer

                analyzer = get_model_analyzer()
                analyzed_specs = analyzer.analyze_model(model_name)

                # 确保包含关键规格信息
                if analyzed_specs.parameter_count:
                    specs["parameter_count"] = analyzed_specs.parameter_count
                if analyzed_specs.context_length:
                    specs["context_length"] = analyzed_specs.context_length

            except Exception:
                pass

        return specs

    def _get_basic_model_specs(self, model_name: str) -> dict:
        """获取基本模型规格信息（回退方案）"""
        try:
            from core.utils.model_analyzer import get_model_analyzer

            analyzer = get_model_analyzer()
            analyzed_specs = analyzer.analyze_model(model_name)

            return {
                "parameter_count": analyzed_specs.parameter_count,
                "context_length": analyzed_specs.context_length,
            }
        except Exception:
            # 提供默认值
            return {"parameter_count": 0, "context_length": 2048}  # 默认上下文长度

    def _infer_channel_tags(self, channel_id: str) -> set:
        """基于渠道ID自动推断标签"""
        inferred_tags = set()
        channel_lower = channel_id.lower()

        # 基于渠道名称的常见标签推断
        tag_mappings = [
            ("openrouter", {"openrouter", "aggregator", "multi-provider"}),
            ("groq", {"groq", "fast", "inference-engine"}),
            ("ollama", {"ollama", "local", "self-hosted", "free"}),
            ("lmstudio", {"lmstudio", "local", "self-hosted", "free"}),
            ("openai", {"openai", "official", "premium"}),
            ("anthropic", {"anthropic", "official", "premium"}),
            ("free", {"free", "gratis"}),
            ("pro", {"pro", "premium", "paid"}),
            ("turbo", {"turbo", "fast"}),
            ("mini", {"mini", "small", "efficient"}),
            ("max", {"max", "large", "powerful"}),
            ("vision", {"vision", "multimodal", "image"}),
            ("code", {"code", "programming", "developer"}),
        ]

        for keyword, tags in tag_mappings:
            if keyword in channel_lower:
                inferred_tags.update(tags)

        # 添加提供商标签
        provider_tag = self._extract_provider_tag(channel_id)
        if provider_tag:
            inferred_tags.add(provider_tag)

        return inferred_tags

    def _estimate_memory_usage(self) -> float:
        """估算内存使用量（MB）"""
        import sys

        total_size = 0
        total_size += sys.getsizeof(self._tag_to_models)
        total_size += sys.getsizeof(self._channel_to_models)
        total_size += sys.getsizeof(self._model_info)

        # 估算内部数据结构的大小
        for tag_set in self._tag_to_models.values():
            total_size += sys.getsizeof(tag_set)

        for model_set in self._channel_to_models.values():
            total_size += sys.getsizeof(model_set)

        return total_size / 1024 / 1024

    def _should_skip_rebuild(self, current_time: float, cache_hash: str) -> bool:
        """判断是否应该跳过重建"""
        # 如果从未构建过，必须构建
        if self._build_count == 0:
            return False

        # 时间间隔检查：如果距离上次构建时间太短，跳过
        time_since_last_build = current_time - self._last_build_time
        if time_since_last_build < self._min_rebuild_interval:
            logger.debug(
                f"INDEX SKIP: Too soon to rebuild ({time_since_last_build:.1f}s < {self._min_rebuild_interval}s)"
            )
            return True

        # 内容变化检查：如果缓存内容没有变化，跳过
        if self._last_build_hash == cache_hash:
            logger.debug(
                f"INDEX SKIP: Cache content unchanged (hash: {cache_hash[:8]}...)"
            )
            return True

        return False

    def add_incremental_model(
        self, channel_id: str, model_name: str, provider: str = "unknown"
    ):
        """增量添加单个模型（避免全量重建）"""
        with self._lock:
            tags = self._generate_model_tags(model_name, provider)
            model_key = (channel_id, model_name)

            # 创建模型信息
            model_info = ModelInfo(
                channel_id=channel_id,
                model_name=model_name,
                provider=provider,
                tags=tags,
            )

            # 更新索引
            self._model_info[model_key] = model_info
            self._channel_to_models[channel_id].add(model_name)

            # 更新标签索引
            for tag in tags:
                self._tag_to_models[tag].add(model_key)

            self._incremental_updates_count += 1
            logger.debug(
                f"📈 INDEX INCREMENT: Added {model_name} to channel {channel_id}"
            )

    def remove_channel_models(self, channel_id: str):
        """移除某个渠道的所有模型"""
        with self._lock:
            models_to_remove = list(self._channel_to_models.get(channel_id, set()))

            for model_name in models_to_remove:
                model_key = (channel_id, model_name)

                # 从模型信息中移除
                if model_key in self._model_info:
                    model_info = self._model_info[model_key]
                    del self._model_info[model_key]

                    # 从标签索引中移除
                    for tag in model_info.tags:
                        self._tag_to_models[tag].discard(model_key)
                        # 如果标签没有任何模型了，删除标签
                        if not self._tag_to_models[tag]:
                            del self._tag_to_models[tag]

            # 清空渠道模型列表
            if channel_id in self._channel_to_models:
                del self._channel_to_models[channel_id]

            logger.debug(
                f"🗑️ INDEX REMOVE: Removed {len(models_to_remove)} models from channel {channel_id}"
            )

    def get_build_stats(self) -> dict[str, Any]:
        """获取构建统计信息"""
        return {
            "total_builds": self._build_count,
            "last_build_time": self._last_build_time,
            "incremental_updates": self._incremental_updates_count,
            "min_rebuild_interval": self._min_rebuild_interval,
            "models_count": len(self._model_info),
            "channels_count": len(self._channel_to_models),
            "tags_count": len(self._tag_to_models),
        }


# 全局索引实例
_memory_index: Optional[MemoryModelIndex] = None


def get_memory_index() -> MemoryModelIndex:
    """获取全局内存索引实例"""
    global _memory_index
    if _memory_index is None:
        _memory_index = MemoryModelIndex()
    return _memory_index


def reset_memory_index():
    """重置全局内存索引实例（用于修复后的重新构建）"""
    global _memory_index
    _memory_index = None


def rebuild_index_if_needed(
    model_cache: dict[str, dict],
    force_rebuild: bool = False,
    channel_configs: Optional[list[dict]] = None,
) -> IndexStats:
    """按需重建索引"""
    index = get_memory_index()

    # 检查是否需要重建（这里可以基于缓存更新时间等条件）
    if force_rebuild:
        return index.build_index_from_cache(model_cache, channel_configs)

    return index.get_stats()
