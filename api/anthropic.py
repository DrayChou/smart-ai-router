"""
Anthropic Claude API 兼容接口
完美复刻 Anthropic Claude API 的接口服务
让客户端可以像使用官方API一样使用Smart AI Router
"""

import json
import uuid
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.exceptions import RouterException
from core.handlers.chat_handler import ChatCompletionHandler, ChatCompletionRequest
from core.json_router import JSONRouter
from core.utils.logger import get_logger
from core.yaml_config import YAMLConfigLoader

logger = get_logger(__name__)

# --- Anthropic Claude API Request/Response Models ---

class AnthropicMessage(BaseModel):
    """Anthropic消息格式"""
    role: str = Field(..., description="消息角色: user or assistant")
    content: Union[str, List[Dict[str, Any]]] = Field(..., description="消息内容")

class AnthropicTool(BaseModel):
    """Anthropic工具定义"""
    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    input_schema: Dict[str, Any] = Field(..., description="输入参数schema")

class AnthropicMessagesRequest(BaseModel):
    """Anthropic Messages API请求格式"""
    model: str = Field(..., description="模型ID")
    messages: List[AnthropicMessage] = Field(..., description="消息列表")
    max_tokens: int = Field(..., description="最大生成token数", ge=1)
    temperature: Optional[float] = Field(0.7, description="温度参数", ge=0.0, le=1.0)
    top_p: Optional[float] = Field(1.0, description="Top-p参数", ge=0.0, le=1.0)
    top_k: Optional[int] = Field(None, description="Top-k参数", ge=0)
    stop_sequences: Optional[List[str]] = Field(None, description="停止序列")
    stream: Optional[bool] = Field(False, description="是否流式输出")
    system: Optional[str] = Field(None, description="系统提示")
    tools: Optional[List[AnthropicTool]] = Field(None, description="工具列表")
    tool_choice: Optional[Union[str, Dict[str, Any]]] = Field(None, description="工具选择")

class AnthropicUsage(BaseModel):
    """Anthropic使用量统计"""
    input_tokens: int = Field(0, description="输入token数")
    output_tokens: int = Field(0, description="输出token数")
    cache_creation_input_tokens: Optional[int] = Field(None, description="缓存创建输入token")
    cache_read_input_tokens: Optional[int] = Field(None, description="缓存读取输入token")

class AnthropicContentBlock(BaseModel):
    """Anthropic内容块"""
    type: str = Field(..., description="内容类型")
    text: Optional[str] = Field(None, description="文本内容")

class AnthropicMessageResponse(BaseModel):
    """Anthropic消息响应"""
    id: str = Field(..., description="消息ID")
    type: str = Field("message", description="响应类型")
    role: str = Field("assistant", description="角色")
    content: List[AnthropicContentBlock] = Field(..., description="内容块")
    model: str = Field(..., description="使用的模型")
    stop_reason: Optional[str] = Field(None, description="停止原因")
    usage: AnthropicUsage = Field(..., description="使用量统计")

# --- Router Factory ---

def create_anthropic_router(
    config_loader: YAMLConfigLoader,
    json_router: JSONRouter,
    chat_handler: ChatCompletionHandler
) -> APIRouter:
    """创建Anthropic Claude API兼容路由"""

    router = APIRouter(prefix="/v1", tags=["anthropic"])

    @router.post("/messages")
    async def create_message(
        request: AnthropicMessagesRequest,
        authorization: Optional[str] = Header(None, alias="Authorization"),
        x_api_key: Optional[str] = Header(None, alias="x-api-key"),
        anthropic_version: str = Header("2023-06-01", alias="anthropic-version")
    ):
        """创建消息 - Anthropic Messages API"""

        # 验证API版本
        if anthropic_version != "2023-06-01":
            raise HTTPException(
                status_code=400,
                detail={
                    "type": "invalid_request_error",
                    "error": {
                        "type": "unsupported_api_version",
                        "message": f"API version {anthropic_version} is not supported"
                    }
                }
            )

        # 验证认证 - 支持多种方式
        api_key = None
        if authorization:
            if authorization.startswith("Bearer "):
                api_key = authorization[7:]
            else:
                api_key = authorization
        elif x_api_key:
            api_key = x_api_key  # Anthropic原生的x-api-key方式

        if not api_key:
            raise HTTPException(
                status_code=401,
                detail={
                    "type": "authentication_error",
                    "error": {
                        "type": "api_key_missing",
                        "message": "Missing authentication headers (Authorization or x-api-key)"
                    }
                }
            )

        # 验证必需参数
        if not request.max_tokens or request.max_tokens < 1:
            raise HTTPException(
                status_code=400,
                detail={
                    "type": "invalid_request_error",
                    "error": {
                        "type": "invalid_max_tokens",
                        "message": "max_tokens must be a positive integer"
                    }
                }
            )

        # 验证消息列表
        if not request.messages or len(request.messages) == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "type": "invalid_request_error",
                    "error": {
                        "type": "missing_messages",
                        "message": "messages list cannot be empty"
                    }
                }
            )

        # 验证最后一条消息是用户消息
        if request.messages[-1].role != "user":
            raise HTTPException(
                status_code=400,
                detail={
                    "type": "invalid_request_error",
                    "error": {
                        "type": "invalid_message_order",
                        "message": "Last message must be from user"
                    }
                }
            )

        try:
            # 转换为内部ChatCompletionRequest格式
            chat_request = convert_to_chat_request(request)

            # 设置认证头（通过extra_params传递）
            if not chat_request.extra_params:
                chat_request.extra_params = {}
            chat_request.extra_params["_anthropic_api_key"] = x_api_key

            if request.stream:
                # 流式响应
                return StreamingResponse(
                    stream_anthropic_response(chat_handler, chat_request),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Headers": "*"
                    }
                )
            else:
                # 非流式响应
                response = await chat_handler.handle_request(chat_request)
                return convert_to_anthropic_response(response, request.model)

        except RouterException as e:
            logger.error(f"Router error: {e}")
            raise HTTPException(
                status_code=e.status_code,
                detail={
                    "type": "api_error",
                    "error": {
                        "type": "router_error",
                        "message": e.message
                    }
                }
            )
        except Exception as e:
            logger.error(f"Unexpected error in Anthropic messages: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={
                    "type": "api_error",
                    "error": {
                        "type": "internal_error",
                        "message": "Internal server error"
                    }
                }
            )

    return router


