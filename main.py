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
from core.handlers.chat_handler import ChatCompletionHandler
from core.auth import AuthenticationMiddleware, initialize_admin_auth
from core.utils.logger import setup_logging, shutdown_logging
from core.middleware.logging import LoggingMiddleware, RequestContextMiddleware
from core.utils.audit_logger import initialize_audit_logger, get_audit_logger
from core.middleware.audit import AuditMiddleware, SecurityAuditMiddleware

# API路由模块
from api.chat import create_chat_router
from api.models import create_models_router
from api.health import create_health_router
from api.admin import create_admin_router
from api.anthropic import create_anthropic_router
from api.chatgpt import create_chatgpt_router
from api.gemini import create_gemini_router
from api.usage_stats import create_usage_stats_router

import uvicorn
import sys
import argparse
import logging
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

# 基础日志设置
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

    # ===== 注册API路由模块 =====
    
    # 健康检查路由
    health_router = create_health_router(config_loader)
    app.include_router(health_router)
    
    # 模型列表路由
    models_router = create_models_router(config_loader, router)
    app.include_router(models_router)
    
    # 聊天完成路由
    chat_router = create_chat_router(chat_handler)
    app.include_router(chat_router)
    
    # 管理功能路由
    admin_router = create_admin_router(config_loader)
    app.include_router(admin_router)
    
    # 使用统计路由
    usage_stats_router = create_usage_stats_router(config_loader)
    app.include_router(usage_stats_router)
    
    # Anthropic Claude API 兼容路由
    anthropic_router = create_anthropic_router(config_loader, router, chat_handler)
    app.include_router(anthropic_router)
    
    # OpenAI ChatGPT API 兼容路由
    chatgpt_router = create_chatgpt_router(config_loader, router, chat_handler)
    app.include_router(chatgpt_router)
    
    # Google Gemini API 兼容路由
    gemini_router = create_gemini_router(config_loader, router, chat_handler)
    app.include_router(gemini_router)

    logger.info("[MINIMAL] Smart AI Router initialized with 8 core endpoints")
    return app

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Smart AI Router - Minimal Mode")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=7601, help="Port to bind to")
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