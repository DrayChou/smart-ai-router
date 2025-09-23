"""Shared routing data structures for Smart AI Router."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

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
    matched_model: Optional[str] = None
    parameter_score: float = 0.0
    context_score: float = 0.0
    free_score: float = 0.0


@dataclass
class ChannelCandidate:
    """Wrapped channel candidate along with the matched model name."""

    channel: Channel
    matched_model: Optional[str] = None


@dataclass
class RoutingRequest:
    """Incoming routing request information used by the router."""

    model: str
    messages: list[dict[str, Any]]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    functions: Optional[list[dict[str, Any]]] = None
    required_capabilities: list[str] = None
    data: Optional[dict[str, Any]] = None
    strategy: Optional[str] = None
