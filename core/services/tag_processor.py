"""
Tag processing utilities extracted from JSONRouter.

This module centralizes tag parsing/extraction so routing, APIs, and tools
share the exact same logic. Keep functions small and dependency‑free so they
can be reused without pulling router internals.
"""
from __future__ import annotations

from typing import List
import re


def extract_complete_segments(model_name: str) -> List[str]:
    """Extract complete core segments from a model name.

    Examples:
    - "qwen/qwen3-235b-a22b:free" -> ["qwen3-235b-a22b"]
    - "anthropic/claude-3-haiku-20240307:free" -> ["claude-3-haiku-20240307", "claude-3-haiku"]
    """
    if not model_name or not isinstance(model_name, str):
        return []

    main_separators = r"[/:@]"
    segments = re.split(main_separators, model_name)

    complete_segments: List[str] = []
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        segment_lower = segment.lower()

        provider_prefixes = [
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
        ]
        if segment_lower in provider_prefixes:
            continue

        suffix_tags = [
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
        ]
        if segment_lower in suffix_tags:
            continue

        if len(segment) <= 1:
            continue

        if len(segment) >= 3 and re.search(r"[a-zA-Z]", segment) and re.search(r"[\d\-]", segment):
            complete_segments.append(segment_lower)

            # Handle date suffix variants: -YYYYMMDD, -YYYYMM, -YYYY-MM-DD
            date_pattern = r"-(\d{8}|\d{6}|\d{4}-\d{2}-\d{2}|\d{4}\d{2}\d{2})$"
            match = re.search(date_pattern, segment_lower)
            if match:
                segment_without_date = segment_lower[: match.start()]
                if len(segment_without_date) >= 3 and segment_without_date not in complete_segments:
                    complete_segments.append(segment_without_date)

    return complete_segments


def extract_tags_from_model_name(model_name: str) -> List[str]:
    """Extract tags from model name, including core complete segments.

    Uses separators: ':', '/', '@', '-', '_', ','.
    """
    if not model_name or not isinstance(model_name, str):
        return []

    complete_segments = extract_complete_segments(model_name)
    separators = r"[/:@\-_,]"
    parts = re.split(separators, model_name.lower())

    split_tags: List[str] = []
    for part in parts:
        part = part.strip()
        if part and len(part) > 1:
            split_tags.append(part)

    # Keep order and deduplicate
    all_tags = list(dict.fromkeys(split_tags + complete_segments))
    return all_tags


def extract_tags_with_aliases(model_name: str, channel) -> List[str]:
    """Extract tags with channel alias enrichment.

    If channel defines model_aliases mapping from standard names to
    channel-specific names, include tags derived from matched aliases.
    """
    base_tags = extract_tags_from_model_name(model_name)
    if not hasattr(channel, "model_aliases") or not channel.model_aliases:
        return base_tags

    alias_tags: List[str] = []
    for standard_name, channel_specific_name in channel.model_aliases.items():
        if model_name.lower() == str(channel_specific_name).lower():
            alias_tags.extend(extract_tags_from_model_name(standard_name))
        elif any(
            tag in model_name.lower()
            for tag in extract_tags_from_model_name(standard_name)
        ):
            alias_tags.extend(extract_tags_from_model_name(standard_name))

    # Merge and deduplicate while keeping order
    all_tags = list(dict.fromkeys(base_tags + alias_tags))
    return all_tags

