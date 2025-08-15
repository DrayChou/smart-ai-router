#!/usr/bin/env python3
"""
Smart AI Router - 统一入口
支持JSON模式(默认)和SQLite模式切换
"""

import sys
import os
import argparse
import logging
from pathlib import Path
from typing import Optional

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Union
import httpx
import asyncio
import json
import time

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 全局模式变量
STORAGE_MODE = "json"  # "json" 或 "sqlite"
app_instance = None

# Pydantic模型
class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False
    top_p: Optional[float] = 1.0
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0
    functions: Optional[List[Dict[str, Any]]] = None
    function_call: Optional[Union[str, Dict[str, str]]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Optional[Dict[str, int]] = None

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str

class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]

def get_storage_mode() -> str:
    """获取存储模式"""
    global STORAGE_MODE
    
    # 1. 命令行参数优先级最高
    if hasattr(get_storage_mode, '_cli_mode'):
        return get_storage_mode._cli_mode
    
    # 2. 环境变量
    env_mode = os.getenv('SMART_ROUTER_MODE', '').lower()
    if env_mode in ['json', 'sqlite']:
        STORAGE_MODE = env_mode
        return STORAGE_MODE
    
    # 3. 配置文件检查
    config_file = Path(__file__).parent / "config" / "simple_config.json"
    if config_file.exists():
        STORAGE_MODE = "json"
    else:
        # 检查是否有数据库文件
        db_file = Path(__file__).parent / "smart_router.db"
        if db_file.exists():
            STORAGE_MODE = "sqlite"
        else:
            STORAGE_MODE = "json"  # 默认JSON模式
    
    return STORAGE_MODE

