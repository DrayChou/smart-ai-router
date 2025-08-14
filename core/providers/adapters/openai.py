"""
OpenAI Provider适配器
支持官方OpenAI API和兼容的API服务
"""

import json
from collections.abc import AsyncGenerator
from typing import Any, Dict, List

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


class OpenAIAdapter(BaseAdapter):
    """OpenAI适配器"""

    def __init__(self, provider_name: str, config: Dict[str, Any]):
        super().__init__(provider_name, config)

        # OpenAI特定配置
        self.organization = config.get("organization")

        # 模型映射和定价
        self.model_pricing = config.get("pricing_config", {}).get("models", {})
        self.default_input_cost = config.get("pricing_config", {}).get(
            "default_input_cost", 0.03
        )
        self.default_output_cost = config.get("pricing_config", {}).get(
            "default_output_cost", 0.06
        )

    def get_auth_headers(self, api_key: str) -> Dict[str, str]:
        """获取OpenAI认证头"""
        headers = {"Authorization": f"Bearer {api_key}"}
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        return headers

    async def chat_completions(
        self, request: ChatRequest, api_key: str, **kwargs
    ) -> ChatResponse:
        """OpenAI聊天完成"""
        url = f"{self.base_url}/v1/chat/completions"
        headers = {**self.default_headers, **self.get_auth_headers(api_key)}

        # 转换请求格式
        payload = self.transform_request(request)

        try:
            response = await self.client.post(
                url, headers=headers, json=payload, timeout=self.timeout
            )

            if not response.is_success:
                raise await self.handle_error(response)

            data = response.json()
            return self.transform_response(data)

        except httpx.HTTPError as e:
            logger.error(f"OpenAI API请求失败: {e}")
            raise ProviderError(f"网络请求失败: {e}")

    async def chat_completions_stream(
        self, request: ChatRequest, api_key: str, **kwargs
    ) -> AsyncGenerator[str, None]:
        """OpenAI流式聊天完成"""
        url = f"{self.base_url}/v1/chat/completions"
        headers = {**self.default_headers, **self.get_auth_headers(api_key)}

        # 转换请求格式，确保stream=True
        payload = self.transform_request(request)
        payload["stream"] = True

        try:
            async with self.client.stream(
                "POST", url, headers=headers, json=payload, timeout=self.timeout
            ) as response:

                if not response.is_success:
                    error = await response.aread()
                    raise await self.handle_error(response)

                async for chunk in response.aiter_lines():
                    if chunk.startswith("data: "):
                        data = chunk[6:]  # 移除"data: "前缀

                        if data == "[DONE]":
                            break

                        try:
                            chunk_data = json.loads(data)
                            delta = chunk_data.get("choices", [{}])[0].get("delta", {})

                            if "content" in delta:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue

        except httpx.HTTPError as e:
            logger.error(f"OpenAI流式API请求失败: {e}")
            raise ProviderError(f"流式网络请求失败: {e}")

    async def list_models(self, api_key: str) -> List[ModelInfo]:
        """获取OpenAI模型列表"""
        url = f"{self.base_url}/v1/models"
        headers = {**self.default_headers, **self.get_auth_headers(api_key)}

        try:
            response = await self.client.get(url, headers=headers)

            if not response.is_success:
                raise await self.handle_error(response)

            data = response.json()
            models = []

            for model_data in data.get("data", []):
                model_id = model_data.get("id", "")

                # 只处理chat模型
                if not self._is_chat_model(model_id):
                    continue

                # 获取定价信息
                pricing = self.model_pricing.get(model_id, {})
                input_cost = pricing.get("input", self.default_input_cost)
                output_cost = pricing.get("output", self.default_output_cost)

                # 推断模型能力
                capabilities = self._get_model_capabilities(model_id)

                model_info = ModelInfo(
                    id=model_id,
                    name=model_id,
                    provider=self.provider_name,
                    capabilities=capabilities,
                    context_length=self._get_context_length(model_id),
                    input_cost_per_1k=input_cost,
                    output_cost_per_1k=output_cost,
                    speed_score=self._get_speed_score(model_id),
                    quality_score=self._get_quality_score(model_id),
                )
                models.append(model_info)

            logger.info(f"获取到{len(models)}个OpenAI模型")
            return models

        except httpx.HTTPError as e:
            logger.error(f"获取OpenAI模型列表失败: {e}")
            raise ProviderError(f"获取模型列表失败: {e}")

    def transform_request(self, request: ChatRequest) -> Dict[str, Any]:
        """转换为OpenAI格式请求"""
        payload = {
            "model": request.model,
            "messages": self._process_messages(request),
            "stream": request.stream,
        }

        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = request.tools
        if request.tool_choice:
            payload["tool_choice"] = request.tool_choice

        # OpenAI不支持单独的system参数，需要转换为messages
        # 这在_process_messages中处理

        # 合并额外参数
        if request.extra_params:
            payload.update(request.extra_params)

        return payload

    def _process_messages(self, request: ChatRequest) -> List[Dict[str, Any]]:
        """处理消息格式，将system参数转换为system消息"""
        messages = request.messages.copy()

        # 如果有system参数且messages中没有system消息，添加到开头
        if request.system:
            has_system = any(msg.get("role") == "system" for msg in messages)
            if not has_system:
                messages.insert(0, {"role": "system", "content": request.system})

        return messages

    def _is_chat_model(self, model_id: str) -> bool:
        """判断是否是聊天模型"""
        chat_model_patterns = [
            "gpt-3.5",
            "gpt-4",
            "gpt-4o",
            "chatgpt",
            # 可以添加更多模式
        ]
        return any(pattern in model_id.lower() for pattern in chat_model_patterns)

    def _get_model_capabilities(self, model_id: str) -> List[str]:
        """根据模型ID推断能力"""
        capabilities = ["text"]

        model_lower = model_id.lower()

        # Function calling支持
        if any(pattern in model_lower for pattern in ["gpt-4", "gpt-3.5-turbo"]):
            capabilities.append("function_calling")

        # Vision支持
        if any(
            pattern in model_lower
            for pattern in ["gpt-4-vision", "gpt-4o", "gpt-4-turbo"]
        ):
            capabilities.append("vision")

        # JSON模式支持
        if any(pattern in model_lower for pattern in ["gpt-4", "gpt-3.5-turbo"]):
            capabilities.append("json_mode")

        # 代码生成能力
        if any(pattern in model_lower for pattern in ["gpt-4", "gpt-3.5"]):
            capabilities.append("code_generation")

        return capabilities

    def _get_context_length(self, model_id: str) -> int:
        """获取模型上下文长度"""
        context_lengths = {
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "gpt-4-turbo": 128000,
            "gpt-4": 8192,
            "gpt-3.5-turbo": 16385,
        }

        for pattern, length in context_lengths.items():
            if pattern in model_id.lower():
                return length

        return 4096  # 默认值

    def _get_speed_score(self, model_id: str) -> float:
        """获取模型速度评分"""
        speed_scores = {
            "gpt-4o-mini": 0.95,
            "gpt-3.5-turbo": 0.9,
            "gpt-4o": 0.8,
            "gpt-4-turbo": 0.75,
            "gpt-4": 0.6,
        }

        for pattern, score in speed_scores.items():
            if pattern in model_id.lower():
                return score

        return 0.7  # 默认值

    def _get_quality_score(self, model_id: str) -> float:
        """获取模型质量评分"""
        quality_scores = {
            "gpt-4o": 0.95,
            "gpt-4-turbo": 0.9,
            "gpt-4": 0.85,
            "gpt-4o-mini": 0.8,
            "gpt-3.5-turbo": 0.75,
        }

        for pattern, score in quality_scores.items():
            if pattern in model_id.lower():
                return score

        return 0.8  # 默认值
