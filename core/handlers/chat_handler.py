# -*- coding: utf-8 -*-
"""
Chat completion request handler with improved architecture
"""
import time
import json
import asyncio
import uuid
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
from ..utils.token_counter import get_cost_tracker
from ..utils.request_cache import get_request_cache
from ..utils.response_aggregator import get_response_aggregator, RequestMetadata
from ..utils.session_manager import get_session_manager
from ..utils.cost_estimator import get_cost_estimator
from ..utils.usage_tracker import get_usage_tracker, create_usage_record
from ..utils.channel_monitor import get_channel_monitor, check_api_error_and_alert
from ..utils.token_estimator import get_token_estimator, get_model_optimizer, TaskComplexity
from ..utils.request_interval_manager import get_request_interval_manager
from ..utils.text_processor import clean_model_response
from ..utils.logging_integration import get_enhanced_logger, log_api_request, log_api_response, log_channel_operation

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
    system: Optional[str] = None
    extra_params: Optional[Dict[str, Any]] = None

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
        request_id = f"req_{uuid.uuid4().hex[:8]}"
        
        # 🚀 使用智能日志记录API请求 (AIRouter功能集成)
        enhanced_logger = get_enhanced_logger(__name__)
        log_api_request(
            enhanced_logger,
            method="POST",
            url="/v1/chat/completions", 
            headers={"content-type": "application/json"},
            body=f"model: {request.model}, messages: {len(request.messages)} msgs, stream: {request.stream}",
            request_id=request_id,
            model=request.model,
            stream=request.stream
        )
        logger.info(f"REQUEST DETAILS: [{request_id}] {len(request.messages)} messages, max_tokens: {request.max_tokens}, temperature: {request.temperature}")
        
        try:
            # 步骤1: 路由请求获取候选渠道
            routing_result = await self._route_request_with_fallback(request, start_time)
            if not routing_result.candidates:
                return self._create_no_channels_error(request.model, time.time() - start_time)
            
            # 步骤2: 请求前成本估算和优化建议
            cost_preview = await self._perform_cost_estimation(request, routing_result.candidates, request_id)
            
            # 步骤3: 执行请求并处理重试
            return await self._execute_request_with_retry(request, routing_result, start_time, request_id, cost_preview)
            
        except TagNotFoundError as e:
            return self._handle_tag_not_found_error(e, request.model, time.time() - start_time)
        except HTTPException:
            raise
        except Exception as e:
            return self._handle_unexpected_error(e, request.model, time.time() - start_time)
    
    async def handle_stream_request(self, request: ChatCompletionRequest):
        """处理流式请求"""
        request_id = str(uuid.uuid4())
        start_time = time.time()
        
        logger.info(f"ANTHROPIC STREAM: [{request_id}] Starting stream request for model '{request.model}'")
        
        try:
            # 步骤1: 路由请求获取候选渠道
            routing_result = await self._route_request_with_fallback(request, start_time)
            if not routing_result.candidates:
                # 返回错误流
                return StreamingResponse(
                    self._error_stream_generator("no_channels_available", "No available channels"),
                    media_type="text/event-stream"
                )
            
            # 步骤2: 执行流式请求
            return StreamingResponse(
                self._execute_stream_request_with_retry(request, routing_result, start_time, request_id),
                media_type="text/event-stream"
            )
                
        except Exception as e:
            logger.error(f"Stream error: {e}")
            return StreamingResponse(
                self._error_stream_generator("stream_error", str(e)),
                media_type="text/event-stream"
            )
    
    async def _execute_stream_request_with_retry(self, request: ChatCompletionRequest, routing_result: RoutingResult, start_time: float, request_id: str):
        """执行流式请求并处理重试逻辑"""
        last_error = None
        failed_channels = set()
        
        for attempt_num, routing_score in enumerate(routing_result.candidates, 1):
            channel = routing_score.channel
            provider = self.config.get_provider(channel.provider)
            
            if channel.id in failed_channels:
                continue
            
            if not provider:
                continue
            
            # 检查渠道间隔限制，如果需要等待则跳过
            interval_manager = get_request_interval_manager()
            min_interval = getattr(channel, 'min_request_interval', 0)
            logger.info(f"🔍 STREAM INTERVAL CHECK: Channel '{channel.name}' min_interval={min_interval}s")
            if min_interval > 0:
                is_ready = interval_manager.is_channel_ready(channel.id, min_interval)
                logger.info(f"🔍 STREAM INTERVAL CHECK: Channel '{channel.name}' is_ready={is_ready}")
                if not is_ready:
                    wait_time = interval_manager.get_remaining_wait_time(channel.id, min_interval)
                    logger.info(f"⏭️ STREAM SKIP #{attempt_num}: Channel '{channel.name}' needs to wait {wait_time:.1f}s (min_interval={min_interval}s), trying next channel")
                    continue
            
            # 在发送流式请求前记录时间（用于间隔控制）
            if min_interval > 0:
                interval_manager.record_request(channel.id)
                logger.info(f"🔍 STREAM INTERVAL RECORDED: Channel '{channel.name}' request time recorded")
            
            try:
                channel_info = self._prepare_channel_request_info(channel, provider, request, routing_score.matched_model)
                
                # 创建请求元数据
                aggregator = get_response_aggregator()
                metadata = aggregator.create_request_metadata(
                    request_id=request_id,
                    model_requested=request.model,
                    model_used=channel_info.request_data['model'],
                    channel_name=channel.name,
                    channel_id=channel.id,
                    provider=channel.provider,
                    attempt_count=attempt_num,
                    is_streaming=True,
                    routing_strategy=getattr(self.router, 'current_strategy', 'balanced'),
                    routing_score=routing_score.total_score,
                    routing_reason=routing_score.reason
                )
                
                # 执行流式请求 - 直接yield流式响应的内容
                async for chunk in self._stream_channel_api_with_summary(channel_info.url, channel_info.headers, channel_info.request_data, channel_info.channel.id, metadata):
                    yield chunk
                
                return  # 成功则退出
                
            except Exception as e:
                last_error = e
                failed_channels.add(channel.id)
                logger.error(f"Stream attempt {attempt_num} failed: {e}")
                continue
        
        # 所有渠道都失败
        yield self._create_stream_error("all_channels_failed", str(last_error or "All channels failed"))
    
    def _create_stream_error(self, error_type: str, message: str) -> str:
        """创建流式错误消息"""
        error_data = {
            "type": "error",
            "error": {
                "type": error_type,
                "message": message
            }
        }
        return f"data: {json.dumps(error_data)}\n\n"
    
    async def _error_stream_generator(self, error_type: str, message: str):
        """错误流生成器"""
        yield self._create_stream_error(error_type, message)
    
    async def _route_request_with_fallback(self, request: ChatCompletionRequest, start_time: float) -> RoutingResult:
        """执行路由请求和智能预检"""
        routing_request = RoutingRequest(
            model=request.model,
            messages=[msg.dict() for msg in request.messages],
            stream=request.stream,
            required_capabilities=self._infer_capabilities(request),
            data=request.dict()  # 传递完整的请求数据用于能力检测
        )
        
        logger.info(f"CHANNEL ROUTING: Starting routing process for model '{request.model}'")
        candidate_channels = await self.router.route_request(routing_request)
        
        if not candidate_channels:
            return RoutingResult(candidates=[], execution_time=time.time() - start_time, total_candidates=0)
        
        logger.info(f"CHANNEL SELECTION: Processing {len(candidate_channels)} channels with intelligent routing")
        
        # 智能渠道预检 - 如果有多个渠道，先并发检查前3个
        if len(candidate_channels) > 1:
            await self._perform_concurrent_channel_check(candidate_channels)
        
        return RoutingResult(
            candidates=candidate_channels,
            execution_time=time.time() - start_time,
            total_candidates=len(candidate_channels)
        )
    
    async def _perform_cost_estimation(self, request: ChatCompletionRequest, candidate_channels: List, request_id: str) -> Optional[Dict[str, Any]]:
        """执行Token预估和智能模型推荐"""
        try:
            # 获取Token预估器和模型优化器
            token_estimator = get_token_estimator()
            model_optimizer = get_model_optimizer()
            
            # 转换消息格式
            messages = [{'role': msg.role, 'content': str(msg.content)} for msg in request.messages]
            
            # 进行Token预估
            token_estimate = token_estimator.estimate_tokens(messages)
            
            # 准备候选渠道信息（包含定价）
            available_channels = []
            for channel_score in candidate_channels[:15]:  # 分析前15个候选
                channel = channel_score.channel
                
                # 尝试获取定价信息
                input_price = getattr(channel, 'input_price', 0.0)
                output_price = getattr(channel, 'output_price', 0.0)
                
                # 如果没有定价信息，尝试从定价数据中获取
                if input_price == 0.0 and output_price == 0.0:
                    pricing_info = self._get_model_pricing(channel.model_name, channel.provider)
                    if pricing_info:
                        input_price = pricing_info.get('input_price', 0.0)
                        output_price = pricing_info.get('output_price', 0.0)
                
                available_channels.append({
                    'id': channel.id,
                    'model_name': channel.model_name,
                    'provider': channel.provider,
                    'input_price': input_price,
                    'output_price': output_price,
                    'routing_score': channel_score.total_score,
                    'matched_model': channel_score.matched_model
                })
            
            # 获取当前路由策略
            current_strategy = getattr(self.router, 'current_strategy', 'balanced')
            
            # 生成模型推荐
            recommendations = model_optimizer.recommend_models(
                token_estimate, available_channels, current_strategy
            )
            
            # 记录Token预估结果
            complexity_name = token_estimate.task_complexity.value
            logger.info(f"🧠 TOKEN ESTIMATE: [{request_id}] Input: {token_estimate.input_tokens}, "
                       f"Output: {token_estimate.estimated_output_tokens} (total: {token_estimate.total_tokens})")
            logger.info(f"🧠 TASK COMPLEXITY: [{request_id}] {complexity_name.upper()} "
                       f"(confidence: {token_estimate.confidence:.1%})")
            
            # 显示推荐结果
            if recommendations:
                best_rec = recommendations[0]
                logger.info(f"🎯 BEST RECOMMENDATION: [{request_id}] {best_rec.model_name} "
                           f"(${best_rec.estimated_cost:.6f}, {best_rec.estimated_time:.1f}s) - {best_rec.reason}")
                
                # 显示免费选项
                free_options = [r for r in recommendations[:5] if r.estimated_cost == 0]
                if free_options:
                    logger.info(f"💰 FREE OPTIONS: [{request_id}] Found {len(free_options)} free channels")
                    for free_rec in free_options[:3]:
                        logger.info(f"   • {free_rec.model_name} - {free_rec.reason}")
                
                # 成本对比
                costs = [r.estimated_cost for r in recommendations[:5] if r.estimated_cost > 0]
                if len(costs) > 1:
                    savings = max(costs) - min(costs)
                    if savings > 0.001:  # 只有当节省超过0.001美元时才提示
                        logger.info(f"💰 COST SAVINGS: [{request_id}] Can save up to ${savings:.6f} by choosing optimal model")
            
            # 构造返回数据
            cost_preview = {
                'token_estimate': {
                    'input_tokens': token_estimate.input_tokens,
                    'estimated_output_tokens': token_estimate.estimated_output_tokens,
                    'total_tokens': token_estimate.total_tokens,
                    'confidence': token_estimate.confidence,
                    'task_complexity': complexity_name
                },
                'recommendations': [
                    {
                        'model_name': rec.model_name,
                        'channel_id': rec.channel_id,
                        'estimated_cost': rec.estimated_cost,
                        'estimated_time': rec.estimated_time,
                        'quality_score': rec.quality_score,
                        'reason': rec.reason,
                        'formatted_cost': f"${rec.estimated_cost:.6f}" if rec.estimated_cost > 0 else "Free"
                    }
                    for rec in recommendations[:10]  # 返回前10个推荐
                ],
                'optimization_strategy': current_strategy,
                'calculation_time_ms': 0  # Token预估很快，基本无延迟
            }
            
            return cost_preview
            
        except Exception as e:
            logger.warning(f"🧠 TOKEN ESTIMATION FAILED: [{request_id}] {e}")
            return None
    
    def _get_model_pricing(self, model_name: str, provider: str) -> Optional[Dict[str, float]]:
        """获取模型定价信息"""
        try:
            # 尝试从静态定价加载器获取
            from ..utils.static_pricing import get_static_pricing_loader
            pricing_loader = get_static_pricing_loader()
            
            if provider == 'siliconflow':
                pricing_result = pricing_loader.get_siliconflow_pricing(model_name)
                if pricing_result:
                    return {
                        'input_price': pricing_result.input_price,
                        'output_price': pricing_result.output_price
                    }
            elif provider == 'doubao':
                pricing_result = pricing_loader.get_doubao_pricing(model_name)
                if pricing_result:
                    return {
                        'input_price': pricing_result.input_price,
                        'output_price': pricing_result.output_price
                    }
            
            return None
        except Exception as e:
            logger.warning(f"获取模型定价失败 {model_name}: {e}")
            return None
    
    async def _perform_concurrent_channel_check(self, candidate_channels: List[RoutingScore]) -> None:
        """执行并发渠道可用性检查"""
        logger.info(f"FAST CHECK: Pre-checking availability of top {min(3, len(candidate_channels))} channels")
        
        check_tasks = []
        for i, routing_score in enumerate(candidate_channels[:3]):
            channel = routing_score.channel
            provider = self.config.get_provider(channel.provider)
            if provider:
                channel_info = self._prepare_channel_request_info(channel, provider, None, routing_score.matched_model)
                check_tasks.append((i, channel, self._fast_channel_check(channel_info.url, channel_info.headers)))
        
        if check_tasks:
            check_results = await asyncio.gather(*[task[2] for task in check_tasks], return_exceptions=True)
            
            # 找出第一个可用且符合间隔要求的渠道并移到首位
            interval_manager = get_request_interval_manager()
            for i, (original_index, channel, result) in enumerate(check_tasks):
                if i < len(check_results) and not isinstance(check_results[i], Exception):
                    is_available, status_code, message = check_results[i]
                    if is_available:
                        # 检查间隔限制
                        min_interval = getattr(channel, 'min_request_interval', 0)
                        logger.info(f"FAST CHECK DEBUG: Channel '{channel.name}' min_interval={min_interval} (id={channel.id}) type={type(channel)}")
                        if min_interval > 0:
                            is_ready = interval_manager.is_channel_ready(channel.id, min_interval)
                            if not is_ready:
                                wait_time = interval_manager.get_remaining_wait_time(channel.id, min_interval)
                                logger.info(f"🔍 FAST CHECK SKIP: Channel '{channel.name}' needs to wait {wait_time:.1f}s (min_interval={min_interval}s), not prioritizing")
                                continue
                        
                        logger.info(f"FAST CHECK: Channel '{channel.name}' is available (HTTP {status_code}), prioritizing")
                        priority_channel = candidate_channels.pop(original_index)
                        candidate_channels.insert(0, priority_channel)
                        break
                    else:
                        logger.info(f"FAST CHECK: Channel '{channel.name}' unavailable ({status_code}: {message})")
    
    async def _execute_request_with_retry(self, request: ChatCompletionRequest, routing_result: RoutingResult, start_time: float, request_id: str, cost_preview: Optional[Dict[str, Any]] = None) -> Union[JSONResponse, StreamingResponse]:
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
                logger.warning(f"ATTEMPT #{attempt_num}: Provider '{channel.provider}' for channel '{channel.name}' not found, skipping")
                continue
            
            # 检查渠道间隔限制，如果需要等待则跳过
            interval_manager = get_request_interval_manager()
            min_interval = getattr(channel, 'min_request_interval', 0)
            logger.info(f"🔍 INTERVAL CHECK: [{request_id}] Channel '{channel.name}' min_interval={min_interval}s")
            if min_interval > 0:
                is_ready = interval_manager.is_channel_ready(channel.id, min_interval)
                logger.info(f"🔍 INTERVAL CHECK: [{request_id}] Channel '{channel.name}' is_ready={is_ready}")
                if not is_ready:
                    wait_time = interval_manager.get_remaining_wait_time(channel.id, min_interval)
                    logger.info(f"⏭️ SKIP #{attempt_num}: Channel '{channel.name}' needs to wait {wait_time:.1f}s (min_interval={min_interval}s), trying next channel")
                    continue
            
            logger.info(f"ATTEMPT #{attempt_num}: [{request_id}] Trying channel '{channel.name}' (ID: {channel.id}) with score {routing_score.total_score:.3f}")
            logger.info(f"ATTEMPT #{attempt_num}: [{request_id}] Score breakdown - {routing_score.reason}")
            
            # 在发送请求前记录时间（用于间隔控制）
            if min_interval > 0:
                interval_manager.record_request(channel.id)
                logger.info(f"🔍 INTERVAL RECORDED: [{request_id}] Channel '{channel.name}' request time recorded")
            
            try:
                channel_info = self._prepare_channel_request_info(channel, provider, request, routing_score.matched_model)
                
                logger.info(f"📡 FORWARDING: [{request_id}] Sending request to {channel_info.url}")
                logger.info(f"📡 FORWARDING: [{request_id}] Target model -> '{channel_info.request_data['model']}'")
                
                # 创建请求元数据
                aggregator = get_response_aggregator()
                metadata = aggregator.create_request_metadata(
                    request_id=request_id,
                    model_requested=request.model,
                    model_used=channel_info.request_data['model'],
                    channel_name=channel.name,
                    channel_id=channel.id,
                    provider=channel.provider,
                    attempt_count=attempt_num,
                    is_streaming=request.stream,
                    routing_strategy=getattr(self.router, 'current_strategy', 'balanced'),
                    routing_score=routing_score.total_score,
                    routing_reason=routing_score.reason,
                    cost_preview=cost_preview
                )
                
                # 存储元数据到请求中，供后续使用
                setattr(request, '_metadata', metadata)
                
                if request.stream:
                    return self._handle_streaming_request(request, channel_info, routing_score, attempt_num, metadata)
                else:
                    return await self._handle_regular_request(request, channel_info, routing_score, attempt_num, start_time, metadata)
                    
            except httpx.HTTPStatusError as e:
                last_error = e
                await self._handle_http_status_error(e, channel, attempt_num, failed_channels, routing_result.candidates)
                continue
            except httpx.RequestError as e:
                last_error = e
                self._handle_request_error(e, channel, attempt_num, routing_result.candidates)
                continue
        
        # 所有渠道都失败了
        return self._create_all_channels_failed_error(request.model, routing_result.candidates, last_error, time.time() - start_time)
    
    def _handle_streaming_request(self, request: ChatCompletionRequest, channel_info: ChannelRequestInfo, routing_score: RoutingScore, attempt_num: int, metadata: RequestMetadata):
        """处理流式请求"""
        logger.info(f"STREAMING: [{metadata.request_id}] Starting streaming response for channel '{channel_info.channel.name}'")
        
        # 返回StreamingResponse对象
        return StreamingResponse(
            self._stream_channel_api_with_summary(channel_info.url, channel_info.headers, channel_info.request_data, channel_info.channel.id, metadata),
            media_type="text/event-stream"
        )
    
    async def _handle_regular_request(self, request: ChatCompletionRequest, channel_info: ChannelRequestInfo, routing_score: RoutingScore, attempt_num: int, start_time: float, metadata: RequestMetadata) -> JSONResponse:
        """处理常规请求"""
        logger.info(f"⏳ REQUEST: [{metadata.request_id}] Sending optimized request to channel '{channel_info.channel.name}'")
        
        response_json, ttfb = await self._call_channel_api(channel_info.url, channel_info.headers, channel_info.request_data)
        
        # 成功，更新健康度并返回
        latency = time.time() - start_time
        self.router.update_channel_health(channel_info.channel.id, True, latency)
        
        # 🚀 使用智能日志记录成功响应 (AIRouter功能集成)  
        log_channel_operation(
            enhanced_logger,
            operation="request",
            channel_id=channel_info.channel.id,
            model=response_json.get('model', 'unknown'),
            success=True,
            request_id=metadata.request_id,
            latency=latency,
            ttfb_ms=ttfb*1000,
            usage=response_json.get('usage', {})
        )
        
        # 记录传统日志（保持兼容性）
        logger.info(f"SUCCESS: [{metadata.request_id}] Channel '{channel_info.channel.name}' responded successfully (latency: {latency:.3f}s)")
        logger.info(f"TIMING: [{metadata.request_id}] TTFB: {ttfb*1000:.1f}ms, Total: {latency*1000:.1f}ms")
        logger.info(f"RESPONSE: [{metadata.request_id}] Model used -> {response_json.get('model', 'unknown')}")
        logger.info(f"RESPONSE: [{metadata.request_id}] Usage -> {response_json.get('usage', {})}")
        
        # 更新元数据
        aggregator = get_response_aggregator()
        usage = response_json.get('usage', {})
        prompt_tokens = usage.get('prompt_tokens', 0)
        completion_tokens = usage.get('completion_tokens', 0)
        total_tokens = usage.get('total_tokens', prompt_tokens + completion_tokens)
        
        # 计算成本信息
        cost_info = self._calculate_request_cost(channel_info.channel, prompt_tokens, completion_tokens, response_json.get('model'))
        
        # 获取用户会话信息
        session_manager = get_session_manager()
        user_identifier = self._extract_user_identifier(request)
        session = session_manager.add_request(
            user_identifier=user_identifier,
            cost=cost_info['total_cost'],
            model=response_json.get('model', 'unknown'),
            channel=channel_info.channel.name
        )
        
        # 更新聚合器 (传递TTFB信息)
        aggregator.update_tokens(metadata.request_id, prompt_tokens, completion_tokens, total_tokens)
        aggregator.update_cost(metadata.request_id, cost_info['total_cost'], session.total_cost, session.total_requests)
        aggregator.update_performance(metadata.request_id, ttfb=ttfb)  # TTFB已经是秒为单位
        
        # 完成请求并获取最终元数据
        final_metadata = aggregator.finish_request(metadata.request_id)
        
        # 记录使用情况到JSONL文件
        await self._record_usage_async(
            metadata.request_id,
            request,
            channel_info.channel,
            response_json.get('model', 'unknown'),
            prompt_tokens,
            completion_tokens,
            cost_info,
            latency,
            "success"
        )
        
        # 🚀 思维链清理处理 (AIRouter功能集成)
        cleaned_response_json = self._clean_response_content(response_json)
        
        # 使用新的响应汇总格式
        enhanced_response = aggregator.enhance_response_with_summary(cleaned_response_json, final_metadata)
        
        # 获取汇总头信息（虽然非流式主要在响应体中，但保留头信息用于调试）
        debug_headers = aggregator.get_headers_summary(metadata.request_id)
        
        return JSONResponse(content=enhanced_response, headers=debug_headers)
    
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
    
    def _invalidate_channel_cache(self, channel_id: str, channel_name: str, reason: str):
        """统一的缓存失效方法"""
        try:
            cache = get_request_cache()
            cache.invalidate_channel(channel_id)
            logger.info(f"🗑️  CACHE INVALIDATED: Cleared cached selections for channel '{channel_name}' due to {reason}")
        except Exception as e:
            logger.warning(f"CACHE INVALIDATION FAILED for channel '{channel_name}': {e}")

    async def _handle_http_status_error(self, error: httpx.HTTPStatusError, channel, attempt_num: int, failed_channels: set, total_candidates: List) -> None:
        """处理HTTP状态错误"""
        error_text = error.response.text if hasattr(error.response, 'text') else str(error)
        logger.warning(f"ATTEMPT #{attempt_num} FAILED: Channel '{channel.name}' returned HTTP {error.response.status_code}")
        logger.warning(f"ERROR DETAILS: {error_text[:200]}...")
        
        # 记录渠道错误并发送告警
        check_api_error_and_alert(channel.id, channel.name, error.response.status_code, error_text)
        
        self.router.update_channel_health(channel.id, False)
        
        # 智能拉黑：对于认证错误等永久性错误，拉黑整个渠道
        if error.response.status_code in [401, 403]:
            failed_channels.add(channel.id)
            logger.warning(f"🚫 CHANNEL BLACKLISTED: Channel '{channel.name}' (ID: {channel.id}) blacklisted due to HTTP {error.response.status_code}")
            logger.info(f"SKIP OPTIMIZATION: Will skip all remaining models from channel '{channel.name}'")
            
            # 使相关缓存失效 - 永久性错误需要立即清除缓存
            self._invalidate_channel_cache(channel.id, channel.name, "permanent error")
        
        # 对于临时错误（如429, 500），也使缓存失效但不永久拉黑，并添加退避延迟
        elif error.response.status_code in [429, 500, 502, 503, 504]:
            self._invalidate_channel_cache(channel.id, channel.name, "temporary error")
            
            # 429错误需要特别处理 - 实施智能退避策略
            if error.response.status_code == 429:
                failed_channels.add(channel.id)  # 暂时拉黑，避免连续重试
                
                # 尝试从错误信息中提取等待时间
                wait_time = self._extract_rate_limit_wait_time(error_text)
                if wait_time:
                    backoff_time = min(wait_time, 60)  # 最大等待60秒
                    logger.warning(f"SMART RATE LIMIT: Channel '{channel.name}' suggests waiting {wait_time}s, applying {backoff_time}s backoff")
                else:
                    backoff_time = min(2 ** (attempt_num - 1), 16)  # 指数退避，最大16秒
                    logger.warning(f"RATE LIMIT: Channel '{channel.name}' rate limited, applying {backoff_time}s backoff")
                
                await asyncio.sleep(backoff_time)
        
        if attempt_num < len(total_candidates):
            logger.info(f"FAILOVER: Trying next channel (#{attempt_num + 1})")
    
    def _extract_rate_limit_wait_time(self, error_text: str) -> Optional[int]:
        """从错误信息中提取建议的等待时间（秒）"""
        import re
        import json
        
        if not error_text:
            return None
        
        try:
            # 尝试解析JSON格式的错误信息
            if error_text.strip().startswith('{'):
                error_data = json.loads(error_text)
                
                # 检查是否是速率限制错误
                if isinstance(error_data, dict):
                    error_obj = error_data.get('error', {})
                    if isinstance(error_obj, dict):
                        message = error_obj.get('message', '')
                        code = error_obj.get('code')
                        
                        # 如果是429错误且包含rate limit相关信息
                        if code == 429 or 'rate' in message.lower() or 'limit' in message.lower():
                            # 从消息中提取等待时间的各种模式
                            wait_patterns = [
                                r'retry after (\d+) seconds?',
                                r'retry in (\d+) seconds?', 
                                r'wait (\d+) seconds?',
                                r'try again in (\d+) seconds?',
                                r'retry shortly',  # 默认等待时间
                                r'请(\d+)秒后重试',
                                r'等待(\d+)秒'
                            ]
                            
                            for pattern in wait_patterns:
                                match = re.search(pattern, message, re.IGNORECASE)
                                if match and match.groups():
                                    return int(match.group(1))
                                elif 'retry shortly' in message.lower():
                                    return 5  # 默认短暂等待5秒
            
            # 直接从文本中搜索等待时间模式
            text_patterns = [
                r'retry after (\d+) seconds?',
                r'retry in (\d+) seconds?',
                r'wait (\d+) seconds?', 
                r'try again in (\d+) seconds?',
                r'请(\d+)秒后重试',
                r'等待(\d+)秒'
            ]
            
            for pattern in text_patterns:
                match = re.search(pattern, error_text, re.IGNORECASE)
                if match:
                    return int(match.group(1))
            
            # 如果包含rate limit相关关键词但没有具体时间，返回默认等待时间
            rate_limit_keywords = ['rate limit', 'rate-limit', 'too many requests', 'quota exceeded', 'temporarily rate-limited']
            if any(keyword in error_text.lower() for keyword in rate_limit_keywords):
                return 10  # 默认等待10秒
                
        except (json.JSONDecodeError, ValueError, AttributeError) as e:
            logger.debug(f"Failed to parse rate limit wait time from error: {e}")
        
        return None
    
    async def _record_usage_async(self, request_id: str, request: ChatCompletionRequest, 
                                  channel, model_used: str, input_tokens: int, output_tokens: int,
                                  cost_info: dict, response_time_ms: float, status: str = "success",
                                  error_message: str = None):
        """异步记录使用情况到JSONL文件"""
        try:
            tracker = get_usage_tracker()
            
            # 创建使用记录
            usage_record = create_usage_record(
                model=model_used,
                channel_id=channel.id,
                channel_name=channel.name,
                provider=channel.provider,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_cost=cost_info.get('input_cost', 0.0),
                output_cost=cost_info.get('output_cost', 0.0),
                request_id=request_id,
                request_type="chat",
                status=status,
                error_message=error_message,
                response_time_ms=int(response_time_ms * 1000),  # 转换为毫秒
                tags=self._extract_request_tags(request)
            )
            
            # 异步记录
            await tracker.record_usage_async(usage_record)
            
        except Exception as e:
            logger.error(f"记录使用情况失败: {e}")
    
    def _extract_request_tags(self, request: ChatCompletionRequest) -> list:
        """从请求中提取标签信息"""
        tags = []
        
        # 从模型名称提取标签
        if request.model.startswith('tag:'):
            tag_part = request.model[4:]  # 去掉 'tag:' 前缀
            tags.extend(tag_part.split(','))
        
        # 添加请求特征标签
        if request.stream:
            tags.append('streaming')
        if request.functions or request.tools:
            tags.append('function_calling')
        if request.max_tokens:
            if request.max_tokens <= 100:
                tags.append('short_response')
            elif request.max_tokens >= 2000:
                tags.append('long_response')
        
        return tags

    def _handle_request_error(self, error: httpx.RequestError, channel, attempt_num: int, total_candidates: List) -> None:
        """处理请求错误"""
        logger.warning(f"ATTEMPT #{attempt_num} FAILED: Channel '{channel.name}' network error: {str(error)}")
        self.router.update_channel_health(channel.id, False)
        
        # 网络错误也可能是渠道问题，清除相关缓存
        self._invalidate_channel_cache(channel.id, channel.name, "network error")
        
        if attempt_num < len(total_candidates):
            logger.info(f"FAILOVER: Trying next channel (#{attempt_num + 1})")
    
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
        logger.error(f"ROUTING FAILED: No available channels found for model '{model}'")
        
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
        logger.error(f"TAG NOT FOUND: {error} (after {execution_time:.3f}s)")
        
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
        """优化的API调用 - 返回响应和TTFB时间"""
        http_pool = get_http_pool()
        
        # 记录开始时间
        request_start = time.time()
        
        async with http_pool.stream('POST', url, json=request_data, headers=headers) as response:
            # 记录首字节时间 (TTFB)
            ttfb = time.time() - request_start
            
            if response.status_code != 200:
                # 读取错误内容，限制大小以避免内存问题
                error_content = await response.aread()
                if len(error_content) > 1024:
                    error_content = error_content[:1024]
                response._content = error_content
                response.raise_for_status()
            
            content = await response.aread()
            result = response.json()
            
            # 返回响应和TTFB时间 (不修改原始响应)
            return result, ttfb
    
    async def _stream_channel_api(self, url: str, headers: dict, request_data: dict, channel_id: str):
        """优化的流式API调用"""
        chunk_count = 0
        stream_start_time = time.time()
        ttfb = None
        first_token_received = False
        
        logger.info(f"STREAM START: Initiating optimized streaming request to channel '{channel_id}'")
        
        try:
            http_pool = get_http_pool()
            
            async with http_pool.stream("POST", url, json=request_data, headers=headers) as response:
                if response.status_code != 200:
                    # 读取错误内容，限制大小以避免内存问题
                    error_body = await response.aread()
                    if len(error_body) > 1024:
                        error_body = error_body[:1024]
                    logger.error(f"STREAM ERROR: Channel '{channel_id}' returned status {response.status_code}")
                    
                    error_text = error_body.decode('utf-8', errors='ignore')[:200]
                    logger.error(f"STREAM ERROR DETAILS: {error_text}")
                    self.router.update_channel_health(channel_id, False)
                    
                    yield f"data: {json.dumps({'error': {'message': f'Upstream API error: {error_text}', 'code': response.status_code}})}\n\n"
                    return

                logger.info(f"STREAM CONNECTED: Successfully connected to channel '{channel_id}', starting optimized data flow")
                
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    if chunk:
                        chunk_count += 1
                        
                        # 记录首次接收到数据的时间 (TTFB)
                        if not first_token_received:
                            ttfb = time.time() - stream_start_time
                            first_token_received = True
                            logger.info(f"FIRST TOKEN: Received first token from channel '{channel_id}' in {ttfb:.3f}s")
                        
                        if chunk_count % 20 == 0:
                            logger.debug(f"STREAMING: Received {chunk_count} chunks from channel '{channel_id}'")
                    yield chunk
                        
            stream_duration = time.time() - stream_start_time
            self.router.update_channel_health(channel_id, True, stream_duration)
            logger.info(f"STREAM COMPLETE: Channel '{channel_id}' completed optimized streaming {chunk_count} chunks in {stream_duration:.3f}s")
            
        except httpx.HTTPStatusError as e:
            error_text = e.response.text if hasattr(e.response, 'text') else str(e)
            logger.error(f"STREAM FAILED: Channel '{channel_id}' HTTP error {e.response.status_code}: {error_text[:200]}...")
            self.router.update_channel_health(channel_id, False)
            yield f"data: {json.dumps({'error': {'message': f'Upstream API error: {error_text}', 'code': e.response.status_code}})}\n\n"
            
        except Exception as e:
            logger.error(f"STREAM EXCEPTION: Streaming request for channel '{channel_id}' failed: {e}", exc_info=True)
            self.router.update_channel_health(channel_id, False)
            yield f"data: {json.dumps({'error': {'message': str(e), 'code': 500}})}\n\n"

    def _clean_response_content(self, response_json: dict) -> dict:
        """
        清理响应内容，移除推理模型的思维链标签
        
        Args:
            response_json (dict): 原始API响应
            
        Returns:
            dict: 清理后的响应，移除思维链内容
        """
        if not response_json or not isinstance(response_json, dict):
            return response_json
        
        try:
            # 创建响应副本避免修改原始数据
            cleaned_response = response_json.copy()
            
            # 处理choices数组中的消息内容
            choices = cleaned_response.get('choices', [])
            if not choices:
                return cleaned_response
            
            cleaned_choices = []
            for choice in choices:
                cleaned_choice = choice.copy() if isinstance(choice, dict) else choice
                
                # 处理message内容
                if isinstance(cleaned_choice, dict) and 'message' in cleaned_choice:
                    message = cleaned_choice['message']
                    if isinstance(message, dict) and 'content' in message:
                        original_content = message.get('content', '')
                        if isinstance(original_content, str) and original_content:
                            # 🚀 应用思维链清理 (AIRouter集成功能)
                            # 检查是否启用思维链清理 (默认启用以支持推理模型)
                            should_clean_thinking = getattr(self.config_loader.config, 'clean_thinking_chains', True)
                            
                            cleaned_content = clean_model_response(
                                original_content, 
                                remove_thinking=should_clean_thinking, 
                                clean_sensitive=False,
                                max_length=None
                            )
                            
                            # 更新消息内容
                            cleaned_message = message.copy()
                            cleaned_message['content'] = cleaned_content
                            cleaned_choice['message'] = cleaned_message
                            
                            # 记录清理效果 (仅在实际清理时记录)
                            if len(cleaned_content) < len(original_content):
                                reduction = len(original_content) - len(cleaned_content)
                                logger.info(f"🧹 THINKING CHAINS CLEANED: Reduced content by {reduction} characters")
                
                # 处理delta内容 (流式响应)
                elif isinstance(cleaned_choice, dict) and 'delta' in cleaned_choice:
                    delta = cleaned_choice['delta']
                    if isinstance(delta, dict) and 'content' in delta:
                        original_content = delta.get('content', '')
                        if isinstance(original_content, str) and original_content:
                            # 对于流式响应，只进行基础的思维链清理
                            # 避免破坏流式传输的连续性
                            should_clean_thinking = getattr(self.config_loader.config, 'clean_thinking_chains', True)
                            
                            cleaned_content = clean_model_response(
                                original_content,
                                remove_thinking=should_clean_thinking,
                                clean_sensitive=False,
                                max_length=None
                            )
                            
                            cleaned_delta = delta.copy()
                            cleaned_delta['content'] = cleaned_content
                            cleaned_choice['delta'] = cleaned_delta
                
                cleaned_choices.append(cleaned_choice)
            
            # 更新清理后的choices
            cleaned_response['choices'] = cleaned_choices
            
            return cleaned_response
            
        except Exception as e:
            # 如果清理过程出现异常，返回原始响应并记录错误
            logger.warning(f"Response content cleaning failed: {e}, returning original response")
            return response_json

    def _add_cost_information(self, response_json: dict, channel, routing_score: RoutingScore) -> dict:
        """为响应添加实时成本信息"""
        try:
            # 获取usage信息
            usage = response_json.get('usage', {})
            if not usage:
                logger.warning("No usage information in response, cannot calculate cost")
                return response_json
            
            prompt_tokens = usage.get('prompt_tokens', 0)
            completion_tokens = usage.get('completion_tokens', 0)
            total_tokens = usage.get('total_tokens', prompt_tokens + completion_tokens)
            
            # 计算成本
            model_used = response_json.get('model', 'unknown')
            cost_info = self._calculate_request_cost(channel, prompt_tokens, completion_tokens, model_used)
            
            # 获取成本追踪器进行记录
            cost_tracker = get_cost_tracker()
            cost_tracker.add_request_cost(
                cost=cost_info['total_cost'],
                model=response_json.get('model', 'unknown'),
                channel_id=channel.id,
                tokens={
                    'prompt_tokens': prompt_tokens,
                    'completion_tokens': completion_tokens,
                    'total_tokens': total_tokens
                }
            )
            
            # 获取会话统计
            session_summary = cost_tracker.get_session_summary()
            
            # 创建增强的响应
            enhanced_response = response_json.copy()
            
            # 添加成本信息到usage部分
            enhanced_usage = usage.copy()
            enhanced_usage.update({
                'cost_breakdown': cost_info,
                'session_cost': session_summary.get('formatted_total_cost', '$0.00'),
                'session_requests': session_summary.get('total_requests', 0)
            })
            enhanced_response['usage'] = enhanced_usage
            
            # 添加路由信息
            enhanced_response['smart_router'] = {
                'channel_used': channel.name,
                'channel_id': channel.id,
                'routing_score': round(routing_score.total_score, 3),
                'cost_score': round(routing_score.cost_score, 3),
                'speed_score': round(routing_score.speed_score, 3),
                'provider': channel.provider
            }
            
            logger.info(f"💰 COST: Request cost ${cost_info['total_cost']:.6f} | Session total: {session_summary.get('formatted_total_cost', '$0.00')}")
            
            return enhanced_response
            
        except Exception as e:
            logger.error(f"Failed to add cost information: {e}")
            return response_json

    def _calculate_request_cost(self, channel, prompt_tokens: int, completion_tokens: int, model_name: str = None) -> dict:
        """计算单次请求的成本 - 优先使用模型级别定价信息"""
        input_cost_per_token = 0.0
        output_cost_per_token = 0.0
        
        # 🔥 优先使用模型级别的定价信息（从缓存中获取）
        if model_name:
            try:
                # 导入配置加载器来访问模型缓存
                from core.yaml_config import YAMLConfigLoader
                config_loader = YAMLConfigLoader()
                
                model_cache = config_loader.get_model_cache()
                if channel.id in model_cache:
                    discovered_info = model_cache[channel.id]
                    if isinstance(discovered_info, dict) and 'models_data' in discovered_info:
                        models_data = discovered_info['models_data']
                        if model_name in models_data:
                            model_data = models_data[model_name]
                            if 'raw_data' in model_data and 'pricing' in model_data['raw_data']:
                                pricing = model_data['raw_data']['pricing']
                                prompt_cost = float(pricing.get('prompt', '0'))
                                completion_cost = float(pricing.get('completion', '0'))
                                if prompt_cost == 0.0 and completion_cost == 0.0:
                                    logger.debug(f"COST: Using model-level free pricing for '{model_name}' (prompt={prompt_cost}, completion={completion_cost})")
                                    input_cost_per_token = 0.0
                                    output_cost_per_token = 0.0
                                else:
                                    # 模型有明确的收费定价
                                    logger.debug(f"COST: Using model-level pricing for '{model_name}' (prompt={prompt_cost}, completion={completion_cost})")
                                    input_cost_per_token = prompt_cost
                                    output_cost_per_token = completion_cost
                            else:
                                logger.debug(f"COST: No model-level pricing found for '{model_name}', falling back to channel pricing")
                        else:
                            logger.debug(f"COST: Model '{model_name}' not found in cache for channel '{channel.id}'")
                    else:
                        logger.debug(f"COST: Invalid cache structure for channel '{channel.id}'")
            except Exception as e:
                logger.warning(f"COST: Error accessing model pricing for '{model_name}': {e}")
        
        # 🔥 如果没有找到模型级别定价，使用渠道级别配置
        if input_cost_per_token == 0.0 and output_cost_per_token == 0.0:
            # 检查是否是明确的免费模型（:free 后缀）
            if model_name and (":free" in model_name.lower() or "-free" in model_name.lower()):
                logger.debug(f"COST: Model '{model_name}' has explicit :free suffix, using zero cost")
                input_cost_per_token = 0.0
                output_cost_per_token = 0.0
            # 使用渠道级别定价
            elif hasattr(channel, 'cost_per_token') and channel.cost_per_token:
                input_cost_per_token = channel.cost_per_token.get('input', 0.0)
                output_cost_per_token = channel.cost_per_token.get('output', 0.0)
                logger.debug(f"COST: Using channel cost_per_token (input={input_cost_per_token}, output={output_cost_per_token})")
            # 回退到pricing配置
            elif hasattr(channel, 'pricing') and channel.pricing:
                input_cost_per_token = channel.pricing.get('input_cost_per_1k', 0.001) / 1000
                output_cost_per_token = channel.pricing.get('output_cost_per_1k', 0.002) / 1000
                logger.debug(f"COST: Using channel pricing (input={input_cost_per_token}, output={output_cost_per_token})")
            else:
                # 默认估算值
                input_cost_per_token = 0.0000005  # $0.0005 per 1K tokens
                output_cost_per_token = 0.0000015  # $0.0015 per 1K tokens
                logger.debug(f"COST: Using default pricing (input={input_cost_per_token}, output={output_cost_per_token})")
        
        input_cost = prompt_tokens * input_cost_per_token
        output_cost = completion_tokens * output_cost_per_token
        total_cost = input_cost + output_cost
        
        return {
            'input_tokens': prompt_tokens,
            'output_tokens': completion_tokens,
            'input_cost_per_token': input_cost_per_token,
            'output_cost_per_token': output_cost_per_token,
            'input_cost': round(input_cost, 8),
            'output_cost': round(output_cost, 8),
            'total_cost': round(total_cost, 8),
            'currency': 'USD'
        }
    
    async def _stream_channel_api_with_summary(self, url: str, headers: dict, request_data: dict, channel_id: str, metadata: RequestMetadata):
        """优化的流式API调用，在结束时添加汇总信息"""
        chunk_count = 0
        stream_start_time = time.time()
        aggregator = get_response_aggregator()
        
        logger.info(f"STREAM START: [{metadata.request_id}] Initiating optimized streaming request to channel '{channel_id}'")
        
        try:
            http_pool = get_http_pool()
            
            async with http_pool.stream("POST", url, json=request_data, headers=headers) as response:
                if response.status_code != 200:
                    # 读取错误内容，限制大小以避免内存问题
                    error_body = await response.aread()
                    if len(error_body) > 1024:
                        error_body = error_body[:1024]
                    logger.error(f"STREAM ERROR: [{metadata.request_id}] Channel '{channel_id}' returned status {response.status_code}")
                    
                    error_text = error_body.decode('utf-8', errors='ignore')
                    logger.error(f"STREAM ERROR DETAILS: [{metadata.request_id}] {error_text[:200]}")
                    self.router.update_channel_health(channel_id, False)
                    
                    # 检测流式响应中的速率限制错误
                    if response.status_code == 429:
                        wait_time = self._extract_rate_limit_wait_time(error_text)
                        if wait_time:
                            logger.warning(f"STREAM RATE LIMIT: [{metadata.request_id}] Channel '{channel_id}' suggests waiting {wait_time}s")
                            # 在错误响应中包含等待时间信息
                            yield f"data: {json.dumps({'error': {'message': f'Rate limited: retry after {wait_time}s - {error_text[:100]}', 'code': response.status_code, 'retry_after': wait_time}})}\\n\\n"
                        else:
                            yield f"data: {json.dumps({'error': {'message': f'Rate limited - {error_text[:100]}', 'code': response.status_code}})}\\n\\n"
                    else:
                        yield f"data: {json.dumps({'error': {'message': f'Upstream API error: {error_text[:100]}', 'code': response.status_code}})}\\n\\n"
                    
                    # 设置错误信息并完成请求
                    aggregator.set_error(metadata.request_id, str(response.status_code), error_text[:200])
                    final_metadata = aggregator.finish_request(metadata.request_id)
                    
                    # 发送错误情况下的汇总信息
                    yield aggregator.create_sse_summary_event(final_metadata)
                    yield "data: [DONE]\\n\\n"
                    return

                logger.info(f"STREAM CONNECTED: [{metadata.request_id}] Successfully connected to channel '{channel_id}', starting optimized data flow")
                
                # 记录TTFB时间 - 修正：连接建立后的第一个数据块时间
                ttfb_recorded = False
                first_data_time = None
                
                # 记录token信息的变量
                total_prompt_tokens = 0
                total_completion_tokens = 0
                total_tokens = 0
                
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    if chunk:
                        chunk_count += 1
                        
                        # 记录第一个数据块的时间作为TTFB（真正的首字节时间）
                        if not ttfb_recorded:
                            first_data_time = time.time()
                            ttfb = first_data_time - stream_start_time
                            aggregator.update_performance(metadata.request_id, ttfb=ttfb)
                            ttfb_recorded = True
                            logger.info(f"TTFB: [{metadata.request_id}] First data received in {ttfb:.3f}s")
                        
                        # 解析响应以提取token信息并检测流式错误（简化版）
                        try:
                            chunk_str = chunk.decode('utf-8', errors='ignore')
                            
                            # 检测流式数据中的速率限制错误
                            if 'data: ' in chunk_str and '"error"' in chunk_str:
                                lines = chunk_str.split('\\n')
                                for line in lines:
                                    if line.startswith('data: ') and line != 'data: [DONE]':
                                        try:
                                            data = json.loads(line[6:])  # 去掉 'data: '
                                            if 'error' in data:
                                                error_obj = data['error']
                                                error_code = error_obj.get('code')
                                                error_message = error_obj.get('message', '')
                                                
                                                # 检测速率限制错误
                                                if error_code == 429 or 'rate limit' in error_message.lower() or 'temporarily rate-limited' in error_message.lower():
                                                    wait_time = self._extract_rate_limit_wait_time(error_message)
                                                    if wait_time:
                                                        logger.warning(f"CONTENT RATE LIMIT: [{metadata.request_id}] Channel '{channel_id}' content suggests waiting {wait_time}s")
                                                        # 修改错误信息以包含等待时间
                                                        error_obj['retry_after'] = wait_time
                                                        data['error'] = error_obj
                                                        
                                                        # 重新构造修改后的chunk
                                                        modified_line = f"data: {json.dumps(data)}"
                                                        chunk_str = chunk_str.replace(line, modified_line)
                                                        chunk = chunk_str.encode('utf-8')
                                                    else:
                                                        logger.warning(f"CONTENT RATE LIMIT: [{metadata.request_id}] Channel '{channel_id}' rate limited in streaming content")
                                        except (json.JSONDecodeError, KeyError):
                                            pass
                            
                            # 提取token使用信息
                            if 'data: ' in chunk_str and '"usage"' in chunk_str:
                                # 尝试提取最后usage信息
                                lines = chunk_str.split('\\n')
                                for line in lines:
                                    if line.startswith('data: ') and line != 'data: [DONE]':
                                        try:
                                            data = json.loads(line[6:])  # 去掉 'data: '
                                            if 'usage' in data:
                                                usage = data['usage']
                                                total_prompt_tokens = usage.get('prompt_tokens', total_prompt_tokens)
                                                total_completion_tokens = usage.get('completion_tokens', total_completion_tokens) 
                                                total_tokens = usage.get('total_tokens', total_tokens)
                                        except (json.JSONDecodeError, KeyError):
                                            pass
                        except Exception:
                            pass  # 忽略解析错误
                        
                        if chunk_count % 20 == 0:
                            logger.debug(f"STREAMING: [{metadata.request_id}] Received {chunk_count} chunks from channel '{channel_id}'")
                    
                    yield chunk
                
                # 更新token和成本信息
                if total_tokens > 0:
                    aggregator.update_tokens(metadata.request_id, total_prompt_tokens, total_completion_tokens, total_tokens)
                    # 计算成本（需要估算模型名）
                    cost_info = self._calculate_request_cost(None, total_prompt_tokens, total_completion_tokens, metadata.model_used)
                    
                    # 获取用户会话信息 (流式请求需要从元数据中获取原始请求)
                    # 这里简化处理，实际应该传递原始请求对象
                    session_manager = get_session_manager()
                    user_identifier = session_manager.create_user_identifier("streaming-user", "streaming-client")
                    session = session_manager.add_request(
                        user_identifier=user_identifier,
                        cost=cost_info['total_cost'],
                        model=metadata.model_used,
                        channel=metadata.channel_name
                    )
                    
                    aggregator.update_cost(metadata.request_id, cost_info['total_cost'], session.total_cost, session.total_requests)
                    
                    # 流式响应专用：计算准确的token生成时间
                    if first_data_time and total_completion_tokens > 0:
                        generation_time = time.time() - first_data_time  # 从第一个token到最后一个token的时间
                        if generation_time > 0:
                            tokens_per_second = total_completion_tokens / generation_time
                            # 更新准确的token生成速度
                            aggregator.update_performance(metadata.request_id, tokens_per_second=tokens_per_second)
                            logger.info(f"TOKEN SPEED: [{metadata.request_id}] {total_completion_tokens} tokens in {generation_time:.3f}s = {tokens_per_second:.1f} tokens/sec")
                
                # 完成请求并生成汇总
                final_metadata = aggregator.finish_request(metadata.request_id)
                        
            stream_duration = time.time() - stream_start_time
            self.router.update_channel_health(channel_id, True, stream_duration)
            logger.info(f"STREAM COMPLETE: [{metadata.request_id}] Channel '{channel_id}' completed optimized streaming {chunk_count} chunks in {stream_duration:.3f}s")
            
            # 在[DONE]之前发送汇总信息
            yield aggregator.create_sse_summary_event(final_metadata)
            yield "data: [DONE]\\n\\n"
            
        except httpx.HTTPStatusError as e:
            error_text = e.response.text if hasattr(e.response, 'text') else str(e)
            logger.error(f"STREAM FAILED: [{metadata.request_id}] Channel '{channel_id}' HTTP error {e.response.status_code}: {error_text[:200]}...")
            self.router.update_channel_health(channel_id, False)
            
            # 设置错误信息并完成请求
            aggregator.set_error(metadata.request_id, str(e.response.status_code), error_text)
            final_metadata = aggregator.finish_request(metadata.request_id)
            
            yield f"data: {json.dumps({'error': {'message': f'Upstream API error: {error_text}', 'code': e.response.status_code}})}\\n\\n"
            yield aggregator.create_sse_summary_event(final_metadata)
            yield "data: [DONE]\\n\\n"
            
        except Exception as e:
            logger.error(f"STREAM EXCEPTION: [{metadata.request_id}] Streaming request for channel '{channel_id}' failed: {e}", exc_info=True)
            self.router.update_channel_health(channel_id, False)
            
            # 设置错误信息并完成请求
            aggregator.set_error(metadata.request_id, "500", str(e))
            final_metadata = aggregator.finish_request(metadata.request_id)
            
            yield f"data: {json.dumps({'error': {'message': str(e), 'code': 500}})}\\n\\n"
            yield aggregator.create_sse_summary_event(final_metadata)
            yield "data: [DONE]\\n\\n"
    
    def _extract_user_identifier(self, request) -> str:
        """从请求中提取用户标识符"""
        # 这里可以从请求头或其他地方提取API key和User-Agent
        # 暂时使用简化版本，实际应该从FastAPI的Request对象中获取
        api_key = getattr(request, 'api_key', None) or "anonymous"
        user_agent = getattr(request, 'user_agent', None) or "unknown-client"
        
        session_manager = get_session_manager()
        return session_manager.create_user_identifier(api_key, user_agent)