def create_json_app() -> FastAPI:
    """创建JSON模式的应用"""
    # 优先尝试YAML配置
    try:
        from core.yaml_config import get_yaml_config_loader
        from core.json_router import JSONRouter, RoutingRequest
        from core.scheduler.task_manager import initialize_background_tasks
        
        config = get_yaml_config_loader()
        router = JSONRouter(config)
        config_type = "yaml"
        logger.info("使用YAML配置模式")
        
    except Exception as e:
        logger.warning(f"YAML配置加载失败: {e}, 回退到JSON配置")
        from core.config_loader import get_config_loader
        from core.json_router import get_router, RoutingRequest
        
        config = get_config_loader()
        router = get_router()
        config_type = "json"
    
    # 获取服务器配置
    server_config = config.get_server_config()
    
    # 创建应用
    app = FastAPI(
        title=f"Smart AI Router - {config_type.upper()} Mode",
        description=f"基于{config_type.upper()}配置的轻量个人AI智能路由系统",
        version=f"0.1.0-{config_type}",
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

    # 启动事件：初始化后台任务
    @app.on_event("startup")
    async def startup_event():
        """应用启动时初始化后台任务"""
        try:
            if config_type == "yaml":
                # 获取任务配置
                tasks_config = config.get_tasks_config()
                
                # 初始化后台任务
                await initialize_background_tasks(tasks_config, config)
                logger.info("后台任务初始化完成")
            
        except Exception as e:
            logger.error(f"初始化后台任务失败: {e}")

    # 关闭事件：清理后台任务
    @app.on_event("shutdown")
    async def shutdown_event():
        """应用关闭时清理后台任务"""
        try:
            if config_type == "yaml":
                from core.scheduler.task_manager import stop_background_tasks
                await stop_background_tasks()
                logger.info("后台任务已停止")
        except Exception as e:
            logger.error(f"停止后台任务失败: {e}")

    @app.get("/")
    async def root():
        """根路径"""
        return JSONResponse({
            "name": f"Smart AI Router - {config_type.upper()} Mode",
            "version": f"0.1.0-{config_type}",
            "description": f"基于{config_type.upper()}配置的轻量个人AI智能路由系统",
            "status": "running",
            "storage_mode": config_type,
            "endpoints": {
                "docs": "/docs",
                "health": "/health",
                "chat": "/v1/chat/completions",
                "models": "/v1/models",
            },
            "statistics": {
                "providers": len(config.providers),
                "channels": len(config.channels),
                "model_groups": len(config.model_groups),
                "enabled_channels": len(config.get_enabled_channels())
            }
        })

    @app.get("/health")
    async def health_check():
        """健康检查"""
        enabled_channels = config.get_enabled_channels()
        
        health_info = {
            "status": "healthy",
            "storage_mode": config_type,
            "timestamp": time.time(),
            "config_loaded": True,
            "enabled_channels": len(enabled_channels),
            "runtime_state": {
                "daily_spent": config.runtime_state.cost_tracking.get("daily_spent", 0.0),
                "total_requests": len(config.runtime_state.request_history),
                "health_scores": len(config.runtime_state.health_scores)
            }
        }
        
        # 如果是YAML模式，添加后台任务状态
        if config_type == "yaml":
            try:
                from core.scheduler.task_manager import get_task_manager_status
                task_status = get_task_manager_status()
                health_info["background_tasks"] = {
                    "initialized": task_status.get("initialized", False),
                    "scheduler_running": task_status.get("scheduler_status", {}).get("scheduler_running", False),
                    "total_tasks": task_status.get("scheduler_status", {}).get("total_tasks", 0),
                    "enabled_tasks": task_status.get("scheduler_status", {}).get("enabled_tasks", 0)
                }
                
                # 添加模型缓存信息
                model_cache = config.get_model_cache()
                health_info["model_cache"] = {
                    "cached_channels": len(model_cache),
                    "cache_size": len(model_cache)
                }
                
            except Exception as e:
                health_info["background_tasks"] = {"error": str(e)}
        
        return JSONResponse(health_info)

    @app.get("/v1/models", response_model=ModelsResponse)
    async def list_models():
        """列出可用模型"""
        available_models = router.get_available_models()
        
        models_data = []
        for model_id in available_models:
            models_data.append(ModelInfo(
                id=model_id,
                created=int(time.time()),
                owned_by="smart-ai-router"
            ))
        
        return ModelsResponse(data=models_data)

    @app.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest):
        """聊天完成接口"""
        start_time = time.time()
        
        try:
            # 转换请求格式
            routing_request = RoutingRequest(
                model=request.model,
                messages=[msg.dict() for msg in request.messages],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=request.stream,
                functions=request.functions or request.tools,
                required_capabilities=_infer_capabilities(request)
            )
            
            # 路由到最佳渠道
            routing_result = router.route_request(routing_request)
            
            if not routing_result:
                raise HTTPException(status_code=503, detail="没有可用的渠道")
            
            channel = routing_result.channel
            provider = config.get_provider(channel.provider)
            
            if not provider:
                raise HTTPException(status_code=500, detail=f"找不到Provider: {channel.provider}")
            
            # 调用实际API
            response = await _call_channel_api(channel, provider, request)
            
            # 更新统计信息
            latency = time.time() - start_time
            router.update_channel_health(channel.id, True, latency)
            
            # 记录请求日志
            config.add_request_log({
                "channel_id": channel.id,
                "model": request.model,
                "latency": latency,
                "success": True,
                "routing_score": routing_result.total_score
            })
            
            # 如果是流式响应
            if request.stream:
                return StreamingResponse(
                    _stream_response(response),
                    media_type="text/plain"
                )
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"处理请求失败: {e}")
            
            # 更新失败统计
            if 'routing_result' in locals():
                router.update_channel_health(routing_result.channel.id, False)
            
            raise HTTPException(status_code=500, detail=str(e))

    async def _call_channel_api(channel, provider, request: ChatCompletionRequest):
        """调用渠道API"""
        # 构建请求URL
        base_url = provider.base_url.rstrip('/')
        if not base_url.endswith('/v1'):
            base_url += '/v1'
        url = f"{base_url}/chat/completions"
        
        # 构建请求头
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "smart-ai-router/0.1.0"
        }
        
        # 根据认证类型设置头部
        if provider.auth_type == "bearer":
            headers["Authorization"] = f"Bearer {channel.api_key}"
        elif provider.auth_type == "x-api-key":
            headers["x-api-key"] = channel.api_key
        
        # 构建请求体
        request_data = request.dict(exclude_unset=True)
        request_data["model"] = channel.model_name  # 使用渠道的实际模型名
        
        # 发送请求
        timeout = httpx.Timeout(300.0)  # 5分钟超时
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=request_data, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"API调用失败: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
            
            return response.json()

    async def _stream_response(response_data):
        """处理流式响应"""
        # 这里应该实现流式响应的处理
        # 暂时简化为非流式
        yield f"data: {json.dumps(response_data)}\n\n"
        yield "data: [DONE]\n\n"

    def _infer_capabilities(request: ChatCompletionRequest) -> List[str]:
        """推断请求需要的能力"""
        capabilities = ["text"]
        
        if request.functions or request.tools:
            capabilities.append("function_calling")
        
        # 检查是否有图片内容
        for message in request.messages:
            if isinstance(message.content, list):
                for content_item in message.content:
                    if isinstance(content_item, dict) and content_item.get("type") == "image_url":
                        capabilities.append("vision")
                        break
        
        return capabilities

    @app.get("/admin/tasks/status")
    async def get_tasks_status():
        """获取后台任务状态"""
        try:
            if config_type == "yaml":
                from core.scheduler.task_manager import get_task_manager_status
                from core.scheduler.tasks.model_discovery import get_model_discovery_task
                
                # 获取任务管理器状态
                status = get_task_manager_status()
                
                # 获取模型发现任务的详细信息
                discovery_task = get_model_discovery_task()
                model_cache = discovery_task.get_cached_models()
                merged_config = discovery_task.get_merged_config()
                
                return JSONResponse({
                    "task_manager": status,
                    "model_discovery": {
                        "cache_valid": discovery_task.is_cache_valid(),
                        "last_update": discovery_task.last_update.isoformat() if discovery_task.last_update else None,
                        "cached_channels": len(model_cache) if model_cache else 0,
                        "total_models": sum(info.get('model_count', 0) for info in (model_cache or {}).values()),
                        "has_merged_config": bool(merged_config)
                    },
                    "cache_info": {
                        "config_model_cache_size": len(config.get_model_cache()),
                        "cache_directory": "cache/",
                        "cache_files": ["discovered_models.json", "merged_config.json", "model_discovery_log.json"]
                    }
                })
            else:
                return JSONResponse({
                    "error": "后台任务仅在YAML模式下可用",
                    "current_mode": config_type
                })
                
        except Exception as e:
            logger.error(f"获取任务状态失败: {e}")
            return JSONResponse({
                "error": str(e),
                "current_mode": config_type
            }, status_code=500)

    @app.post("/admin/tasks/run_model_discovery")
    async def run_model_discovery_now():
        """立即运行模型发现任务"""
        try:
            if config_type == "yaml":
                from core.scheduler.tasks.model_discovery import run_model_discovery
                
                # 获取当前配置
                channels = [ch.__dict__ if hasattr(ch, '__dict__') else ch for ch in config.get_enabled_channels()]
                current_config = {
                    'channels': channels,
                    'providers': config.providers,
                    'model_groups': config.model_groups
                }
                
                # 运行模型发现
                result = await run_model_discovery(channels, current_config)
                
                return JSONResponse({
                    "message": "模型发现任务已执行",
                    "result": result
                })
            else:
                return JSONResponse({
                    "error": "模型发现任务仅在YAML模式下可用",
                    "current_mode": config_type
                }, status_code=400)
                
        except Exception as e:
            logger.error(f"执行模型发现任务失败: {e}")
            return JSONResponse({
                "error": str(e)
            }, status_code=500)

    @app.get("/admin/config/merged")
    async def get_merged_config():
        """获取合并了模型信息的配置"""
        try:
            if config_type == "yaml":
                merged_config = config.get_merged_config_with_models()
                return JSONResponse(merged_config)
            else:
                return JSONResponse({
                    "error": "合并配置仅在YAML模式下可用",
                    "current_mode": config_type
                }, status_code=400)
                
        except Exception as e:
            logger.error(f"获取合并配置失败: {e}")
            return JSONResponse({
                "error": str(e)
            }, status_code=500)

    @app.get("/admin/pricing/models")
    async def get_model_pricing():
        """获取模型定价信息"""
        try:
            from core.scheduler.tasks.pricing_extractor import get_pricing_extractor
            
            extractor = get_pricing_extractor()
            
            # 检查是否有提取的定价数据
            if not extractor.model_pricing:
                # 尝试提取定价
                from core.scheduler.tasks.pricing_extractor import extract_pricing_from_discovered_models
                result = extract_pricing_from_discovered_models()
                
                if not result.get("success"):
                    return JSONResponse({
                        "error": "无法获取定价信息",
                        "details": result.get("error", "未知错误")
                    }, status_code=500)
            
            return JSONResponse({
                "total_models": len(extractor.model_pricing),
                "pricing_data": extractor.model_pricing,
                "statistics": extractor.pricing_stats
            })
            
        except Exception as e:
            logger.error(f"获取模型定价失败: {e}")
            return JSONResponse({
                "error": str(e)
            }, status_code=500)

    @app.get("/admin/pricing/cheapest")
    async def get_cheapest_models(limit: int = 10, exclude_free: bool = False):
        """获取最便宜的模型"""
        try:
            from core.scheduler.tasks.pricing_extractor import get_pricing_extractor
            
            extractor = get_pricing_extractor()
            cheapest = extractor.get_cheapest_models(limit, exclude_free)
            
            return JSONResponse({
                "limit": limit,
                "exclude_free": exclude_free,
                "models": cheapest
            })
            
        except Exception as e:
            logger.error(f"获取最便宜模型失败: {e}")
            return JSONResponse({
                "error": str(e)
            }, status_code=500)

    @app.get("/admin/pricing/provider/{provider}")
    async def get_provider_pricing(provider: str):
        """获取特定Provider的定价信息"""
        try:
            from core.scheduler.tasks.pricing_extractor import get_pricing_extractor
            
            extractor = get_pricing_extractor()
            models = extractor.get_models_by_provider(provider)
            
            if not models:
                return JSONResponse({
                    "error": f"未找到Provider '{provider}' 的模型",
                    "available_providers": list(extractor.pricing_stats.get("by_provider", {}).keys())
                }, status_code=404)
            
            return JSONResponse({
                "provider": provider,
                "model_count": len(models),
                "models": models
            })
            
        except Exception as e:
            logger.error(f"获取Provider定价失败: {e}")
            return JSONResponse({
                "error": str(e)
            }, status_code=500)

    @app.post("/admin/pricing/estimate")
    async def estimate_cost(request_data: dict):
        """估算请求成本"""
        try:
            model_id = request_data.get("model_id")
            input_tokens = request_data.get("input_tokens", 0)
            output_tokens = request_data.get("output_tokens", 0)
            
            if not model_id:
                return JSONResponse({
                    "error": "缺少model_id参数"
                }, status_code=400)
            
            from core.scheduler.tasks.pricing_extractor import get_pricing_extractor
            
            extractor = get_pricing_extractor()
            cost = extractor.estimate_cost(model_id, input_tokens, output_tokens)
            
            if cost is None:
                return JSONResponse({
                    "error": f"未找到模型 '{model_id}' 的定价信息"
                }, status_code=404)
            
            return JSONResponse({
                "model_id": model_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_cost": cost,
                "cost_breakdown": {
                    "input_cost": extractor.model_pricing[model_id]["pricing"]["input_per_million_tokens"] * input_tokens / 1000000,
                    "output_cost": extractor.model_pricing[model_id]["pricing"]["output_per_million_tokens"] * output_tokens / 1000000
                }
            })
            
        except Exception as e:
            logger.error(f"成本估算失败: {e}")
            return JSONResponse({
                "error": str(e)
            }, status_code=500)

    @app.post("/admin/pricing/extract")
    async def extract_pricing():
        """手动触发定价提取"""
        try:
            from core.scheduler.tasks.pricing_extractor import extract_pricing_from_discovered_models
            
            result = extract_pricing_from_discovered_models()
            
            return JSONResponse({
                "message": "定价提取任务已执行",
                "result": result
            })
            
        except Exception as e:
            logger.error(f"定价提取失败: {e}")
            return JSONResponse({
                "error": str(e)
            }, status_code=500)

    return app

