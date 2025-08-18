# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Smart AI Router - 重构后的统一入口
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

# 设置日志
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

class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]
    total_models: int = 0

# --- FastAPI Application Factory ---

def create_app() -> FastAPI:
    """创建并配置FastAPI应用"""
    # 初始化配置和路由器
    config_loader: YAMLConfigLoader = get_yaml_config_loader()
    router: JSONRouter = JSONRouter(config_loader)
    server_config: Dict[str, Any] = config_loader.get_server_config()

    # 创建FastAPI应用
    app = FastAPI(
        title="Smart AI Router - Refactored",
        description="A lightweight AI router with improved architecture and code quality",
        version="0.3.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 添加认证中间件
    auth_config = config_loader.config.auth
    if auth_config.enabled:
        app.add_middleware(
            AuthenticationMiddleware,
            enabled=auth_config.enabled,
            api_token=auth_config.api_token
        )
        logger.info(f"[AUTH] Authentication middleware enabled")
    else:
        logger.info("[AUTH] Authentication middleware disabled")
    
    # 添加CORS中间件
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
            # 初始化Admin认证
            initialize_admin_auth(config_loader)
            logger.info("[ADMIN] Admin authentication initialized")
            
            tasks_config = config_loader.get_tasks_config()
            await initialize_background_tasks(tasks_config, config_loader)
            logger.info("[STARTUP] Background tasks initialized successfully")
            
            # 显示启动信息
            _display_startup_info(config_loader, router)
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to initialize background tasks: {e}")

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        """应用关闭事件"""
        try:
            await stop_background_tasks()
            logger.info("[TASKS] Background tasks stopped")
            
            await close_global_pool()
            logger.info("[HTTP] HTTP connection pool closed")
            
            await close_global_cache()
            logger.info("[CACHE] Smart cache closed")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to cleanup resources: {e}")

    # --- API 路由 ---

    @app.get("/")
    async def root() -> Dict[str, str]:
        """根路径"""
        return {
            "name": "Smart AI Router",
            "version": "0.3.0",
            "status": "running",
            "docs": "/docs",
            "architecture": "refactored"
        }

    @app.get("/health")
    async def health_check() -> Dict[str, Any]:
        """健康检查"""
        cost_tracker = get_cost_tracker()
        session_summary = cost_tracker.get_session_summary()
        
        return {
            "status": "healthy",
            "config_loaded": True,
            "session_cost": session_summary.get("formatted_total_cost", "$0.00"),
            "total_requests": session_summary.get("total_requests", 0)
        }

    @app.get("/v1/models", response_model=ModelsResponse)
    async def list_models() -> ModelsResponse:
        """返回所有可用的模型"""
        all_models = set()

        # 1. 从路由器获取配置模型
        configured_models = router.get_available_models()
        all_models.update(configured_models)

        # 2. 从模型发现缓存获取物理模型
        model_cache = config_loader.get_model_cache()
        if model_cache:
            for channel_id, discovery_data in model_cache.items():
                for model_name in discovery_data.get("models", []):
                    all_models.add(model_name)

        # 3. 构建响应
        models_data = []
        current_time = int(time.time())
        
        for model_id in sorted(list(all_models)):
            models_data.append(ModelInfo(
                id=model_id,
                created=current_time,
                owned_by="smart-ai-router",
                name=model_id,
                model_type="model_group" if model_id.startswith("auto:") or model_id.startswith("tag:") else "model",
                available=True
            ))

        return ModelsResponse(data=models_data, total_models=len(models_data))

    @app.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest):
        """聊天完成API - 重构后的统一处理入口"""
        try:
            return await chat_handler.handle_request(request)
        except RouterException as e:
            # 统一处理路由器异常
            execution_time = getattr(e, 'execution_time', None)
            return ErrorHandler.create_error_response(e, execution_time)
        except Exception as e:
            # 处理未预期的异常
            logger.error(f"Unexpected error in chat completions: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/admin/routing/strategy")
    async def set_routing_strategy(strategy_data: Dict[str, Any], auth: bool = Depends(get_admin_auth_dependency)):
        """动态设置路由策略"""
        try:
            strategy_name = strategy_data.get("strategy")
            if not strategy_name:
                raise HTTPException(status_code=400, detail="Missing 'strategy' field")
            
            # 验证策略是否有效
            valid_strategies = ["cost_first", "free_first", "local_first", "balanced", "speed_optimized", "quality_optimized"]
            if strategy_name not in valid_strategies:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid strategy '{strategy_name}'. Valid options: {valid_strategies}"
                )
            
            # 动态更新路由策略
            if hasattr(config_loader.config, 'routing'):
                config_loader.config.routing.default_strategy = strategy_name
            else:
                # 如果没有routing配置，创建一个基本的
                from core.config_models import Routing
                config_loader.config.routing = Routing(default_strategy=strategy_name)
            
            # 清除路由器缓存以使新策略生效
            router.clear_cache()
            
            logger.info(f"[STRATEGY] Routing strategy changed to '{strategy_name}'")
            
            return {
                "status": "success",
                "message": f"Routing strategy changed to '{strategy_name}'",
                "previous_strategy": strategy_data.get("previous_strategy"),
                "new_strategy": strategy_name,
                "available_strategies": valid_strategies
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to change routing strategy: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/admin/routing/strategy")
    async def get_routing_strategy(auth: bool = Depends(get_admin_auth_dependency)):
        """获取当前路由策略"""
        try:
            current_strategy = "cost_first"  # 默认值
            
            if hasattr(config_loader.config, 'routing') and hasattr(config_loader.config.routing, 'default_strategy'):
                current_strategy = config_loader.config.routing.default_strategy
            
            available_strategies = ["cost_first", "free_first", "local_first", "balanced", "speed_optimized", "quality_optimized"]
            
            return {
                "current_strategy": current_strategy,
                "available_strategies": available_strategies,
                "strategy_descriptions": {
                    "cost_first": "成本优先 - 最低成本的模型",
                    "free_first": "免费优先 - 优先使用免费模型",
                    "local_first": "本地优先 - 优先使用本地模型",
                    "balanced": "平衡策略 - 成本、速度、质量平衡",
                    "speed_optimized": "速度优先 - 最快响应的模型",
                    "quality_optimized": "质量优先 - 最高质量的模型"
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get routing strategy: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/admin/cost/optimize")
    async def get_cost_optimization_suggestions(auth: bool = Depends(get_admin_auth_dependency)):
        """获取成本优化建议"""
        try:
            cost_tracker = get_cost_tracker()
            session_summary = cost_tracker.get_session_summary()
            
            current_strategy = "cost_first"
            if hasattr(config_loader.config, 'routing') and hasattr(config_loader.config.routing, 'default_strategy'):
                current_strategy = config_loader.config.routing.default_strategy
            
            suggestions = []
            
            # 基于当前策略给出建议
            if current_strategy != "free_first":
                suggestions.append({
                    "type": "strategy_change",
                    "priority": "high",
                    "title": "切换到免费优先策略",
                    "description": "使用 'free_first' 策略可以最大化免费资源的使用",
                    "action": "POST /v1/admin/routing/strategy",
                    "data": {"strategy": "free_first"},
                    "estimated_savings": "60-90%"
                })
            
            if current_strategy != "local_first":
                suggestions.append({
                    "type": "strategy_change", 
                    "priority": "medium",
                    "title": "考虑本地优先策略",
                    "description": "使用 'local_first' 策略可以减少网络请求成本",
                    "action": "POST /v1/admin/routing/strategy",
                    "data": {"strategy": "local_first"},
                    "estimated_savings": "30-70%"
                })
            
            # 基于请求量给出建议
            total_requests = session_summary.get('total_requests', 0)
            if total_requests > 100:
                suggestions.append({
                    "type": "usage_optimization",
                    "priority": "medium",
                    "title": "考虑批量处理",
                    "description": f"您已发送 {total_requests} 个请求，考虑批量处理以减少API调用次数",
                    "estimated_savings": "20-40%"
                })
            
            # 基于成本给出建议
            total_cost = session_summary.get('total_cost', 0.0)
            if total_cost > 1.0:  # 超过$1
                suggestions.append({
                    "type": "cost_alert",
                    "priority": "high", 
                    "title": "成本预警",
                    "description": f"会话成本已达到 {session_summary.get('formatted_total_cost', '$0.00')}，建议检查策略设置",
                    "estimated_savings": "可能节省 40-80%"
                })
            
            return {
                "current_session": session_summary,
                "current_strategy": current_strategy,
                "suggestions": suggestions,
                "available_cost_strategies": ["free_first", "cost_first", "local_first"],
                "optimization_tips": [
                    "使用 'tag:free' 直接请求免费模型",
                    "使用 'tag:local' 直接请求本地模型", 
                    "批量处理多个请求以减少开销",
                    "定期监控成本趋势"
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to get cost optimization suggestions: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # --- SiliconFlow管理API ---
    
    @app.post("/v1/admin/siliconflow/pricing/refresh")
    async def refresh_siliconflow_pricing(request: Dict[str, Any], auth: bool = Depends(get_admin_auth_dependency)):
        """手动刷新SiliconFlow定价信息"""
        try:
            from core.scheduler.tasks.siliconflow_pricing import run_siliconflow_pricing_update
            
            force = request.get("force", False)
            logger.info(f"开始手动刷新SiliconFlow定价 (force={force})")
            
            # 执行定价抓取
            result = await run_siliconflow_pricing_update(force=force)
            
            return {
                "success": True,
                "message": "SiliconFlow定价刷新完成",
                "data": result
            }
            
        except Exception as e:
            logger.error(f"SiliconFlow定价刷新失败: {e}")
            raise HTTPException(status_code=500, detail=f"定价刷新失败: {str(e)}")
    
    @app.get("/v1/admin/siliconflow/pricing/status")
    async def get_siliconflow_pricing_status(auth: bool = Depends(get_admin_auth_dependency)):
        """获取SiliconFlow定价状态"""
        try:
            from core.scheduler.tasks.siliconflow_pricing import get_siliconflow_pricing_task
            
            pricing_task = get_siliconflow_pricing_task()
            stats = pricing_task.get_pricing_stats()
            
            return {
                "success": True,
                "data": {
                    "pricing_stats": stats,
                    "cache_status": {
                        "total_models": len(pricing_task.cached_pricing),
                        "last_update": pricing_task.last_update.isoformat() if pricing_task.last_update else None,
                        "needs_update": pricing_task.should_update_pricing()
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"获取SiliconFlow定价状态失败: {e}")
            raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")
    
    @app.get("/v1/admin/siliconflow/pricing/models")
    async def get_siliconflow_pricing_models(auth: bool = Depends(get_admin_auth_dependency)):
        """获取所有SiliconFlow模型的定价信息"""
        try:
            from core.scheduler.tasks.siliconflow_pricing import get_siliconflow_pricing_task
            
            pricing_task = get_siliconflow_pricing_task()
            all_pricing = pricing_task.get_all_pricing()
            
            return {
                "success": True,
                "data": {
                    "total_models": len(all_pricing),
                    "models": all_pricing
                }
            }
            
        except Exception as e:
            logger.error(f"获取SiliconFlow模型定价失败: {e}")
            raise HTTPException(status_code=500, detail=f"获取模型定价失败: {str(e)}")

    return app

# --- 辅助函数 ---

def _display_startup_info(config_loader: YAMLConfigLoader, router: JSONRouter) -> None:
    """显示启动信息"""
    try:
        # 获取渠道和模型统计
        available_models = router.get_available_models()
        model_cache = config_loader.get_model_cache()
        
        # 统计渠道信息
        total_channels = len(config_loader.config.channels) if hasattr(config_loader.config, 'channels') else 0
        enabled_channels = sum(1 for ch in config_loader.config.channels if ch.enabled) if hasattr(config_loader.config, 'channels') else 0
        
        # 统计模型信息
        total_cached_models = sum(len(data.get("models", [])) for data in (model_cache or {}).values())
        
        # 统计标签信息
        tag_models = [m for m in available_models if m.startswith("tag:")]
        physical_models = [m for m in available_models if not m.startswith("tag:")]
        unique_tags = set()
        for tag_model in tag_models:
            if tag_model.startswith("tag:"):
                tag_name = tag_model[4:]  # 去掉 "tag:" 前缀
                unique_tags.add(tag_name)
        
        # 认证状态
        auth_config = config_loader.config.auth
        auth_status = "[AUTH] Enabled" if auth_config.enabled else "[AUTH] Disabled"
        
        # 路由策略
        routing_config = getattr(config_loader.config, 'routing', None)
        default_strategy = getattr(routing_config, 'default_strategy', 'cost_first') if routing_config else 'cost_first'
        
        logger.info("=" * 65)
        logger.info("[AI] Smart AI Router - Phase 7 Cost Optimization")
        logger.info("=" * 65)
        logger.info("[STATUS] System Status:")
        logger.info(f"   • Total Channels: {total_channels} ({enabled_channels} enabled)")
        logger.info(f"   • Physical Models: {len(physical_models)}")
        logger.info(f"   • Available Tags: {len(unique_tags)} (tag:* queries supported)")
        logger.info(f"   • Cached Models: {total_cached_models}")
        logger.info(f"   • Authentication: {auth_status}")
        logger.info(f"   • Default Strategy: {default_strategy}")
        logger.info("=" * 65)
        logger.info("[TAGS] Tag-Based Routing: Use 'tag:free', 'tag:gpt', 'tag:local', etc.")
        logger.info("[COST] Cost Optimization: Intelligent routing for minimal costs")
        logger.info("[READY] Ready to serve intelligent routing requests!")
        
    except Exception as e:
        logger.warning(f"Failed to display startup info: {e}")

# --- 主程序入口 ---

def main() -> None:
    """主程序入口"""
    parser = argparse.ArgumentParser(description="Smart AI Router - Refactored")
    parser.add_argument("--host", default=None, help="Server host address")
    parser.add_argument("--port", type=int, default=None, help="Server port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (for development)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    try:
        config = get_yaml_config_loader().get_server_config()
        host = args.host or config.get("host", "0.0.0.0")
        port = args.port or config.get("port", 7601)
        debug = args.debug or config.get("debug", False)

        print(f"\n[AI] Smart AI Router - Refactored Architecture")
        print(f"[CONFIG] Configuration: config/router_config.yaml")
        print(f"[WEB] Service: http://{host}:{port}")
        print(f"[DOCS] API Docs: http://{host}:{port}/docs")
        print(f"[ARCH] Architecture: Modular, Type-Safe, High-Performance\n")

        uvicorn.run(
            "main:create_app",
            factory=True,
            host=host,
            port=port,
            reload=args.reload or debug,
            log_level="debug" if debug else "info",
        )
    except FileNotFoundError:
        logger.error("[ERROR] Configuration file 'config/router_config.yaml' not found.")
        logger.error("[TIP] Please copy 'config/router_config.yaml.template' to 'config/router_config.yaml' and configure it.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"[ERROR] Failed to start application: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()