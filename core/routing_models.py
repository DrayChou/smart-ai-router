"""Compatibility layer for legacy imports of routing data classes."""
from __future__ import annotations

from core.router.types import (
    ChannelCandidate as RoutingChannelCandidate,
    RoutingRequest as RoutingRoutingRequest,
    RoutingScore as RoutingRoutingScore,
)

RoutingRequest = RoutingRoutingRequest
RoutingScore = RoutingRoutingScore
ChannelCandidate = RoutingChannelCandidate

__all__ = ["RoutingRequest", "RoutingScore", "ChannelCandidate"]
