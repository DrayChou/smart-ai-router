"""
Provider基础适配器
所有Provider适配器的基类，定义标准接口
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ChatRequest:
    """标准化的聊天请求"""

    model: str
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    system: Optional[str] = None
    extra_params: Optional[Dict[str, Any]] = None


@dataclass
class ChatResponse:
    """标准化的聊天响应"""

    content: str
    finish_reason: str
    usage: Dict[str, int]
    model: str
    provider_response: Optional[Dict[str, Any]] = None
    tools_called: Optional[List[Dict[str, Any]]] = None


@dataclass
class ModelInfo:
    """模型信息"""

    id: str
    name: str
    provider: str
    capabilities: List[str]  # ["text", "vision", "function_calling", "code_generation"]
    context_length: int
    input_cost_per_1k: float
    output_cost_per_1k: float
    speed_score: float = 1.0  # 相对速度评分 0.0-1.0
    quality_score: float = 1.0  # 质量评分 0.0-1.0


class BaseAdapter(ABC):
    """Provider适配器基类"""

    def __init__(self, provider_name: str, config: Dict[str, Any]):
        """
        初始化适配器

        Args:
            provider_name: Provider名称
            config: Provider配置
        """
        self.provider_name = provider_name
        self.config = config
        self.base_url = config.get("base_url", "")
        self.default_headers = config.get("default_headers", {})
        self.timeout = config.get("timeout", 30)
        self.max_retries = config.get("max_retries", 3)

        # HTTP客户端
        self._client = None

        logger.info(f"初始化{provider_name}适配器")

    @property
    def client(self) -> httpx.AsyncClient:
        """获取HTTP客户端（懒加载）"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.default_headers,
                timeout=self.timeout,
            )
        return self._client

    async def close(self):
        """关闭HTTP客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None

    @abstractmethod
    async def chat_completions(
        self, request: ChatRequest, api_key: str, **kwargs
    ) -> ChatResponse:
        """
        聊天完成接口

        Args:
            request: 标准化聊天请求
            api_key: API密钥
            **kwargs: 额外参数

        Returns:
            标准化聊天响应
        """
        pass

    @abstractmethod
    async def chat_completions_stream(
        self, request: ChatRequest, api_key: str, **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天完成接口

        Args:
            request: 标准化聊天请求
            api_key: API密钥
            **kwargs: 额外参数

        Yields:
            流式响应数据
        """
        pass

    @abstractmethod
    async def list_models(self, api_key: str) -> List[ModelInfo]:
        """
        获取可用模型列表

        Args:
            api_key: API密钥

        Returns:
            模型信息列表
        """
        pass

    async def check_api_key(self, api_key: str) -> bool:
        """
        检查API密钥有效性

        Args:
            api_key: API密钥

        Returns:
            是否有效
        """
        try:
            models = await self.list_models(api_key)
            return len(models) > 0
        except Exception as e:
            logger.warning(f"API密钥检查失败: {e}")
            return False

    def transform_request(self, request: ChatRequest) -> Dict[str, Any]:
        """
        将标准请求转换为Provider特定格式

        Args:
            request: 标准化请求

        Returns:
            Provider特定格式的请求
        """
        # 默认实现，子类可以覆盖
        payload = {
            "model": request.model,
            "messages": request.messages,
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
        if request.system:
            # 一些Provider支持system参数，一些需要转换为messages
            payload["system"] = request.system

        # 合并额外参数
        if request.extra_params:
            payload.update(request.extra_params)

        return payload

    def transform_response(self, provider_response: Dict[str, Any]) -> ChatResponse:
        """
        将Provider响应转换为标准格式

        Args:
            provider_response: Provider原始响应

        Returns:
            标准化响应
        """
        # 默认OpenAI兼容格式实现
        choice = provider_response.get("choices", [{}])[0]
        message = choice.get("message", {})

        return ChatResponse(
            content=message.get("content", ""),
            finish_reason=choice.get("finish_reason", "unknown"),
            usage=provider_response.get("usage", {}),
            model=provider_response.get("model", ""),
            provider_response=provider_response,
            tools_called=message.get("tool_calls"),
        )

    def get_auth_headers(self, api_key: str) -> Dict[str, str]:
        """
        获取认证头

        Args:
            api_key: API密钥

        Returns:
            认证头字典
        """
        auth_type = self.config.get("auth_type", "bearer")

        if auth_type == "bearer":
            return {"Authorization": f"Bearer {api_key}"}
        elif auth_type == "x-api-key":
            return {"x-api-key": api_key}
        elif auth_type == "api-key":
            return {"api-key": api_key}
        else:
            logger.warning(f"未知的认证类型: {auth_type}")
            return {"Authorization": f"Bearer {api_key}"}

    async def handle_error(self, response: httpx.Response) -> Exception:
        """
        处理HTTP错误响应

        Args:
            response: HTTP响应

        Returns:
            对应的异常
        """
        try:
            error_data = response.json()
            error_msg = error_data.get("error", {}).get("message", str(error_data))
        except:
            error_msg = response.text

        if response.status_code == 401:
            return ProviderAuthError(f"认证失败: {error_msg}")
        elif response.status_code == 429:
            return ProviderRateLimitError(f"速率限制: {error_msg}")
        elif response.status_code == 400:
            return ProviderRequestError(f"请求错误: {error_msg}")
        elif response.status_code >= 500:
            return ProviderServerError(f"服务器错误: {error_msg}")
        else:
            return ProviderError(f"未知错误 ({response.status_code}): {error_msg}")

    def calculate_cost(self, usage: Dict[str, int], model_info: ModelInfo) -> float:
        """
        计算请求成本

        Args:
            usage: token使用量
            model_info: 模型信息

        Returns:
            成本（美元）
        """
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        input_cost = (input_tokens / 1000) * model_info.input_cost_per_1k
        output_cost = (output_tokens / 1000) * model_info.output_cost_per_1k

        return input_cost + output_cost


# 自定义异常类
class ProviderError(Exception):
    """Provider基础异常"""

    pass


class ProviderAuthError(ProviderError):
    """认证错误"""

    pass


class ProviderRateLimitError(ProviderError):
    """速率限制错误"""

    pass


class ProviderRequestError(ProviderError):
    """请求错误"""

    pass


class ProviderServerError(ProviderError):
    """服务器错误"""

    pass