def create_sqlite_app() -> FastAPI:
    """创建SQLite模式的应用"""
    # 导入原有的数据库模式组件
    try:
        from core.database import get_db_session
        from core.models import VirtualModelGroup
        from core.router.base import RoutingEngine, RoutingRequest as SQLiteRoutingRequest
        from core.utils.config import load_config
        from core.utils.logger import setup_logging
        from api.admin import router as admin_router
        from api.chat import router as chat_router
        from api.health import router as health_router
    except ImportError as e:
        raise RuntimeError(f"SQLite模式依赖缺失: {e}. 请使用JSON模式或安装相关依赖。")
    
    # 加载配置
    config = load_config()

    # 设置日志
    setup_logging(config.get("logging", {}))

    # 创建应用
    app = FastAPI(
        title="Smart AI Router - SQLite Mode",
        description="基于数据库的完整AI智能路由系统",
        version="0.1.0-sqlite",
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
            "name": "Smart AI Router - SQLite Mode",
            "version": "0.1.0-sqlite",
            "description": "基于数据库的完整AI智能路由系统",
            "status": "running",
            "storage_mode": "sqlite",
            "endpoints": {
                "docs": "/docs",
                "health": "/health",
                "chat": "/v1/chat/completions",
                "models": "/v1/models",
                "admin": "/admin",
            },
        })

    # 存储配置到应用状态
    app.state.config = config

    return app

