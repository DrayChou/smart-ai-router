"""
Provider适配器模块
提供统一的AI服务提供商接口
"""

from .adapters.anthropic import AnthropicAdapter
from .adapters.groq import GroqAdapter
from .adapters.openai import OpenAIAdapter
from .base import (
    BaseAdapter,
    ChatRequest,
    ChatResponse,
    ModelInfo,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderServerError,
)
from .registry import (
    ProviderRegistry,
    create_adapter_from_config,
    get_provider_registry,
    provider_registry,
    register_adapter,
)

__all__ = [
    # 基础类
    "BaseAdapter",
    "ChatRequest",
    "ChatResponse",
    "ModelInfo",
    # 异常类
    "ProviderError",
    "ProviderAuthError",
    "ProviderRateLimitError",
    "ProviderRequestError",
    "ProviderServerError",
    # 注册中心
    "ProviderRegistry",
    "get_provider_registry",
    "register_adapter",
    "create_adapter_from_config",
    "provider_registry",
    # 具体适配器
    "OpenAIAdapter",
    "AnthropicAdapter",
    "GroqAdapter",
]