def convert_to_chat_request(request: AnthropicMessagesRequest) -> ChatCompletionRequest:
    """将Anthropic请求转换为内部ChatCompletionRequest格式"""

    # 转换消息格式
    messages = []
    for msg in request.messages:
        # Anthropic不支持system角色，需要特殊处理
        if msg.role == "system":
            continue  # system消息会在system字段中处理

        messages.append({
            "role": msg.role,
            "content": msg.content
        })

    # 转换工具格式
    tools = None
    if request.tools:
        tools = []
        for tool in request.tools:
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            })

    # 创建ChatCompletionRequest
    chat_request = ChatCompletionRequest(
        model=request.model,
        messages=messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stream=request.stream,
        top_p=request.top_p,
        system=request.system,
        tools=tools,
        tool_choice=request.tool_choice
    )

    # 添加额外参数
    extra_params = {}
    if request.top_k is not None:
        extra_params["top_k"] = request.top_k
    if request.stop_sequences:
        extra_params["stop"] = request.stop_sequences

    if extra_params:
        chat_request.extra_params = extra_params

    return chat_request


def convert_to_anthropic_response(response: Dict[str, Any], model: str) -> Dict[str, Any]:
    """将内部响应转换为Anthropic格式"""

    # 生成消息ID
    message_id = f"msg_{uuid.uuid4().hex}"

    # 处理响应，可能是JSONResponse或字典
    if hasattr(response, 'body'):
        # 如果是JSONResponse，需要解析body
        import json
        response_data = json.loads(response.body)
    else:
        # 如果是字典，直接使用
        response_data = response

    # 提取内容
    content_text = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")

    # 提取使用量
    usage = response_data.get("usage", {})
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)

    # 构建响应
    anthropic_response = {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": content_text
            }
        ],
        "model": model,
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }
    }

    return anthropic_response


async def stream_anthropic_response(chat_handler: ChatCompletionHandler, request: ChatCompletionRequest):
    """流式生成Anthropic格式响应"""

    # 生成消息ID
    message_id = f"msg_{uuid.uuid4().hex}"

    # 发送消息开始事件
    message_start_data = {
        "type": "message_start",
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": request.model,
            "stop_reason": None,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0
            }
        }
    }
    yield f"data: {json.dumps(message_start_data)}\n\n"

    # 获取流式响应
    content_buffer = ""
    total_output_tokens = 0

    try:
        # 使用chat_handler的流式处理
        async for chunk in chat_handler.handle_stream_request(request):
            # 处理不同类型的chunk
            if isinstance(chunk, str):
                # 如果是字符串，尝试解析为JSON
                try:
                    chunk_data = json.loads(chunk)
                    if chunk_data.get("type") == "error":
                        # 错误消息
                        yield f"data: {json.dumps(chunk_data)}\n\n"
                        return
                except:
                    # 如果不是JSON，当作文本内容处理
                    content = chunk
            else:
                # 如果是字典，提取内容
                content = ""
                if chunk.get("choices"):
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")

            if content:
                content_buffer += content
                total_output_tokens += len(content.split())  # 简单估算

                # 发送内容块增量
                content_delta_data = {
                    "type": "content_block_delta",
                    "delta": {
                        "type": "text_delta",
                        "text": content
                    }
                }
                yield f"data: {json.dumps(content_delta_data)}\n\n"

    except Exception as e:
        logger.error(f"Stream error: {e}")
        error_data = {
            "type": "error",
            "error": {
                "type": "stream_error",
                "message": "Stream processing error"
            }
        }
        yield f"data: {json.dumps(error_data)}\n\n"
        return

    # 发送消息结束事件
    message_delta_data = {
        "type": "message_delta",
        "delta": {
            "stop_reason": "end_turn"
        },
        "usage": {
            "output_tokens": total_output_tokens
        }
    }
    yield f"data: {json.dumps(message_delta_data)}\n\n"

    # 发送消息停止事件
    message_stop_data = {
        "type": "message_stop"
    }
    yield f"data: {json.dumps(message_stop_data)}\n\n"


# --- 错误处理 ---

class AnthropicAPIError(Exception):
    """Anthropic API错误"""

    def __init__(self, error_type: str, message: str, status_code: int = 500):
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为错误响应格式"""
        return {
            "type": "error",
            "error": {
                "type": self.error_type,
                "message": self.message
            }
        }
