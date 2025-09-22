# -*- coding: utf-8 -*-
"""
OpenRouter API适配器 - 支持价格优先排序和OpenRouter特有功能
"""

import logging
from typing import Dict, Any, List, Optional
import httpx

from .openai import OpenAIAdapter
from ..base import ProviderError
from ...config_models import Channel
from ...models.chat_request import ChatRequest

logger = logging.getLogger(__name__)


class OpenRouterAdapter(OpenAIAdapter):
    """
    OpenRouter API适配器
    继承OpenAI适配器，但添加OpenRouter特有的功能：
    - 价格优先排序 (provider.sort = "price")
    - HTTP-Referer和X-Title头部支持
    - OpenRouter特定的模型路由选项
    """

    def __init__(self, provider_name: str, config: Dict[str, Any]):
        config = dict(config or {})
        base_url = config.get("base_url") or "https://openrouter.ai/api"
        config["base_url"] = base_url.rstrip('/')
        super().__init__(provider_name, config)

    @staticmethod
    def is_provider_match(provider: str, base_url: str = None) -> bool:
        """判断是否匹配OpenRouter服务商"""
        provider_lower = provider.lower() if provider else ""
        base = base_url.lower() if base_url else ""
        return "openrouter" in provider_lower or "openrouter.ai" in base

    def transform_request(self, request: ChatRequest) -> Dict[str, Any]:
        """转换为OpenRouter格式请求，添加价格优先排序支持"""
        # 先获取基础OpenAI格式
        payload = super().transform_request(request)

        # 添加OpenRouter特有的extra_body参数
        extra_body = {}

        # 🔥 核心功能：价格优先排序
        # 当用户的路由策略包含成本优化时，自动启用价格排序
        routing_strategy = getattr(request, "routing_strategy", "balanced")
        if (
            routing_strategy in ["cost_first", "free_first"]
            or "cost" in routing_strategy.lower()
        ):
            extra_body["provider"] = {"sort": "price"}
            logger.info(
                f"🎯 OPENROUTER: Enabled price-priority sorting for cost-optimized routing ({routing_strategy})"
            )

        # 支持用户手动指定排序方式
        if hasattr(request, "extra_params") and request.extra_params:
            if "openrouter_sort" in request.extra_params:
                sort_method = request.extra_params.pop("openrouter_sort")
                extra_body["provider"] = {"sort": sort_method}
                logger.info(
                    f"🎯 OPENROUTER: Manual sort method specified: {sort_method}"
                )

            # 支持其他OpenRouter特定参数
            if "openrouter_transforms" in request.extra_params:
                extra_body["transforms"] = request.extra_params.pop(
                    "openrouter_transforms"
                )

            if "openrouter_route" in request.extra_params:
                extra_body["route"] = request.extra_params.pop("openrouter_route")

        # 如果有extra_body内容，作为独立字段添加到请求中
        # OpenRouter API期望的格式：{"model": "...", "messages": [...], "provider": {...}}  
        # 但这些额外参数不是标准OpenAI字段，需要通过某种方式传递
        if extra_body:
            # 直接将extra_body的内容合并到payload的根级别
            # 这样 {"provider": {"sort": "price"}} 就直接在请求的根级别
            payload.update(extra_body)
            logger.debug(f"🔧 OPENROUTER: Added OpenRouter-specific params: {list(extra_body.keys())}")

        return payload

    def get_request_headers(
        self, channel: Channel, request: ChatRequest
    ) -> Dict[str, str]:
        """获取OpenRouter特有的请求头"""
        headers = super().get_request_headers(channel, request)

        # 添加OpenRouter推荐的头部，用于在openrouter.ai上的排名
        # 这些头部是可选的，但有助于在OpenRouter平台上获得更好的排名
        headers.update(
            {
                "HTTP-Referer": self._get_site_url(request),
                "X-Title": self._get_site_title(request),
            }
        )

        return headers

    def _get_site_url(self, request: ChatRequest) -> str:
        """获取站点URL，用于OpenRouter排名"""
        # 优先使用请求中指定的URL
        if hasattr(request, "extra_params") and request.extra_params:
            if "site_url" in request.extra_params:
                return request.extra_params["site_url"]

        # 默认使用Smart AI Router的标识
        return "https://github.com/smart-ai-router/smart-ai-router"

    def _get_site_title(self, request: ChatRequest) -> str:
        """获取站点标题，用于OpenRouter排名"""
        # 优先使用请求中指定的标题
        if hasattr(request, "extra_params") and request.extra_params:
            if "site_title" in request.extra_params:
                return request.extra_params["site_title"]

        # 默认使用Smart AI Router的标识
        return "Smart AI Router - Personal AI Gateway"

    async def get_models(self, base_url: str, api_key: str) -> List[Dict[str, Any]]:
        """
        获取OpenRouter模型列表
        OpenRouter返回更详细的模型信息，包括定价和能力
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base_url}/models",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "HTTP-Referer": "https://github.com/smart-ai-router/smart-ai-router",
                        "X-Title": "Smart AI Router",
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            models = []
            for model_data in data.get("data", []):
                model_id = model_data.get("id", "")

                # 过滤掉非聊天模型
                if not self._is_openrouter_chat_model(model_data):
                    continue

                # 提取定价信息（OpenRouter特有）
                pricing = model_data.get("pricing", {})
                input_cost = (
                    float(pricing.get("prompt", "0")) * 1000
                )  # 转换为per-1k-tokens
                output_cost = float(pricing.get("completion", "0")) * 1000

                # 提取上下文长度
                context_length = model_data.get("context_length", 0)

                # 提取能力信息
                capabilities = self._get_openrouter_model_capabilities(model_data)

                model_info = {
                    "id": model_id,
                    "name": model_data.get("name", model_id),
                    "capabilities": capabilities,
                    "context_length": context_length,
                    "input_cost_per_1k": input_cost,
                    "output_cost_per_1k": output_cost,
                    "speed_score": self._get_openrouter_speed_score(model_data),
                    "quality_score": self._get_openrouter_quality_score(model_data),
                    # OpenRouter特有字段
                    "provider": model_data.get("provider", ""),
                    "modality": model_data.get("modality", ""),
                    "input_modalities": model_data.get("input_modalities", []),
                    "output_modalities": model_data.get("output_modalities", []),
                }
                models.append(model_info)

            logger.info(f"获取到{len(models)}个OpenRouter模型")
            return models

        except httpx.HTTPError as e:
            logger.error(f"获取OpenRouter模型列表失败: {e}")
            raise ProviderError(f"获取模型列表失败: {e}")

    def _is_openrouter_chat_model(self, model_data: Dict[str, Any]) -> bool:
        """判断是否是OpenRouter聊天模型"""
        model_id = model_data.get("id", "").lower()

        # 排除明确的非聊天模型
        exclude_patterns = [
            "embedding",
            "whisper",
            "dall-e",
            "tts",
            "stt",
            "image-generation",
        ]

        if any(pattern in model_id for pattern in exclude_patterns):
            return False

        # 检查模态信息
        modality = model_data.get("modality", "")
        if modality and "text" not in modality:
            return False

        return True

    def _get_openrouter_model_capabilities(
        self, model_data: Dict[str, Any]
    ) -> List[str]:
        """从OpenRouter模型数据提取能力信息"""
        capabilities = ["text"]

        model_id = model_data.get("id", "").lower()
        input_modalities = model_data.get("input_modalities", [])
        supported_parameters = model_data.get("supported_parameters", [])

        # Vision能力
        if "image" in input_modalities:
            capabilities.append("vision")

        # Function calling能力
        if any(param in supported_parameters for param in ["tools", "tool_choice"]):
            capabilities.append("function_calling")

        # JSON模式支持
        if "response_format" in supported_parameters:
            capabilities.append("json_mode")

        # 基于模型名称的能力推断
        if any(pattern in model_id for pattern in ["gpt-4", "claude-3", "gemini-pro"]):
            if "function_calling" not in capabilities:
                capabilities.append("function_calling")
            if "code_generation" not in capabilities:
                capabilities.append("code_generation")

        return capabilities

    def _get_openrouter_speed_score(self, model_data: Dict[str, Any]) -> float:
        """根据OpenRouter模型数据计算速度评分"""
        # OpenRouter没有直接的速度指标，根据模型类型和大小推断
        model_id = model_data.get("id", "").lower()

        # 小模型通常更快
        if any(
            pattern in model_id for pattern in ["mini", "turbo", "fast", "7b", "8b"]
        ):
            return 0.9
        elif any(pattern in model_id for pattern in ["13b", "14b", "20b", "medium"]):
            return 0.7
        elif any(pattern in model_id for pattern in ["30b", "70b", "large", "max"]):
            return 0.5
        else:
            return 0.6

    def _get_openrouter_quality_score(self, model_data: Dict[str, Any]) -> float:
        """根据OpenRouter模型数据计算质量评分"""
        model_id = model_data.get("id", "").lower()

        # 根据模型系列和版本推断质量
        if any(
            pattern in model_id
            for pattern in ["gpt-4o", "claude-3.5-sonnet", "gemini-pro"]
        ):
            return 0.95
        elif any(pattern in model_id for pattern in ["gpt-4", "claude-3", "gemini"]):
            return 0.9
        elif any(pattern in model_id for pattern in ["gpt-3.5", "llama-3", "mixtral"]):
            return 0.8
        elif "70b" in model_id or "large" in model_id:
            return 0.85
        elif "30b" in model_id or "medium" in model_id:
            return 0.75
        else:
            return 0.7

    def get_error_type(self, status_code: int, error_message: str) -> str:
        """获取OpenRouter特定的错误类型"""
        # OpenRouter特有的错误处理
        if "rate limit" in error_message.lower():
            # OpenRouter免费用户有特殊的速率限制
            if "free tier" in error_message.lower():
                return "free_tier_limit"
            return "rate_limit"

        if "insufficient credits" in error_message.lower():
            return "insufficient_credits"

        if (
            "model not found" in error_message.lower()
            or "no provider available" in error_message.lower()
        ):
            return "model_unavailable"

        # 回退到父类处理
        return super().get_error_type(status_code, error_message)
