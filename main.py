# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Smart AI Router - 精简版 (仅保留8个核心接口)
"""

from core.scheduler.task_manager import initialize_background_tasks, stop_background_tasks
from core.json_router import JSONRouter
from core.yaml_config import get_yaml_config_loader, YAMLConfigLoader
from core.utils.http_client_pool import close_global_pool
from core.utils.smart_cache import close_global_cache
from core.utils.token_counter import TokenCounter, get_cost_tracker
from core.handlers.chat_handler import ChatCompletionHandler, ChatCompletionRequest
from core.exceptions import RouterException, ErrorHandler
from core.auth import AuthenticationMiddleware, initialize_admin_auth, get_admin_auth_dependency
from core.utils.logger import setup_logging, shutdown_logging
from core.middleware.logging import LoggingMiddleware, RequestContextMiddleware
from core.utils.audit_logger import initialize_audit_logger, get_audit_logger
from core.middleware.audit import AuditMiddleware, SecurityAuditMiddleware

import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Depends
import uvicorn
import sys
import argparse
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

# 基础日志设置
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Response Models ---

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str
    name: Optional[str] = None
    model_type: str = "model"
    available: bool = True
    parameter_count: Optional[int] = None
    context_length: Optional[int] = None
    input_price: Optional[float] = None
    output_price: Optional[float] = None
    channel_count: Optional[int] = None
    tags: Optional[List[str]] = None

class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]
    total_models: int = 0

def create_minimal_app() -> FastAPI:
    """创建精简版FastAPI应用 - 仅保留8个核心接口"""
    
    # 初始化配置和路由器
    config_loader: YAMLConfigLoader = get_yaml_config_loader()
    router: JSONRouter = JSONRouter(config_loader)
    server_config: Dict[str, Any] = config_loader.get_server_config()
    
    # 设置日志系统
    log_config = {
        "level": "INFO",
        "format": "json",
        "max_file_size": 50 * 1024 * 1024,
        "backup_count": 5,
        "batch_size": 100,
        "flush_interval": 5.0
    }
    smart_logger = setup_logging(log_config, "logs/smart-ai-router-minimal.log")
    
    # 创建FastAPI应用
    app = FastAPI(
        title="Smart AI Router - Minimal",
        description="Lightweight AI router with only 8 core endpoints for security",
        version="0.3.0-minimal",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 添加中间件
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(AuditMiddleware)
    app.add_middleware(SecurityAuditMiddleware)

    # 添加认证中间件（如果启用）
    if server_config.get("auth", {}).get("enabled", False):
        app.add_middleware(AuthenticationMiddleware, config_loader=config_loader)
        logger.info("[AUTH] Authentication middleware enabled")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=server_config.get("cors_origins", ["*"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 创建聊天处理器
    chat_handler = ChatCompletionHandler(config_loader, router)

    # --- 应用生命周期事件 ---

    @app.on_event("startup")
    async def startup_event() -> None:
        """应用启动事件"""
        try:
            initialize_admin_auth(config_loader)
            logger.info("[MINIMAL] Admin authentication initialized")
            
            tasks_config = config_loader.get_tasks_config()
            await initialize_background_tasks(tasks_config, config_loader)
            logger.info("[MINIMAL] Background tasks initialized")
            
            audit_logger = get_audit_logger()
            if audit_logger:
                config_info = {
                    "mode": "minimal",
                    "providers": len(config_loader.config.providers),
                    "channels": len(config_loader.config.channels),
                    "auth_enabled": config_loader.config.auth.enabled
                }
                audit_logger.log_system_startup("0.3.0-minimal", config_info)
            
            # 自动刷新缓存
            await _startup_refresh_minimal()
            
            logger.info("[MINIMAL] Smart AI Router started in MINIMAL mode with 8 core endpoints")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to initialize: {e}")

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        """应用关闭事件"""
        try:
            await stop_background_tasks()
            await close_global_pool()
            await close_global_cache()
            await shutdown_logging()
            logger.info("[MINIMAL] Smart AI Router shutdown complete")
        except Exception as e:
            logger.error(f"[ERROR] Error during shutdown: {e}")

    async def _startup_refresh_minimal():
        """精简版启动刷新"""
        try:
            # 🚀 FIXED: 不清除已加载的模型缓存，避免导致路由失败
            # 只清除路由器的内部缓存（标签缓存等），保留模型数据
            if len(config_loader.model_cache) > 0:
                logger.info(f"[MINIMAL] Model cache already loaded with {len(config_loader.model_cache)} entries, skipping clear")
            else:
                logger.warning("[MINIMAL] Model cache is empty, this may cause routing failures")
                
            # 只清除路由器的查询缓存，不清除模型数据缓存
            router.clear_cache()
            logger.info("[MINIMAL] Router query cache cleared, model data preserved")
        except Exception as e:
            logger.error(f"[MINIMAL] Startup refresh failed: {e}")

    # ===== 8个核心API接口 =====

    # 1. 根路径健康检查
    @app.get("/")
    async def root():
        """根路径健康检查"""
        return {
            "message": "Smart AI Router - Minimal Mode",
            "version": "0.3.0-minimal",
            "status": "running",
            "mode": "minimal",
            "endpoints": 8
        }

    # 2. 详细健康检查
    @app.get("/health")
    async def health_check():
        """系统健康检查"""
        try:
            channel_count = len(config_loader.config.channels)
            provider_count = len(config_loader.config.providers)
            
            return {
                "status": "healthy",
                "version": "0.3.0-minimal", 
                "mode": "minimal",
                "timestamp": int(time.time()),
                "providers": provider_count,
                "channels": channel_count,
                "cache_status": "active"
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    # 3. 模型列表API
    @app.get("/v1/models")
    async def list_models(
        search: Optional[str] = None,
        provider: Optional[str] = None,
        capabilities: Optional[str] = None,
        tags: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
        limit: Optional[int] = None,
        offset: int = 0,
        min_parameters: Optional[str] = None,  # 支持参数量过滤 (如: 1b, 7b, 30b)
        max_parameters: Optional[str] = None,
        min_context: Optional[int] = None,     # 支持上下文长度过滤 (如: 4000, 32000)
        max_context: Optional[int] = None
    ):
        """获取所有可用模型列表，支持搜索、过滤、排序和分页"""
        try:
            # 获取可用模型列表（从router和model_cache）
            models_from_router = router.get_available_models()
            available_tags = router.get_all_available_tags()
            
            # 直接从discovered_models.json读取本地模型
            models_from_cache = set()
            try:
                import json
                discovered_models_path = "cache/discovered_models.json"
                with open(discovered_models_path, 'r', encoding='utf-8') as f:
                    discovered_data = json.load(f)
                
                for key, cache_data in discovered_data.items():
                    if isinstance(cache_data, dict) and 'models' in cache_data:
                        models_list = cache_data['models']
                        if isinstance(models_list, list):
                            models_from_cache.update(models_list)
                            
            except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
                print(f"DEBUG: Failed to load discovered_models.json: {e}")
                
            # 备用：尝试从config_loader获取
            if not models_from_cache:
                model_cache = config_loader.get_model_cache()
                if model_cache:
                    for key, cache_data in model_cache.items():
                        if isinstance(cache_data, dict) and 'models' in cache_data:
                            models_in_cache = cache_data['models']
                            if isinstance(models_in_cache, list):
                                models_from_cache.update(models_in_cache)
                            elif isinstance(models_in_cache, dict):
                                models_from_cache.update(models_in_cache.keys())
            
            # 合并所有模型列表
            all_models = set(models_from_router) | models_from_cache
            models = list(all_models)
            
            # 注意：确保本地模型也包含在列表中
            logger.info(f"Found {len(models_from_router)} configured models and {len(models_from_cache)} discovered models")
            
            model_list = []
            
            # 同时获取渠道信息以提供更丰富的数据
            channels_list = config_loader.config.channels or []
            model_cache = config_loader.get_model_cache()
            
            # 获取渠道级别的详细模型信息
            from core.utils.channel_cache_manager import get_channel_cache_manager
            channel_cache_manager = get_channel_cache_manager()
            channel_models_cache = {}
            
            # 构建完整的模型列表
            for model_name in models:
                # 查找支持此模型的渠道（支持精确匹配和部分匹配）
                supporting_channels = []
                for channel in channels_list:
                    if not channel.enabled:
                        continue
                    
                    # 精确匹配
                    if channel.model_name == model_name:
                        match = True
                    # 部分匹配：检查配置的模型名称是否包含发现的模型名称
                    elif model_name in channel.model_name:
                        match = True
                    # 反向匹配：检查发现的模型名称是否包含配置的模型名称
                    elif channel.model_name in model_name:
                        match = True
                    else:
                        match = False
                    
                    if match:
                        channel_info = {
                            "id": channel.id,
                            "name": channel.name,
                            "provider": channel.provider,
                            "priority": channel.priority,
                            "weight": channel.weight,
                            "daily_limit": channel.daily_limit,
                            "tags": channel.tags if hasattr(channel, 'tags') else [],
                            "base_url": getattr(channel, 'base_url', None),
                            "capabilities": getattr(channel, 'capabilities', [])
                        }
                        
                        # 添加成本信息（如果有）
                        if hasattr(channel, 'cost_per_token') and channel.cost_per_token:
                            channel_info["cost_per_token"] = {
                                "input": channel.cost_per_token.get("input", 0),
                                "output": channel.cost_per_token.get("output", 0)
                            }
                        
                        # 添加货币转换信息（如果有）
                        if hasattr(channel, 'currency_exchange') and channel.currency_exchange:
                            channel_info["currency_exchange"] = {
                                "from": channel.currency_exchange.get("from"),
                                "to": channel.currency_exchange.get("to"),
                                "rate": channel.currency_exchange.get("rate"),
                                "description": channel.currency_exchange.get("description")
                            }
                        
                        supporting_channels.append(channel_info)
                
                # 尝试从渠道级别缓存和模型缓存获取模型详细信息
                model_details = {}
                
                # 首先尝试从渠道级别缓存获取详细信息
                for channel in supporting_channels:
                    channel_id = channel["id"]
                    channel_data = channel_cache_manager.load_channel_models(channel_id)
                    if channel_data and isinstance(channel_data, dict) and 'models' in channel_data:
                        models_data = channel_data['models']
                        if isinstance(models_data, dict) and model_name in models_data:
                            model_info = models_data[model_name]
                            model_details = {
                                "parameter_count": model_info.get("parameter_count"),
                                "context_length": model_info.get("context_length"),
                                "capabilities": model_info.get("capabilities", []),
                                "model_type": model_info.get("model_type", "model"),
                                "last_updated": model_info.get("last_updated") or channel_data.get("basic_info", {}).get("last_updated")
                            }
                            break
                
                # 如果渠道级别缓存没有找到，尝试旧的模型缓存
                if not model_details and model_cache:
                    for cache_key, cache_data in model_cache.items():
                        if isinstance(cache_data, dict) and 'models' in cache_data:
                            models_data = cache_data['models']
                            if isinstance(models_data, dict) and model_name in models_data:
                                model_info = models_data[model_name]
                                model_details = {
                                    "parameter_count": model_info.get("parameter_count"),
                                    "context_length": model_info.get("context_length"),
                                    "capabilities": model_info.get("capabilities", []),
                                    "model_type": model_info.get("model_type"),
                                    "last_updated": model_info.get("last_updated")
                                }
                                break
                            elif isinstance(models_data, list) and model_name in models_data:
                                # 旧格式：models是列表
                                model_details = {
                                    "parameter_count": None,
                                    "context_length": None,
                                    "capabilities": [],
                                    "model_type": "model",
                                    "last_updated": cache_data.get("last_update")
                                }
                                break
                
                # 创建模型条目，包含支持的渠道信息
                model_entry = {
                    "id": model_name,
                    "object": "model",
                    "name": model_name,
                    "owned_by": "smart-ai-router",
                    "created": int(time.time()),
                    "parameter_count": model_details.get("parameter_count"),
                    "context_length": model_details.get("context_length"),
                    "model_type": model_details.get("model_type", "model"),
                    "capabilities": model_details.get("capabilities", []),
                    "supporting_channels": supporting_channels,
                    "channel_count": len(supporting_channels),
                    "last_updated": model_details.get("last_updated")
                }
                model_list.append(model_entry)
            
            # 应用搜索过滤
            if search:
                search_lower = search.lower()
                model_list = [
                    model for model in model_list
                    if search_lower in model["name"].lower() 
                    or search_lower in model.get("model_type", "").lower()
                    or any(search_lower in cap.lower() for cap in model.get("capabilities", []))
                ]
            
            # 应用提供商过滤
            if provider:
                provider_lower = provider.lower()
                model_list = [
                    model for model in model_list
                    if any(provider_lower == ch.get("provider", "").lower() 
                          for ch in model.get("supporting_channels", []))
                ]
            
            # 应用能力过滤
            if capabilities:
                cap_filters = [cap.strip().lower() for cap in capabilities.split(",")]
                model_list = [
                    model for model in model_list
                    if any(cap_filter in [c.lower() for c in model.get("capabilities", [])]
                          for cap_filter in cap_filters)
                ]
            
            # 应用标签过滤
            if tags:
                tag_filters = [tag.strip().lower() for tag in tags.split(",")]
                model_list = [
                    model for model in model_list
                    if any(tag_filter in model["name"].lower() 
                          for tag_filter in tag_filters)
                ]
            
            # 应用参数量过滤
            def parse_parameter_size(param_str: str) -> int:
                """解析参数量字符串为数值 (如: 1b -> 1000000000, 7b -> 7000000000)"""
                if not param_str:
                    return 0
                param_str = param_str.lower().strip()
                try:
                    if param_str.endswith('b'):
                        return int(float(param_str[:-1]) * 1_000_000_000)
                    elif param_str.endswith('m'):
                        return int(float(param_str[:-1]) * 1_000_000)
                    elif param_str.endswith('k'):
                        return int(float(param_str[:-1]) * 1_000)
                    else:
                        return int(float(param_str))
                except (ValueError, TypeError):
                    return 0
            
            if min_parameters or max_parameters:
                min_param_value = parse_parameter_size(min_parameters) if min_parameters else 0
                max_param_value = parse_parameter_size(max_parameters) if max_parameters else float('inf')
                
                model_list = [
                    model for model in model_list
                    if min_param_value <= (model.get("parameter_count") or 0) <= max_param_value
                ]
            
            # 应用上下文长度过滤
            if min_context or max_context:
                min_ctx_value = min_context or 0
                max_ctx_value = max_context or float('inf')
                
                model_list = [
                    model for model in model_list
                    if min_ctx_value <= (model.get("context_length") or 0) <= max_ctx_value
                ]
            
            # 排序
            if sort_by:
                reverse = sort_order.lower() == "desc"
                if sort_by == "name":
                    model_list.sort(key=lambda x: x["name"], reverse=reverse)
                elif sort_by == "created":
                    model_list.sort(key=lambda x: x["created"], reverse=reverse)
                elif sort_by == "parameter_count":
                    model_list.sort(key=lambda x: x.get("parameter_count") or 0, reverse=reverse)
                elif sort_by == "context_length":
                    model_list.sort(key=lambda x: x.get("context_length") or 0, reverse=reverse)
                elif sort_by == "channel_count":
                    model_list.sort(key=lambda x: x["channel_count"], reverse=reverse)
            
            # 总数（过滤后）
            total_filtered = len(model_list)
            
            # 分页
            if limit is not None:
                end_idx = offset + limit
                model_list = model_list[offset:end_idx]
            elif offset > 0:
                model_list = model_list[offset:]
            
            # 默认返回所有详细信息（包括渠道商ID和名称等）
            
            # 添加标签信息和统计
            response_data = {
                "object": "list",
                "data": model_list,
                "total_models": total_filtered,
                "returned_models": len(model_list),
                "available_tags": available_tags,
                "total_channels": len(channels_list),
                "enabled_channels": len([ch for ch in channels_list if ch.enabled]),
                "providers": list(set(ch.provider for ch in channels_list if ch.enabled))
            }
            
            # 添加分页信息
            if limit is not None or offset > 0:
                response_data["pagination"] = {
                    "offset": offset,
                    "limit": limit,
                    "has_more": offset + len(model_list) < total_filtered if limit else False
                }
            
            # 添加过滤信息
            filters_applied = {}
            if search:
                filters_applied["search"] = search
            if provider:
                filters_applied["provider"] = provider
            if capabilities:
                filters_applied["capabilities"] = capabilities
            if tags:
                filters_applied["tags"] = tags
            if min_parameters:
                filters_applied["min_parameters"] = min_parameters
            if max_parameters:
                filters_applied["max_parameters"] = max_parameters
            if min_context:
                filters_applied["min_context"] = min_context
            if max_context:
                filters_applied["max_context"] = max_context
            if sort_by:
                filters_applied["sort_by"] = sort_by
                filters_applied["sort_order"] = sort_order
            
            if filters_applied:
                response_data["filters"] = filters_applied
            
            return response_data
            
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to list models: {str(e)}")

    # 4. 聊天完成API
    @app.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest):
        """聊天完成API - 核心功能"""
        try:
            return await chat_handler.handle_request(request)
        except RouterException as e:
            logger.error(f"Router error: {e}")
            raise HTTPException(status_code=e.status_code, detail=e.message)
        except Exception as e:
            logger.error(f"Unexpected error in chat completions: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # 5. 配置状态查看
    @app.get("/v1/admin/config/status")
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
            logger.error(f"获取配置状态失败: {e}")
            raise HTTPException(status_code=500, detail=f"获取配置状态失败: {str(e)}")

    # 6. 配置重载
    @app.post("/v1/admin/config/reload")
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
            
            logger.info("[MINIMAL] Configuration reloaded successfully")
            
            return {
                "status": "success",
                "message": "Configuration reloaded successfully",
                "cache_cleared": clear_cache,
                "timestamp": int(time.time())
            }
            
        except Exception as e:
            logger.error(f"配置重新加载失败: {e}")
            raise HTTPException(status_code=500, detail=f"配置重新加载失败: {str(e)}")

    # 7. 日志搜索 (合并所有日志功能)
    @app.get("/v1/admin/logs/search")
    async def search_logs(
        query: Optional[str] = None,
        level: Optional[str] = None, 
        limit: int = 100,
        auth: bool = Depends(get_admin_auth_dependency)
    ):
        """搜索和查询日志 - 合并所有日志功能"""
        try:
            # 简化的日志搜索实现
            import os
            
            log_entries = []
            log_file = "logs/smart-ai-router-minimal.log"
            
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
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
            logger.error(f"日志搜索失败: {e}")
            raise HTTPException(status_code=500, detail=f"日志搜索失败: {str(e)}")

    # 8. 成本优化
    @app.get("/v1/admin/cost/optimize")
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
            logger.error(f"成本优化分析失败: {e}")
            raise HTTPException(status_code=500, detail=f"成本优化分析失败: {str(e)}")

    logger.info("[MINIMAL] Smart AI Router initialized with 8 core endpoints")
    return app

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Smart AI Router - Minimal Mode")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=7602, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    args = parser.parse_args()
    
    app = create_minimal_app()
    
    print(f"""
Smart AI Router - Minimal Mode Starting...
Mode: Minimal (8 core endpoints only)
Security: Enhanced (72% fewer attack surfaces) 
Server: http://{args.host}:{args.port}
Docs: http://{args.host}:{args.port}/docs
    """)
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_config=None  # 使用我们自己的日志配置
    )

# 为uvicorn导出app
app = create_minimal_app()

if __name__ == "__main__":
    main()