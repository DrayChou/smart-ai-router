"""
Google Gemini API 兼容接口
完美复刻 Google Gemini API 的接口服务
让客户端可以像使用官方API一样使用Smart AI Router
"""

import json
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.exceptions import RoutingException
from core.handlers.chat_handler import ChatCompletionHandler, ChatCompletionRequest
from core.json_router import JSONRouter
from core.utils.logger import get_logger
from core.yaml_config import YAMLConfigLoader

logger = get_logger(__name__)

# --- Google Gemini API Request/Response Models ---


class GeminiContent(BaseModel):
    """Gemini内容块"""

    parts: list[dict[str, Any]] = Field(..., description="内容部分列表")
    role: str = Field(..., description="消息角色")


class GeminiMessage(BaseModel):
    """Gemini消息格式"""

    role: str = Field(..., description="消息角色")
    parts: list[dict[str, Any]] = Field(..., description="消息部分")


class GeminiTool(BaseModel):
    """Gemini工具定义"""

    function_declarations: list[dict[str, Any]] = Field(..., description="函数声明列表")


class GeminiToolConfig(BaseModel):
    """Gemini工具配置"""

    function_calling_config: Optional[dict[str, Any]] = Field(
        None, description="函数调用配置"
    )


class GeminiGenerationConfig(BaseModel):
    """Gemini生成配置"""

    temperature: Optional[float] = Field(None, description="温度参数", ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, description="Top-p参数", ge=0.0, le=1.0)
    top_k: Optional[int] = Field(None, description="Top-k参数", ge=1)
    max_output_tokens: Optional[int] = Field(None, description="最大输出token数", ge=1)
    stop_sequences: Optional[list[str]] = Field(None, description="停止序列")
    presence_penalty: Optional[float] = Field(
        None, description="存在惩罚", ge=-2.0, le=2.0
    )
    frequency_penalty: Optional[float] = Field(
        None, description="频率惩罚", ge=-2.0, le=2.0
    )
    response_mime_type: Optional[str] = Field(None, description="响应MIME类型")
    response_schema: Optional[dict[str, Any]] = Field(None, description="响应模式")


class GeminiSafetySetting(BaseModel):
    """Gemini安全设置"""

    category: str = Field(..., description="安全类别")
    threshold: str = Field(..., description="阈值")


class GeminiRequest(BaseModel):
    """Gemini API请求格式"""

    contents: list[GeminiMessage] = Field(..., description="对话内容")
    tools: Optional[list[GeminiTool]] = Field(None, description="工具列表")
    tool_config: Optional[GeminiToolConfig] = Field(None, description="工具配置")
    safety_settings: Optional[list[GeminiSafetySetting]] = Field(
        None, description="安全设置"
    )
    system_instruction: Optional[GeminiMessage] = Field(None, description="系统指令")
    generation_config: Optional[GeminiGenerationConfig] = Field(
        None, description="生成配置"
    )


# --- Router Factory ---


