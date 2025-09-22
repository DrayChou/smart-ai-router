"""Tag-based routing helpers."""
from __future__ import annotations

import logging
import re
from typing import Optional

from core.config_models import Channel
from core.router.types import ChannelCandidate, RoutingRequest
from core.routing.exceptions import TagNotFoundError
from core.routing.size_filters import apply_size_filters, parse_size_filter

logger = logging.getLogger(__name__)


class TagRoutingMixin:
    """Provides helpers for tag-oriented routing queries."""

    def _handle_tag_queries(self, request: RoutingRequest) -> Optional[list[ChannelCandidate]]:
        if "," in request.model and not request.model.startswith("tag:") and not request.model.startswith("tags:"):
            return self._process_tag_sequence(request.model)

        if request.model.startswith("tag:") or request.model.startswith("tags:"):
            prefix = "tag:" if request.model.startswith("tag:") else "tags:"
            tag_query = request.model.split(":", 1)[1]
            return self._process_explicit_tag_query(tag_query, prefix)

        return None

    def _process_tag_sequence(self, query: str) -> list[ChannelCandidate]:
        logger.info("IMPLICIT TAG QUERY: Detected comma-separated query '%s'", query)
        tag_parts = [tag.strip() for tag in query.split(",") if tag.strip()]
        positive_tags: list[str] = []
        negative_tags: list[str] = []

        for tag_part in tag_parts:
            if tag_part.startswith("!"):
                negative_tags.append(tag_part[1:].lower())
            else:
                size_filter = parse_size_filter(tag_part)
                if not size_filter:
                    positive_tags.append(tag_part.lower())

        logger.info("IMPLICIT TAG ROUTING: positive=%s, negative=%s", positive_tags, negative_tags)
        candidates = self._get_candidate_channels_by_auto_tags(positive_tags, negative_tags)
        if not candidates:
            logger.error("IMPLICIT TAG NOT FOUND: No models for %s excluding %s", positive_tags, negative_tags)
            raise TagNotFoundError(positive_tags + [f"!{tag}" for tag in negative_tags])

        size_filters = [
            sf
            for tag_part in tag_parts
            if not tag_part.startswith("!")
            for sf in [parse_size_filter(tag_part)]
            if sf
        ]
        if size_filters:
            logger.info(
                "SIZE FILTERS: Applying %s filters: %s",
                len(size_filters),
                [f"{sf.operator}{sf.value}{sf.unit}" for sf in size_filters],
            )
            filtered_candidates = apply_size_filters(candidates, size_filters)
            logger.info(
                "SIZE FILTERS: Filtered from %s to %s candidates",
                len(candidates),
                len(filtered_candidates),
            )
            candidates = filtered_candidates

        if not candidates:
            logger.error("SIZE FILTERS: No candidates left after applying size filters")
            raise TagNotFoundError(positive_tags + [f"!{tag}" for tag in negative_tags])

        logger.info("IMPLICIT TAG ROUTING: Found %s candidate channels", len(candidates))
        return candidates

    def _process_explicit_tag_query(self, query: str, prefix: str) -> list[ChannelCandidate]:
        if "," in query:
            tag_parts = [tag.strip() for tag in query.split(",") if tag.strip()]
            positive_tags: list[str] = []
            negative_tags: list[str] = []

            for tag_part in tag_parts:
                if tag_part.startswith("!"):
                    negative_tags.append(tag_part[1:].lower())
                else:
                    size_filter = parse_size_filter(tag_part)
                    if not size_filter:
                        positive_tags.append(tag_part.lower())

            logger.info(
                "TAG ROUTING: Processing multi-tag query '%s' -> positive: %s, negative: %s (prefix: %s)",
                query,
                positive_tags,
                negative_tags,
                prefix,
            )
            candidates = self._get_candidate_channels_by_auto_tags(positive_tags, negative_tags)
            if not candidates:
                logger.error("TAG NOT FOUND: No models found matching tags %s excluding %s", positive_tags, negative_tags)
                raise TagNotFoundError(positive_tags + [f"!{tag}" for tag in negative_tags])

            size_filters = [
                sf
                for tag_part in tag_parts
                if not tag_part.startswith("!")
                for sf in [parse_size_filter(tag_part)]
                if sf
            ]
            if size_filters:
                logger.info(
                    "SIZE FILTERS: Applying %s size filters: %s",
                    len(size_filters),
                    [f"{sf.operator}{sf.value}{sf.unit}" for sf in size_filters],
                )
                filtered_candidates = apply_size_filters(candidates, size_filters)
                logger.info(
                    "SIZE FILTERS: Filtered from %s to %s candidates",
                    len(candidates),
                    len(filtered_candidates),
                )
                candidates = filtered_candidates

            if not candidates:
                logger.error("SIZE FILTERS: No candidates left after applying size filters")
                raise TagNotFoundError(positive_tags + [f"!{tag}" for tag in negative_tags])

            logger.info("TAG ROUTING: Multi-tag query found %s candidate channels", len(candidates))
            return candidates

        tag_part = query.strip()
        if tag_part.startswith("!"):
            negative_tag = tag_part[1:].lower()
            logger.info(
                "TAG ROUTING: Processing negative tag query '%s' -> excluding: '%s' (prefix: %s)",
                query,
                negative_tag,
                prefix,
            )
            candidates = self._get_candidate_channels_by_auto_tags([], [negative_tag])
        else:
            size_filter = parse_size_filter(tag_part)
            if size_filter:
                logger.info(
                    "TAG ROUTING: Processing size filter query '%s' -> filter: '%s' (prefix: %s)",
                    query,
                    tag_part,
                    prefix,
                )
                candidates = self._get_candidate_channels_by_auto_tags([], [])
                filtered_candidates = apply_size_filters(candidates, [size_filter])
                logger.info(
                    "SIZE FILTERS: Filtered from %s to %s candidates",
                    len(candidates),
                    len(filtered_candidates),
                )
                candidates = filtered_candidates
            else:
                tag = tag_part.lower()
                logger.info(
                    "TAG ROUTING: Processing single tag query '%s' -> tag: '%s' (prefix: %s)",
                    query,
                    tag,
                    prefix,
                )
                candidates = self._get_candidate_channels_by_auto_tags([tag], [])

        if not candidates:
            logger.error("TAG NOT FOUND: No models found for query '%s'", query)
            raise TagNotFoundError([query])
        logger.info("TAG ROUTING: Found %s candidate channels", len(candidates))
        return candidates

    def _get_candidate_channels_by_auto_tags(
        self,
        positive_tags: list[str],
        negative_tags: Optional[list[str]] = None,
    ) -> list[ChannelCandidate]:
        if negative_tags is None:
            negative_tags = []

        if not positive_tags and not negative_tags:
            return []

        normalized_positive = [tag.lower().strip() for tag in positive_tags if tag and isinstance(tag, str)]
        normalized_negative = [tag.lower().strip() for tag in negative_tags if tag and isinstance(tag, str)]

        logger.info(
            "TAG MATCHING: Searching for channels with positive tags: %s, excluding: %s",
            normalized_positive,
            normalized_negative,
        )

        model_cache = self.config_loader.get_model_cache()
        if not model_cache:
            logger.warning("TAG MATCHING: Model cache is empty, cannot perform tag routing")
            return []

        has_api_key_format = any('_' in key and len(key.split('_')[-1]) == 8 for key in model_cache.keys())
        if has_api_key_format:
            logger.info("TAG MATCHING: Using API key-level cache format with %s entries", len(model_cache))
        else:
            logger.info("TAG MATCHING: Using legacy cache format with %s entries", len(model_cache))

        candidates: list[ChannelCandidate] = []
        matched_models = []

        for cache_key, discovery_data in model_cache.items():
            if not isinstance(discovery_data, dict):
                continue

            channel_id = self._extract_channel_id(cache_key)
            if not channel_id:
                continue

            channel = self.config_loader.get_channel_by_id(channel_id)
            if not channel or not channel.enabled:
                continue

            models = discovery_data.get("models", [])
            models_data = discovery_data.get("models_data", {})

            for model_name in models:
                if not model_name:
                    continue

                model_tags = self._extract_tags_with_aliases(model_name, channel)
                combined_tags = set(tag.lower() for tag in model_tags)

                if all(tag in combined_tags for tag in normalized_positive) and not any(
                    tag in combined_tags for tag in normalized_negative
                ):
                    matched_models.append((channel.name, model_name))
                    matched_model_id = model_name
                    if models_data and model_name in models_data:
                        model_info = models_data[model_name]
                        matched_model_id = model_info.get("id", model_name)

                    candidates.append(ChannelCandidate(channel=channel, matched_model=matched_model_id))

        if matched_models:
            logger.info(
                "🎯 TOTAL MATCHED MODELS: %s models found: %s%s",
                len(matched_models),
                matched_models[:5],
                '...' if len(matched_models) > 5 else '',
            )

        return candidates

    def _get_candidate_channels_by_complete_segment(self, complete_segments: list[str]) -> list[ChannelCandidate]:
        normalized_segments = [segment.lower().strip() for segment in complete_segments if segment]
        logger.info("COMPLETE SEGMENT MATCHING: Searching for segments %s", normalized_segments)

        candidates: list[ChannelCandidate] = []
        model_cache = self.config_loader.get_model_cache()
        if not model_cache:
            logger.warning("COMPLETE SEGMENT MATCHING: Model cache is empty")
            return []

        for cache_key, discovery_data in model_cache.items():
            if not isinstance(discovery_data, dict):
                continue

            channel_id = self._extract_channel_id(cache_key)
            if not channel_id:
                continue

            channel = self.config_loader.get_channel_by_id(channel_id)
            if not channel or not channel.enabled:
                continue

            models = discovery_data.get("models", [])
            models_data = discovery_data.get("models_data", {})

            for model_name in models:
                model_tags = self._extract_tags_from_model_name(model_name)
                if any(segment in (tag.lower() for tag in model_tags) for segment in normalized_segments):
                    real_model_id = model_name
                    if models_data and model_name in models_data:
                        model_info = models_data[model_name]
                        real_model_id = model_info.get("id", model_name)

                    candidates.append(ChannelCandidate(channel=channel, matched_model=real_model_id))
                    break

        logger.info("COMPLETE SEGMENT MATCHING: Found %s candidates for segments %s", len(candidates), normalized_segments)
        return candidates

    def _find_channels_with_all_tags(self, tags: list[str], model_cache: dict) -> list[ChannelCandidate]:
        candidate_channels: list[ChannelCandidate] = []
        has_free_tag = any(tag.lower() in {"free", "免费", "0cost", "nocost"} for tag in tags)

        for channel in self.config_loader.get_enabled_channels():
            try:
                discovered_info = self._get_discovered_info(channel)  # type: ignore[attr-defined]
            except AttributeError:
                discovered_info = self.config_loader.get_model_cache_by_channel(channel.id)
            if not isinstance(discovered_info, dict):
                continue

            models = discovered_info.get("models", [])
            if not models:
                continue

            channel_tags = getattr(channel, 'tags', []) or []
            normalized_query_tags = [tag.lower() for tag in tags]

            for model_name in models:
                if not model_name:
                    continue

                model_tags = self._extract_tags_with_aliases(model_name, channel)
                combined_tags = list(set([tag.lower() for tag in channel_tags] + [tag.lower() for tag in model_tags]))

                if all(tag in combined_tags for tag in normalized_query_tags):
                    if has_free_tag:
                        free_score = self._calculate_free_score(channel, model_name)
                        if free_score < 0.9:
                            logger.debug(
                                "FREE TAG VALIDATION FAILED: Channel '%s' model '%s' has free_score=%.2f < 0.9",
                                channel.name,
                                model_name,
                                free_score,
                            )
                            continue

                    candidate_channels.append(ChannelCandidate(channel=channel, matched_model=model_name))
                    break

        return candidate_channels

    def _find_channels_with_positive_negative_tags(
        self,
        positive_tags: list[str],
        negative_tags: list[str],
        model_cache: dict,
    ) -> list[ChannelCandidate]:
        candidate_channels: list[ChannelCandidate] = []

        for channel in self.config_loader.get_enabled_channels():
            try:
                discovered_info = self._get_discovered_info(channel)  # type: ignore[attr-defined]
            except AttributeError:
                discovered_info = self.config_loader.get_model_cache_by_channel(channel.id)
            if not isinstance(discovered_info, dict):
                continue

            models = discovered_info.get("models", [])
            if not models:
                continue

            channel_tags = getattr(channel, 'tags', []) or []
            for model_name in models:
                if not model_name:
                    continue

                model_tags = self._extract_tags_with_aliases(model_name, channel)
                combined_tags = list(set([tag.lower() for tag in channel_tags] + [tag.lower() for tag in model_tags]))

                if all(tag.lower() in combined_tags for tag in positive_tags) and not any(
                    tag.lower() in combined_tags for tag in negative_tags
                ):
                    candidate_channels.append(ChannelCandidate(channel=channel, matched_model=model_name))
                    break

        return candidate_channels

    def _get_discovered_info(self, channel: Channel) -> dict:
        try:
            api_key = getattr(channel, "api_key", None) or ""
            if api_key:
                info = self.config_loader.get_model_cache_by_channel_and_key(channel.id, api_key)
                if isinstance(info, dict):
                    return info
        except Exception:
            pass
        try:
            info = self.config_loader.get_model_cache_by_channel(channel.id)
            return info if isinstance(info, dict) else {}
        except Exception:
            return {}

    def _resolve_model_aliases(self, model_name: str, channel) -> str:
        if not model_name or not hasattr(channel, 'model_aliases'):
            return model_name

        if channel.model_aliases and model_name in channel.model_aliases:
            resolved_name = channel.model_aliases[model_name]
            logger.debug("ALIAS RESOLVED: '%s' -> '%s' for channel %s", model_name, resolved_name, channel.id)
            return resolved_name

        model_lower = model_name.lower()
        for alias_key, alias_value in channel.model_aliases.items():
            if alias_key.lower() == model_lower:
                logger.debug("ALIAS RESOLVED (case-insensitive): '%s' -> '%s' for channel %s", model_name, alias_value, channel.id)
                return alias_value

        if '/' in model_name:
            _, base_name = model_name.rsplit('/', 1)
            if base_name in channel.model_aliases:
                resolved_name = channel.model_aliases[base_name]
                logger.debug("ALIAS RESOLVED (prefix): '%s' -> '%s' for channel %s", model_name, resolved_name, channel.id)
                return resolved_name

        return model_name

    def _extract_tags_with_aliases(self, model_name: str, channel) -> list[str]:
        try:
            from core.services.tag_processor import extract_tags_with_aliases as _with_alias

            return _with_alias(model_name, channel)
        except Exception:
            return self._extract_tags_from_model_name(model_name)

    def _extract_tags_from_model_name(self, model_name: str) -> list[str]:
        if not model_name or not isinstance(model_name, str):
            return []

        separators = r"[/:@\-_,]"
        parts = re.split(separators, model_name.lower())
        tags = [part.strip() for part in parts if part.strip() and len(part.strip()) > 1]

        complete_segments = self._extract_complete_segments(model_name)
        all_tags = list(dict.fromkeys(tags + complete_segments))
        return all_tags

    def _extract_complete_segments(self, model_name: str) -> list[str]:
        if not model_name or not isinstance(model_name, str):
            return []

        main_separators = r"[/:@]"
        segments = re.split(main_separators, model_name)

        complete_segments: list[str] = []
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue

            segment_lower = segment.lower()
            provider_prefixes = {
                "openai",
                "anthropic",
                "qwen",
                "deepseek",
                "google",
                "meta",
                "mistral",
                "cohere",
                "groq",
                "together",
                "fireworks",
                "siliconflow",
                "moonshot",
                "ollama",
                "lmstudio",
            }
            if segment_lower in provider_prefixes:
                continue

            suffix_tags = {
                "free",
                "pro",
                "premium",
                "paid",
                "api",
                "chat",
                "instruct",
                "base",
                "tuned",
                "finetune",
                "ft",
                "sft",
                "rlhf",
                "dpo",
            }
            if segment_lower in suffix_tags:
                continue

            if len(segment) <= 1:
                continue

            if len(segment) >= 3 and re.search(r"[a-zA-Z]", segment) and re.search(r"[\d\-]", segment):
                complete_segments.append(segment_lower)

                date_pattern = r"-(\d{8}|\d{6}|\d{4}-\d{2}-\d{2}|\d{4}\d{2}\d{2})$"
                match = re.search(date_pattern, segment_lower)
                if match:
                    segment_without_date = segment_lower[: match.start()]
                    if len(segment_without_date) >= 3 and segment_without_date not in complete_segments:
                        complete_segments.append(segment_without_date)

        return complete_segments

    def _is_suitable_for_chat(self, model_name: str) -> bool:
        unsuitable_keywords = ["embedding", "search", "rerank", "tts", "image"]
        model_lower = model_name.lower()
        return not any(keyword in model_lower for keyword in unsuitable_keywords)

    def _extract_channel_id(self, cache_key: str) -> Optional[str]:
        if not cache_key:
            return None

        if '_' not in cache_key:
            return cache_key

        parts = cache_key.split('_')
        potential_hash = parts[-1]
        if len(potential_hash) == 8 and all(c in '0123456789abcdef' for c in potential_hash.lower()):
            return '_'.join(parts[:-1])
        return cache_key

    def get_available_models(self) -> list[str]:
        if self._available_models_cache is not None:
            return self._available_models_cache

        models = set()
        all_tags = set()

        for ch in self.config.channels:
            if ch.enabled and ch.model_name:
                models.add(ch.model_name)
                for tag in ch.tags:
                    if tag:
                        all_tags.add(f"tag:{tag}")

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
                        auto_tags = self._extract_tags_from_model_name(model_name)
                        for tag in auto_tags:
                            if tag:
                                all_tags.add(f"tag:{tag}")

        result = sorted(models | all_tags)
        self._available_models_cache = result
        return result

    def get_all_available_tags(self) -> list[str]:
        models = self.get_available_models()
        tags = [model[4:] for model in models if model.startswith("tag:")]
        return sorted(tags)

