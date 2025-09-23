"""Shared routing data structures for Smart AI Router."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.config_models import Channel


@dataclass
class RoutingScore:
    """Represents the scoring result for a channel candidate."""

    channel: Channel
    total_score: float
    cost_score: float
    speed_score: float
    quality_score: float
    reliability_score: float
    reason: str
    matched_model: str | None = None
    parameter_score: float = 0.0
    context_score: float = 0.0
    free_score: float = 0.0


@dataclass
class ChannelCandidate:
    """Wrapped channel candidate along with the matched model name."""

    channel: Channel
    matched_model: str | None = None


@dataclass
class RoutingRequest:
    """Incoming routing request information used by the router."""

    model: str
    messages: list[dict[str, Any]]
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    functions: list[dict[str, Any]] | None = None
    required_capabilities: list[str] = None
    data: dict[str, Any] | None = None
    strategy: str | None = None
