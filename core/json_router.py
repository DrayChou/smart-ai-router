"""Tag-based routing engine wired for YAML configuration."""

from __future__ import annotations

import logging
import threading

from core.exceptions import ParameterComparisonError, TagNotFoundError
from core.router.mixins.candidate import CandidateDiscoveryMixin
from core.router.mixins.scoring import ScoringMixin
from core.router.types import ChannelCandidate, RoutingRequest, RoutingScore
from core.utils.capability_mapper import get_capability_mapper
from core.utils.channel_cache_manager import get_channel_cache_manager
from core.utils.local_model_capabilities import get_capability_detector
from core.utils.model_analyzer import get_model_analyzer
from core.utils.model_channel_blacklist import get_model_blacklist_manager
from core.utils.parameter_comparator import get_parameter_comparator
from core.utils.request_cache import RequestFingerprint, get_request_cache
from core.utils.unified_model_registry import get_unified_model_registry
from core.yaml_config import YAMLConfigLoader, get_yaml_config_loader

logger = logging.getLogger(__name__)


class JSONRouter(CandidateDiscoveryMixin, ScoringMixin):
    """基于Pydantic验证后配置的路由器"""

    def __init__(self, config_loader: YAMLConfigLoader | None = None):
        self.config_loader = config_loader or get_yaml_config_loader()
        self.config = self.config_loader.config

        self._tag_cache: dict[str, list[str]] = {}
        self._tag_cache_lock = threading.RLock()
        self._available_tags_cache: set | None = None
        self._available_models_cache: list[str] | None = None

        self.unified_registry = get_unified_model_registry()
        self.model_analyzer = get_model_analyzer()
        self.cache_manager = get_channel_cache_manager()
        self.parameter_comparator = get_parameter_comparator()
        self.capability_detector = get_capability_detector()
        self.capability_mapper = get_capability_mapper()
        self.blacklist_manager = get_model_blacklist_manager()

        try:
            from core.services.scoring import ScoringService

            self._scoring_service = ScoringService(self)
        except (ImportError, AttributeError) as exc:
            logger.warning("Failed to import ScoringService: %s", exc)
            self._scoring_service = None

    async def route_request(self, request: RoutingRequest) -> list[RoutingScore]:
        """
        路由请求，返回按评分排序的候选渠道列表。

        支持请求级缓存以提高性能：
        - 缓存TTL: 60秒
        - 基于请求指纹的智能缓存键生成
        - 自动故障转移和缓存失效
        """
        logger.info("ROUTING START: Processing request for model '%s'", request.model)

        fingerprint = RequestFingerprint(
            model=request.model,
            routing_strategy=getattr(request, "strategy", "cost_first"),
            required_capabilities=getattr(request, "required_capabilities", None),
            min_context_length=getattr(request, "min_context_length", None),
            max_cost_per_1k=getattr(request, "max_cost_per_1k", None),
            prefer_local=getattr(request, "prefer_local", False),
            exclude_providers=getattr(request, "exclude_providers", None),
            max_tokens=getattr(request, "max_tokens", None),
            temperature=getattr(request, "temperature", None),
            stream=getattr(request, "stream", False),
            has_functions=bool(
                getattr(request, "functions", None) or getattr(request, "tools", None)
            ),
        )

        cache = get_request_cache()
        cache_key = fingerprint.to_cache_key()
        logger.debug("CACHE LOOKUP: Key=%s, Model=%s", cache_key, request.model)

        cached_result = await cache.get_cached_selection(fingerprint)

        if cached_result:
            logger.info(
                "CACHE HIT: Using cached selection for '%s' (cost: $%.4f)",
                request.model,
                cached_result.cost_estimate,
            )

            scores: list[RoutingScore] = []
            scores.append(
                RoutingScore(
                    channel=cached_result.primary_channel,
                    total_score=1.0,
                    cost_score=1.0 if cached_result.cost_estimate == 0.0 else 0.8,
                    speed_score=0.9,
                    quality_score=0.8,
                    reliability_score=0.9,
                    reason=f"CACHED: {cached_result.selection_reason}",
                    matched_model=cached_result.primary_matched_model or request.model,
                )
            )

            for index, backup_channel in enumerate(cached_result.backup_channels):
                backup_matched_model = None
                if cached_result.backup_matched_models and index < len(
                    cached_result.backup_matched_models
                ):
                    backup_matched_model = cached_result.backup_matched_models[index]

                scores.append(
                    RoutingScore(
                        channel=backup_channel,
                        total_score=0.9 - index * 0.1,
                        cost_score=0.7,
                        speed_score=0.8,
                        quality_score=0.7,
                        reliability_score=0.8,
                        reason=f"CACHED_BACKUP_{index + 1}",
                        matched_model=backup_matched_model or request.model,
                    )
                )

            return scores

        logger.info("CACHE MISS: Computing fresh routing for '%s'", request.model)
        try:
            logger.info("STEP 1: Finding candidate channels...")
            candidates = self._get_candidate_channels(request)
            if not candidates:
                logger.warning(
                    "ROUTING FAILED: No suitable channels found for model '%s'",
                    request.model,
                )
                return []
            logger.info("STEP 1 COMPLETE: Found %s candidate channels", len(candidates))

            logger.info("STEP 2: Filtering channels by health and availability...")
            filtered_candidates = self._filter_channels(candidates, request)
            if not filtered_candidates:
                logger.warning(
                    "ROUTING FAILED: No available channels after filtering for model '%s'",
                    request.model,
                )
                return []

            logger.info("STEP 2.5: Checking model capabilities...")
            capability_filtered = await self._filter_by_capabilities(
                filtered_candidates, request
            )
            if not capability_filtered:
                logger.warning(
                    "ROUTING FAILED: No channels with required capabilities for model '%s'",
                    request.model,
                )
                return []
            logger.info(
                "STEP 2.5 COMPLETE: %s channels passed capability check (filtered out %s)",
                len(capability_filtered),
                len(filtered_candidates) - len(capability_filtered),
            )
            filtered_candidates = capability_filtered

            if len(filtered_candidates) > 20:
                logger.info(
                    "STEP 2.7: Pre-filtering %s channels to reduce scoring overhead...",
                    len(filtered_candidates),
                )
                pre_filtered = await self._pre_filter_channels(
                    filtered_candidates, request, max_channels=20
                )
                logger.info(
                    "STEP 2.7 COMPLETE: Pre-filtered to %s channels for detailed scoring",
                    len(pre_filtered),
                )
                filtered_candidates = pre_filtered

            logger.info("[TARGET] STEP 3: Scoring and ranking channels...")
            scored_channels = await self._score_channels(filtered_candidates, request)
            if not scored_channels:
                logger.warning(
                    "ROUTING FAILED: Failed to score any channels for model '%s'",
                    request.model,
                )
                return []
            logger.info("STEP 3 COMPLETE: Scored %s channels", len(scored_channels))

            if scored_channels:
                primary_channel = scored_channels[0].channel
                backup_channels = [score.channel for score in scored_channels[1:6]]
                selection_reason = scored_channels[0].reason
                cost_estimate = self._estimate_cost_for_channel(
                    primary_channel, request
                )
                primary_matched_model = scored_channels[0].matched_model
                backup_matched_models = [
                    score.matched_model for score in scored_channels[1:6]
                ]

                try:
                    await cache.cache_selection(
                        fingerprint=fingerprint,
                        primary_channel=primary_channel,
                        backup_channels=backup_channels,
                        selection_reason=selection_reason,
                        cost_estimate=cost_estimate,
                        ttl_seconds=60,
                        primary_matched_model=primary_matched_model,
                        backup_matched_models=backup_matched_models,
                    )
                    logger.debug(
                        "💾 CACHED RESULT: %s -> %s", cache_key, primary_channel.name
                    )
                except Exception as cache_error:
                    logger.warning(
                        "[WARNING]  CACHE SAVE FAILED: %s, continuing without caching",
                        cache_error,
                    )

            logger.info(
                "🎉 ROUTING SUCCESS: Ready to attempt %s channels in ranked order for model '%s'",
                len(scored_channels),
                request.model,
            )

            return scored_channels

        except TagNotFoundError:
            raise
        except ParameterComparisonError:
            raise
        except Exception as exc:
            logger.error(
                "ROUTING ERROR: Request failed for model '%s': %s",
                request.model,
                exc,
                exc_info=True,
            )
            return []

    def clear_cache(self) -> None:
        """清除所有缓存"""
        self._tag_cache.clear()
        self._available_tags_cache = None
        self._available_models_cache = None
        logger.info("Router cache cleared")

    def update_channel_health(
        self, channel_id: str, success: bool, latency: float | None = None
    ) -> None:
        """更新渠道健康状态"""
        self.config_loader.update_channel_health(channel_id, success, latency)


__all__ = [
    "JSONRouter",
    "RoutingRequest",
    "RoutingScore",
    "ChannelCandidate",
]


_router: JSONRouter | None = None
_router_lock = threading.Lock()


def get_router() -> JSONRouter:
    """获取全局路由器实例（线程安全）"""
    global _router
    if _router is None:
        with _router_lock:
            if _router is None:
                _router = JSONRouter()
    return _router
