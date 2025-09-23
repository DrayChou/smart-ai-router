"""
Scoring service extracted from JSONRouter.

This centralizes scoring/sorting so JSONRouter delegates here. It calls back
into the router instance for calculators and sorting to keep behavior identical.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, List

if TYPE_CHECKING:
    from core.json_router import RoutingScore


logger = logging.getLogger(__name__)


class ScoringService:
    """Compute channel scores using the router's calculators and strategy."""

    def __init__(self, router: Any):
        # Router must provide calculator methods, strategy getter, and sorter.
        self._router = router

    async def score(self, channels: List[Any], request: Any) -> List[Any]:
        """Batch-optimized scoring with fallback to individual for small sets."""
        start_time = time.time()
        channel_count = len(channels)

        logger.info(
            f"📊 SCORING: Evaluating {channel_count} candidate channels for model '{request.model}'"
        )

        if channel_count < 5:
            result = await self.score_individual(channels, request)
            elapsed_ms = (time.time() - start_time) * 1000
            # router keeps original perf logging
            self._router._log_performance_metrics(
                channel_count, elapsed_ms, "individual"
            )
            return result

        # Lazy import to avoid cycles
        if not hasattr(self._router, "_batch_scorer"):
            from core.utils.batch_scorer import BatchScorer

            self._router._batch_scorer = BatchScorer(self._router)

        batch_result, metrics = await self._router._batch_scorer.batch_score_channels(
            channels, request
        )

        strategy = self._router._get_routing_strategy(request)
        logger.info(f"📊 SCORING: Using routing strategy with {len(strategy)} rules")
        for rule in strategy:
            logger.debug(
                f"📊 SCORING: Strategy rule: {rule['field']} (weight: {rule['weight']}, order: {rule['order']})"
            )

        scored_channels = []
        for candidate in channels:
            scores = self._router._batch_scorer.get_score_for_channel(
                batch_result, candidate
            )

            total_score = self._router._calculate_total_score(
                strategy,
                scores["cost_score"],
                scores["speed_score"],
                scores["quality_score"],
                scores["reliability_score"],
                scores["parameter_score"],
                scores["context_score"],
                scores["free_score"],
                scores["local_score"],
            )

            model_display = candidate.matched_model or candidate.channel.model_name
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    f"📊 SCORE: '{candidate.channel.name}' -> '{model_display}' = {total_score:.3f} (Q:{scores['quality_score']:.2f})"
                )

            # Import at runtime to avoid circular imports
            from core.json_router import RoutingScore

            scored_channels.append(
                RoutingScore(
                    channel=candidate.channel,
                    total_score=total_score,
                    cost_score=scores["cost_score"],
                    speed_score=scores["speed_score"],
                    quality_score=scores["quality_score"],
                    reliability_score=scores["reliability_score"],
                    reason=(
                        f"cost:{scores['cost_score']:.2f} "
                        f"speed:{scores['speed_score']:.2f} "
                        f"quality:{scores['quality_score']:.2f} "
                        f"reliability:{scores['reliability_score']:.2f}"
                    ),
                    matched_model=candidate.matched_model,
                    parameter_score=scores["parameter_score"],
                    context_score=scores["context_score"],
                    free_score=scores["free_score"],
                )
            )

        scored_channels = self._router._hierarchical_sort(scored_channels)

        total_elapsed_ms = (time.time() - start_time) * 1000
        self._router._log_performance_metrics(
            channel_count, total_elapsed_ms, "batch", metrics
        )

        logger.info(
            f"🏆 SCORING RESULT: Channels ranked by score (computed in {total_elapsed_ms:.1f}ms):"
        )
        for i, scored in enumerate(scored_channels[:5]):
            logger.info(
                f"🏆   #{i+1}: '{scored.channel.name}' (Score: {scored.total_score:.3f})"
            )

        return scored_channels

    async def score_individual(self, channels: List[Any], request: Any) -> List[Any]:
        """Individual scoring for small sets."""
        logger.info(
            f"📊 SCORING: Using individual scoring for {len(channels)} channels"
        )
        strategy = self._router._get_routing_strategy(request)

        # Import at runtime to avoid circular imports
        from core.json_router import RoutingScore

        scored_channels = []
        for candidate in channels:
            channel = candidate.channel

            cost_score = self._router._calculate_cost_score(channel, request)
            speed_score = self._router._calculate_speed_score(channel)
            quality_score = self._router._calculate_quality_score(
                channel, candidate.matched_model
            )
            reliability_score = self._router._calculate_reliability_score(channel)
            parameter_score = self._router._calculate_parameter_score(
                channel, candidate.matched_model
            )
            context_score = self._router._calculate_context_score(
                channel, candidate.matched_model
            )
            free_score = self._router._calculate_free_score(
                channel, candidate.matched_model
            )
            local_score = self._router._calculate_local_score(
                channel, candidate.matched_model
            )

            total_score = self._router._calculate_total_score(
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
                    f"📊 SCORE: '{channel.name}' -> '{model_display}' = {total_score:.3f} (Q:{quality_score:.2f})"
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
                        f"cost:{cost_score:.2f} "
                        f"speed:{speed_score:.2f} "
                        f"quality:{quality_score:.2f} "
                        f"reliability:{reliability_score:.2f}"
                    ),
                    matched_model=candidate.matched_model,
                    parameter_score=parameter_score,
                    context_score=context_score,
                    free_score=free_score,
                )
            )

        scored_channels = self._router._hierarchical_sort(scored_channels)

        logger.info(
            f"🏆 INDIVIDUAL SCORING RESULT: Processed {len(scored_channels)} channels"
        )
        for i, scored in enumerate(scored_channels[:3]):
            logger.info(
                f"🏆   #{i+1}: '{scored.channel.name}' (Score: {scored.total_score:.3f})"
            )

        return scored_channels