def create_gemini_router(
    config_loader: YAMLConfigLoader,
    json_router: JSONRouter,
    chat_handler: ChatCompletionHandler,
) -> APIRouter:
    """创建Google Gemini API兼容路由 - 同时支持v1和v1beta版本"""

    # 创建主路由器（无前缀，用于包含不同版本）
    main_router = APIRouter(tags=["gemini"])

    # 创建v1路由器
    v1_router = APIRouter(prefix="/v1", tags=["gemini-v1"])

    # 创建v1beta路由器
    v1beta_router = APIRouter(prefix="/v1beta", tags=["gemini-v1beta"])

    # 为v1和v1beta创建路由处理器
    def _register_routes(router_instance: APIRouter, version: str):
        """为指定版本注册路由"""

        @router_instance.post("/models/{model}:generateContent")
        async def generate_content(
            model: str,
            request: GeminiRequest,
            authorization: Optional[str] = Header(None, alias="Authorization"),
            x_goog_api_key: Optional[str] = Header(None, alias="x-goog-api-key"),
        ):
            """Gemini Generate Content API"""

            # 验证认证 - 支持多种方式
            api_key = None
            if authorization:
                if authorization.startswith("Bearer "):
                    api_key = authorization[7:]
                else:
                    api_key = authorization
            elif x_goog_api_key:
                api_key = x_goog_api_key  # Gemini原生的x-goog-api-key方式

            if not api_key:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "error": {
                            "code": 401,
                            "message": "Missing authentication headers (Authorization or x-goog-api-key)",
                            "status": "UNAUTHENTICATED",
                        }
                    },
                )

            # 转换为内部ChatCompletionRequest格式
            chat_request = convert_to_chat_request(request, model, api_key)

            try:
                response = await chat_handler.handle_request(chat_request)
                return convert_to_gemini_response(response, model, request)

            except RoutingException as e:
                logger.error(f"Router error: {e}")
                raise HTTPException(
                    status_code=e.status_code,
                    detail={
                        "error": {
                            "code": e.status_code,
                            "message": e.message,
                            "status": "FAILED",
                        }
                    },
                ) from e
            except Exception as e:
                logger.error(
                    f"Unexpected error in Gemini generateContent: {e}", exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": {
                            "code": 500,
                            "message": "Internal server error",
                            "status": "FAILED",
                        }
                    },
                ) from e

        @router_instance.post("/models/{model}:streamGenerateContent")
        async def stream_generate_content(
            model: str,
            request: GeminiRequest,
            authorization: Optional[str] = Header(None, alias="Authorization"),
            x_goog_api_key: Optional[str] = Header(None, alias="x-goog-api-key"),
        ):
            """Gemini Stream Generate Content API"""

            # 验证认证 - 支持多种方式
            api_key = None
            if authorization:
                if authorization.startswith("Bearer "):
                    api_key = authorization[7:]
                else:
                    api_key = authorization
            elif x_goog_api_key:
                api_key = x_goog_api_key  # Gemini原生的x-goog-api-key方式

            if not api_key:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "error": {
                            "code": 401,
                            "message": "Missing authentication headers (Authorization or x-goog-api-key)",
                            "status": "UNAUTHENTICATED",
                        }
                    },
                )

            # 转换为内部ChatCompletionRequest格式
            chat_request = convert_to_chat_request(request, model, api_key)
            chat_request.stream = True

            try:
                # 流式响应
                return StreamingResponse(
                    stream_gemini_response(chat_handler, chat_request, model),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Headers": "*",
                    },
                )

            except RoutingException as e:
                logger.error(f"Router error: {e}")
                raise HTTPException(
                    status_code=e.status_code,
                    detail={
                        "error": {
                            "code": e.status_code,
                            "message": e.message,
                            "status": "FAILED",
                        }
                    },
                ) from e
            except Exception as e:
                logger.error(
                    f"Unexpected error in Gemini streamGenerateContent: {e}",
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": {
                            "code": 500,
                            "message": "Internal server error",
                            "status": "FAILED",
                        }
                    },
                ) from e

    # 为v1和v1beta版本注册路由
    _register_routes(v1_router, "v1")
    _register_routes(v1beta_router, "v1beta")

    # 将v1和v1beta路由包含到主路由器中
    main_router.include_router(v1_router)
    main_router.include_router(v1beta_router)

    return main_router


