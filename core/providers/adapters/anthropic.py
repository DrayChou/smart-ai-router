"""
Anthropic Provider适配器
支持Claude系列模型
"""

import json
from collections.abc import AsyncGenerator
from typing import Any, Optional

import httpx

from core.utils.logger import get_logger

from ..base import (
    BaseAdapter,
    ChatRequest,
    ChatResponse,
    ModelInfo,
    ProviderError,
)

logger = get_logger(__name__)


class AnthropicAdapter(BaseAdapter):
    """Anthropic适配器"""

    def __init__(self, provider_name: str, config: dict[str, Any]):
        super().__init__(provider_name, config)

        # Anthropic API版本
        self.api_version = config.get("api_version", "2023-06-01")

        # 模型定价配置
        self.model_pricing = config.get("pricing_config", {}).get("models", {})
        self.default_input_cost = config.get("pricing_config", {}).get(
            "default_input_cost", 0.015
        )
        self.default_output_cost = config.get("pricing_config", {}).get(
            "default_output_cost", 0.075
        )

    def get_auth_headers(self, api_key: str) -> dict[str, str]:
        """获取Anthropic认证头"""
        return {
            "x-api-key": api_key,
            "anthropic-version": self.api_version,
            "content-type": "application/json",
        }

    async def chat_completions(
        self, request: ChatRequest, api_key: str, **kwargs
    ) -> ChatResponse:
        """Anthropic消息完成"""
        url = f"{self.base_url}/v1/messages"
        headers = {**self.default_headers, **self.get_auth_headers(api_key)}

        # 转换请求格式
        payload = self.transform_request(request)

        # 记录请求信息
        logger.info(
            f"Anthropic API请求 - 模型: {request.model}, 消息数: {len(request.messages)}"
        )

        try:
            response = await self.client.post(
                url, headers=headers, json=payload, timeout=self.timeout
            )

            if not response.is_success:
                logger.error(
                    f"Anthropic API错误响应: {response.status_code} - {response.text}"
                )
                raise await self.handle_error(response)

            data = response.json()
            logger.info(
                f"Anthropic API成功响应 - 模型: {data.get('model')}, 消耗token: {data.get('usage', {}).get('total_tokens', 0)}"
            )
            return self.transform_response(data)

        except httpx.HTTPError as e:
            logger.error(f"Anthropic API网络请求失败: {e}")
            raise ProviderError(f"网络请求失败: {e}") from e
        except Exception as e:
            logger.error(f"Anthropic API未知错误: {e}")
            raise ProviderError(f"请求失败: {e}") from e

    async def chat_completions_stream(
        self, request: ChatRequest, api_key: str, **kwargs
    ) -> AsyncGenerator[str, None]:
        """Anthropic流式消息完成"""
        url = f"{self.base_url}/v1/messages"
        headers = {**self.default_headers, **self.get_auth_headers(api_key)}

        # 转换请求格式，确保stream=True
        payload = self.transform_request(request)
        payload["stream"] = True

        logger.info(f"Anthropic流式API请求 - 模型: {request.model}")

        try:
            async with self.client.stream(
                "POST", url, headers=headers, json=payload, timeout=self.timeout
            ) as response:

                if not response.is_success:
                    logger.error(
                        f"Anthropic流式API错误响应: {response.status_code} - {response.text}"
                    )
                    raise await self.handle_error(response)

                async for chunk in response.aiter_lines():
                    if chunk.startswith("data: "):
                        data = chunk[6:]  # 移除"data: "前缀

                        try:
                            chunk_data = json.loads(data)

                            # Anthropic流式响应格式
                            if chunk_data.get("type") == "content_block_delta":
                                delta = chunk_data.get("delta", {})
                                if "text" in delta:
                                    yield delta["text"]
                            elif chunk_data.get("type") == "message_stop":
                                logger.info("Anthropic流式响应完成")

                        except json.JSONDecodeError:
                            continue

        except httpx.HTTPError as e:
            logger.error(f"Anthropic流式API网络请求失败: {e}")
            raise ProviderError(f"流式网络请求失败: {e}") from e
        except Exception as e:
            logger.error(f"Anthropic流式API未知错误: {e}")
            raise ProviderError(f"流式请求失败: {e}") from e

    async def list_models(self, api_key: str) -> list[ModelInfo]:
        """获取Anthropic模型列表"""
        # Anthropic不提供模型列表API，返回预定义模型
        models = [
            ModelInfo(
                id="claude-3-5-sonnet-20241022",
                name="Claude 3.5 Sonnet",
                provider=self.provider_name,
                capabilities=["text", "vision", "function_calling", "code_generation"],
                context_length=200000,
                input_cost_per_1k=0.003,
                output_cost_per_1k=0.015,
                speed_score=0.85,
                quality_score=0.95,
            ),
            ModelInfo(
                id="claude-3-5-haiku-20241022",
                name="Claude 3.5 Haiku",
                provider=self.provider_name,
                capabilities=["text", "function_calling"],
                context_length=200000,
                input_cost_per_1k=0.001,
                output_cost_per_1k=0.005,
                speed_score=0.95,
                quality_score=0.8,
            ),
            ModelInfo(
                id="claude-3-opus-20240229",
                name="Claude 3 Opus",
                provider=self.provider_name,
                capabilities=["text", "vision", "function_calling", "code_generation"],
                context_length=200000,
                input_cost_per_1k=0.015,
                output_cost_per_1k=0.075,
                speed_score=0.7,
                quality_score=0.98,
            ),
            # 添加Claude 3 Haiku (旧版本)
            ModelInfo(
                id="claude-3-haiku-20240307",
                name="Claude 3 Haiku",
                provider=self.provider_name,
                capabilities=["text", "vision", "function_calling"],
                context_length=200000,
                input_cost_per_1k=0.00025,
                output_cost_per_1k=0.00125,
                speed_score=0.9,
                quality_score=0.75,
            ),
        ]

        # 应用配置中的定价覆盖
        for model in models:
            if model.id in self.model_pricing:
                pricing = self.model_pricing[model.id]
                model.input_cost_per_1k = pricing.get("input", model.input_cost_per_1k)
                model.output_cost_per_1k = pricing.get(
                    "output", model.output_cost_per_1k
                )

        logger.info(f"返回{len(models)}个Anthropic模型")
        return models

    def transform_request(self, request: ChatRequest) -> dict[str, Any]:
        """转换为Anthropic格式请求"""
        # Anthropic使用不同的API格式
        messages = self._process_messages(request)
        system_message = self._extract_system_message(request)

        payload = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,  # Anthropic要求max_tokens
        }

        if system_message:
            payload["system"] = system_message

        if request.temperature is not None:
            payload["temperature"] = request.temperature

        if request.stream:
            payload["stream"] = True

        # Anthropic的工具调用格式不同
        if request.tools:
            payload["tools"] = self._convert_tools(request.tools)

        if request.extra_params:
            payload.update(request.extra_params)

        return payload

    def transform_response(self, provider_response: dict[str, Any]) -> ChatResponse:
        """转换Anthropic响应为标准格式"""
        content_blocks = provider_response.get("content", [])

        # 提取文本内容
        text_content = ""
        tool_calls = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    }
                )

        return ChatResponse(
            content=text_content,
            finish_reason=provider_response.get("stop_reason", "unknown"),
            usage=provider_response.get("usage", {}),
            model=provider_response.get("model", ""),
            provider_response=provider_response,
            tools_called=tool_calls if tool_calls else None,
        )

    def _process_messages(self, request: ChatRequest) -> list[dict[str, Any]]:
        """处理消息格式，移除system消息"""
        messages = []

        for msg in request.messages:
            if msg.get("role") != "system":  # Anthropic的system消息单独处理
                # 确保消息内容格式正确
                content = msg.get("content")
                if isinstance(content, str):
                    messages.append({"role": msg["role"], "content": content})
                else:
                    # 处理复杂内容（如图片）
                    messages.append(msg)

        return messages

    def _extract_system_message(self, request: ChatRequest) -> Optional[str]:
        """提取系统消息"""
        # 优先使用request.system
        if request.system:
            return request.system

        # 从messages中查找system消息
        for msg in request.messages:
            if msg.get("role") == "system":
                return msg.get("content", "")

        return None

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """转换工具格式为Anthropic格式"""
        converted_tools = []

        for tool in tools:
            if tool.get("type") == "function":
                function = tool.get("function", {})
                converted_tools.append(
                    {
                        "name": function.get("name"),
                        "description": function.get("description"),
                        "input_schema": function.get("parameters", {}),
                    }
                )

        return converted_tools
