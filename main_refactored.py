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

import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
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
            tasks_config = config_loader.get_tasks_config()
            await initialize_background_tasks(tasks_config, config_loader)
            logger.info("🚀 Background tasks initialized successfully")
            
            # 显示启动信息
            _display_startup_info(config_loader, router)
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize background tasks: {e}")

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        """应用关闭事件"""
        try:
            await stop_background_tasks()
            logger.info("⏹️ Background tasks stopped")
            
            await close_global_pool()
            logger.info("🔌 HTTP connection pool closed")
            
            await close_global_cache()
            logger.info("🗄️ Smart cache closed")
            
        except Exception as e:
            logger.error(f"❌ Failed to cleanup resources: {e}")

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

    return app

# --- 辅助函数 ---

def _display_startup_info(config_loader: YAMLConfigLoader, router: JSONRouter) -> None:
    """显示启动信息"""
    try:
        # 获取渠道和模型统计
        available_models = router.get_available_models()
        model_cache = config_loader.get_model_cache()
        
        total_channels = len(config_loader.config.channels) if hasattr(config_loader.config, 'channels') else 0
        total_cached_models = sum(len(data.get("models", [])) for data in (model_cache or {}).values())
        
        logger.info("=" * 60)
        logger.info("🤖 Smart AI Router - Architecture Refactored")
        logger.info("=" * 60)
        logger.info(f"📊 System Status:")
        logger.info(f"   • Total Channels: {total_channels}")
        logger.info(f"   • Configured Models: {len(available_models)}")
        logger.info(f"   • Cached Models: {total_cached_models}")
        logger.info(f"   • Architecture: Modular & Type-Safe")
        logger.info("=" * 60)
        logger.info("🚀 Ready to serve intelligent routing requests!")
        
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
        host = args.host or config.get("host", "127.0.0.1")
        port = args.port or config.get("port", 7601)
        debug = args.debug or config.get("debug", False)

        print(f"\n🤖 Smart AI Router - Refactored Architecture")
        print(f"📋 Configuration: config/router_config.yaml")
        print(f"🌐 Service: http://{host}:{port}")
        print(f"📚 API Docs: http://{host}:{port}/docs")
        print(f"🔧 Architecture: Modular, Type-Safe, High-Performance\n")

        uvicorn.run(
            "main_refactored:create_app",
            factory=True,
            host=host,
            port=port,
            reload=args.reload or debug,
            log_level="debug" if debug else "info",
        )
    except FileNotFoundError:
        logger.error("❌ Configuration file 'config/router_config.yaml' not found.")
        logger.error("💡 Please copy 'config/router_config.yaml.template' to 'config/router_config.yaml' and configure it.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Failed to start application: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()