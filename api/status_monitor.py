# -*- coding: utf-8 -*-
"""
状态监控页面API和WebSocket接口
提供实时的系统状态、请求日志、渠道监控等功能
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from core.yaml_config import YAMLConfigLoader
from core.json_router import JSONRouter
from core.utils.model_channel_blacklist import get_model_blacklist_manager

logger = logging.getLogger(__name__)

# 请求日志存储（内存中保存最近1000条）
request_logs: List[Dict[str, Any]] = []
MAX_LOGS = 1000

# WebSocket连接管理
active_connections: List[WebSocket] = []

# 请求上下文存储（用于在请求期间传递渠道信息）
import threading

_request_context = threading.local()


class ModelSearchRequest(BaseModel):
    """模型搜索请求"""

    query: str
    max_results: Optional[int] = 50


class ChannelTestRequest(BaseModel):
    """渠道测试请求"""

    channel_id: str
    model_name: Optional[str] = None


def create_status_monitor_router(
    config_loader: YAMLConfigLoader, router: JSONRouter
) -> APIRouter:
    """创建状态监控路由"""

    api_router = APIRouter(prefix="/status", tags=["Status Monitor"])

    # 模板渲染器 - 使用不同的分隔符避免与Vue.js冲突
    from jinja2 import Environment, FileSystemLoader

    jinja_env = Environment(
        loader=FileSystemLoader("templates"),
        variable_start_string="[[",
        variable_end_string="]]",
        block_start_string="[%",
        block_end_string="%]",
    )
    templates = Jinja2Templates(env=jinja_env)

    @api_router.get("/", response_class=HTMLResponse)
    async def status_monitor_page(request: Request):
        """状态监控主页面"""
        return templates.TemplateResponse(
            "status_monitor.html",
            {"request": request, "title": "Smart AI Router - 状态监控"},
        )

    @api_router.get("/api/channels")
    async def get_channels_status():
        """获取所有渠道状态"""
        channels = config_loader.get_enabled_channels()
        blacklist_manager = get_model_blacklist_manager()

        channels_data = []
        for channel in channels:
            # 获取渠道健康状态
            health_score = 1.0  # 简化处理，固定健康分数

            # 获取黑名单模型数量
            blacklisted_models = blacklist_manager.get_blacklisted_models_for_channel(
                channel.id
            )

            # 估算总模型数（从缓存中获取）
            channel_cache = config_loader.get_model_cache_by_channel(channel.id)
            models = channel_cache.get("models", [])
            total_models = len(models)
            

            channels_data.append(
                {
                    "id": channel.id,
                    "name": channel.name,
                    "provider": channel.provider,
                    "enabled": channel.enabled,
                    "has_api_key": bool(channel.api_key),
                    "health_score": health_score,
                    "status": (
                        "healthy"
                        if health_score >= 0.7
                        else "degraded" if health_score >= 0.3 else "unhealthy"
                    ),
                    "total_models": total_models,
                    "blacklisted_models": len(blacklisted_models),
                    "available_models": total_models - len(blacklisted_models),
                    "priority": channel.priority,
                    "last_updated": datetime.now().isoformat(),
                }
            )

        return {
            "channels": channels_data,
            "total_channels": len(channels_data),
            "healthy_channels": sum(
                1 for c in channels_data if c["status"] == "healthy"
            ),
            "timestamp": datetime.now().isoformat(),
        }

    @api_router.get("/api/channels/{channel_id}/models")
    async def get_channel_models(channel_id: str):
        """获取指定渠道的模型列表"""
        channel_cache = config_loader.get_model_cache_by_channel(channel_id)
        models = channel_cache.get("models", [])
        

        blacklist_manager = get_model_blacklist_manager()
        blacklisted_models = blacklist_manager.get_blacklisted_models_for_channel(
            channel_id
        )

        models_data = []
        for model in models:
            # Handle both string and dict model formats
            if isinstance(model, str):
                model_name = model
                model_dict = {"name": model_name, "id": model_name}
            else:
                model_name = model.get("name", model.get("id", "unknown"))
                model_dict = model

            is_blacklisted, blacklist_entry = blacklist_manager.is_model_blacklisted(
                channel_id, model_name
            )

            model_info = {
                "name": model_name,
                "id": model_dict.get("id", model_name),
                "available": not is_blacklisted,
                "parameter_count": model_dict.get("parameter_count"),
                "context_length": model_dict.get("context_length"),
                "capabilities": model_dict.get("capabilities", {}),
                "pricing": {
                    "input": model_dict.get("input_price"),
                    "output": model_dict.get("output_price"),
                },
            }

            if is_blacklisted and blacklist_entry:
                model_info["blacklist_info"] = {
                    "error_type": blacklist_entry.error_type.value,
                    "remaining_time": blacklist_entry.get_remaining_time(),
                    "blacklisted_at": blacklist_entry.blacklisted_at.isoformat(),
                    "failure_count": blacklist_entry.failure_count,
                    "is_permanent": blacklist_entry.is_permanent,
                }

            models_data.append(model_info)

        return {
            "channel_id": channel_id,
            "models": models_data,
            "total_models": len(models_data),
            "available_models": sum(1 for m in models_data if m["available"]),
            "blacklisted_models": sum(1 for m in models_data if not m["available"]),
        }

    @api_router.post("/api/search")
    async def search_models(search_request: ModelSearchRequest):
        """搜索模型并返回路由顺序"""
        try:
            # 使用路由器进行模型搜索
            from core.json_router import RoutingRequest

            # 构建路由请求
            routing_request = RoutingRequest(
                model=search_request.query,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=10,
            )

            # 使用路由器进行路由评分
            routing_scores = await router.route_request(routing_request)

            if not routing_scores:
                return {
                    "query": search_request.query,
                    "matches": [],
                    "total_matches": 0,
                    "message": "未找到匹配的模型",
                }

            # 限制结果数量
            limited_scores = routing_scores[: search_request.max_results]

            # 构建详细的结果列表
            results = []
            blacklist_manager = get_model_blacklist_manager()

            for i, score in enumerate(limited_scores):
                channel = score.channel
                model_name = score.matched_model or search_request.query

                # 获取黑名单状态
                is_blacklisted, blacklist_entry = (
                    blacklist_manager.is_model_blacklisted(channel.id, model_name)
                )

                # 估算成本（简化版）
                estimated_cost = router._estimate_cost_for_channel(
                    channel, routing_request
                )

                result = {
                    "rank": i + 1,
                    "model_name": model_name,
                    "channel_id": channel.id,
                    "channel_name": channel.name,
                    "provider": channel.provider,
                    "priority": channel.priority,
                    "available": not is_blacklisted,
                    "health_score": 1.0,  # 简化处理
                    "cost_score": score.cost_score,
                    "speed_score": score.speed_score,
                    "quality_score": score.quality_score,
                    "total_score": score.total_score,
                    "estimated_cost": {
                        "total": estimated_cost,
                        "input": estimated_cost * 0.6,  # 估算输入成本占比
                        "output": estimated_cost * 0.4,  # 估算输出成本占比
                    },
                }

                if is_blacklisted and blacklist_entry:
                    result["blacklist_reason"] = blacklist_entry.error_type.value
                    result["blacklist_remaining"] = blacklist_entry.get_remaining_time()

                results.append(result)

            return {
                "query": search_request.query,
                "matches": results,
                "total_matches": len(routing_scores),
                "showing": len(limited_scores),
                "routing_strategy": "intelligent",
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"模型搜索失败: {e}")
            return {
                "query": search_request.query,
                "matches": [],
                "total_matches": 0,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    @api_router.get("/api/logs")
    async def get_request_logs(limit: int = Query(100, ge=1, le=1000)):
        """获取最近的请求日志"""
        recent_logs = request_logs[-limit:] if request_logs else []
        return {
            "logs": recent_logs,
            "total_logs": len(request_logs),
            "showing": len(recent_logs),
            "timestamp": datetime.now().isoformat(),
        }

    @api_router.get("/api/blacklist")
    async def get_blacklist_summary():
        """获取黑名单摘要信息"""
        blacklist_manager = get_model_blacklist_manager()
        stats = blacklist_manager.get_blacklist_stats()

        return {
            "summary": {
                "total_blacklisted": stats["total_blacklisted"],
                "permanent": stats["permanent_blacklisted"],
                "temporary": stats["temporary_blacklisted"],
            },
            "by_channel": stats["by_channel"],
            "by_error_type": stats["by_error_type"],
            "timestamp": datetime.now().isoformat(),
        }

    @api_router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket连接用于实时更新"""
        await websocket.accept()
        active_connections.append(websocket)

        try:
            while True:
                # 保持连接活跃
                await websocket.receive_text()
        except WebSocketDisconnect:
            active_connections.remove(websocket)

    return api_router


