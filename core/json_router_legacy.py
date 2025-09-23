"""
遗留版JSON路由器 - 兼容性封装
为了保持向后兼容性，保留原有的JSONRouter类接口
内部使用新的服务层架构
"""

import logging
from typing import Any, Optional

from .routing_models import RoutingRequest, RoutingScore
from .services import get_router_service
from .yaml_config import YAMLConfigLoader

logger = logging.getLogger(__name__)


class JSONRouter:
    """兼容性封装的JSONRouter类"""

    def __init__(self, config_loader: Optional[YAMLConfigLoader] = None):
        self.config_loader = config_loader
        self._router_service = get_router_service()
        logger.info("JSONRouter (兼容版) 初始化完成")

    async def route_request(self, request_data: dict[str, Any]) -> list[dict[str, Any]]:
        """路由请求 - 兼容原有接口"""
        try:
            # 转换请求格式
            routing_request = RoutingRequest(
                model=request_data.get("model", ""),
                messages=request_data.get("messages", []),
                temperature=request_data.get("temperature"),
                max_tokens=request_data.get("max_tokens"),
                stream=bool(request_data.get("stream", False)),
                functions=request_data.get("functions"),
                required_capabilities=request_data.get("required_capabilities") or [],
                data=request_data,
                strategy=request_data.get("strategy"),
            )

            # 调用新的服务层
            results = await self._router_service.route_request(routing_request)

            # 转换响应格式以保持兼容性
            return self._convert_results_to_legacy_format(results)

        except Exception as e:
            logger.error(f"路由请求失败: {e}")
            return []

    def _convert_results_to_legacy_format(
        self, results: list[RoutingScore]
    ) -> list[dict[str, Any]]:
        """将新格式结果转换为遗留格式"""
        legacy_results = []

        for score in results:
            legacy_result = {
                "channel_id": score.channel.id,
                "total_score": score.total_score,
                "scores": {
                    "cost_score": score.cost_score,
                    "speed_score": score.speed_score,
                    "quality_score": score.quality_score,
                    "reliability_score": score.reliability_score,
                    "parameter_score": score.parameter_score,
                    "context_score": score.context_score,
                    "free_score": score.free_score,
                },
                "estimated_cost": None,
                "estimated_tokens": None,
                "matched_model": score.matched_model,
            }
            legacy_results.append(legacy_result)

        return legacy_results


# 全局实例，保持与原版本的兼容性
_global_router: Optional[JSONRouter] = None


def get_router() -> JSONRouter:
    """获取全局路由器实例 - 兼容原有接口"""
    global _global_router
    if _global_router is None:
        _global_router = JSONRouter()
    return _global_router