def convert_to_chat_request(
    request: GeminiRequest, model: str, api_key: Optional[str]
) -> ChatCompletionRequest:
    """将Gemini请求转换为内部ChatCompletionRequest格式"""

    # 转换消息格式
    messages = []

    # 添加系统指令
    if request.system_instruction:
        system_content = ""
        for part in request.system_instruction.parts:
            if "text" in part:
                system_content += part["text"]

        if system_content:
            messages.append({"role": "system", "content": system_content})

    # 添加消息内容
    for msg in request.contents:
        # Gemini使用user/model角色，转换为user/assistant
        role = "user" if msg.role == "user" else "assistant"

        # 合并所有parts为内容
        content = ""
        for part in msg.parts:
            if "text" in part:
                content += part["text"]
            elif "inline_data" in part:
                # 处理图片等内联数据
                content += f"[Image: {part['inline_data'].get('mime_type', 'unknown')}]"

        messages.append({"role": role, "content": content})

    # 转换工具格式
    tools = None
    if request.tools:
        tools = []
        for tool in request.tools:
            if tool.function_declarations:
                for func_decl in tool.function_declarations:
                    tools.append({"type": "function", "function": func_decl})

    # 创建ChatCompletionRequest
    chat_request = ChatCompletionRequest(model=model, messages=messages, tools=tools)

    # 添加生成配置
    extra_params = {}
    if request.generation_config:
        config = request.generation_config
        if config.temperature is not None:
            extra_params["temperature"] = config.temperature
        if config.top_p is not None:
            extra_params["top_p"] = config.top_p
        if config.top_k is not None:
            extra_params["top_k"] = config.top_k
        if config.max_output_tokens is not None:
            extra_params["max_tokens"] = config.max_output_tokens
        if config.stop_sequences:
            extra_params["stop"] = config.stop_sequences
        if config.presence_penalty is not None:
            extra_params["presence_penalty"] = config.presence_penalty
        if config.frequency_penalty is not None:
            extra_params["frequency_penalty"] = config.frequency_penalty

    # 添加工具配置
    if request.tool_config:
        extra_params["tool_choice"] = request.tool_config.function_calling_config

    # 添加API密钥
    if api_key:
        extra_params["_gemini_api_key"] = api_key

    if extra_params:
        chat_request.extra_params = extra_params

    return chat_request


def convert_to_gemini_response(
    response: dict[str, Any], model: str, request: GeminiRequest
) -> dict[str, Any]:
    """将内部响应转换为Gemini格式"""

    # 处理响应，可能是JSONResponse或字典
    if hasattr(response, "body"):
        import json

        response_data = json.loads(response.body)
    else:
        response_data = response

    # 提取选择
    choices = response_data.get("choices", [])
    candidates = []

    for choice in choices:
        message = choice.get("message", {})
        content = message.get("content", "")

        # 创建内容
        gemini_content = {"parts": [{"text": content}], "role": "model"}

        # 创建候选
        candidate = {
            "index": choice.get("index", 0),
            "content": gemini_content,
            "finish_reason": choice.get("finish_reason", "STOP"),
            "safety_ratings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "probability": "NEGLIGIBLE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "probability": "NEGLIGIBLE"},
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "probability": "NEGLIGIBLE",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "probability": "NEGLIGIBLE",
                },
            ],
        }

        candidates.append(candidate)

    # 提取使用量
    usage = response_data.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

    # 构建响应
    gemini_response = {
        "candidates": candidates,
        "usage_metadata": {
            "prompt_token_count": prompt_tokens,
            "candidates_token_count": completion_tokens,
            "total_token_count": total_tokens,
        },
        "model_version": model,
    }

    return gemini_response


async def stream_gemini_response(
    chat_handler: ChatCompletionHandler, request: ChatCompletionRequest, model: str
):
    """流式生成Gemini格式响应"""

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
                except (json.JSONDecodeError, ValueError):
                    # 如果不是JSON，当作普通处理
                    continue
            else:
                # 如果是字典，处理流式响应
                if chunk.get("choices"):
                    for choice in chunk["choices"]:
                        message = choice.get("message", {})
                        content = message.get("content", "")

                        # 创建Gemini流式响应
                        stream_chunk = {
                            "candidates": [
                                {
                                    "index": choice.get("index", 0),
                                    "content": {
                                        "parts": [{"text": content}],
                                        "role": "model",
                                    },
                                    "finish_reason": choice.get(
                                        "finish_reason", "STOP"
                                    ),
                                }
                            ]
                        }

                        yield f"data: {json.dumps(stream_chunk)}\n\n"

    except Exception as e:
        logger.error(f"Stream error: {e}")
        error_chunk = {
            "error": {
                "code": 500,
                "message": "Stream processing error",
                "status": "FAILED",
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"


# --- 错误处理 ---


class GeminiAPIError(Exception):
    """Gemini API错误"""

    def __init__(self, error_type: str, message: str, status_code: int = 500):
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """转换为错误响应格式"""
        return {
            "error": {
                "code": self.status_code,
                "message": self.message,
                "status": "FAILED",
            }
        }
