"""
响应汇总器 - 统一处理流式和非流式请求的元数据输出
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class RequestMetadata:
    """请求元数据"""

    request_id: str
    model_requested: str
    model_used: str
    channel_name: str
    channel_id: str
    provider: str
    attempt_count: int
    is_streaming: bool
    start_time: float
    end_time: Optional[float] = None
    latency: Optional[float] = None

    # 成本信息
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    request_cost: float = 0.0
    session_cost: float = 0.0
    session_requests: int = 0

    # 路由信息
    routing_strategy: str = "balanced"
    routing_score: float = 0.0
    routing_reason: str = ""

    # 性能信息
    ttfb: Optional[float] = None  # Time to first byte
    tokens_per_second: Optional[float] = None

    # 错误信息
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    # 成本预览信息
    cost_preview: Optional[dict[str, Any]] = None

    def finish_request(self, end_time: Optional[float] = None):
        """结束请求，计算最终指标"""
        self.end_time = end_time or time.time()
        self.latency = self.end_time - self.start_time

        if self.completion_tokens > 0 and self.latency:
            self.tokens_per_second = self.completion_tokens / self.latency


class ResponseAggregator:
    """响应汇总器 - 统一处理不同类型的响应输出"""

    def __init__(self):
        self.active_requests: dict[str, RequestMetadata] = {}

    def create_request_metadata(
        self,
        request_id: str,
        model_requested: str,
        model_used: str,
        channel_name: str,
        channel_id: str,
        provider: str,
        attempt_count: int,
        is_streaming: bool,
        routing_strategy: str = "balanced",
        routing_score: float = 0.0,
        routing_reason: str = "",
        cost_preview: Optional[dict[str, Any]] = None,
    ) -> RequestMetadata:
        """创建请求元数据"""
        metadata = RequestMetadata(
            request_id=request_id,
            model_requested=model_requested,
            model_used=model_used,
            channel_name=channel_name,
            channel_id=channel_id,
            provider=provider,
            attempt_count=attempt_count,
            is_streaming=is_streaming,
            start_time=time.time(),
            routing_strategy=routing_strategy,
            routing_score=routing_score,
            routing_reason=routing_reason,
            cost_preview=cost_preview,
        )

        self.active_requests[request_id] = metadata
        return metadata

    def update_tokens(
        self,
        request_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ):
        """更新token信息"""
        if request_id in self.active_requests:
            metadata = self.active_requests[request_id]
            metadata.prompt_tokens = prompt_tokens
            metadata.completion_tokens = completion_tokens
            metadata.total_tokens = total_tokens

    def update_cost(
        self,
        request_id: str,
        request_cost: float,
        session_cost: float,
        session_requests: int,
    ):
        """更新成本信息"""
        if request_id in self.active_requests:
            metadata = self.active_requests[request_id]
            metadata.request_cost = request_cost
            metadata.session_cost = session_cost
            metadata.session_requests = session_requests

    def update_performance(
        self,
        request_id: str,
        ttfb: Optional[float] = None,
        tokens_per_second: Optional[float] = None,
    ):
        """更新性能信息"""
        if request_id in self.active_requests:
            metadata = self.active_requests[request_id]
            if ttfb is not None:
                metadata.ttfb = ttfb
            if tokens_per_second is not None:
                metadata.tokens_per_second = tokens_per_second

    def set_error(self, request_id: str, error_code: str, error_message: str):
        """设置错误信息"""
        if request_id in self.active_requests:
            metadata = self.active_requests[request_id]
            metadata.error_code = error_code
            metadata.error_message = error_message

    def finish_request(self, request_id: str) -> Optional[RequestMetadata]:
        """完成请求，返回最终元数据"""
        if request_id not in self.active_requests:
            return None

        metadata = self.active_requests[request_id]
        metadata.finish_request()

        # 从活跃请求中移除
        del self.active_requests[request_id]

        return metadata

    def get_headers_summary(self, request_id: str) -> dict[str, str]:
        """获取用于HTTP头的汇总信息（流式请求使用）"""
        if request_id not in self.active_requests:
            return {}

        metadata = self.active_requests[request_id]

        return {
            "X-Router-Request-ID": metadata.request_id,
            "X-Router-Channel": f"{metadata.channel_name} (ID: {metadata.channel_id})",
            "X-Router-Provider": metadata.provider,
            "X-Router-Model": f"{metadata.model_requested} -> {metadata.model_used}",
            "X-Router-Attempt": str(metadata.attempt_count),
            "X-Router-Strategy": metadata.routing_strategy,
            "X-Router-Score": f"{metadata.routing_score:.3f}",
            "X-Router-Streaming": "true" if metadata.is_streaming else "false",
        }

    def get_final_summary(self, metadata: RequestMetadata) -> dict[str, Any]:
        """获取最终的完整汇总信息"""
        summary = {
            "request_metadata": {
                "request_id": metadata.request_id,
                "model_requested": metadata.model_requested,
                "model_used": metadata.model_used,
                "channel": {
                    "name": metadata.channel_name,
                    "id": metadata.channel_id,
                    "provider": metadata.provider,
                },
                "routing": {
                    "strategy": metadata.routing_strategy,
                    "score": metadata.routing_score,
                    "reason": metadata.routing_reason,
                    "attempt_count": metadata.attempt_count,
                },
                "streaming": metadata.is_streaming,
            },
            "performance": {
                "latency_ms": (
                    round(metadata.latency * 1000, 2) if metadata.latency else None
                ),
                "ttfb_ms": round(metadata.ttfb * 1000, 2) if metadata.ttfb else None,
                "tokens_per_second": (
                    round(metadata.tokens_per_second, 2)
                    if metadata.tokens_per_second
                    else None
                ),
            },
            "usage": {
                "prompt_tokens": metadata.prompt_tokens,
                "completion_tokens": metadata.completion_tokens,
                "total_tokens": metadata.total_tokens,
            },
            "cost": {
                "request_cost": f"${metadata.request_cost:.6f}",
                "session_cost": f"${metadata.session_cost:.6f}",
                "session_requests": metadata.session_requests,
            },
        }

        # 添加错误信息（如果有）
        if metadata.error_code:
            summary["error"] = {
                "code": metadata.error_code,
                "message": metadata.error_message,
            }

        return summary

    def create_sse_summary_event(self, metadata: RequestMetadata) -> str:
        """创建SSE格式的汇总事件（流式请求结束时，在[DONE]之前使用）"""

        # 创建Smart AI Router专用的汇总数据结构
        smart_ai_router_data = {
            "request_id": metadata.request_id,
            "routing": {
                "model_requested": metadata.model_requested,
                "model_used": metadata.model_used,
                "channel": {
                    "name": metadata.channel_name,
                    "id": metadata.channel_id,
                    "provider": metadata.provider,
                },
                "strategy": metadata.routing_strategy,
                "score": metadata.routing_score,
                "reason": metadata.routing_reason,
                "attempt_count": metadata.attempt_count,
            },
            "performance": {
                "latency_ms": (
                    round(metadata.latency * 1000, 2) if metadata.latency else None
                ),
                "ttfb_ms": round(metadata.ttfb * 1000, 2) if metadata.ttfb else None,
                "tokens_per_second": (
                    round(metadata.tokens_per_second, 2)
                    if metadata.tokens_per_second
                    else None
                ),
            },
            "cost": {
                "request": {
                    "prompt_cost": f"${(metadata.request_cost * metadata.prompt_tokens / max(metadata.total_tokens, 1)):.6f}",
                    "completion_cost": f"${(metadata.request_cost * metadata.completion_tokens / max(metadata.total_tokens, 1)):.6f}",
                    "total_cost": f"${metadata.request_cost:.6f}",
                },
                "session": {
                    "total_cost": f"${metadata.session_cost:.6f}",
                    "total_requests": metadata.session_requests,
                },
            },
            "tokens": {
                "prompt_tokens": metadata.prompt_tokens,
                "completion_tokens": metadata.completion_tokens,
                "total_tokens": metadata.total_tokens,
            },
        }

        # 如果有错误信息，也添加到数据结构中
        if metadata.error_code:
            smart_ai_router_data["error"] = {
                "code": metadata.error_code,
                "message": metadata.error_message,
            }

        # 创建符合OpenAI SSE格式的汇总事件，但内容是我们的数据
        summary_chunk = {
            "id": f"summary-{metadata.request_id}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": metadata.model_used,
            "choices": [{"index": 0, "delta": {}, "finish_reason": None}],
            "smart_ai_router": smart_ai_router_data,
        }

        return f"data: {json.dumps(summary_chunk)}\n\n"

    def enhance_response_with_summary(
        self, response_data: dict[str, Any], metadata: RequestMetadata
    ) -> dict[str, Any]:
        """为响应数据添加汇总信息（非流式请求使用）"""
        enhanced_response = response_data.copy()

        # 添加独立的Smart AI Router数据结构
        enhanced_response["smart_ai_router"] = {
            "request_id": metadata.request_id,
            "routing": {
                "model_requested": metadata.model_requested,
                "model_used": metadata.model_used,
                "channel": {
                    "name": metadata.channel_name,
                    "id": metadata.channel_id,
                    "provider": metadata.provider,
                },
                "strategy": metadata.routing_strategy,
                "score": metadata.routing_score,
                "reason": metadata.routing_reason,
                "attempt_count": metadata.attempt_count,
            },
            "performance": {
                "latency_ms": (
                    round(metadata.latency * 1000, 2) if metadata.latency else None
                ),
                "ttfb_ms": round(metadata.ttfb * 1000, 2) if metadata.ttfb else None,
                "tokens_per_second": (
                    round(metadata.tokens_per_second, 2)
                    if metadata.tokens_per_second
                    else None
                ),
            },
            "cost": {
                "request": {
                    "prompt_cost": f"${(metadata.request_cost * metadata.prompt_tokens / max(metadata.total_tokens, 1)):.6f}",
                    "completion_cost": f"${(metadata.request_cost * metadata.completion_tokens / max(metadata.total_tokens, 1)):.6f}",
                    "total_cost": f"${metadata.request_cost:.6f}",
                },
                "session": {
                    "total_cost": f"${metadata.session_cost:.6f}",
                    "total_requests": metadata.session_requests,
                },
            },
            "tokens": {
                "prompt_tokens": metadata.prompt_tokens,
                "completion_tokens": metadata.completion_tokens,
                "total_tokens": metadata.total_tokens,
            },
        }

        # 如果有错误信息，也添加到我们的数据结构中
        if metadata.error_code:
            enhanced_response["smart_ai_router"]["error"] = {
                "code": metadata.error_code,
                "message": metadata.error_message,
            }

        return enhanced_response


# 全局实例
_response_aggregator: Optional[ResponseAggregator] = None


def get_response_aggregator() -> ResponseAggregator:
    """获取全局响应汇总器实例"""
    global _response_aggregator
    if _response_aggregator is None:
        _response_aggregator = ResponseAggregator()
    return _response_aggregator
