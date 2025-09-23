"""Routing API integration built on the consolidated JSONRouter."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from core.json_router import RoutingRequest, get_router
from core.services import get_cache_service, get_config_service, get_router_service
from core.yaml_config import get_yaml_config_loader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["routing"])
_router_service = get_router_service()
_config_loader = get_yaml_config_loader()


def _build_routing_request(payload: Dict[str, Any]) -> RoutingRequest:
    return RoutingRequest(
        model=payload.get("model", ""),
        messages=payload.get("messages", []),
        temperature=payload.get("temperature"),
        max_tokens=payload.get("max_tokens"),
        stream=bool(payload.get("stream", False)),
        functions=payload.get("functions"),
        required_capabilities=payload.get("required_capabilities") or [],
        data=payload,
        strategy=payload.get("strategy"),
    )


@router.post("/chat/completions")
async def chat_completions(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """OpenAI-compatible chat completion routing endpoint."""
    routing_request = _build_routing_request(request_data)
    scores = await _router_service.route_request(routing_request)
    if not scores:
        raise HTTPException(
            status_code=404,
            detail=f"No available channels found for model: {routing_request.model}",
        )

    best = scores[0]
    channel = best.channel
    now = datetime.now()

    response: Dict[str, Any] = {
        "id": f"chatcmpl-{now.strftime('%Y%m%d%H%M%S')}",
        "object": "chat.completion",
        "created": int(now.timestamp()),
        "model": routing_request.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": f"Routed to channel: {channel.name or channel.id}",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "routing_info": {
            "channel_id": channel.id,
            "channel_name": channel.name,
            "provider": channel.provider,
            "matched_model": best.matched_model or routing_request.model,
            "total_score": best.total_score,
            "cost_score": best.cost_score,
            "speed_score": best.speed_score,
            "quality_score": best.quality_score,
            "reliability_score": best.reliability_score,
            "alternatives": len(scores) - 1,
        },
    }

    return response


@router.get("/models")
async def list_models() -> Dict[str, Any]:
    """Return a simple list of available models and tags."""
    json_router = get_router()
    models = json_router.get_available_models()
    now = int(datetime.now().timestamp())

    model_objects = [
        {
            "id": model_id,
            "object": "model",
            "created": now,
            "owned_by": "smart-ai-router",
        }
        for model_id in models
    ]

    return {"object": "list", "data": model_objects, "total_models": len(model_objects)}


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    now = datetime.now()
    return {"status": "healthy", "timestamp": now.isoformat(), "version": "0.3.0"}


@router.get("/admin/config")
async def get_config_summary() -> Dict[str, Any]:
    config_service = get_config_service()
    return config_service.get_config_summary()


@router.get("/admin/cache/stats")
async def get_cache_stats() -> Dict[str, Any]:
    cache_service = get_cache_service()
    return cache_service.get_cache_stats()


@router.post("/admin/cache/clear")
async def clear_cache(
    namespace: Optional[str] = None, background_tasks: Optional[BackgroundTasks] = None
) -> Dict[str, Any]:
    cache_service = get_cache_service()
    target_namespace = namespace or "default"
    await cache_service.clear_namespace(target_namespace)
    if namespace:
        message = f"Cleared cache namespace: {namespace}"
    else:
        message = "Cleared default cache namespace"

    return {
        "status": "success",
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/admin/routing/strategies")
async def get_routing_strategies() -> Dict[str, Any]:
    routing_config = getattr(_config_loader.config, "routing", None)
    custom_strategies = {}
    default_strategies = [
        "cost_first",
        "free_first",
        "local_first",
        "cost_optimized",
        "speed_optimized",
        "quality_optimized",
        "balanced",
    ]

    if routing_config and getattr(routing_config, "sorting_strategies", None):
        custom_strategies = routing_config.sorting_strategies

    return {
        "available_strategies": default_strategies + list(custom_strategies.keys()),
        "custom_strategies": custom_strategies,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/admin/routing/test")
async def test_routing(request_data: Dict[str, Any]) -> Dict[str, Any]:
    routing_request = _build_routing_request(request_data)
    scores = await _router_service.route_request(routing_request)

    formatted = [
        {
            "channel_id": score.channel.id,
            "channel_name": score.channel.name,
            "provider": score.channel.provider,
            "matched_model": score.matched_model or routing_request.model,
            "total_score": score.total_score,
            "cost_score": score.cost_score,
            "speed_score": score.speed_score,
            "quality_score": score.quality_score,
            "reliability_score": score.reliability_score,
            "parameter_score": score.parameter_score,
            "context_score": score.context_score,
            "free_score": score.free_score,
        }
        for score in scores
    ]

    return {
        "request": {
            "model": routing_request.model,
            "strategy": routing_request.strategy,
        },
        "results": formatted,
        "result_count": len(formatted),
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/admin/channels")
async def get_channels_info() -> Dict[str, Any]:
    channels = _config_loader.get_enabled_channels()
    channel_info: List[Dict[str, Any]] = []

    for channel in channels:
        channel_info.append(
            {
                "id": channel.id,
                "name": channel.name,
                "provider": channel.provider,
                "enabled": channel.enabled,
                "priority": getattr(channel, "priority", None),
                "tags": getattr(channel, "tags", []),
            }
        )

    return {
        "channels": channel_info,
        "total_channels": len(channel_info),
        "timestamp": datetime.now().isoformat(),
    }


__all__ = ["router"]
