"""Candidate discovery orchestration."""

from __future__ import annotations

import logging

from core.router.mixins.parameter import ParameterComparisonMixin
from core.router.mixins.tag import TagRoutingMixin
from core.router.types import ChannelCandidate, RoutingRequest

logger = logging.getLogger(__name__)


class CandidateDiscoveryMixin(ParameterComparisonMixin, TagRoutingMixin):
    """Combines parameter and tag based routing to produce channel candidates."""

    def __init__(self):
        super().__init__()
        self.config_loader = None

    def _get_candidate_channels(
        self, request: RoutingRequest
    ) -> list[ChannelCandidate]:
        parameter_candidates = self._get_parameter_comparison_candidates(request)
        if parameter_candidates is not None:
            return parameter_candidates

        tag_candidates = self._handle_tag_queries(request)
        if tag_candidates is not None:
            return tag_candidates

        all_enabled_channels = self.config_loader.get_enabled_channels()

        physical_candidates: list[ChannelCandidate] = []
        for channel in all_enabled_channels:
            try:
                discovered_info = self._get_discovered_info(channel)  # type: ignore[attr-defined]
            except AttributeError:
                discovered_info = self.config_loader.get_model_cache_by_channel(
                    channel.id
                )

            models_data = (
                discovered_info.get("models_data", {})
                if isinstance(discovered_info, dict)
                else {}
            )

            if isinstance(
                discovered_info, dict
            ) and request.model in discovered_info.get("models", []):
                real_model_id = request.model
                if models_data and request.model in models_data:
                    model_info = models_data[request.model]
                    real_model_id = model_info.get("id", request.model)

                logger.debug(
                    "PHYSICAL MODEL: Found '%s' -> '%s' in channel '%s'",
                    request.model,
                    real_model_id,
                    channel.name,
                )
                physical_candidates.append(
                    ChannelCandidate(channel=channel, matched_model=real_model_id)
                )

        complete_segment_candidates = self._get_candidate_channels_by_complete_segment(
            [request.model.lower()]
        )
        if complete_segment_candidates:
            logger.info(
                "COMPLETE SEGMENT MATCHING: Found %s candidate channels using complete segment match",
                len(complete_segment_candidates),
            )

        all_candidates = physical_candidates.copy()
        for segment_candidate in complete_segment_candidates:
            if not any(
                c.channel.id == segment_candidate.channel.id
                and c.matched_model == segment_candidate.matched_model
                for c in all_candidates
            ):
                all_candidates.append(segment_candidate)

        if all_candidates:
            logger.info(
                "MODEL MATCHING SUCCESS: Found %s candidates for '%s' (physical: %s, complete-segment: %s)",
                len(all_candidates),
                request.model,
                len(physical_candidates),
                len(complete_segment_candidates),
            )
            return all_candidates

        config_candidates = self._lookup_configured_channels(request)
        if config_candidates:
            return config_candidates

        logger.warning(
            "NO MATCH: No channels found for model '%s' (tried physical, auto-tag, and config)",
            request.model,
        )
        return []

    def _lookup_configured_channels(
        self, request: RoutingRequest
    ) -> list[ChannelCandidate] | None:
        config_channels = self.config_loader.get_channels_by_model(request.model)
        if not config_channels:
            return None

        logger.info(
            "CONFIG FALLBACK: Found %s channels in configuration for model '%s'",
            len(config_channels),
            request.model,
        )
        config_candidates: list[ChannelCandidate] = []
        for ch in config_channels:
            real_model_id = request.model
            try:
                discovered_info = self._get_discovered_info(ch)  # type: ignore[attr-defined]
            except AttributeError:
                discovered_info = self.config_loader.get_model_cache_by_channel(ch.id)
            models_data = (
                discovered_info.get("models_data", {})
                if isinstance(discovered_info, dict)
                else {}
            )
            if models_data and request.model in models_data:
                model_info = models_data[request.model]
                real_model_id = model_info.get("id", request.model)

            config_candidates.append(
                ChannelCandidate(channel=ch, matched_model=real_model_id)
            )
        return config_candidates
