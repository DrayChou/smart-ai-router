"""Scoring, filtering, and capability helpers for JSON routing."""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Optional

from core.config_models import Channel
from core.router.types import ChannelCandidate, RoutingRequest, RoutingScore

logger = logging.getLogger(__name__)


class ScoringMixin:
    """Provides scoring and filtering helpers for the router."""

    def _filter_channels(self, channels: list[ChannelCandidate], request: RoutingRequest) -> list[ChannelCandidate]:
        """过滤渠道，包含能力检测"""
        filtered = []

        routing_config = self.config.routing if hasattr(self.config, 'routing') else None
        if routing_config and hasattr(routing_config, 'model_filters'):
            model_filters = routing_config.model_filters or {}
        else:
            model_filters = {}

        min_context_length = getattr(model_filters, 'min_context_length', 0) if hasattr(model_filters, 'min_context_length') else model_filters.get('min_context_length', 0) if isinstance(model_filters, dict) else 0
        min_parameter_count = getattr(model_filters, 'min_parameter_count', 0) if hasattr(model_filters, 'min_parameter_count') else model_filters.get('min_parameter_count', 0) if isinstance(model_filters, dict) else 0
        exclude_embedding = getattr(model_filters, 'exclude_embedding_models', True) if hasattr(model_filters, 'exclude_embedding_models') else model_filters.get('exclude_embedding_models', True) if isinstance(model_filters, dict) else True
        exclude_vision_only = getattr(model_filters, 'exclude_vision_only_models', True) if hasattr(model_filters, 'exclude_vision_only_models') else model_filters.get('exclude_vision_only_models', True) if isinstance(model_filters, dict) else True

        for candidate in channels:
            channel = candidate.channel
            if not channel.enabled or not channel.api_key:
                continue

            model_name = candidate.matched_model or channel.model_name
            is_blacklisted, blacklist_entry = self.blacklist_manager.is_model_blacklisted(channel.id, model_name)
            if is_blacklisted:
                remaining_time = blacklist_entry.get_remaining_time() if blacklist_entry else -1
                if remaining_time > 0:
                    logger.debug(
                        "BLACKLIST FILTER: Skipping %s -> %s (blacklisted for %ss due to %s)",
                        channel.name,
                        model_name,
                        remaining_time,
                        blacklist_entry.error_type.value if blacklist_entry else "unknown",
                    )
                else:
                    logger.debug("BLACKLIST FILTER: Skipping %s -> %s (permanently blacklisted)", channel.name, model_name)
                continue

            if not hasattr(self, '_cached_health_scores'):
                self._cached_health_scores = self.config_loader.runtime_state.health_scores.copy()

            health_score = self._cached_health_scores.get(channel.id, 1.0)
            if health_score < 0.3:
                continue

            if candidate.matched_model and (min_context_length > 0 or min_parameter_count > 0 or exclude_embedding or exclude_vision_only):
                model_name = candidate.matched_model

                if exclude_embedding and self._is_embedding_model(model_name):
                    logger.debug("Filtered out embedding model: %s", model_name)
                    continue

                if exclude_vision_only and self._is_vision_only_model(model_name):
                    logger.debug("Filtered out vision-only model: %s", model_name)
                    continue

                model_specs = self._get_model_specs(channel.id, model_name)

                if min_context_length > 0:
                    context_length = model_specs.get('context_length', 0) if model_specs else 0
                    if context_length < min_context_length:
                        logger.debug("Filtered out model %s: context %s < %s", model_name, context_length, min_context_length)
                        continue

                if min_parameter_count > 0:
                    param_count = model_specs.get('parameter_count', 0) if model_specs else 0
                    if param_count < min_parameter_count:
                        logger.debug("Filtered out model %s: params %sM < %sM", model_name, param_count, min_parameter_count)
                        continue

            filtered.append(candidate)
        return filtered

    async def _score_channels(self, channels: list[ChannelCandidate], request: RoutingRequest) -> list[RoutingScore]:
        """计算渠道评分 - 委托到 ScoringService，保持行为不变。"""
        if getattr(self, "_scoring_service", None) is not None:
            return await self._scoring_service.score(channels, request)
        return await self._score_channels_individual(channels, request)

    async def _score_channels_individual(self, channels: list[ChannelCandidate], request: RoutingRequest) -> list[RoutingScore]:
        """单个渠道评分方式（用于小数量渠道）"""
        logger.info("📊 SCORING: Using individual scoring for %s channels", len(channels))

        scored_channels: list[RoutingScore] = []
        strategy = self._get_routing_strategy(request)

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
                strategy,
                cost_score,
                speed_score,
                quality_score,
                reliability_score,
                parameter_score,
                context_score,
                free_score,
                local_score,
            )

            model_display = candidate.matched_model or channel.model_name
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "📊 SCORE: '%s' -> '%s' = %.3f (Q:%.2f)",
                    channel.name,
                    model_display,
                    total_score,
                    quality_score,
                )

            scored_channels.append(
                RoutingScore(
                    channel=channel,
                    total_score=total_score,
                    cost_score=cost_score,
                    speed_score=speed_score,
                    quality_score=quality_score,
                    reliability_score=reliability_score,
                    reason=(
                        f"cost:{cost_score:.2f} speed:{speed_score:.2f} "
                        f"quality:{quality_score:.2f} reliability:{reliability_score:.2f}"
                    ),
                    matched_model=candidate.matched_model,
                    parameter_score=parameter_score,
                    context_score=context_score,
                    free_score=free_score,
                )
            )

        scored_channels = self._hierarchical_sort(scored_channels)

        if getattr(self, "_scoring_service", None) is not None:
            return await self._scoring_service.score_individual(channels, request)
        return scored_channels

    def _get_routing_strategy(self, request: RoutingRequest) -> list[dict[str, Any]]:
        """获取并解析路由策略，始终返回规则列表"""
        routing_config = self.config.routing if hasattr(self.config, 'routing') else None

        if hasattr(request, 'strategy') and request.strategy:
            strategy_name = request.strategy
        else:
            if routing_config and hasattr(routing_config, 'default_strategy'):
                strategy_name = routing_config.default_strategy or 'cost_first'
            else:
                strategy_name = 'cost_first'

        if routing_config and hasattr(routing_config, 'sorting_strategies'):
            custom_strategies = routing_config.sorting_strategies or {}
        else:
            custom_strategies = {}
        if strategy_name in custom_strategies:
            return custom_strategies[strategy_name]

        predefined_strategies = {
            "cost_first": [
                {"field": "cost_score", "order": "desc", "weight": 0.4},
                {"field": "parameter_score", "order": "desc", "weight": 0.25},
                {"field": "context_score", "order": "desc", "weight": 0.2},
                {"field": "speed_score", "order": "desc", "weight": 0.15},
            ],
            "free_first": [
                {"field": "free_score", "order": "desc", "weight": 0.5},
                {"field": "cost_score", "order": "desc", "weight": 0.3},
                {"field": "speed_score", "order": "desc", "weight": 0.15},
                {"field": "reliability_score", "order": "desc", "weight": 0.05},
            ],
            "local_first": [
                {"field": "local_score", "order": "desc", "weight": 0.6},
                {"field": "speed_score", "order": "desc", "weight": 0.25},
                {"field": "cost_score", "order": "desc", "weight": 0.1},
                {"field": "reliability_score", "order": "desc", "weight": 0.05},
            ],
            "cost_optimized": [
                {"field": "cost_score", "order": "desc", "weight": 0.7},
                {"field": "reliability_score", "order": "desc", "weight": 0.2},
                {"field": "speed_score", "order": "desc", "weight": 0.1},
            ],
            "speed_optimized": [
                {"field": "speed_score", "order": "desc", "weight": 0.4},
                {"field": "cost_score", "order": "desc", "weight": 0.3},
                {"field": "parameter_score", "order": "desc", "weight": 0.2},
                {"field": "context_score", "order": "desc", "weight": 0.1},
            ],
            "quality_optimized": [
                {"field": "parameter_score", "order": "desc", "weight": 0.4},
                {"field": "context_score", "order": "desc", "weight": 0.3},
                {"field": "quality_score", "order": "desc", "weight": 0.2},
                {"field": "cost_score", "order": "desc", "weight": 0.1},
            ],
            "balanced": [
                {"field": "cost_score", "order": "desc", "weight": 0.3},
                {"field": "parameter_score", "order": "desc", "weight": 0.25},
                {"field": "context_score", "order": "desc", "weight": 0.2},
                {"field": "speed_score", "order": "desc", "weight": 0.15},
                {"field": "reliability_score", "order": "desc", "weight": 0.1},
            ],
        }

        return predefined_strategies.get(strategy_name, predefined_strategies["cost_first"])

    def _calculate_cost_score(self, channel: Channel, request: RoutingRequest) -> float:
        """计算成本评分(0-1，越低成本越高分)"""
        logger.info("🔍 COST SCORE CALCULATION: %s | %s", channel.id, request.model)

        try:
            from core.utils.cost_estimator import CostEstimator

            estimator = CostEstimator()
            logger.info("  ✅ CostEstimator created successfully")

            input_tokens = self._estimate_tokens(request.messages)
            max_output_tokens = request.max_tokens or 1000
            logger.info("  📊 Tokens: input=%s, max_output=%s", input_tokens, max_output_tokens)

            cost_result = estimator.estimate_cost(
                channel=channel,
                model_name=request.model,
                messages=request.messages,
                max_output_tokens=max_output_tokens,
            )
            logger.info("  💰 CostEstimator result: %s", cost_result)

            if cost_result and cost_result.total_cost > 0:
                total_cost = cost_result.total_cost
                logger.info("  ✅ COST SCORE: Using dynamic pricing for %s: $%.6f", request.model, total_cost)
            else:
                cost_estimate = self._estimate_cost_for_channel(channel, request)
                total_cost = max(0.0001, cost_estimate)
                logger.info(
                    "  ⚠️ COST SCORE: Fallback to channel pricing for %s: $%.6f",
                    request.model,
                    total_cost,
                )
        except Exception as e:
            logger.warning("  ⚠️ COST SCORE: Cost estimator failed, fallback applied: %s", e)
            cost_estimate = self._estimate_cost_for_channel(channel, request)
            total_cost = max(0.0001, cost_estimate)

        if total_cost <= 0:
            return 1.0

        max_cost = 0.05
        normalized_cost = min(total_cost / max_cost, 1.0)
        cost_score = 1.0 - normalized_cost
        cost_score = max(0.0, min(cost_score, 1.0))

        logger.debug("COST SCORE RESULT: Channel=%s, Model=%s, Cost=$%.6f, Score=%.4f", channel.name, request.model, total_cost, cost_score)
        return cost_score

    def _calculate_fallback_cost(self, channel: Channel, input_tokens: int, max_output_tokens: int) -> float:
        """回退到渠道级定价计算成本"""
        if channel.cost_per_token:
            cost_per_token = channel.cost_per_token
            input_cost = cost_per_token.get("input", 0.0) * input_tokens
            output_cost = cost_per_token.get("output", 0.0) * max_output_tokens
            return input_cost + output_cost

        pricing = getattr(channel, 'pricing', None)
        if pricing:
            input_cost_per_1k = pricing.get("input_cost_per_1k", 0.0)
            output_cost_per_1k = pricing.get("output_cost_per_1k", 0.0)
            return (input_tokens / 1000) * input_cost_per_1k + (max_output_tokens / 1000) * output_cost_per_1k

        return 0.0

    def _calculate_quality_score(self, channel: Channel, matched_model: Optional[str] = None) -> float:
        """计算模型质量评分"""
        model_name = matched_model or channel.model_name
        if not model_name:
            return 0.5

        model_specs = self._get_model_specs(channel.id, model_name)
        if not model_specs:
            return 0.5

        quality_metrics = {
            "gpt-4": 0.95,
            "claude-3-opus": 0.93,
            "claude": 0.9,
            "gpt-4-turbo": 0.9,
            "gpt-4o": 0.9,
            "deepseek-v3": 0.87,
            "qwen-max": 0.85,
            "qwen-plus": 0.83,
            "gpt-3.5": 0.75,
            "gemini-1.5-flash": 0.72,
            "glm-4": 0.7,
        }

        for keyword, score in quality_metrics.items():
            if keyword in model_name.lower():
                return score

        return 0.6

    def _calculate_parameter_score(self, channel: Channel, matched_model: Optional[str] = None) -> float:
        """计算模型参数量评分"""
        model_name = matched_model or channel.model_name
        if not model_name:
            return 0.5

        model_specs = self._get_model_specs(channel.id, model_name)
        if not model_specs:
            return 0.5

        parameter_count = model_specs.get('parameter_count', 0)
        if parameter_count >= 1000000:
            return 1.0
        if parameter_count >= 500000:
            return 0.9
        if parameter_count >= 200000:
            return 0.8
        if parameter_count >= 100000:
            return 0.7
        if parameter_count >= 50000:
            return 0.6
        if parameter_count >= 20000:
            return 0.5
        if parameter_count >= 7000:
            return 0.4
        return 0.3

    def _calculate_context_score(self, channel: Channel, matched_model: Optional[str] = None) -> float:
        """计算上下文长度评分"""
        model_name = matched_model or channel.model_name
        if not model_name:
            return 0.5

        model_specs = self._get_model_specs(channel.id, model_name)
        if not model_specs:
            return 0.5

        context_length = model_specs.get('context_length', 0)
        if context_length >= 2000000:
            return 1.0
        if context_length >= 1000000:
            return 0.95
        if context_length >= 512000:
            return 0.9
        if context_length >= 200000:
            return 0.85
        if context_length >= 128000:
            return 0.8
        if context_length >= 64000:
            return 0.7
        if context_length >= 32000:
            return 0.6
        if context_length >= 16000:
            return 0.5
        if context_length >= 8000:
            return 0.4
        if context_length >= 4000:
            return 0.3
        return 0.2

    def _get_model_specs(self, channel_id: str, model_name: str) -> Optional[dict[str, Any]]:
        model_cache = self.config_loader.get_model_cache()
        if not model_cache:
            return None

        cache_key_variants = [channel_id]
        for key in model_cache.keys():
            if key.startswith(f"{channel_id}_"):
                cache_key_variants.append(key)

        for cache_key in cache_key_variants:
            cache_data = model_cache.get(cache_key)
            if not isinstance(cache_data, dict):
                continue

            models_data = cache_data.get("models_data", {})
            if model_name in models_data:
                return models_data[model_name]

        return None

    def _is_embedding_model(self, model_name: str) -> bool:
        if not model_name:
            return False
        model_lower = model_name.lower()
        return any(keyword in model_lower for keyword in ['embedding', 'rerank', 'search'])

    def _is_vision_only_model(self, model_name: str) -> bool:
        if not model_name:
            return False
        model_lower = model_name.lower()
        return 'vision-only' in model_lower or model_lower.endswith('-vision')

    def _calculate_speed_score(self, channel: Channel) -> float:
        response_time = getattr(channel, 'avg_response_time', None)
        if response_time is None:
            return 0.6

        if response_time <= 0.5:
            return 1.0
        if response_time <= 1.0:
            return 0.9
        if response_time <= 2.0:
            return 0.8
        if response_time <= 4.0:
            return 0.6
        if response_time <= 6.0:
            return 0.4
        return 0.2

    def _calculate_reliability_score(self, channel: Channel) -> float:
        success_rate = getattr(channel, 'success_rate', None)
        if success_rate is None:
            runtime_state = getattr(self.config_loader, 'runtime_state', None)
            if runtime_state and hasattr(runtime_state, 'channel_stats'):
                stats = runtime_state.channel_stats.get(channel.id)
                if stats and isinstance(stats, dict):
                    # 修复：stats 是字典，需要使用字典访问方式
                    request_count = stats.get('request_count', 0)
                    success_count = stats.get('success_count', request_count)  # 如果没有 success_count，假设全部成功
                    if request_count >= 5:
                        success_rate = success_count / request_count

        if success_rate is None:
            return 0.5

        if success_rate >= 0.99:
            return 1.0
        if success_rate >= 0.95:
            return 0.9
        if success_rate >= 0.9:
            return 0.8
        if success_rate >= 0.8:
            return 0.6
        if success_rate >= 0.7:
            return 0.4
        return 0.2

    def _calculate_free_score(self, channel: Channel, model_name: Optional[str] = None) -> float:
        free_tags = {"free", "免费", "0cost", "nocost"}

        if model_name:
            model_tags = self._extract_tags_from_model_name(model_name)
            if any(tag.lower() in free_tags for tag in model_tags):
                logger.debug("FREE SCORE: Model '%s' contains free tags", model_name)
                return 1.0

        model_cache = self.config_loader.get_model_cache()
        if model_cache and channel.id in model_cache:
            cache_data = model_cache[channel.id]
            models_pricing = cache_data.get("models_pricing", {})
            discounted_price = cache_data.get("discounted_price", {})

            if model_name and model_name in models_pricing:
                pricing_info = models_pricing.get(model_name, {})
                if pricing_info.get('is_free'):
                    logger.debug("FREE SCORE: Channel '%s' model '%s' marked as free in pricing", channel.name, model_name)
                    return 1.0

            if discounted_price:
                input_cost = discounted_price.get("input_cost_per_1k", 0.001)
                output_cost = discounted_price.get("output_cost_per_1k", 0.001)
                avg_cost = (input_cost + output_cost) / 2
                if avg_cost <= 0.00005:
                    logger.debug("FREE SCORE: Channel '%s' has discounted avg cost %.6f", channel.name, avg_cost)
                    return 1.0

            if model_name and model_name in models_pricing:
                model_price = models_pricing.get(model_name, {})
                input_price = model_price.get("input_cost_per_token", 0.0)
                output_price = model_price.get("output_cost_per_token", 0.0)
                if input_price <= 0.0000005 and output_price <= 0.0000005:
                    logger.debug("FREE SCORE: Channel '%s' model '%s' token pricing indicates free", channel.name, model_name)
                    return 1.0

        if hasattr(channel, 'cost_per_token') and channel.cost_per_token:
            cost_per_token = channel.cost_per_token
            input_cost = cost_per_token.get("input", 0.0)
            output_cost = cost_per_token.get("output", 0.0)
            if input_cost <= 0.0 and output_cost <= 0.0:
                logger.debug("FREE SCORE: Channel '%s' confirmed free via cost_per_token", channel.name)
                return 1.0
            if model_name and (":free" in model_name.lower() or "-free" in model_name.lower()):
                logger.debug("FREE SCORE: Channel '%s' has costs but model '%s' explicitly marked as free", channel.name, model_name)
                return 1.0
            logger.debug("FREE SCORE: Channel '%s' has non-zero costs", channel.name)
            return 0.1

        pricing = getattr(channel, 'pricing', None)
        if pricing:
            input_cost = pricing.get("input_cost_per_1k", 0.001)
            output_cost = pricing.get("output_cost_per_1k", 0.002)
            avg_cost = (input_cost + output_cost) / 2
            if avg_cost <= 0.0001:
                logger.debug("FREE SCORE: Channel '%s' very low cost (avg=%.6f)", channel.name, avg_cost)
                return 0.9
            if avg_cost <= 0.001:
                logger.debug("FREE SCORE: Channel '%s' low cost (avg=%.6f)", channel.name, avg_cost)
                return 0.7
            if model_name and (":free" in model_name.lower() or "-free" in model_name.lower()):
                logger.debug("FREE SCORE: Channel has costs but model '%s' explicitly marked as free", model_name)
                return 1.0
            logger.debug("FREE SCORE: Channel '%s' has significant costs (avg=%.6f)", channel.name, avg_cost)
            return 0.1

        channel_tags_lower = [tag.lower() for tag in getattr(channel, 'tags', [])]
        if any(tag in free_tags for tag in channel_tags_lower):
            logger.debug("FREE SCORE: Channel '%s' has free tag in channel tags", channel.name)
            return 1.0

        logger.debug("FREE SCORE: Channel '%s' no evidence of being free", channel.name)
        return 0.1

    def _calculate_local_score(self, channel: Channel, model_name: Optional[str] = None) -> float:
        local_tags = {"local", "本地", "localhost", "127.0.0.1", "offline", "edge"}

        channel_tags_lower = [tag.lower() for tag in channel.tags]
        if any(tag in local_tags for tag in channel_tags_lower):
            return 1.0

        if model_name:
            model_tags = self._extract_tags_from_model_name(model_name)
            model_tags_lower = [tag.lower() for tag in model_tags]
            if any(tag in local_tags for tag in model_tags_lower):
                return 1.0

        base_url = getattr(channel, 'base_url', None)
        if base_url:
            base_url_lower = base_url.lower()
            local_indicators = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
            if any(indicator in base_url_lower for indicator in local_indicators):
                return 1.0

        provider_config = None
        if hasattr(self.config, 'providers'):
            provider_config = next((p for p in self.config.providers.values() if p.name == channel.provider), None)

        if provider_config and hasattr(provider_config, 'base_url'):
            provider_url_lower = provider_config.base_url.lower()
            local_indicators = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
            if any(indicator in provider_url_lower for indicator in local_indicators):
                return 1.0

        if model_name:
            local_model_patterns = ["ollama", "llama.cpp", "local", "自己的", "私有"]
            model_lower = model_name.lower()
            if any(pattern in model_lower for pattern in local_model_patterns):
                return 0.8

        return 0.1

    def _calculate_total_score(
        self,
        strategy: list[dict[str, Any]],
        cost_score: float,
        speed_score: float,
        quality_score: float,
        reliability_score: float,
        parameter_score: float = 0.5,
        context_score: float = 0.5,
        free_score: float = 0.1,
        local_score: float = 0.1,
    ) -> float:
        total_score = 0.0
        score_map = {
            "cost_score": cost_score,
            "speed_score": speed_score,
            "quality_score": quality_score,
            "reliability_score": reliability_score,
            "parameter_score": parameter_score,
            "context_score": context_score,
            "free_score": free_score,
            "local_score": local_score,
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
        logger.info("HIERARCHICAL SORTING: 6-digit scoring system (Cost|Context|Param|Speed|Quality|Reliability)")

        def sorting_key(score: RoutingScore):
            cost_tier = min(9, int(score.cost_score * 9))
            context_tier = min(9, int(score.context_score * 9))
            parameter_tier = min(9, int(score.parameter_score * 9))
            speed_tier = min(9, int(score.speed_score * 9))
            quality_tier = min(9, int(score.quality_score * 9))
            reliability_tier = min(9, int(score.reliability_score * 9))

            hierarchical_score = (
                cost_tier * 100000 +
                context_tier * 10000 +
                parameter_tier * 1000 +
                speed_tier * 100 +
                quality_tier * 10 +
                reliability_tier
            )
            return (-hierarchical_score, score.channel.name)

        sorted_channels = sorted(scored_channels, key=sorting_key)

        for i, scored in enumerate(sorted_channels[:5]):
            cost_tier = min(9, int(scored.cost_score * 9))
            context_tier = min(9, int(scored.context_score * 9))
            parameter_tier = min(9, int(scored.parameter_score * 9))
            speed_tier = min(9, int(scored.speed_score * 9))
            quality_tier = min(9, int(scored.quality_score * 9))
            reliability_tier = min(9, int(scored.reliability_score * 9))

            hierarchical_score = (
                cost_tier * 100000 +
                context_tier * 10000 +
                parameter_tier * 1000 +
                speed_tier * 100 +
                quality_tier * 10 +
                reliability_tier
            )

            score_display = f"{cost_tier}{context_tier}{parameter_tier}{speed_tier}{quality_tier}{reliability_tier}"
            is_free = "FREE" if scored.free_score >= 0.9 else "PAID"
            logger.info("   #%s: '%s' [%s] Score: %s (Total: %s)", i + 1, scored.channel.name, is_free, score_display, f"{hierarchical_score:,}")

        return sorted_channels

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        try:
            import tiktoken

            encoding = tiktoken.get_encoding("cl100k_base")
            total_tokens = 0
            for message in messages:
                content = message.get("content", "")
                if isinstance(content, str):
                    role_overhead = 4
                    content_tokens = len(encoding.encode(content))
                    total_tokens += content_tokens + role_overhead

            return max(1, total_tokens)
        except ImportError:
            logger.debug("tiktoken不可用，使用改进的字符估算方法")

        total_chars = 0
        all_content = ""
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                total_chars += len(f"role: {message.get('role', 'user')}")
                total_chars += len(content)
                all_content += content

        chinese_chars = sum(1 for char in all_content if '\u4e00' <= char <= '\u9fff')
        english_chars = len(all_content) - chinese_chars
        estimated_tokens = chinese_chars + (english_chars // 4) + (len(messages) * 4)

        return max(1, estimated_tokens)

    def _estimate_cost_for_channel(self, channel: Channel, request: RoutingRequest) -> float:
        try:
            from core.utils.cost_estimator import CostEstimator

            estimator = CostEstimator()
            input_tokens = self._estimate_tokens(request.messages)
            max_output_tokens = request.max_tokens or max(50, input_tokens // 4)

            cost_result = estimator.estimate_cost(
                channel_id=channel.id,
                model_name=request.model,
                input_tokens=input_tokens,
                output_tokens=max_output_tokens,
            )
            if cost_result and cost_result.total_cost > 0:
                return cost_result.total_cost
        except Exception as e:
            logger.debug("Enhanced cost estimation failed for %s: %s", channel.id, e)

        input_tokens = self._estimate_tokens(request.messages)
        estimated_output_tokens = max(50, input_tokens // 4)

        model_cache = self.config_loader.get_model_cache()
        if channel.id in model_cache:
            discovered_info = model_cache[channel.id]
            models_pricing = discovered_info.get("models_pricing", {})

            model_pricing = None
            for model_name, pricing in models_pricing.items():
                if model_name == request.model or request.model in model_name:
                    model_pricing = pricing
                    break

            if model_pricing:
                input_cost = model_pricing.get("input_cost_per_token", 0.0)
                output_cost = model_pricing.get("output_cost_per_token", 0.0)
                total_cost = input_tokens * input_cost + estimated_output_tokens * output_cost
                return total_cost

        free_score = self._calculate_free_score(channel, request.model)
        if free_score >= 0.9:
            return 0.0
        return 0.001

    async def _filter_by_capabilities(self, channels: list[ChannelCandidate], request: RoutingRequest) -> list[ChannelCandidate]:
        if not hasattr(request, 'data') or not request.data:
            return channels

        capability_requirements = self.capability_mapper.get_capability_requirements(request.data)
        if not any(capability_requirements.values()):
            logger.debug("Request doesn't require special capabilities, skipping capability check")
            return channels

        logger.info("CAPABILITY REQUIREMENTS: %s", capability_requirements)

        capability_filtered = []
        fallback_channels = []

        for candidate in channels:
            channel = candidate.channel
            model_name = candidate.matched_model or channel.model_name

            try:
                capabilities = await self.capability_detector.detect_model_capabilities(
                    model_name=model_name,
                    provider=channel.provider,
                    base_url=channel.base_url or "",
                    api_key=channel.api_key,
                )

                can_handle = self.capability_detector.can_handle_request(capabilities, request.data)

                if can_handle:
                    capability_filtered.append(candidate)
                    logger.debug("CAPABILITY MATCH: %s can handle request", channel.name)
                else:
                    if capabilities.is_local:
                        fallback_channels.append((candidate, capabilities))
                        logger.debug("⚠️ LOCAL LIMITATION: %s lacks required capabilities", channel.name)
                    else:
                        logger.debug("CAPABILITY MISMATCH: %s cannot handle request", channel.name)

            except Exception as e:
                logger.warning("Error checking capabilities for %s: %s", channel.name, e)
                capability_filtered.append(candidate)

        if not capability_filtered and fallback_channels:
            logger.info("FALLBACK SEARCH: Looking for cloud alternatives for local model limitations...")

            all_channels = []
            for provider_config in self.config.providers:
                for channel_config in provider_config.channels:
                    if channel_config.enabled:
                        all_channels.append(
                            {
                                "id": channel_config.id,
                                "name": channel_config.name,
                                "provider": provider_config.name,
                                "model_name": channel_config.model_name,
                                "base_url": channel_config.base_url or provider_config.base_url,
                                "api_key": channel_config.api_key,
                                "priority": getattr(channel_config, 'priority', 1),
                            }
                        )

            for failed_candidate, _failed_capabilities in fallback_channels[:1]:
                fallback_candidates = await self.capability_detector.get_fallback_channels(
                    original_channel=failed_candidate.channel.id,
                    request_data=request.data,
                    available_channels=all_channels,
                )

                if fallback_candidates:
                    logger.info("FOUND FALLBACK: %s alternative channels for %s", len(fallback_candidates), failed_candidate.channel.name)

                    for fallback_channel_config in fallback_candidates[:3]:
                        fallback_channel = Channel(
                            id=fallback_channel_config["id"],
                            name=fallback_channel_config["name"],
                            provider=fallback_channel_config["provider"],
                            model_name=fallback_channel_config["model_name"],
                            api_key=fallback_channel_config["api_key"],
                            base_url=fallback_channel_config["base_url"],
                            enabled=True,
                            priority=fallback_channel_config.get("priority", 1),
                        )

                        fallback_candidate = ChannelCandidate(
                            channel=fallback_channel,
                            matched_model=fallback_channel_config["model_name"],
                        )

                        capability_filtered.append(fallback_candidate)
                    break

        return capability_filtered

    async def _pre_filter_channels(self, channels: list[ChannelCandidate], request: RoutingRequest, max_channels: int = 20) -> list[ChannelCandidate]:
        if len(channels) <= max_channels:
            return channels

        logger.info("PRE-FILTER: Fast pre-filtering %s channels to top %s", len(channels), max_channels)

        channel_scores = []
        for candidate in channels:
            channel = candidate.channel
            score = 0.0

            if self._is_free_channel(channel, candidate.matched_model):
                score += 1000

            if hasattr(channel, 'priority') and channel.priority:
                score += (10 - channel.priority) * 10

            if self._is_local_channel(channel):
                score += 100

            if getattr(channel, 'enabled', True):
                score += 50

            score += random.uniform(0, 10)
            channel_scores.append((score, candidate))

        channel_scores.sort(key=lambda x: x[0], reverse=True)
        selected = [candidate for score, candidate in channel_scores[:max_channels]]

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("PRE-FILTER RESULTS:")
            for i, (score, candidate) in enumerate(channel_scores[:max_channels]):
                logger.debug("  #%s: %s (score: %.1f)", i + 1, candidate.channel.name, score)

        logger.info("PRE-FILTER COMPLETE: Selected %s/%s channels for detailed scoring", len(selected), len(channels))
        return selected

    def _is_free_channel(self, channel: Channel, model_name: Optional[str]) -> bool:
        if hasattr(channel, 'cost') and channel.cost == 0:
            return True
        if model_name and 'free' in model_name.lower():
            return True
        if hasattr(channel, 'name') and channel.name and 'free' in channel.name.lower():
            return True
        return False

    def _is_local_channel(self, channel: Channel) -> bool:
        if hasattr(channel, 'base_url') and channel.base_url:
            url = channel.base_url.lower()
            return any(local_indicator in url for local_indicator in [
                'localhost', '127.0.0.1', ':11434', ':1234', 'ollama', 'lmstudio'
            ])
        return False

    def _log_performance_metrics(self, channel_count: int, elapsed_ms: float, scoring_type: str, metrics=None):
        avg_time_per_channel = elapsed_ms / max(channel_count, 1)

        slow_threshold_ms = 1000
        very_slow_threshold_ms = 2000

        if elapsed_ms > very_slow_threshold_ms:
            logger.warning(
                "🐌 VERY SLOW SCORING: %s channels took %.1fms (avg: %.1fms/channel) - Consider optimization",
                channel_count,
                elapsed_ms,
                avg_time_per_channel,
            )
        elif elapsed_ms > slow_threshold_ms:
            logger.warning(
                "⚠️ SLOW SCORING: %s channels took %.1fms (avg: %.1fms/channel)",
                channel_count,
                elapsed_ms,
                avg_time_per_channel,
            )
        else:
            logger.info(
                "SCORING PERFORMANCE: %s channels in %.1fms (avg: %.1fms/channel)",
                channel_count,
                elapsed_ms,
                avg_time_per_channel,
            )

        if metrics and scoring_type == "batch":
            if metrics.slow_threshold_exceeded:
                logger.warning("BATCH SCORER ANALYSIS: %s", metrics.optimization_applied)

            if metrics.cache_hit:
                logger.info("💾 CACHE HIT: Scoring completed with cached results")

        if channel_count > 50 and elapsed_ms > 1500:
            logger.info("💡 OPTIMIZATION TIP: Consider implementing channel pre-filtering for %s+ channels", channel_count)
        elif channel_count > 20 and elapsed_ms > 800:
            logger.info("💡 OPTIMIZATION TIP: Performance could benefit from caching strategies")

