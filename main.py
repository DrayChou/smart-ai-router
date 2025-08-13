#!/usr/bin/env python3
"""
Smart AI Router - 个人AI智能路由系统
主程序入口
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.utils.config import load_config
from core.utils.logger import setup_logging
from api.chat import router as chat_router
from api.admin import router as admin_router
from api.health import router as health_router


def create_app() -> FastAPI:
    """创建FastAPI应用实例"""
    
    # 加载配置
    config = load_config()
    
    # 设置日志
    setup_logging(config.get("logging", {}))
    
    # 创建应用
    app = FastAPI(
        title="Smart AI Router",
        description="轻量化个人AI智能路由系统 - 成本优化、智能路由、故障转移",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    # 添加CORS中间件
    cors_config = config.get("security", {})
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_config.get("cors_origins", ["*"]),
        allow_credentials=True,
        allow_methods=cors_config.get("cors_methods", ["*"]),
        allow_headers=cors_config.get("cors_headers", ["*"]),
    )
    
    # 注册路由
    app.include_router(health_router, prefix="/health", tags=["健康检查"])
    app.include_router(chat_router, prefix="/v1", tags=["聊天接口"])
    app.include_router(admin_router, prefix="/admin", tags=["管理接口"])
    
    # 根路径
    @app.get("/")
    async def root():
        return JSONResponse({
            "name": "Smart AI Router",
            "version": "0.1.0",
            "description": "轻量化个人AI智能路由系统",
            "status": "running",
            "endpoints": {
                "docs": "/docs",
                "health": "/health",
                "chat": "/v1/chat/completions",
                "models": "/v1/models",
                "admin": "/admin"
            }
        })
    
    # 存储配置到应用状态
    app.state.config = config
    
    return app


def main():
    """主函数"""
    # 加载配置
    config = load_config()
    server_config = config.get("server", {})
    
    # 服务器配置
    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 8000)
    workers = server_config.get("workers", 1)
    reload = server_config.get("reload", False)
    log_level = server_config.get("log_level", "info")
    
    print(f"""
🚀 Smart AI Router 启动中...

📡 服务地址: http://{host}:{port}
📚 API文档: http://{host}:{port}/docs
🔍 健康检查: http://{host}:{port}/health
💬 聊天接口: http://{host}:{port}/v1/chat/completions
🎛️  管理接口: http://{host}:{port}/admin

🎯 核心特性:
  • 🧠 虚拟模型系统 - 智能模型分组
  • 💰 成本优化路由 - 自动选择最便宜渠道  
  • ⚡ 延迟优化路由 - 选择最快响应渠道
  • 🔄 智能故障转移 - 自动错误处理和恢复

正在启动服务器...
    """)
    
    # 启动服务
    uvicorn.run(
        "main:create_app",
        factory=True,
        host=host,
        port=port,
        workers=workers if not reload else 1,
        reload=reload,
        log_level=log_level,
        access_log=True,
    )


if __name__ == "__main__":
    main()