def create_app() -> FastAPI:
    """根据模式创建对应的应用"""
    global app_instance
    
    mode = get_storage_mode()
    logger.info(f"启动模式: {mode}")
    
    if mode == "json":
        app_instance = create_json_app()
    elif mode == "sqlite":
        app_instance = create_sqlite_app()
    else:
        raise ValueError(f"不支持的模式: {mode}")
    
    return app_instance

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Smart AI Router - 统一入口")
    
    parser.add_argument(
        "--mode", 
        choices=["json", "sqlite"],
        default=None,
        help="存储模式: json(默认,轻量) 或 sqlite(完整功能)"
    )
    
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="服务器主机地址 (默认: 127.0.0.1)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="服务器端口 (默认: 8000)"
    )
    
    parser.add_argument(
        "--reload",
        action="store_true",
        help="启用自动重载 (开发模式)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true", 
        help="启用调试模式"
    )
    
    return parser.parse_args()

def main():
    """主函数"""
    try:
        args = parse_args()
        
        # 设置命令行模式
        if args.mode:
            get_storage_mode._cli_mode = args.mode
        
        # 获取最终模式
        mode = get_storage_mode()
        
        # 加载对应模式的配置
        if mode == "json":
            try:
                from core.config_loader import get_config_loader
                config_loader = get_config_loader()
                server_config = config_loader.get_server_config()
                
                host = args.host or server_config.get("host", "127.0.0.1")
                port = args.port or server_config.get("port", 8000)
                debug = args.debug or server_config.get("debug", False)
                
                # 统计信息
                enabled_channels = len(config_loader.get_enabled_channels())
                total_channels = len(config_loader.channels)
                providers = len(config_loader.providers)
                
            except Exception as e:
                logger.warning(f"加载JSON配置失败: {e}, 使用默认配置")
                host = args.host
                port = args.port  
                debug = args.debug
                enabled_channels = 0
                total_channels = 0
                providers = 0
                
        else:  # sqlite模式
            try:
                from core.utils.config import load_config
                config = load_config()
                server_config = config.get("server", {})
                
                host = args.host or server_config.get("host", "127.0.0.1")
                port = args.port or server_config.get("port", 8000)
                debug = args.debug or server_config.get("debug", False)
                
                # 这里可以添加SQLite模式的统计信息
                enabled_channels = "N/A"
                total_channels = "N/A"
                providers = "N/A"
                
            except Exception as e:
                logger.warning(f"加载SQLite配置失败: {e}, 使用默认配置")
                host = args.host
                port = args.port
                debug = args.debug
                enabled_channels = "N/A"
                total_channels = "N/A"
                providers = "N/A"

        print(f"""
Smart AI Router 统一入口启动中...

运行模式: {mode.upper()}
存储方式: {'YAML/JSON文件配置' if mode == "json" else 'SQLite数据库'}
服务地址: http://{host}:{port}
API文档: http://{host}:{port}/docs
健康检查: http://{host}:{port}/health
聊天接口: http://{host}:{port}/v1/chat/completions

系统统计:
  - 存储模式: {mode}
  - Providers: {providers}
  - 总渠道数: {total_channels}
  - 可用渠道: {enabled_channels}

模式切换:
  命令行: --mode json|sqlite
  环境变量: SMART_ROUTER_MODE=json|sqlite
  
特性对比:
  JSON模式: 轻量便携、零依赖、配置直观
  SQLite模式: 功能完整、高性能、企业级

正在启动 {mode.upper()} 模式服务器...
        """)

        # 启动服务
        uvicorn.run(
            "main:create_app",
            factory=True,
            host=host,
            port=port,
            reload=args.reload or debug,
            log_level="debug" if debug else "info",
            access_log=True,
        )

    except KeyboardInterrupt:
        logger.info("用户中断，正在退出...")
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()