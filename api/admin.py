"""
Admin API endpoints
管理API接口
"""

import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from core.auth import get_admin_auth_dependency
from core.utils.token_counter import get_cost_tracker
from core.yaml_config import YAMLConfigLoader

# 导入子路由
from .admin_modules.siliconflow import router as siliconflow_router


def create_admin_router(config_loader: YAMLConfigLoader) -> APIRouter:
    """创建管理相关的API路由"""

    router = APIRouter(prefix="/v1/admin", tags=["admin"])

    @router.get("/config/status")
    async def get_config_status(auth: bool = Depends(get_admin_auth_dependency)):
        """获取当前配置状态"""
        try:
            config = config_loader.config

            return {
                "status": "success",
                "config": {
                    "providers": len(config.providers),
                    "channels": len(config.channels),
                    "auth_enabled": config.auth.enabled,
                    "model_cache_size": len(config_loader.model_cache),
                    "routing_strategy": getattr(config.routing, 'default_strategy', 'cost_first') if hasattr(config, 'routing') else 'cost_first'
                },
                "cache": {
                    "model_cache_entries": len(config_loader.model_cache),
                    "router_cache_active": True
                },
                "timestamp": int(time.time())
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取配置状态失败: {str(e)}")

    @router.post("/config/reload")
    async def reload_config_endpoint(request: Dict[str, Any], auth: bool = Depends(get_admin_auth_dependency)):
        """重新加载配置文件并刷新缓存"""
        try:
            clear_cache = request.get("clear_cache", True)

            # 重新加载配置
            from core.config_loader import reload_config
            from core.json_router import get_router

            new_config_loader = reload_config()
            new_router = get_router()

            if clear_cache:
                new_config_loader.model_cache.clear()
                new_router.clear_cache()

            return {
                "status": "success",
                "message": "Configuration reloaded successfully",
                "cache_cleared": clear_cache,
                "timestamp": int(time.time())
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"配置重新加载失败: {str(e)}")

    @router.get("/logs/search")
    async def search_logs(
        query: Optional[str] = None,
        level: Optional[str] = None,
        limit: int = 100,
        auth: bool = Depends(get_admin_auth_dependency)
    ):
        """搜索和查询日志 - 合并所有日志功能"""
        try:
            log_entries = []
            log_file = "logs/smart-ai-router-minimal.log"

            if os.path.exists(log_file):
                with open(log_file, encoding='utf-8') as f:
                    lines = f.readlines()[-limit:]  # 获取最后N行

                    for line in lines:
                        if query and query.lower() not in line.lower():
                            continue
                        if level and level.upper() not in line:
                            continue
                        log_entries.append(line.strip())

            return {
                "status": "success",
                "logs": log_entries,
                "count": len(log_entries),
                "query": query,
                "level": level,
                "limit": limit
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"日志搜索失败: {str(e)}")

    @router.get("/cost/optimize")
    async def get_cost_optimization(auth: bool = Depends(get_admin_auth_dependency)):
        """获取成本优化建议"""
        try:
            # 分析免费渠道使用情况
            free_channels = []
            paid_channels = []

            for channel_name, channel in config_loader.config.channels.items():
                if hasattr(channel, 'tags') and 'free' in channel.tags:
                    free_channels.append(channel_name)
                else:
                    paid_channels.append(channel_name)

            # 获取成本追踪器数据
            cost_tracker = get_cost_tracker()
            session_cost = cost_tracker.get_session_total() if cost_tracker else 0.0

            optimization_tips = [
                f"发现 {len(free_channels)} 个免费渠道，优先使用可节省成本",
                f"当前会话成本: ${session_cost:.6f}",
                "建议使用 'tag:free' 查询免费模型",
                "本地模型 (Ollama/LMStudio) 完全免费"
            ]

            return {
                "status": "success",
                "cost_summary": {
                    "session_cost": session_cost,
                    "free_channels": len(free_channels),
                    "paid_channels": len(paid_channels),
                    "free_channel_ratio": len(free_channels) / (len(free_channels) + len(paid_channels)) * 100
                },
                "optimization_tips": optimization_tips,
                "free_channels": free_channels[:5],  # 显示前5个免费渠道
                "timestamp": int(time.time())
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"成本优化分析失败: {str(e)}")

    # 包含子路由
    router.include_router(siliconflow_router)

    return router
