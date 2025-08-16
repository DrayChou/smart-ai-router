# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Smart AI Router - 统一入口 (YAML模式)
"""

from core.scheduler.task_manager import initialize_background_tasks, stop_background_tasks
from core.json_router import JSONRouter, RoutingRequest, TagNotFoundError
from core.yaml_config import get_yaml_config_loader
from core.utils.http_client_pool import get_http_pool, close_global_pool
from core.utils.smart_cache import close_global_cache
import time
import json
import httpx
import asyncio
from typing import List, Dict, Any, Union
from pydantic import BaseModel
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
import uvicorn
import sys
import os
import argparse
import logging
from pathlib import Path
from typing import Optional

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))


# 导入核心组件

# 设置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Pydantic 模型定义 ---


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


# --- Tokenizer 工具 ---
tiktoken_encoder = None


def get_tiktoken_encoder():
    global tiktoken_encoder
    if tiktoken_encoder is None:
        try:
            import tiktoken
            tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
            logger.info("tiktoken encoder loaded successfully.")
        except ImportError:
            logger.warning(
                "tiktoken library not found, token calculation will be approximate.")
            tiktoken_encoder = "simple"
        except Exception as e:
            logger.error(f"Failed to load tiktoken encoder: {e}")
            tiktoken_encoder = "simple"
    return tiktoken_encoder


def estimate_prompt_tokens(messages: List[Dict[str, Any]]) -> int:
    encoder = get_tiktoken_encoder()
    if encoder == "simple" or not hasattr(encoder, 'encode'):
        return sum(len(str(msg.get("content", "")).split()) for msg in messages)

    num_tokens = 0
    for message in messages:
        num_tokens += 4
        for key, value in message.items():
            if isinstance(value, str):
                num_tokens += len(encoder.encode(value))
            if key == "name":
                num_tokens -= 1
    num_tokens += 2
    return num_tokens

# --- FastAPI 应用创建 ---


def create_app() -> FastAPI:
    config = get_yaml_config_loader()
    router = JSONRouter(config)
    server_config = config.get_server_config()

    app = FastAPI(
        title="Smart AI Router - YAML Mode",
        description="A lightweight AI router for personal use, driven by a YAML configuration.",
        version="0.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=server_config.get("cors_origins", ["*"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup_event():
        try:
            tasks_config = config.get_tasks_config()
            await initialize_background_tasks(tasks_config, config)
            logger.info("Background tasks initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize background tasks: {e}")

    @app.on_event("shutdown")
    async def shutdown_event():
        try:
            await stop_background_tasks()
            logger.info("Background tasks stopped.")
            
            # 关闭全局HTTP连接池
            await close_global_pool()
            logger.info("HTTP connection pool closed.")
            
            # 关闭全局智能缓存
            await close_global_cache()
            logger.info("Smart cache closed.")
        except Exception as e:
            logger.error(f"Failed to stop background tasks or close pools: {e}")

    @app.get("/")
    async def root():
        return {"name": "Smart AI Router", "status": "running", "docs": "/docs"}

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "config_loaded": True}

    @app.get("/v1/models", response_model=ModelsResponse)
    async def list_models():
        """返回所有可用的模型，包括配置的虚拟模型和自动发现的物理模型"""
        all_models = set()

        # 1. 从路由器获取在配置中定义好的模型
        configured_models = router.get_available_models()
        for model_id in configured_models:
            all_models.add(model_id)

        # 2. 从模型发现缓存中获取所有物理模型
        model_cache = config.get_model_cache()
        if model_cache:
            for channel_id, discovery_data in model_cache.items():
                for model_name in discovery_data.get("models", []):
                    all_models.add(model_name)

        # 3. 构建响应
        models_data = []
        for model_id in sorted(list(all_models)):
            models_data.append(ModelInfo(
                id=model_id,
                created=int(time.time()),
                owned_by="smart-ai-router",
                name=model_id,
                model_type="model_group" if model_id.startswith(
                    "auto:") else "model",
                available=True
            ))

        return ModelsResponse(data=models_data, total_models=len(models_data))

    @app.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest):
        start_time = time.time()
        get_tiktoken_encoder()

        logger.info(f"🌐 API REQUEST: Received chat completion request for model '{request.model}' (stream: {request.stream})")
        logger.info(f"🌐 REQUEST DETAILS: {len(request.messages)} messages, max_tokens: {request.max_tokens}, temperature: {request.temperature}")

        try:
            routing_request = RoutingRequest(
                model=request.model,
                messages=[msg.dict() for msg in request.messages],
                stream=request.stream,
                required_capabilities=_infer_capabilities(request)
            )

            # 1. 获取所有候选渠道，按顺序排列
            logger.info(f"🔄 CHANNEL ROUTING: Starting routing process for model '{request.model}'")
            candidate_channels = router.route_request(routing_request)
            if not candidate_channels:
                total_time = time.time() - start_time
                logger.error(f"❌ ROUTING FAILED: No available channels found for model '{request.model}'")
                
                # 为无可用渠道错误添加调试头信息
                no_channels_headers = {
                    "X-Router-Status": "no-channels-found",
                    "X-Router-Time": f"{total_time:.3f}s",
                    "X-Router-Model-Requested": request.model
                }
                
                return JSONResponse(
                    status_code=503,
                    content={"detail": f"No available channels found for model '{request.model}'."},
                    headers=no_channels_headers
                )

            # 2. 智能渠道选择：如果有多个渠道，先并发快速检查可用性
            logger.info(f"🔄 CHANNEL SELECTION: Processing {len(candidate_channels)} channels with intelligent routing")
            
            # 如果有多个渠道，先并发检查前3个渠道的可用性
            if len(candidate_channels) > 1:
                logger.info(f"⚡ FAST CHECK: Pre-checking availability of top {min(3, len(candidate_channels))} channels")
                
                # 并发检查前3个渠道
                check_tasks = []
                for i, routing_score in enumerate(candidate_channels[:3]):
                    channel = routing_score.channel
                    provider = config.get_provider(channel.provider)
                    if provider:
                        url, headers, _ = _prepare_channel_api_request(channel, provider, request, routing_score.matched_model)
                        check_tasks.append((i, channel, _fast_channel_check(url, headers)))
                
                # 执行并发检查
                if check_tasks:
                    check_results = await asyncio.gather(*[task[2] for task in check_tasks], return_exceptions=True)
                    
                    # 找出第一个可用的渠道
                    for i, (original_index, channel, result) in enumerate(check_tasks):
                        if i < len(check_results) and not isinstance(check_results[i], Exception):
                            is_available, status_code, message = check_results[i]
                            if is_available:
                                logger.info(f"⚡ FAST CHECK: Channel '{channel.name}' is available (HTTP {status_code}), prioritizing")
                                # 把这个渠道移到首位
                                priority_channel = candidate_channels.pop(original_index)
                                candidate_channels.insert(0, priority_channel)
                                break
                            else:
                                logger.info(f"⚡ FAST CHECK: Channel '{channel.name}' unavailable ({status_code}: {message})")
            
            last_error = None
            # 智能渠道黑名单：记录已失败的渠道，避免重复尝试
            failed_channels = set()
            
            for attempt_num, routing_score in enumerate(candidate_channels, 1):
                channel = routing_score.channel
                provider = config.get_provider(channel.provider)

                # 检查渠道是否已被拉黑
                if channel.id in failed_channels:
                    logger.info(f"⚫ SKIP #{attempt_num}: Channel '{channel.name}' (ID: {channel.id}) is blacklisted due to previous failures")
                    continue

                if not provider:
                    logger.warning(f"❌ ATTEMPT #{attempt_num}: Provider '{channel.provider}' for channel '{channel.name}' not found, skipping")
                    continue

                logger.info(f"🚀 ATTEMPT #{attempt_num}: Trying channel '{channel.name}' (ID: {channel.id}) with score {routing_score.total_score:.3f}")
                logger.info(f"🚀 ATTEMPT #{attempt_num}: Score breakdown - {routing_score.reason}")

                try:
                    url, headers, request_data = _prepare_channel_api_request(channel, provider, request, routing_score.matched_model)
                    
                    logger.info(f"📡 FORWARDING: Sending request to {url}")
                    logger.info(f"📡 FORWARDING: Target model -> '{request_data['model']}'")
                    logger.debug(f"📡 FORWARDING: Headers -> {dict(headers)}")

                    if request.stream:
                        logger.info(f"🌊 STREAMING: Starting streaming response for channel '{channel.name}'")
                        
                        # 为流式请求添加调试头信息 (移除中文字符以避免编码错误)
                        stream_debug_headers = {
                            "X-Router-Channel": f"{channel.name} (ID: {channel.id})",
                            "X-Router-Provider": provider.name if hasattr(provider, 'name') else channel.provider,
                            "X-Router-Model": routing_score.matched_model or channel.model_name,
                            "X-Router-Score": f"{routing_score.total_score:.3f}",
                            "X-Router-Attempts": str(attempt_num),
                            "X-Router-Score-Breakdown": f"cost:{routing_score.cost_score:.2f} speed:{routing_score.speed_score:.2f} quality:{routing_score.quality_score:.2f} reliability:{routing_score.reliability_score:.2f}",
                            "X-Router-Type": "streaming"
                        }
                        
                        # 对于流式请求，我们需要一种方法来检测初始错误
                        return StreamingResponse(
                            _stream_channel_api(url, headers, request_data, channel.id),
                            media_type="text/event-stream",
                            headers=stream_debug_headers
                        )

                    # 非流式请求 - 使用优化的快速失败检测
                    logger.info(f"⏳ REQUEST: Sending optimized request to channel '{channel.name}'")
                    response_json = await _call_channel_api(url, headers, request_data)

                    # 成功，更新健康度并返回
                    latency = time.time() - start_time
                    router.update_channel_health(channel.id, True, latency)
                    
                    logger.info(f"✅ SUCCESS: Channel '{channel.name}' responded successfully (latency: {latency:.3f}s)")
                    logger.info(f"✅ RESPONSE: Model used -> {response_json.get('model', 'unknown')}")
                    logger.info(f"✅ RESPONSE: Usage -> {response_json.get('usage', {})}")
                    
                    # 添加路由调试头信息 (移除中文字符以避免编码错误)
                    debug_headers = {
                        "X-Router-Channel": f"{channel.name} (ID: {channel.id})",
                        "X-Router-Provider": provider.name if hasattr(provider, 'name') else channel.provider,
                        "X-Router-Model": routing_score.matched_model or channel.model_name,
                        "X-Router-Score": f"{routing_score.total_score:.3f}",
                        "X-Router-Attempts": str(attempt_num),
                        "X-Router-Latency": f"{latency:.3f}s",
                        "X-Router-Score-Breakdown": f"cost:{routing_score.cost_score:.2f} speed:{routing_score.speed_score:.2f} quality:{routing_score.quality_score:.2f} reliability:{routing_score.reliability_score:.2f}"
                    }
                    
                    return JSONResponse(content=response_json, headers=debug_headers)

                except httpx.HTTPStatusError as e:
                    error_text = e.response.text if hasattr(e.response, 'text') else str(e)
                    logger.warning(f"❌ ATTEMPT #{attempt_num} FAILED: Channel '{channel.name}' returned HTTP {e.response.status_code}")
                    logger.warning(f"❌ ERROR DETAILS: {error_text[:200]}...")
                    last_error = e
                    router.update_channel_health(channel.id, False)
                    
                    # 智能拉黑：对于认证错误等永久性错误，拉黑整个渠道
                    if e.response.status_code in [401, 403]:  # Unauthorized, Forbidden
                        failed_channels.add(channel.id)
                        logger.warning(f"🚫 CHANNEL BLACKLISTED: Channel '{channel.name}' (ID: {channel.id}) blacklisted due to HTTP {e.response.status_code}")
                        logger.info(f"⚡ SKIP OPTIMIZATION: Will skip all remaining models from channel '{channel.name}'")
                    
                    # 继续下一个渠道
                    if attempt_num < len(candidate_channels):
                        logger.info(f"🔄 FAILOVER: Trying next channel (#{attempt_num + 1})")
                    continue
                    
                except httpx.RequestError as e:
                    logger.warning(f"❌ ATTEMPT #{attempt_num} FAILED: Channel '{channel.name}' network error: {str(e)}")
                    last_error = e
                    router.update_channel_health(channel.id, False)
                    # 继续下一个渠道
                    if attempt_num < len(candidate_channels):
                        logger.info(f"🔄 FAILOVER: Trying next channel (#{attempt_num + 1})")
                    continue

            # 如果所有渠道都失败了
            total_time = time.time() - start_time
            logger.error(f"💥 ALL CHANNELS FAILED: All {len(candidate_channels)} channels failed for model '{request.model}' after {total_time:.3f}s")
            
            error_detail = f"All available channels failed. Last error: {str(last_error)}"
            if hasattr(last_error, 'response'):
                error_detail += f" - Details: {last_error.response.text}"

            logger.error(f"💥 FINAL ERROR: {error_detail}")
            
            # 为错误响应添加调试头信息
            error_headers = {
                "X-Router-Status": "all-channels-failed",
                "X-Router-Attempts": str(len(candidate_channels)),
                "X-Router-Time": f"{total_time:.3f}s",
                "X-Router-Model-Requested": request.model
            }
            
            return JSONResponse(
                status_code=503,
                content={"detail": error_detail},
                headers=error_headers
            )

        except TagNotFoundError as e:
            total_time = time.time() - start_time
            logger.error(f"❌ TAG NOT FOUND: {e} (after {total_time:.3f}s)")
            
            # 为标签不存在错误添加调试头信息
            tag_error_headers = {
                "X-Router-Status": "tag-not-found",
                "X-Router-Tags": ",".join(e.tags),
                "X-Router-Time": f"{total_time:.3f}s",
                "X-Router-Model-Requested": request.model
            }
            
            return JSONResponse(
                status_code=404,
                content={"detail": str(e)},
                headers=tag_error_headers
            )
        except HTTPException:
            raise
        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"💥 UNEXPECTED ERROR: Internal error occurred after {total_time:.3f}s: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"An internal server error occurred: {e}")

    def _prepare_channel_api_request(channel, provider, request: ChatCompletionRequest, matched_model: Optional[str] = None):
        base_url = (channel.base_url or provider.base_url).rstrip('/')
        if not base_url.endswith('/v1'):
            base_url += '/v1'
        url = f"{base_url}/chat/completions"

        headers = {"Content-Type": "application/json",
                   "User-Agent": "smart-ai-router/0.2.0"}
        if provider.auth_type == "bearer":
            headers["Authorization"] = f"Bearer {channel.api_key}"
        elif provider.auth_type == "x-api-key":
            headers["x-api-key"] = channel.api_key

        request_data = request.dict(exclude_unset=True)
        
        # 智能模型选择逻辑
        if matched_model:
            # 如果有匹配的模型（来自标签路由或物理模型路由），优先使用它
            request_data["model"] = matched_model
            logger.info(f"📡 MODEL SELECTION: Using matched model '{matched_model}' for routing")
        elif request.model.startswith("auto:") or request.model.startswith("tag:"):
            # 虚拟模型查询但没有匹配模型，使用渠道默认模型
            request_data["model"] = channel.model_name
            logger.info(f"📡 MODEL SELECTION: Using channel default model '{channel.model_name}' for virtual query")
        else:
            # 物理模型请求，使用用户请求的具体模型名
            request_data["model"] = request.model
            logger.info(f"📡 MODEL SELECTION: Using requested model '{request.model}' for physical query")
        
        return url, headers, request_data

    async def _stream_channel_api(url: str, headers: dict, request_data: dict, channel_id: str):
        """优化的流式API调用，使用连接池和预检机制"""
        chunk_count = 0
        stream_start_time = time.time()
        
        logger.info(f"🌊 STREAM START: Initiating optimized streaming request to channel '{channel_id}'")
        logger.info(f"🌊 STREAM URL: {url}")
        
        try:
            # 使用连接池进行流式请求
            http_pool = get_http_pool()
            
            async with http_pool.stream("POST", url, json=request_data, headers=headers) as response:
                # 优化：快速检查状态码，避免等待完整错误响应
                if response.status_code != 200:
                    # 读取少量错误信息就足够了
                    error_body = await response.aread(max_bytes=1024)
                    logger.error(f"🌊 STREAM ERROR: Channel '{channel_id}' returned status {response.status_code}")
                    
                    # 快速失败，不继续读取完整响应
                    error_text = error_body.decode('utf-8', errors='ignore')[:200]
                    logger.error(f"🌊 STREAM ERROR DETAILS: {error_text}")
                    router.update_channel_health(channel_id, False)
                    
                    # 向客户端返回错误信息
                    yield f"data: {json.dumps({'error': {'message': f'Upstream API error: {error_text}', 'code': response.status_code}})}\n\n"
                    return

                logger.info(f"🌊 STREAM CONNECTED: Successfully connected to channel '{channel_id}', starting optimized data flow")
                
                # 优化的流式读取
                async for chunk in response.aiter_bytes(chunk_size=8192):  # 优化chunk大小
                    if chunk:
                        chunk_count += 1
                        if chunk_count % 20 == 0:  # 减少日志频率
                            logger.debug(f"🌊 STREAMING: Received {chunk_count} chunks from channel '{channel_id}'")
                    yield chunk
                        
            # 成功后更新健康度
            stream_duration = time.time() - stream_start_time
            router.update_channel_health(channel_id, True, stream_duration)
            logger.info(f"🌊 STREAM COMPLETE: Channel '{channel_id}' completed optimized streaming {chunk_count} chunks in {stream_duration:.3f}s")
            
        except httpx.HTTPStatusError as e:
            error_text = e.response.text if hasattr(e.response, 'text') else str(e)
            logger.error(f"🌊 STREAM FAILED: Channel '{channel_id}' HTTP error {e.response.status_code}: {error_text[:200]}...")
            router.update_channel_health(channel_id, False)
            yield f"data: {json.dumps({'error': {'message': f'Upstream API error: {error_text}', 'code': e.response.status_code}})}\n\n"
            
        except Exception as e:
            logger.error(f"🌊 STREAM EXCEPTION: Streaming request for channel '{channel_id}' failed: {e}", exc_info=True)
            router.update_channel_health(channel_id, False)
            yield f"data: {json.dumps({'error': {'message': str(e), 'code': 500}})}\n\n"

    async def _fast_channel_check(url: str, headers: dict) -> tuple[bool, int, str]:
        """快速检查渠道是否可用（使用连接池和缓存）"""
        from core.utils.smart_cache import cache_get, cache_set
        
        # 生成缓存键
        cache_key = f"{url}:{hash(str(headers))}"
        
        # 检查缓存的可用性结果
        cached_result = await cache_get("channel_availability", cache_key)
        if cached_result:
            logger.debug(f"使用缓存的渠道可用性结果: {url}")
            return cached_result['available'], cached_result['status_code'], cached_result['message']
        
        try:
            http_pool = get_http_pool()
            
            # 发送小数据量测试
            test_data = {
                "model": "test-availability",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1
            }
            
            # 使用连接池的流式请求
            async with http_pool.stream('POST', url, json=test_data, headers=headers) as response:
                # 只检查状态码，不读取内容
                if response.status_code in [200, 400, 404, 422]:  # 这些都表明服务在线
                    result = {'available': True, 'status_code': response.status_code, 'message': "OK"}
                    await cache_set("channel_availability", cache_key, result)
                    return True, response.status_code, "OK"
                else:
                    result = {'available': False, 'status_code': response.status_code, 'message': "Service error"}
                    await cache_set("channel_availability", cache_key, result)
                    return False, response.status_code, "Service error"
        except Exception as e:
            result = {'available': False, 'status_code': 0, 'message': str(e)}
            await cache_set("channel_availability", cache_key, result)
            return False, 0, str(e)
    
    async def _call_channel_api(url: str, headers: dict, request_data: dict):
        """优化的API调用，使用连接池和快速失败检测"""
        http_pool = get_http_pool()
        
        # 使用连接池的流式请求来快速检查HTTP状态码
        async with http_pool.stream('POST', url, json=request_data, headers=headers) as response:
            # 先检查状态码，如果不是200就立即失败
            if response.status_code != 200:
                # 读取错误信息（最多读1KB就够了）
                error_content = await response.aread(max_bytes=1024)
                response._content = error_content  # 设置内容以便后续错误处理可以访问
                response.raise_for_status()
            
            # 状态码正常，读取完整响应
            content = await response.aread()
            return response.json()



    def _infer_capabilities(request: ChatCompletionRequest) -> List[str]:
        capabilities = ["text"]
        if request.functions or request.tools:
            capabilities.append("function_calling")
        for message in request.messages:
            if isinstance(message.content, list):
                for item in message.content:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        capabilities.append("vision")
                        break
        return capabilities

    return app

# --- Main Execution ---


def main():
    parser = argparse.ArgumentParser(description="Smart AI Router - YAML Mode")
    parser.add_argument("--host", default=None, help="Server host address")
    parser.add_argument("--port", type=int, default=None, help="Server port")
    parser.add_argument("--reload", action="store_true",
                        help="Enable auto-reload (for development)")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug mode")
    args = parser.parse_args()

    try:
        config = get_yaml_config_loader().get_server_config()
        host = args.host or config.get("host", "127.0.0.1")
        port = args.port or config.get("port", 7601)
        debug = args.debug or config.get("debug", False)

        print(f"\n--- Smart AI Router ---\n")
        print(f"Mode: YAML (single mode)")
        print(f"Configuration: config/router_config.yaml")
        print(f"Service running at: http://{host}:{port}")
        print(f"API Docs available at: http://{host}:{port}/docs\n")

        uvicorn.run(
            "main:create_app",
            factory=True,
            host=host,
            port=port,
            reload=args.reload or debug,
            log_level="debug" if debug else "info",
        )
    except FileNotFoundError:
        logger.error(
            "FATAL: Configuration file 'config/router_config.yaml' not found.")
        logger.error(
            "Please copy 'config/router_config.yaml.template' to 'config/router_config.yaml' and set it up.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"FATAL: Failed to start application: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
