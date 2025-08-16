# -*- coding: utf-8 -*-
"""
Chat completion request handler with improved architecture
"""
import time
import json
import asyncio
from typing import List, Dict, Any, Optional, Union, Tuple
from dataclasses import dataclass
import logging

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ..json_router import JSONRouter, RoutingRequest, TagNotFoundError, RoutingScore
from ..yaml_config import YAMLConfigLoader
from ..utils.http_client_pool import get_http_pool
from ..utils.smart_cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# --- Request/Response Models ---

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

@dataclass
class RoutingResult:
    """路由结果包装"""
    candidates: List[RoutingScore]
    execution_time: float
    total_candidates: int
    
@dataclass 
class ChannelRequestInfo:
    """渠道请求信息"""
    url: str
    headers: Dict[str, str]
    request_data: Dict[str, Any]
    channel: Any
    provider: Any
    matched_model: Optional[str]

# --- Core Handler Class ---

class ChatCompletionHandler:
    """聊天完成请求处理器"""
    
    def __init__(self, config_loader: YAMLConfigLoader, router: JSONRouter):
        self.config = config_loader
        self.router = router
        
    async def handle_request(self, request: ChatCompletionRequest) -> Union[JSONResponse, StreamingResponse]:
        """处理聊天完成请求的主入口"""
        start_time = time.time()
        
        logger.info(f"🌐 API REQUEST: Received chat completion request for model '{request.model}' (stream: {request.stream})")
        logger.info(f"🌐 REQUEST DETAILS: {len(request.messages)} messages, max_tokens: {request.max_tokens}, temperature: {request.temperature}")
        
        try:
            # 步骤1: 路由请求获取候选渠道
            routing_result = await self._route_request_with_fallback(request, start_time)
            if not routing_result.candidates:
                return self._create_no_channels_error(request.model, time.time() - start_time)
            
            # 步骤2: 执行请求并处理重试
            return await self._execute_request_with_retry(request, routing_result, start_time)
            
        except TagNotFoundError as e:
            return self._handle_tag_not_found_error(e, request.model, time.time() - start_time)
        except HTTPException:
            raise
        except Exception as e:
            return self._handle_unexpected_error(e, request.model, time.time() - start_time)
    
    async def _route_request_with_fallback(self, request: ChatCompletionRequest, start_time: float) -> RoutingResult:
        """执行路由请求和智能预检"""
        routing_request = RoutingRequest(
            model=request.model,
            messages=[msg.dict() for msg in request.messages],
            stream=request.stream,
            required_capabilities=self._infer_capabilities(request)
        )
        
        logger.info(f"🔄 CHANNEL ROUTING: Starting routing process for model '{request.model}'")
        candidate_channels = self.router.route_request(routing_request)
        
        if not candidate_channels:
            return RoutingResult(candidates=[], execution_time=time.time() - start_time, total_candidates=0)
        
        logger.info(f"🔄 CHANNEL SELECTION: Processing {len(candidate_channels)} channels with intelligent routing")
        
        # 智能渠道预检 - 如果有多个渠道，先并发检查前3个
        if len(candidate_channels) > 1:
            await self._perform_concurrent_channel_check(candidate_channels)
        
        return RoutingResult(
            candidates=candidate_channels,
            execution_time=time.time() - start_time,
            total_candidates=len(candidate_channels)
        )
    
    async def _perform_concurrent_channel_check(self, candidate_channels: List[RoutingScore]) -> None:
        """执行并发渠道可用性检查"""
        logger.info(f"⚡ FAST CHECK: Pre-checking availability of top {min(3, len(candidate_channels))} channels")
        
        check_tasks = []
        for i, routing_score in enumerate(candidate_channels[:3]):
            channel = routing_score.channel
            provider = self.config.get_provider(channel.provider)
            if provider:
                channel_info = self._prepare_channel_request_info(channel, provider, None, routing_score.matched_model)
                check_tasks.append((i, channel, self._fast_channel_check(channel_info.url, channel_info.headers)))
        
        if check_tasks:
            check_results = await asyncio.gather(*[task[2] for task in check_tasks], return_exceptions=True)
            
            # 找出第一个可用的渠道并移到首位
            for i, (original_index, channel, result) in enumerate(check_tasks):
                if i < len(check_results) and not isinstance(check_results[i], Exception):
                    is_available, status_code, message = check_results[i]
                    if is_available:
                        logger.info(f"⚡ FAST CHECK: Channel '{channel.name}' is available (HTTP {status_code}), prioritizing")
                        priority_channel = candidate_channels.pop(original_index)
                        candidate_channels.insert(0, priority_channel)
                        break
                    else:
                        logger.info(f"⚡ FAST CHECK: Channel '{channel.name}' unavailable ({status_code}: {message})")
    
    async def _execute_request_with_retry(self, request: ChatCompletionRequest, routing_result: RoutingResult, start_time: float) -> Union[JSONResponse, StreamingResponse]:
        """执行请求并处理重试逻辑"""
        last_error = None
        failed_channels = set()  # 智能渠道黑名单
        
        for attempt_num, routing_score in enumerate(routing_result.candidates, 1):
            channel = routing_score.channel
            provider = self.config.get_provider(channel.provider)
            
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
                channel_info = self._prepare_channel_request_info(channel, provider, request, routing_score.matched_model)
                
                logger.info(f"📡 FORWARDING: Sending request to {channel_info.url}")
                logger.info(f"📡 FORWARDING: Target model -> '{channel_info.request_data['model']}'")
                
                if request.stream:
                    return await self._handle_streaming_request(request, channel_info, routing_score, attempt_num)
                else:
                    return await self._handle_regular_request(request, channel_info, routing_score, attempt_num, start_time)
                    
            except httpx.HTTPStatusError as e:
                last_error = e
                self._handle_http_status_error(e, channel, attempt_num, failed_channels, routing_result.candidates)
                continue
            except httpx.RequestError as e:
                last_error = e
                self._handle_request_error(e, channel, attempt_num, routing_result.candidates)
                continue
        
        # 所有渠道都失败了
        return self._create_all_channels_failed_error(request.model, routing_result.candidates, last_error, time.time() - start_time)
    
    async def _handle_streaming_request(self, request: ChatCompletionRequest, channel_info: ChannelRequestInfo, routing_score: RoutingScore, attempt_num: int) -> StreamingResponse:
        """处理流式请求"""
        logger.info(f"🌊 STREAMING: Starting streaming response for channel '{channel_info.channel.name}'")
        
        debug_headers = self._create_debug_headers(channel_info, routing_score, attempt_num, "streaming")
        
        return StreamingResponse(
            self._stream_channel_api(channel_info.url, channel_info.headers, channel_info.request_data, channel_info.channel.id),
            media_type="text/event-stream",
            headers=debug_headers
        )
    
    async def _handle_regular_request(self, request: ChatCompletionRequest, channel_info: ChannelRequestInfo, routing_score: RoutingScore, attempt_num: int, start_time: float) -> JSONResponse:
        """处理常规请求"""
        logger.info(f"⏳ REQUEST: Sending optimized request to channel '{channel_info.channel.name}'")
        
        response_json = await self._call_channel_api(channel_info.url, channel_info.headers, channel_info.request_data)
        
        # 成功，更新健康度并返回
        latency = time.time() - start_time
        self.router.update_channel_health(channel_info.channel.id, True, latency)
        
        logger.info(f"✅ SUCCESS: Channel '{channel_info.channel.name}' responded successfully (latency: {latency:.3f}s)")
        logger.info(f"✅ RESPONSE: Model used -> {response_json.get('model', 'unknown')}")
        logger.info(f"✅ RESPONSE: Usage -> {response_json.get('usage', {})}")
        
        debug_headers = self._create_debug_headers(channel_info, routing_score, attempt_num, "regular", latency)
        
        return JSONResponse(content=response_json, headers=debug_headers)
    
    def _prepare_channel_request_info(self, channel, provider, request: Optional[ChatCompletionRequest], matched_model: Optional[str]) -> ChannelRequestInfo:
        """准备渠道请求信息"""
        base_url = (channel.base_url or provider.base_url).rstrip('/')
        if not base_url.endswith('/v1'):
            base_url += '/v1'
        url = f"{base_url}/chat/completions"

        headers = {"Content-Type": "application/json", "User-Agent": "smart-ai-router/0.2.0"}
        if provider.auth_type == "bearer":
            headers["Authorization"] = f"Bearer {channel.api_key}"
        elif provider.auth_type == "x-api-key":
            headers["x-api-key"] = channel.api_key

        request_data = {}
        if request:
            request_data = request.dict(exclude_unset=True)
            # 智能模型选择逻辑
            if matched_model:
                request_data["model"] = matched_model
                logger.info(f"📡 MODEL SELECTION: Using matched model '{matched_model}' for routing")
            elif request.model.startswith("auto:") or request.model.startswith("tag:"):
                request_data["model"] = channel.model_name
                logger.info(f"📡 MODEL SELECTION: Using channel default model '{channel.model_name}' for virtual query")
            else:
                request_data["model"] = request.model
                logger.info(f"📡 MODEL SELECTION: Using requested model '{request.model}' for physical query")
        
        return ChannelRequestInfo(
            url=url,
            headers=headers,
            request_data=request_data,
            channel=channel,
            provider=provider,
            matched_model=matched_model
        )
    
    def _create_debug_headers(self, channel_info: ChannelRequestInfo, routing_score: RoutingScore, attempt_num: int, request_type: str, latency: Optional[float] = None) -> Dict[str, str]:
        """创建调试头信息"""
        headers = {
            "X-Router-Channel": f"{channel_info.channel.name} (ID: {channel_info.channel.id})",
            "X-Router-Provider": getattr(channel_info.provider, 'name', channel_info.channel.provider),
            "X-Router-Model": routing_score.matched_model or channel_info.channel.model_name,
            "X-Router-Score": f"{routing_score.total_score:.3f}",
            "X-Router-Attempts": str(attempt_num),
            "X-Router-Score-Breakdown": f"cost:{routing_score.cost_score:.2f} speed:{routing_score.speed_score:.2f} quality:{routing_score.quality_score:.2f} reliability:{routing_score.reliability_score:.2f}",
            "X-Router-Type": request_type
        }
        
        if latency is not None:
            headers["X-Router-Latency"] = f"{latency:.3f}s"
        
        return headers
    
    def _handle_http_status_error(self, error: httpx.HTTPStatusError, channel, attempt_num: int, failed_channels: set, total_candidates: List) -> None:
        """处理HTTP状态错误"""
        error_text = error.response.text if hasattr(error.response, 'text') else str(error)
        logger.warning(f"❌ ATTEMPT #{attempt_num} FAILED: Channel '{channel.name}' returned HTTP {error.response.status_code}")
        logger.warning(f"❌ ERROR DETAILS: {error_text[:200]}...")
        
        self.router.update_channel_health(channel.id, False)
        
        # 智能拉黑：对于认证错误等永久性错误，拉黑整个渠道
        if error.response.status_code in [401, 403]:
            failed_channels.add(channel.id)
            logger.warning(f"🚫 CHANNEL BLACKLISTED: Channel '{channel.name}' (ID: {channel.id}) blacklisted due to HTTP {error.response.status_code}")
            logger.info(f"⚡ SKIP OPTIMIZATION: Will skip all remaining models from channel '{channel.name}'")
        
        if attempt_num < len(total_candidates):
            logger.info(f"🔄 FAILOVER: Trying next channel (#{attempt_num + 1})")
    
    def _handle_request_error(self, error: httpx.RequestError, channel, attempt_num: int, total_candidates: List) -> None:
        """处理请求错误"""
        logger.warning(f"❌ ATTEMPT #{attempt_num} FAILED: Channel '{channel.name}' network error: {str(error)}")
        self.router.update_channel_health(channel.id, False)
        
        if attempt_num < len(total_candidates):
            logger.info(f"🔄 FAILOVER: Trying next channel (#{attempt_num + 1})")
    
    def _infer_capabilities(self, request: ChatCompletionRequest) -> List[str]:
        """推断请求所需的能力"""
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
    
    # --- Error Response Creators ---
    
    def _create_no_channels_error(self, model: str, execution_time: float) -> JSONResponse:
        """创建无可用渠道错误响应"""
        logger.error(f"❌ ROUTING FAILED: No available channels found for model '{model}'")
        
        headers = {
            "X-Router-Status": "no-channels-found",
            "X-Router-Time": f"{execution_time:.3f}s",
            "X-Router-Model-Requested": model
        }
        
        return JSONResponse(
            status_code=503,
            content={"detail": f"No available channels found for model '{model}'."},
            headers=headers
        )
    
    def _handle_tag_not_found_error(self, error: TagNotFoundError, model: str, execution_time: float) -> JSONResponse:
        """处理标签未找到错误"""
        logger.error(f"❌ TAG NOT FOUND: {error} (after {execution_time:.3f}s)")
        
        headers = {
            "X-Router-Status": "tag-not-found",
            "X-Router-Tags": ",".join(error.tags),
            "X-Router-Time": f"{execution_time:.3f}s",
            "X-Router-Model-Requested": model
        }
        
        return JSONResponse(
            status_code=404,
            content={"detail": str(error)},
            headers=headers
        )
    
    def _handle_unexpected_error(self, error: Exception, model: str, execution_time: float) -> HTTPException:
        """处理意外错误"""
        logger.error(f"💥 UNEXPECTED ERROR: Internal error occurred after {execution_time:.3f}s: {error}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {error}")
    
    def _create_all_channels_failed_error(self, model: str, candidates: List, last_error: Optional[Exception], execution_time: float) -> JSONResponse:
        """创建所有渠道失败错误响应"""
        logger.error(f"💥 ALL CHANNELS FAILED: All {len(candidates)} channels failed for model '{model}' after {execution_time:.3f}s")
        
        error_detail = f"All available channels failed. Last error: {str(last_error)}"
        if hasattr(last_error, 'response'):
            error_detail += f" - Details: {last_error.response.text}"

        logger.error(f"💥 FINAL ERROR: {error_detail}")
        
        headers = {
            "X-Router-Status": "all-channels-failed",
            "X-Router-Attempts": str(len(candidates)),
            "X-Router-Time": f"{execution_time:.3f}s",
            "X-Router-Model-Requested": model
        }
        
        return JSONResponse(
            status_code=503,
            content={"detail": error_detail},
            headers=headers
        )
    
    # --- Low-level API calls (moved from main.py) ---
    
    async def _fast_channel_check(self, url: str, headers: dict) -> Tuple[bool, int, str]:
        """快速检查渠道是否可用"""
        cache_key = f"{url}:{hash(str(headers))}"
        
        cached_result = await cache_get("channel_availability", cache_key)
        if cached_result:
            logger.debug(f"使用缓存的渠道可用性结果: {url}")
            return cached_result['available'], cached_result['status_code'], cached_result['message']
        
        try:
            http_pool = get_http_pool()
            
            test_data = {
                "model": "test-availability",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1
            }
            
            async with http_pool.stream('POST', url, json=test_data, headers=headers) as response:
                if response.status_code in [200, 400, 404, 422]:
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
    
    async def _call_channel_api(self, url: str, headers: dict, request_data: dict):
        """优化的API调用"""
        http_pool = get_http_pool()
        
        async with http_pool.stream('POST', url, json=request_data, headers=headers) as response:
            if response.status_code != 200:
                error_content = await response.aread(max_bytes=1024)
                response._content = error_content
                response.raise_for_status()
            
            content = await response.aread()
            return response.json()
    
    async def _stream_channel_api(self, url: str, headers: dict, request_data: dict, channel_id: str):
        """优化的流式API调用"""
        chunk_count = 0
        stream_start_time = time.time()
        
        logger.info(f"🌊 STREAM START: Initiating optimized streaming request to channel '{channel_id}'")
        
        try:
            http_pool = get_http_pool()
            
            async with http_pool.stream("POST", url, json=request_data, headers=headers) as response:
                if response.status_code != 200:
                    error_body = await response.aread(max_bytes=1024)
                    logger.error(f"🌊 STREAM ERROR: Channel '{channel_id}' returned status {response.status_code}")
                    
                    error_text = error_body.decode('utf-8', errors='ignore')[:200]
                    logger.error(f"🌊 STREAM ERROR DETAILS: {error_text}")
                    self.router.update_channel_health(channel_id, False)
                    
                    yield f"data: {json.dumps({'error': {'message': f'Upstream API error: {error_text}', 'code': response.status_code}})}\n\n"
                    return

                logger.info(f"🌊 STREAM CONNECTED: Successfully connected to channel '{channel_id}', starting optimized data flow")
                
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    if chunk:
                        chunk_count += 1
                        if chunk_count % 20 == 0:
                            logger.debug(f"🌊 STREAMING: Received {chunk_count} chunks from channel '{channel_id}'")
                    yield chunk
                        
            stream_duration = time.time() - stream_start_time
            self.router.update_channel_health(channel_id, True, stream_duration)
            logger.info(f"🌊 STREAM COMPLETE: Channel '{channel_id}' completed optimized streaming {chunk_count} chunks in {stream_duration:.3f}s")
            
        except httpx.HTTPStatusError as e:
            error_text = e.response.text if hasattr(e.response, 'text') else str(e)
            logger.error(f"🌊 STREAM FAILED: Channel '{channel_id}' HTTP error {e.response.status_code}: {error_text[:200]}...")
            self.router.update_channel_health(channel_id, False)
            yield f"data: {json.dumps({'error': {'message': f'Upstream API error: {error_text}', 'code': e.response.status_code}})}\n\n"
            
        except Exception as e:
            logger.error(f"🌊 STREAM EXCEPTION: Streaming request for channel '{channel_id}' failed: {e}", exc_info=True)
            self.router.update_channel_health(channel_id, False)
            yield f"data: {json.dumps({'error': {'message': str(e), 'code': 500}})}\n\n"