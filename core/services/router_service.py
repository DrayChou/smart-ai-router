"""Router service wrapper built on the modern JSONRouter."""

from __future__ import annotations

import logging

from core.json_router import JSONRouter, RoutingRequest, RoutingScore, get_router
from core.yaml_config import YAMLConfigLoader, get_yaml_config_loader

logger = logging.getLogger(__name__)


class RouterService:
    """Thin service layer that delegates to the shared JSONRouter instance."""

    def __init__(
        self,
        config_loader: YAMLConfigLoader | None = None,
        router: JSONRouter | None = None,
    ) -> None:
        self.config_loader = config_loader or get_yaml_config_loader()
        self.router = router or get_router()
        logger.debug("RouterService initialised with YAML configuration loader")

    async def route_request(self, request: RoutingRequest) -> list[RoutingScore]:
        """Route a request using the consolidated JSONRouter."""
        logger.debug("Routing request via RouterService: model=%s", request.model)
        return await self.router.route_request(request)

    def get_available_models(self) -> list[str]:
        """Expose JSONRouter's available model list (including tag:* entries)."""
        return self.router.get_available_models()

    def get_channel_info(self, channel_id: str) -> dict | None:
        """Return basic channel information from the loaded configuration."""
        channel = self.config_loader.get_channel_by_id(channel_id)
        if not channel:
            return None

        return {
            "id": channel.id,
            "name": channel.name,
            "provider": channel.provider,
            "priority": getattr(channel, "priority", None),
            "tags": getattr(channel, "tags", []),
            "enabled": channel.enabled,
        }


_global_router_service: RouterService | None = None


def get_router_service() -> RouterService:
    """Provide a shared RouterService instance."""
    global _global_router_service
    if _global_router_service is None:
        _global_router_service = RouterService()
    return _global_router_service


__all__ = ["RouterService", "get_router_service"]
