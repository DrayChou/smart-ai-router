"""Size filter utilities for tag-based routing."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from core.router.types import ChannelCandidate
from core.utils.model_analyzer import get_model_analyzer
from core.yaml_config import get_yaml_config_loader

logger = logging.getLogger(__name__)


@dataclass
class SizeFilter:
    """Represents a size constraint for parameter or context length."""

    operator: str  # >, <, >=, <=, =
    value: float
    unit: str  # b, m, k for parameters; ki/ko/mi/mo for context
    filter_type: str  # 'params', 'input_context', 'output_context'

    def matches(self, target_value: float) -> bool:
        if target_value is None:
            return False
        if self.operator == ">":
            return target_value > self.value
        if self.operator == "<":
            return target_value < self.value
        if self.operator == ">=":
            return target_value >= self.value
        if self.operator == "<=":
            return target_value <= self.value
        if self.operator == "=":
            return abs(target_value - self.value) < 1e-6
        return False


_PARAM_PATTERN = re.compile(r"^([><=]+)(\d+\.?\d*)([bmk])$", re.IGNORECASE)
_CONTEXT_PATTERN = re.compile(r"^([><=]+)(\d+\.?\d*)([kK]?[iI]|[mM]?[oO])$")


def parse_size_filter(tag: str) -> Optional[SizeFilter]:
    """Parse expressions like ">20b" or "<8ko" into SizeFilter objects."""
    param_match = _PARAM_PATTERN.match(tag)
    if param_match:
        operator, value_str, unit = param_match.groups()
        try:
            value = float(value_str)
        except ValueError:
            return None
        return SizeFilter(operator=operator, value=value, unit=unit, filter_type="params")

    context_match = _CONTEXT_PATTERN.match(tag)
    if context_match:
        operator, value_str, unit = context_match.groups()
        try:
            value = float(value_str)
        except ValueError:
            return None
        normalized = unit.lower()
        filter_type = "input_context" if normalized.endswith("i") else "output_context"
        return SizeFilter(operator=operator, value=value, unit=unit, filter_type=filter_type)

    return None


def apply_size_filters(candidates: List[ChannelCandidate], size_filters: List[SizeFilter]) -> List[ChannelCandidate]:
    """Apply size filters to channel candidates."""
    if not size_filters:
        return candidates

    analyzer = get_model_analyzer()
    config_loader = get_yaml_config_loader()

    filtered: List[ChannelCandidate] = []

    for candidate in candidates:
        channel = candidate.channel
        model_name = candidate.matched_model or channel.model_name
        model_analysis = analyzer.get_model_analysis(channel.id, model_name)

        if not model_analysis:
            # Try to pull from discovery cache as fallback
            discovery = config_loader.get_model_cache_by_channel(channel.id)
            if isinstance(discovery, dict):
                models_data = discovery.get("models_data", {})
                model_analysis = models_data.get(model_name, {})

        if not model_analysis:
            logger.debug("SIZE FILTER: Missing analysis for %s@%s", model_name, channel.id)
            continue

        if _matches_all_filters(model_analysis, size_filters):
            filtered.append(candidate)

    return filtered


def _matches_all_filters(model_data: dict, size_filters: List[SizeFilter]) -> bool:
    for filter_obj in size_filters:
        if filter_obj.filter_type == "params":
            param_count = model_data.get("parameter_count")
            if param_count is None:
                return False
            value = _convert_parameters(param_count, filter_obj.unit)
        else:
            context_key = (
                "max_input_tokens" if filter_obj.filter_type == "input_context" else "max_output_tokens"
            )
            context_size = model_data.get(context_key) or model_data.get("context_length")
            if context_size is None:
                return False
            value = _convert_context(context_size, filter_obj.unit)

        if not filter_obj.matches(value):
            return False

    return True


def _convert_parameters(raw_value: float, unit: str) -> float:
    unit_lower = unit.lower()
    if unit_lower == "b":
        return raw_value / 1e9
    if unit_lower == "m":
        return raw_value / 1e6
    if unit_lower == "k":
        return raw_value / 1e3
    return raw_value


def _convert_context(raw_value: float, unit: str) -> float:
    unit_lower = unit.lower()
    if unit_lower in {"ki", "i", "ko", "o"}:
        return raw_value / 1000.0
    if unit_lower in {"mi", "mo"}:
        return raw_value / 1e6
    return raw_value


__all__ = ["SizeFilter", "parse_size_filter", "apply_size_filters"]