def set_request_channel(channel_name: str):
    """设置当前请求的渠道信息"""
    _request_context.channel_name = channel_name


def get_request_channel() -> str:
    """获取当前请求的渠道信息"""
    return getattr(_request_context, "channel_name", "unknown")


def log_request(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    model: str = None,
    channel: str = None,
    error: str = None,
):
    """记录请求日志"""
    global request_logs

    # 如果没有传入渠道信息，尝试从上下文获取
    if channel is None or channel == "unknown":
        channel = get_request_channel()

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "model": model,
        "channel": channel,
        "error": error,
    }

    request_logs.append(log_entry)

    # 保持日志数量在限制内
    if len(request_logs) > MAX_LOGS:
        request_logs = request_logs[-MAX_LOGS:]

    # 通知WebSocket客户端 (后台任务方式避免阻塞)
    try:
        import asyncio
        # 使用 asyncio.ensure_future 来避免协程警告
        asyncio.ensure_future(broadcast_update("request_log", log_entry))
    except Exception:
        # 如果异步处理失败，跳过WebSocket广播但不影响日志记录
        pass


async def broadcast_update(event_type: str, data: Any):
    """向所有WebSocket客户端广播更新"""
    if not active_connections:
        return

    message = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.now().isoformat(),
    }

    # 移除断开的连接
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_text(json.dumps(message))
        except:
            disconnected.append(connection)

    for connection in disconnected:
        if connection in active_connections:
            active_connections.remove(connection)
