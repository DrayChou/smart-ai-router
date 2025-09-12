"""
OpenAI ChatGPT API 兼容接口
完美复刻 OpenAI ChatGPT API 的接口服务
支持最新的参数和返回值结构，包括vision、tools等功能
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.exceptions import RoutingException
from core.handlers.chat_handler import ChatCompletionHandler, ChatCompletionRequest
from core.json_router import JSONRouter
from core.utils.logger import get_logger
from core.yaml_config import YAMLConfigLoader

logger = get_logger(__name__)

# --- OpenAI ChatGPT API Request/Response Models ---

class ChatGPTContentPart(BaseModel):
    """OpenAI内容部分"""
    type: str = Field(..., description="内容类型")
    text: Optional[str] = Field(None, description="文本内容")
    image_url: Optional[Dict[str, Any]] = Field(None, description="图片URL")

class ChatGPTMessage(BaseModel):
    """OpenAI消息格式"""
    role: str = Field(..., description="消息角色: system, user, assistant, or tool")
    content: Union[str, List[Union[ChatGPTContentPart, Dict[str, Any]]]] = Field(..., description="消息内容")
    name: Optional[str] = Field(None, description="工具名称")
    tool_call_id: Optional[str] = Field(None, description="工具调用ID")

class ChatGPTTool(BaseModel):
    """OpenAI工具定义"""
    type: str = Field("function", description="工具类型")
    function: Dict[str, Any] = Field(..., description="函数定义")

class ChatGPTResponseFormat(BaseModel):
    """OpenAI响应格式"""
    type: str = Field("json_object", description="响应类型")
    json_schema: Optional[Dict[str, Any]] = Field(None, description="JSON schema")

class ChatGPTCompletionRequest(BaseModel):
    """OpenAI Chat Completions API请求格式"""
    model: str = Field(..., description="模型ID")
    messages: List[ChatGPTMessage] = Field(..., description="消息列表")
    temperature: Optional[float] = Field(0.7, description="温度参数", ge=0.0, le=2.0)
    top_p: Optional[float] = Field(1.0, description="Top-p参数", ge=0.0, le=1.0)
    n: Optional[int] = Field(1, description="生成数量", ge=1, le=10)
    stream: Optional[bool] = Field(False, description="是否流式输出")
    stop: Optional[Union[str, List[str]]] = Field(None, description="停止条件")
    max_tokens: Optional[int] = Field(None, description="最大token数", ge=1)
    presence_penalty: Optional[float] = Field(0.0, description="存在惩罚", ge=-2.0, le=2.0)
    frequency_penalty: Optional[float] = Field(0.0, description="频率惩罚", ge=-2.0, le=2.0)
    logit_bias: Optional[Dict[str, int]] = Field(None, description="Logit偏差")
    user: Optional[str] = Field(None, description="用户标识")
    tools: Optional[List[ChatGPTTool]] = Field(None, description="工具列表")
    tool_choice: Optional[Union[str, Dict[str, Any]]] = Field(None, description="工具选择")
    response_format: Optional[ChatGPTResponseFormat] = Field(None, description="响应格式")
    seed: Optional[int] = Field(None, description="随机种子")
    logprobs: Optional[bool] = Field(False, description="是否返回log概率")
    top_logprobs: Optional[int] = Field(None, description="返回的top log概率数量", ge=0, le=20)

class ChatGPTUsage(BaseModel):
    """OpenAI使用量统计"""
    prompt_tokens: int = Field(0, description="输入token数")
    completion_tokens: int = Field(0, description="输出token数")
    total_tokens: int = Field(0, description="总token数")

class ChatGPTLogProb(BaseModel):
    """OpenAI Log概率"""
    token: str = Field(..., description="token")
    logprob: float = Field(..., description="log概率")
    bytes: Optional[List[int]] = Field(None, description="token字节")

class ChatGPTTopLogProb(BaseModel):
    """OpenAI Top Log概率"""
    token: str = Field(..., description="token")
    logprob: float = Field(..., description="log概率")
    bytes: Optional[List[int]] = Field(None, description="token字节")
    top_logprobs: Optional[List[ChatGPTLogProb]] = Field(None, description="top log概率")

class ChatGPTChoiceLogProbs(BaseModel):
    """OpenAI选择Log概率"""
    content: Optional[List[ChatGPTTopLogProb]] = Field(None, description="内容log概率")

class ChatGPTToolCall(BaseModel):
    """OpenAI工具调用"""
    id: str = Field(..., description="工具调用ID")
    type: str = Field("function", description="工具类型")
    function: Dict[str, Any] = Field(..., description="函数调用")

class ChatGPTMessageResponse(BaseModel):
    """OpenAI消息响应"""
    role: str = Field("assistant", description="角色")
    content: Optional[Union[str, None]] = Field(None, description="内容")
    tool_calls: Optional[List[ChatGPTToolCall]] = Field(None, description="工具调用")

class ChatGPTChoice(BaseModel):
    """OpenAI选择"""
    index: int = Field(0, description="选择索引")
    message: ChatGPTMessageResponse = Field(..., description="消息")
    finish_reason: Optional[str] = Field(None, description="完成原因")
    logprobs: Optional[ChatGPTChoiceLogProbs] = Field(None, description="Log概率")

class ChatGPTCompletionResponse(BaseModel):
    """OpenAI Chat Completions API响应格式"""
    id: str = Field(..., description="响应ID")
    object: str = Field("chat.completion", description="对象类型")
    created: int = Field(..., description="创建时间")
    model: str = Field(..., description="使用的模型")
    system_fingerprint: Optional[str] = Field(None, description="系统指纹")
    choices: List[ChatGPTChoice] = Field(..., description="选择列表")
    usage: ChatGPTUsage = Field(..., description="使用量统计")

class ChatGPTCompletionChunk(BaseModel):
    """OpenAI流式响应块"""
    id: str = Field(..., description="响应ID")
    object: str = Field("chat.completion.chunk", description="对象类型")
    created: int = Field(..., description="创建时间")
    model: str = Field(..., description="使用的模型")
    system_fingerprint: Optional[str] = Field(None, description="系统指纹")
    choices: List[ChatGPTChoice] = Field(..., description="选择列表")

# --- Router Factory ---

def create_chatgpt_router(
    config_loader: YAMLConfigLoader,
    json_router: JSONRouter,
    chat_handler: ChatCompletionHandler
) -> APIRouter:
    """创建OpenAI ChatGPT API兼容路由"""

    router = APIRouter(prefix="/v1", tags=["chatgpt"])

    @router.post("/chat/completions", response_model=Union[ChatGPTCompletionResponse, List[ChatGPTCompletionChunk]])
    async def chat_completions(
        request: ChatGPTCompletionRequest,
        authorization: Optional[str] = Header(None, alias="Authorization")
    ):
        """OpenAI Chat Completions API - 完全兼容"""

        # 验证认证 - 统一使用Bearer Token
        api_key = None
        if authorization and authorization.startswith("Bearer "):
            api_key = authorization[7:]
        elif authorization:
            api_key = authorization  # 兼容直接传递API密钥的情况

        # 转换为内部ChatCompletionRequest格式
        chat_request = convert_to_chat_request(request, api_key)

        try:
            if request.stream:
                # 流式响应
                return StreamingResponse(
                    stream_chatgpt_response(chat_handler, chat_request, request),
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
                return convert_to_chatgpt_response(response, request)

        except RoutingException as e:
            logger.error(f"Router error: {e}")
            raise HTTPException(
                status_code=e.status_code,
                detail={
                    "error": {
                        "message": e.message,
                        "type": "api_error",
                        "code": e.status_code
                    }
                }
            )
        except Exception as e:
            logger.error(f"Unexpected error in ChatGPT completions: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "message": "Internal server error",
                        "type": "api_error",
                        "code": 500
                    }
                }
            )

    return router


def convert_to_chat_request(request: ChatGPTCompletionRequest, api_key: Optional[str]) -> ChatCompletionRequest:
    """将OpenAI请求转换为内部ChatCompletionRequest格式"""

    # 转换消息格式
    messages = []
    for msg in request.messages:
        message_dict = {
            "role": msg.role,
            "content": msg.content
        }
        if msg.name:
            message_dict["name"] = msg.name
        if msg.tool_call_id:
            message_dict["tool_call_id"] = msg.tool_call_id
        messages.append(message_dict)

    # 转换工具格式
    tools = None
    if request.tools:
        tools = []
        for tool in request.tools:
            tools.append({
                "type": tool.type,
                "function": tool.function
            })

    # 创建ChatCompletionRequest
    chat_request = ChatCompletionRequest(
        model=request.model,
        messages=messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stream=request.stream,
        top_p=request.top_p,
        n=request.n,
        stop=request.stop,
        presence_penalty=request.presence_penalty,
        frequency_penalty=request.frequency_penalty,
        tools=tools,
        tool_choice=request.tool_choice
    )

    # 添加额外参数
    extra_params = {}
    if request.logit_bias:
        extra_params["logit_bias"] = request.logit_bias
    if request.user:
        extra_params["user"] = request.user
    if request.response_format:
        extra_params["response_format"] = request.response_format.dict()
    if request.seed:
        extra_params["seed"] = request.seed
    if request.logprobs:
        extra_params["logprobs"] = request.logprobs
    if request.top_logprobs:
        extra_params["top_logprobs"] = request.top_logprobs
    if api_key:
        extra_params["_openai_api_key"] = api_key

    if extra_params:
        chat_request.extra_params = extra_params

    return chat_request


def convert_to_chatgpt_response(response: Dict[str, Any], request: ChatGPTCompletionRequest) -> Dict[str, Any]:
    """将内部响应转换为OpenAI格式"""

    # 生成响应ID和创建时间
    response_id = f"chatcmpl-{uuid.uuid4().hex}"
    created_time = int(time.time())

    # 处理响应，可能是JSONResponse或字典
    if hasattr(response, 'body'):
        import json
        response_data = json.loads(response.body)
    else:
        response_data = response

    # 提取选择
    choices = response_data.get("choices", [])
    converted_choices = []

    for choice in choices:
        message = choice.get("message", {})
        content = message.get("content")

        # 处理工具调用
        tool_calls = None
        if "tool_calls" in message:
            tool_calls = []
            for tool_call in message["tool_calls"]:
                tool_calls.append({
                    "id": tool_call.get("id"),
                    "type": "function",
                    "function": tool_call.get("function", {})
                })

        converted_choice = {
            "index": choice.get("index", 0),
            "message": {
                "role": "assistant",
                "content": content
            }
        }

        if tool_calls:
            converted_choice["message"]["tool_calls"] = tool_calls

        finish_reason = choice.get("finish_reason")
        if finish_reason:
            converted_choice["finish_reason"] = finish_reason

        converted_choices.append(converted_choice)

    # 提取使用量
    usage = response_data.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

    # 构建响应
    chatgpt_response = {
        "id": response_id,
        "object": "chat.completion",
        "created": created_time,
        "model": request.model,
        "choices": converted_choices,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens
        }
    }

    # 添加系统指纹
    if hasattr(response, 'system_fingerprint'):
        chatgpt_response["system_fingerprint"] = response.system_fingerprint
    else:
        chatgpt_response["system_fingerprint"] = f"fp_{uuid.uuid4().hex[:8]}"

    return chatgpt_response


async def stream_chatgpt_response(chat_handler: ChatCompletionHandler, request: ChatCompletionRequest, original_request: ChatGPTCompletionRequest):
    """流式生成OpenAI格式响应"""

    # 生成响应ID和创建时间
    response_id = f"chatcmpl-{uuid.uuid4().hex}"
    created_time = int(time.time())

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
                    # 如果不是JSON，当作普通处理
                    continue
            else:
                # 如果是字典，处理流式响应
                if chunk.get("choices"):
                    for choice in chunk["choices"]:
                        # 创建流式响应块
                        chunk_response = {
                            "id": response_id,
                            "object": "chat.completion.chunk",
                            "created": created_time,
                            "model": original_request.model,
                            "choices": [choice]
                        }

                        # 添加系统指纹
                        if hasattr(chunk, 'system_fingerprint'):
                            chunk_response["system_fingerprint"] = chunk.system_fingerprint
                        else:
                            chunk_response["system_fingerprint"] = f"fp_{uuid.uuid4().hex[:8]}"

                        yield f"data: {json.dumps(chunk_response)}\n\n"

    except Exception as e:
        logger.error(f"Stream error: {e}")
        error_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": original_request.model,
            "choices": [{
                "index": 0,
                "finish_reason": "error",
                "message": {
                    "role": "assistant",
                    "content": None
                }
            }]
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"

    # 发送结束标记
    yield "data: [DONE]\n\n"


# --- 错误处理 ---

class ChatGPTAPIError(Exception):
    """OpenAI API错误"""

    def __init__(self, error_type: str, message: str, status_code: int = 500):
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为错误响应格式"""
        return {
            "error": {
                "message": self.message,
                "type": self.error_type,
                "code": self.status_code
            }
        }
