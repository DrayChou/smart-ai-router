"""Parameter-based candidate selection logic."""

from __future__ import annotations

import logging

from core.exceptions import ParameterComparisonError
from core.router.types import ChannelCandidate, RoutingRequest

logger = logging.getLogger(__name__)


class ParameterComparisonMixin:
    """Provides helpers for parameter-size driven routing queries."""

    def _get_parameter_comparison_candidates(
        self, request: RoutingRequest
    ) -> list[ChannelCandidate] | None:
        if not self.parameter_comparator.is_parameter_comparison(request.model):
            return None

        logger.info("🔢 PARAMETER COMPARISON: Processing query '%s'", request.model)
        comparison = self.parameter_comparator.parse_comparison(request.model)
        if not comparison:
            logger.error(
                "PARAM PARSE FAILED: Could not parse parameter comparison '%s'",
                request.model,
            )
            raise ParameterComparisonError(request.model)

        model_cache = self.config_loader.get_model_cache()
        if not model_cache:
            logger.error(
                "NO MODEL CACHE: Model cache is empty for parameter comparison"
            )
            raise ParameterComparisonError(
                request.model, "模型缓存为空，无法进行参数量比较"
            )

        matching_models = self.parameter_comparator.filter_models_by_comparison(
            comparison, model_cache
        )
        if not matching_models:
            logger.error(
                "PARAM COMPARISON FAILED: No models found matching '%s'", request.model
            )
            raise ParameterComparisonError(request.model)

        logger.info("📝 First 5 matched models:")
        for index, (channel_id, model_name, model_params) in enumerate(
            matching_models[:5]
        ):
            logger.info(
                "  %s. %s -> %s (%.3fB)",
                index + 1,
                channel_id,
                model_name,
                model_params,
            )

        candidates: list[ChannelCandidate] = []
        disabled_count = 0
        not_found_count = 0

        logger.debug(
            "Processing %s matching models for channel lookup...", len(matching_models)
        )

        for channel_id, model_name, model_params in matching_models:
            real_channel_id = channel_id
            if "_" in channel_id:
                parts = channel_id.split("_")
                if len(parts) >= 2:
                    potential_hash = parts[-1]
                    if len(potential_hash) == 8 and all(
                        c in "0123456789abcdef" for c in potential_hash.lower()
                    ):
                        real_channel_id = "_".join(parts[:-1])

            logger.debug(
                "Channel ID mapping: '%s' -> '%s'", channel_id, real_channel_id
            )

            channel = self.config_loader.get_channel_by_id(real_channel_id)
            if channel:
                if channel.enabled:
                    candidates.append(
                        ChannelCandidate(channel=channel, matched_model=model_name)
                    )
                    logger.debug(
                        "Added channel: %s -> %s (%.3fB)",
                        channel.name,
                        model_name,
                        model_params,
                    )
                else:
                    disabled_count += 1
                    logger.debug(
                        "Disabled channel: %s -> %s", real_channel_id, model_name
                    )
            else:
                not_found_count += 1
                logger.debug(
                    "Channel not found: %s (from %s) -> %s",
                    real_channel_id,
                    channel_id,
                    model_name,
                )

        logger.info(
            "CHANNEL LOOKUP: Found %s enabled channels, disabled: %s, not_found: %s",
            len(candidates),
            disabled_count,
            not_found_count,
        )
        logger.info(
            "PARAMETER COMPARISON: Found %s candidate channels for '%s' models %s %sB",
            len(candidates),
            comparison.model_prefix,
            comparison.operator,
            comparison.target_params,
        )

        if candidates:
            logger.info("📝 Top matched channels:")
            for index, candidate in enumerate(candidates[:5]):
                logger.info(
                    "  %s. %s -> %s",
                    index + 1,
                    candidate.channel.name,
                    candidate.matched_model,
                )

        return candidates
