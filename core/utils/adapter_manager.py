"""
适配器管理器 - 动态选择和使用正确的Provider适配器
"""

import logging
from typing import Any, Optional

from ..config_models import Channel
from ..models.chat_request import ChatRequest
from ..providers.adapters.anthropic import AnthropicAdapter
from ..providers.adapters.groq import GroqAdapter
from ..providers.adapters.openai import OpenAIAdapter
from ..providers.adapters.openrouter import OpenRouterAdapter
from ..providers.base import BaseAdapter

logger = logging.getLogger(__name__)


class AdapterManager:
    """适配器管理器 - 智能选择和使用合适的Provider适配器"""

    def __init__(self):
        self._adapter_registry: dict[str, type[BaseAdapter]] = {}
        self._adapter_cache: dict[tuple[str, str, str], BaseAdapter] = {}
        self._register_adapters()

    def _register_adapters(self):
        """注册所有可用的适配器 (按名称映射到类)."""
        registry: dict[str, type[BaseAdapter]] = {
            "openrouter": OpenRouterAdapter,
            "anthropic": AnthropicAdapter,
            "groq": GroqAdapter,
            "openai": OpenAIAdapter,
        }
        # 兼容通过完整类名查找的配置
        registry.update(
            {
                "openrouteradapter": OpenRouterAdapter,
                "anthropicadapter": AnthropicAdapter,
                "groqadapter": GroqAdapter,
                "openaiadapter": OpenAIAdapter,
            }
        )
        self._adapter_registry = registry
        unique = {name for name in registry.keys() if not name.endswith("adapter")}
        logger.info("注册了 %d 个适配器", len(unique))

    def _select_adapter_class(
        self, channel: Channel, provider: Any
    ) -> type[BaseAdapter]:
        provider_name = getattr(provider, "name", channel.provider).lower()
        base_url = (channel.base_url or getattr(provider, "base_url", "") or "").lower()
        adapter_name = getattr(provider, "adapter_class", None)

        if isinstance(adapter_name, str):
            lookup = adapter_name.lower()
            if lookup in self._adapter_registry:
                return self._adapter_registry[lookup]

        if "openrouter" in provider_name or "openrouter" in base_url:
            return self._adapter_registry["openrouter"]
        if "anthropic" in provider_name or "anthropic" in base_url:
            return self._adapter_registry["anthropic"]
        if "groq" in provider_name or "groq" in base_url:
            return self._adapter_registry["groq"]

        return self._adapter_registry["openai"]

    def _build_adapter_config(self, channel: Channel, provider: Any) -> dict[str, Any]:
        config: dict[str, Any]
        if hasattr(provider, "dict"):
            config = provider.dict()  # type: ignore[assignment]
        else:
            config = {}

        base_url = (
            channel.base_url
            or config.get("base_url")
            or getattr(provider, "base_url", "")
        )
        if base_url:
            config["base_url"] = base_url
        config.setdefault("default_headers", {})
        return config

    def _get_adapter_instance(
        self, adapter_cls: type[BaseAdapter], channel: Channel, provider: Any
    ) -> BaseAdapter:
        base_url = channel.base_url or getattr(provider, "base_url", "") or ""
        cache_key = (
            adapter_cls.__name__,
            getattr(provider, "name", channel.provider),
            base_url,
        )
        adapter = self._adapter_cache.get(cache_key)
        if adapter is None:
            config = self._build_adapter_config(channel, provider)
            adapter = adapter_cls(getattr(provider, "name", channel.provider), config)
            self._adapter_cache[cache_key] = adapter
        return adapter

    def prepare_request_with_adapter(
        self,
        channel: Channel,
        provider: Any,
        request: ChatRequest,
        matched_model: Optional[str] = None,
    ) -> dict[str, Any]:
        """使用适配器准备请求"""
        adapter_cls = self._select_adapter_class(channel, provider)
        adapter = self._get_adapter_instance(adapter_cls, channel, provider)

        # 构建ChatRequest对象（如果还不是）
        if not isinstance(request, ChatRequest):
            # 从字典构建ChatRequest
            request_dict = request if isinstance(request, dict) else request.dict()
            request = ChatRequest(**request_dict)

        # 设置匹配的模型
        if matched_model:
            request.model = matched_model

        # 使用适配器转换请求
        try:
            request_data = adapter.transform_request(request)
            headers = adapter.get_request_headers(channel, request)

            # 构建完整的URL
            base_url = (channel.base_url or getattr(provider, "base_url", "")).rstrip(
                "/"
            )
            if not base_url.endswith("/v1"):
                base_url += "/v1"
            url = f"{base_url}/chat/completions"

            logger.debug(
                f"📡 使用适配器 {adapter.__class__.__name__} 准备请求: {request.model}"
            )

            return {
                "url": url,
                "headers": headers,
                "request_data": request_data,
                "adapter": adapter,
            }

        except Exception as e:
            logger.error(f"[FAIL] 适配器准备请求失败: {e}")
            # 回退到基础准备方式
            return self._prepare_fallback_request(
                channel, provider, request, matched_model
            )

    def _prepare_fallback_request(
        self,
        channel: Channel,
        provider: Any,
        request: ChatRequest,
        matched_model: Optional[str] = None,
    ) -> dict[str, Any]:
        """回退的请求准备方式（兼容原有逻辑）"""
        base_url = (channel.base_url or getattr(provider, "base_url", "")).rstrip("/")
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        url = f"{base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "smart-ai-router/0.2.0",
        }
        auth_type = getattr(provider, "auth_type", "bearer")
        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {channel.api_key}"
        elif auth_type == "x-api-key":
            headers["x-api-key"] = channel.api_key

        request_data = (
            request.dict(exclude_unset=True) if hasattr(request, "dict") else request
        )
        if matched_model:
            request_data["model"] = matched_model

        return {
            "url": url,
            "headers": headers,
            "request_data": request_data,
            "adapter": None,
        }

    def enhance_request_for_cost_optimization(
        self,
        request_data: dict[str, Any],
        adapter: BaseAdapter,
        routing_strategy: str = "balanced",
    ) -> dict[str, Any]:
        """为成本优化增强请求（特别是OpenRouter）"""
        if not isinstance(adapter, OpenRouterAdapter):
            return request_data

        # [HOT] 核心功能：为成本优化策略自动启用价格排序
        if (
            routing_strategy in ["cost_first", "free_first"]
            or "cost" in routing_strategy.lower()
        ):
            if "extra_body" not in request_data:
                request_data["extra_body"] = {}

            request_data["extra_body"]["provider"] = {"sort": "price"}
            logger.info(
                f"[TARGET] COST OPTIMIZATION: 为 {routing_strategy} 策略启用OpenRouter价格排序"
            )

        return request_data


# 全局适配器管理器实例
_global_adapter_manager: Optional[AdapterManager] = None


def get_adapter_manager() -> AdapterManager:
    """获取全局适配器管理器实例"""
    global _global_adapter_manager
    if _global_adapter_manager is None:
        _global_adapter_manager = AdapterManager()
    return _global_adapter_manager
