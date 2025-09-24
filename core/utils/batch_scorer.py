"""
批量评分器 - 优化模型筛选性能
用于大幅减少单个模型评分时间，从70-80ms降低到10ms以下
"""

import asyncio
import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Optional, cast

from core.json_router import ChannelCandidate

logger = logging.getLogger(__name__)


@dataclass
class BatchedScoreComponents:
    """批量评分结果"""

    cost_scores: dict[str, float]
    speed_scores: dict[str, float]
    quality_scores: dict[str, float]
    reliability_scores: dict[str, float]
    parameter_scores: dict[str, float]
    context_scores: dict[str, float]
    free_scores: dict[str, float]
    local_scores: dict[str, float]
    computation_time_ms: float


@dataclass
class PerformanceMetrics:
    """性能监控指标"""

    channel_count: int
    total_time_ms: float
    avg_time_per_channel: float
    cache_hit: bool
    slow_threshold_exceeded: bool = False
    optimization_applied: str = "none"


class BatchScorer:
    """批量评分器 - 优化模型筛选性能"""

    def __init__(self, router):
        """初始化批量评分器"""
        self.router = router
        self.cache = {}
        self.cache_timeout = 300  # 5分钟缓存
        self.thread_pool = ThreadPoolExecutor(max_workers=4)

        # 性能监控配置
        self.slow_threshold_ms = 1000  # 慢查询阈值：1秒
        self.performance_stats = {
            "total_requests": 0,
            "slow_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_hit_rate": 0.0,
            "optimizations_applied": defaultdict(int),
        }

        # [BOOST] 智能缓存配置
        self.min_cache_timeout = 60  # 1分钟最小缓存
        self.max_cache_timeout = 600  # 10分钟最大缓存
        self.adaptive_cache_timeout = self.cache_timeout  # 初始值

    def _get_cache_key(self, channels: list[ChannelCandidate], request) -> str:
        """生成缓存键（优化版：包含更多请求上下文）"""
        channel_ids = sorted([c.channel.id for c in channels])
        model_name = getattr(request, "model", "unknown")

        # [BOOST] 添加请求上下文信息以提高缓存命中率
        request_context = {
            "model": model_name,
            "channels": channel_ids,
            "timestamp": int(time.time() / 60),  # 每分钟变化一次
        }

        # 使用更稳定的哈希算法
        import hashlib

        key_data = str(request_context).encode("utf-8")
        cache_hash = hashlib.sha256(key_data).hexdigest()[:12]

        return f"batch_score_{cache_hash}"

    def _check_cache(self, cache_key: str) -> Optional[BatchedScoreComponents]:
        """检查缓存（支持自适应超时）"""
        if cache_key in self.cache:
            cached_time, cached_result = self.cache[cache_key]

            # [BOOST] 使用自适应缓存超时
            current_timeout = self.adaptive_cache_timeout
            if (time.time() - cached_time) < current_timeout:
                logger.debug(
                    f"BATCH_SCORER: Cache hit for {cache_key} (timeout: {current_timeout}s)"
                )
                self.performance_stats["cache_hits"] += 1
                return cast(Optional[BatchedScoreComponents], cached_result)
            else:
                # 缓存过期，移除
                del self.cache[cache_key]

        self.performance_stats["cache_misses"] += 1
        return None

    def _store_cache(self, cache_key: str, result: BatchedScoreComponents):
        """存储到缓存（更新统计信息）"""
        self.cache[cache_key] = (time.time(), result)

        # [BOOST] 更新缓存统计和自适应超时
        self._update_cache_statistics()

    def _update_cache_statistics(self):
        """更新缓存统计信息和自适应超时"""
        total = (
            self.performance_stats["cache_hits"]
            + self.performance_stats["cache_misses"]
        )
        if total > 0:
            hit_rate = self.performance_stats["cache_hits"] / total
            self.performance_stats["cache_hit_rate"] = hit_rate

            # [BOOST] 自适应调整缓存超时：命中率高则延长超时
            if hit_rate > 0.7:  # 命中率超过70%
                self.adaptive_cache_timeout = min(
                    self.max_cache_timeout, self.adaptive_cache_timeout * 1.2
                )
            elif hit_rate < 0.3:  # 命中率低于30%
                self.adaptive_cache_timeout = max(
                    self.min_cache_timeout, self.adaptive_cache_timeout * 0.8
                )

            logger.debug(
                f"CACHE STATS: Hit rate {hit_rate:.1%}, timeout: {self.adaptive_cache_timeout}s"
            )

    def _batch_get_model_specs(
        self, channels: list[ChannelCandidate]
    ) -> dict[str, dict[str, Any]]:
        """批量获取模型规格信息（内存索引优化版）"""
        model_specs = {}

        # [BOOST] 性能优化：优先使用内存索引，避免文件I/O
        try:
            from core.utils.memory_index import get_memory_index

            memory_index = get_memory_index()

            for candidate in channels:
                if candidate.matched_model:
                    key = f"{candidate.channel.id}_{candidate.matched_model}"

                    # 首先尝试从内存索引获取
                    specs = memory_index.get_model_specs(
                        candidate.channel.id, candidate.matched_model
                    )
                    if specs:
                        model_specs[key] = specs
                        continue

                    # 回退到文件缓存
                    try:
                        channel_cache = self.router.cache_manager.load_channel_models(
                            candidate.channel.id
                        )
                        if channel_cache and "models" in channel_cache:
                            cached_spec = channel_cache["models"].get(
                                candidate.matched_model
                            )
                            if cached_spec:
                                model_specs[key] = cached_spec
                                continue
                    except Exception:
                        pass

                    # 最后使用分析器
                    try:
                        analyzed_specs = self.router.model_analyzer.analyze_model(
                            candidate.matched_model
                        )
                        model_specs[key] = {
                            "parameter_count": analyzed_specs.parameter_count,
                            "context_length": analyzed_specs.context_length,
                        }
                    except (AttributeError, ValueError):
                        model_specs[key] = {"parameter_count": 0, "context_length": 0}

        except Exception as e:
            logger.warning(
                f"BATCH_SCORER: Memory index lookup failed, falling back to file cache: {e}"
            )
            # 回退到原始文件缓存方法
            specs_by_channel = defaultdict(list)
            for candidate in channels:
                if candidate.matched_model:
                    specs_by_channel[candidate.channel.id].append(
                        candidate.matched_model
                    )

            for channel_id, models in specs_by_channel.items():
                try:
                    channel_cache = self.router.cache_manager.load_channel_models(
                        channel_id
                    )
                    if channel_cache and "models" in channel_cache:
                        for model_name in models:
                            key = f"{channel_id}_{model_name}"
                            cached_spec = channel_cache["models"].get(model_name)
                            if cached_spec:
                                model_specs[key] = cached_spec
                            else:
                                analyzed_specs = (
                                    self.router.model_analyzer.analyze_model(model_name)
                                )
                                model_specs[key] = {
                                    "parameter_count": analyzed_specs.parameter_count,
                                    "context_length": analyzed_specs.context_length,
                                }
                except Exception as e2:
                    logger.debug(
                        f"BATCH_SCORER: Failed to load specs for channel {channel_id}: {e2}"
                    )
                    for model_name in models:
                        key = f"{channel_id}_{model_name}"
                        try:
                            analyzed_specs = self.router.model_analyzer.analyze_model(
                                model_name
                            )
                            model_specs[key] = {
                                "parameter_count": analyzed_specs.parameter_count,
                                "context_length": analyzed_specs.context_length,
                            }
                        except (AttributeError, ValueError):
                            model_specs[key] = {
                                "parameter_count": 0,
                                "context_length": 0,
                            }

        return model_specs

    def _batch_calculate_parameter_scores(
        self, channels: list[ChannelCandidate], model_specs: dict[str, dict[str, Any]]
    ) -> dict[str, float]:
        """批量计算参数数量评分"""
        parameter_scores = {}

        for candidate in channels:
            channel_id = candidate.channel.id
            model_name = candidate.matched_model
            key = f"{channel_id}_{model_name}" if model_name else channel_id

            if model_name:
                spec_key = f"{channel_id}_{model_name}"
                specs = model_specs.get(spec_key, {})
                param_count = specs.get("parameter_count", 0)
            else:
                param_count = 0

            # 确保param_count不为None
            if param_count is None:
                param_count = 0

            # 参数数量评分逻辑
            if param_count >= 70000:  # 70B+
                score = 1.0
            elif param_count >= 30000:  # 30B+
                score = 0.9
            elif param_count >= 8000:  # 8B+
                score = 0.8
            elif param_count >= 3000:  # 3B+
                score = 0.7
            elif param_count >= 1000:  # 1B+
                score = 0.6
            elif param_count >= 500:  # 500M+
                score = 0.5
            elif param_count >= 100:  # 100M+
                score = 0.4
            else:  # <100M or unknown
                score = 0.3

            parameter_scores[key] = score

        return parameter_scores

    def _batch_calculate_context_scores(
        self, channels: list[ChannelCandidate], model_specs: dict[str, dict[str, Any]]
    ) -> dict[str, float]:
        """批量计算上下文长度评分"""
        context_scores = {}

        for candidate in channels:
            channel_id = candidate.channel.id
            model_name = candidate.matched_model
            key = f"{channel_id}_{model_name}" if model_name else channel_id

            if model_name:
                spec_key = f"{channel_id}_{model_name}"
                specs = model_specs.get(spec_key, {})
                context_length = specs.get("context_length", 0)
            else:
                context_length = 0

            # 确保context_length不为None
            if context_length is None:
                context_length = 0

            # 上下文长度评分逻辑
            if context_length >= 1000000:  # 1M+
                score = 1.0
            elif context_length >= 200000:  # 200k+
                score = 0.9
            elif context_length >= 32000:  # 32k+
                score = 0.8
            elif context_length >= 16000:  # 16k+
                score = 0.7
            elif context_length >= 8000:  # 8k+
                score = 0.6
            elif context_length >= 4000:  # 4k+
                score = 0.5
            else:  # <4k
                score = 0.3

            context_scores[key] = score

        return context_scores

    def _batch_calculate_free_scores(
        self, channels: list[ChannelCandidate], model_specs: dict[str, dict[str, Any]]
    ) -> dict[str, float]:
        """批量计算免费优先评分"""
        free_scores = {}
        free_tags = {"free", "免费", "0cost", "nocost", "trial"}

        for candidate in channels:
            channel = candidate.channel
            model_name = candidate.matched_model
            key = f"{channel.id}_{model_name}" if model_name else channel.id
            score = 0.1  # 默认评分

            # 检查模型级别定价信息
            if model_name:
                spec_key = f"{channel.id}_{model_name}"
                specs = model_specs.get(spec_key, {})
                if "raw_data" in specs and "pricing" in specs["raw_data"]:
                    pricing = specs["raw_data"]["pricing"]
                    prompt_cost = float(pricing.get("prompt", "0"))
                    completion_cost = float(pricing.get("completion", "0"))
                    if prompt_cost == 0.0 and completion_cost == 0.0:
                        score = 1.0
                    else:
                        score = 0.1
                # 检查模型名称中的免费标识
                elif any(
                    tag in model_name.lower() for tag in [":free", "-free", "_free"]
                ):
                    score = 1.0

            # 如果模型级别没有明确证据，检查渠道级别
            if score == 0.1:
                # 检查渠道成本配置
                cost_per_token = getattr(channel, "cost_per_token", None)
                if cost_per_token:
                    input_cost = cost_per_token.get("input", 0.0)
                    output_cost = cost_per_token.get("output", 0.0)
                    if input_cost <= 0.0 and output_cost <= 0.0:
                        score = 1.0
                    elif model_name and any(
                        tag in model_name.lower() for tag in [":free", "-free"]
                    ):
                        score = 1.0
                    else:
                        score = 0.1

                # 检查传统pricing配置
                elif hasattr(channel, "pricing"):
                    pricing = channel.pricing
                    input_cost = pricing.get("input_cost_per_1k", 0.001)
                    output_cost = pricing.get("output_cost_per_1k", 0.002)
                    avg_cost = (input_cost + output_cost) / 2
                    if avg_cost <= 0.0001:
                        score = 0.9
                    elif avg_cost <= 0.001:
                        score = 0.7
                    elif model_name and any(
                        tag in model_name.lower() for tag in [":free", "-free"]
                    ):
                        score = 1.0
                    else:
                        score = 0.1

                # 检查渠道标签
                elif any(
                    tag.lower() in free_tags for tag in getattr(channel, "tags", [])
                ):
                    score = 1.0

            free_scores[key] = score

        return free_scores

    def _batch_calculate_basic_scores(
        self, channels: list[ChannelCandidate], request
    ) -> tuple[
        dict[str, float],
        dict[str, float],
        dict[str, float],
        dict[str, float],
        dict[str, float],
    ]:
        """批量计算基础评分（成本、速度、质量、可靠性、本地）"""
        cost_scores = {}
        speed_scores = {}
        quality_scores = {}
        reliability_scores = {}
        local_scores = {}

        # [BOOST] 批量获取运行时状态 - 优化健康评分获取
        runtime_state = self.router.config_loader.runtime_state
        channel_stats = runtime_state.channel_stats

        # [BOOST] 优化：优先使用内存索引的健康缓存，减少实时计算
        health_scores_dict = {}
        health_cache_hits = 0
        health_cache_misses = 0

        try:
            from core.utils.memory_index import get_memory_index

            memory_index = get_memory_index()
            for candidate in channels:
                cached_health = memory_index.get_health_score(
                    candidate.channel.id, cache_ttl=600.0
                )  # 10分钟TTL
                if cached_health is not None:
                    health_scores_dict[candidate.channel.id] = cached_health
                    health_cache_hits += 1
                else:
                    # 回退到运行时状态
                    health_scores_dict[candidate.channel.id] = (
                        runtime_state.health_scores.get(candidate.channel.id, 1.0)
                    )
                    health_cache_misses += 1

            if health_cache_hits + health_cache_misses > 0:
                hit_rate = (
                    health_cache_hits / (health_cache_hits + health_cache_misses) * 100
                )
                logger.debug(
                    f"🏥 HEALTH CACHE: {health_cache_hits}/{health_cache_hits + health_cache_misses} hits ({hit_rate:.1f}%)"
                )

        except Exception as e:
            # 如果内存索引失败，使用运行时状态
            logger.warning(
                f"🏥 HEALTH CACHE: Failed to access memory index, using runtime state: {e}"
            )
            health_scores_dict = runtime_state.health_scores

        local_tags = {"local", "本地", "localhost", "127.0.0.1", "offline", "edge"}

        for candidate in channels:
            channel = candidate.channel
            model_name = candidate.matched_model
            key = f"{channel.id}_{model_name}" if model_name else channel.id

            # 成本评分
            cost_scores[key] = self.router._calculate_cost_score(channel, request)

            # 速度评分 - 优化版本
            stats = channel_stats.get(channel.id)
            if stats and "avg_latency_ms" in stats:
                avg_latency = stats["avg_latency_ms"]
                base_latency = 2000.0
                score = max(0.0, 1.0 - (avg_latency / base_latency))
                speed_scores[key] = 0.1 + score * 0.9
            else:
                speed_scores[key] = channel.performance.get("speed_score", 0.8)

            # 质量评分 - 直接计算
            quality_scores[key] = self.router._calculate_quality_score(
                channel, model_name
            )

            # 可靠性评分
            reliability_scores[key] = health_scores_dict.get(channel.id, 1.0)

            # 本地评分
            score = 0.1
            channel_tags_lower = [tag.lower() for tag in channel.tags]
            if any(tag in local_tags for tag in channel_tags_lower):
                score = 1.0
            elif model_name:
                model_tags = self.router._extract_tags_from_model_name(model_name)
                model_tags_lower = [tag.lower() for tag in model_tags]
                if any(tag in local_tags for tag in model_tags_lower):
                    score = 1.0

            # 检查base_url
            if score == 0.1:
                base_url = getattr(channel, "base_url", None)
                if base_url:
                    base_url_lower = base_url.lower()
                    local_indicators = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
                    if any(
                        indicator in base_url_lower for indicator in local_indicators
                    ):
                        score = 1.0

            local_scores[key] = score

        return (
            cost_scores,
            speed_scores,
            quality_scores,
            reliability_scores,
            local_scores,
        )

    async def batch_score_channels(
        self, channels: list[ChannelCandidate], request
    ) -> tuple[BatchedScoreComponents, PerformanceMetrics]:
        """批量评分渠道列表，返回评分结果和性能指标"""
        start_time = time.time()
        channel_count = len(channels)
        self.performance_stats["total_requests"] += 1

        # 检查缓存
        cache_key = self._get_cache_key(channels, request)
        cached_result = self._check_cache(cache_key)
        if cached_result:
            elapsed_ms = (time.time() - start_time) * 1000
            self.performance_stats["cache_hits"] += 1
            logger.info(
                f"BATCH_SCORER: Using cached scores for {channel_count} channels ({elapsed_ms:.1f}ms)"
            )

            metrics = PerformanceMetrics(
                channel_count=channel_count,
                total_time_ms=elapsed_ms,
                avg_time_per_channel=elapsed_ms / max(channel_count, 1),
                cache_hit=True,
                optimization_applied="cache_hit",
            )
            return cached_result, metrics

        logger.info(f"BATCH_SCORER: Computing scores for {len(channels)} channels")

        # 批量获取模型规格（最耗时的操作）
        model_specs = self._batch_get_model_specs(channels)

        # 并行计算各种评分
        async def compute_scores():
            # 在线程池中执行计算密集型任务
            loop = asyncio.get_event_loop()

            # 分批并行执行评分计算
            basic_scores_future = loop.run_in_executor(
                self.thread_pool, self._batch_calculate_basic_scores, channels, request
            )

            parameter_scores_future = loop.run_in_executor(
                self.thread_pool,
                self._batch_calculate_parameter_scores,
                channels,
                model_specs,
            )

            context_scores_future = loop.run_in_executor(
                self.thread_pool,
                self._batch_calculate_context_scores,
                channels,
                model_specs,
            )

            free_scores_future = loop.run_in_executor(
                self.thread_pool,
                self._batch_calculate_free_scores,
                channels,
                model_specs,
            )

            # 等待所有计算完成
            basic_scores, parameter_scores, context_scores, free_scores = (
                await asyncio.gather(
                    basic_scores_future,
                    parameter_scores_future,
                    context_scores_future,
                    free_scores_future,
                )
            )

            (
                cost_scores,
                speed_scores,
                quality_scores,
                reliability_scores,
                local_scores,
            ) = basic_scores

            return BatchedScoreComponents(
                cost_scores=cost_scores,
                speed_scores=speed_scores,
                quality_scores=quality_scores,
                reliability_scores=reliability_scores,
                parameter_scores=parameter_scores,
                context_scores=context_scores,
                free_scores=free_scores,
                local_scores=local_scores,
                computation_time_ms=(time.time() - start_time) * 1000,
            )

        result = await compute_scores()

        # 缓存结果
        self._store_cache(cache_key, result)

        # 性能监控和优化建议
        elapsed_ms = (time.time() - start_time) * 1000
        avg_time_per_channel = elapsed_ms / max(channel_count, 1)
        is_slow = elapsed_ms > self.slow_threshold_ms

        if is_slow:
            self.performance_stats["slow_requests"] += 1
            logger.warning(
                f"[WARNING] SLOW BATCH SCORING: {channel_count} channels took {elapsed_ms:.1f}ms (avg: {avg_time_per_channel:.1f}ms/channel)"
            )

        # 应用优化策略
        optimization = self._determine_optimization(channel_count, elapsed_ms)
        if optimization != "none":
            self.performance_stats["optimizations_applied"][optimization] += 1

        logger.info(
            f"BATCH_SCORER: Computed {channel_count} scores in {elapsed_ms:.1f}ms (avg: {avg_time_per_channel:.1f}ms/channel)"
        )

        metrics = PerformanceMetrics(
            channel_count=channel_count,
            total_time_ms=elapsed_ms,
            avg_time_per_channel=avg_time_per_channel,
            cache_hit=False,
            slow_threshold_exceeded=is_slow,
            optimization_applied=optimization,
        )

        return result, metrics

    def get_score_for_channel(
        self, batch_result: BatchedScoreComponents, candidate: ChannelCandidate
    ) -> dict[str, float]:
        """从批量结果中获取特定渠道的评分"""
        channel_id = candidate.channel.id
        model_name = candidate.matched_model
        key = f"{channel_id}_{model_name}" if model_name else channel_id

        return {
            "cost_score": batch_result.cost_scores.get(key, 0.5),
            "speed_score": batch_result.speed_scores.get(key, 0.5),
            "quality_score": batch_result.quality_scores.get(key, 0.5),
            "reliability_score": batch_result.reliability_scores.get(key, 0.5),
            "parameter_score": batch_result.parameter_scores.get(key, 0.5),
            "context_score": batch_result.context_scores.get(key, 0.5),
            "free_score": batch_result.free_scores.get(key, 0.1),
            "local_score": batch_result.local_scores.get(key, 0.1),
        }

    def _determine_optimization(self, channel_count: int, elapsed_ms: float) -> str:
        """确定应用的优化策略"""
        if channel_count > 50 and elapsed_ms > 2000:
            return "large_batch_optimization"
        elif elapsed_ms > 1000:
            return "slow_query_optimization"
        elif channel_count > 20 and elapsed_ms > 500:
            return "medium_batch_optimization"
        return "none"

    def get_performance_stats(self) -> dict[str, Any]:
        """获取性能统计信息"""
        total_requests = self.performance_stats["total_requests"]
        if total_requests == 0:
            return {"message": "No requests processed yet"}

        cache_hit_rate = (self.performance_stats["cache_hits"] / total_requests) * 100
        slow_request_rate = (
            self.performance_stats["slow_requests"] / total_requests
        ) * 100

        return {
            "total_requests": total_requests,
            "cache_hit_rate": f"{cache_hit_rate:.1f}%",
            "slow_request_rate": f"{slow_request_rate:.1f}%",
            "slow_threshold_ms": self.slow_threshold_ms,
            "optimizations_applied": dict(
                self.performance_stats["optimizations_applied"]
            ),
            "recommendations": self._generate_performance_recommendations(),
        }

    def _generate_performance_recommendations(self) -> list[str]:
        """生成性能优化建议"""
        recommendations = []
        stats = self.performance_stats

        cache_hit_rate = stats["cache_hits"] / max(stats["total_requests"], 1)
        slow_rate = stats["slow_requests"] / max(stats["total_requests"], 1)

        if cache_hit_rate < 0.5:
            recommendations.append("缓存命中率较低，考虑增加缓存TTL或优化缓存键策略")

        if slow_rate > 0.1:
            recommendations.append("慢查询比例较高，考虑实施渠道预过滤或分批处理")

        optimizations_applied = stats["optimizations_applied"]
        if (
            isinstance(optimizations_applied, dict)
            and optimizations_applied.get("large_batch_optimization", 0) > 5
        ):
            recommendations.append("大批量查询频繁，建议实施分层缓存策略")

        if len(recommendations) == 0:
            recommendations.append("性能表现良好，无需特别优化")

        return recommendations

    def cleanup_cache(self):
        """清理过期缓存（使用自适应超时）"""
        current_time = time.time()
        expired_keys = []

        for key, (cached_time, _) in self.cache.items():
            if (current_time - cached_time) > self.adaptive_cache_timeout:
                expired_keys.append(key)

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            logger.debug(
                f"BATCH_SCORER: Cleaned up {len(expired_keys)} expired cache entries (timeout: {self.adaptive_cache_timeout}s)"
            )
