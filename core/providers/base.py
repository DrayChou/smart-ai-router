"""
Provider基础适配器
所有Provider适配器的基类，定义标准接口
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

import httpx

from core.utils.logger import get_logger

if TYPE_CHECKING:
    from core.config_models import Channel

logger = get_logger(__name__)


@dataclass
class ChatRequest:
    """标准化的聊天请求"""

    model: str
    messages: list[dict[str, Any]]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    tools: Optional[list[dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    system: Optional[str] = None
    extra_params: Optional[dict[str, Any]] = None


@dataclass
class ChatResponse:
    """标准化的聊天响应"""

    content: str
    finish_reason: str
    usage: dict[str, int]
    model: str
    provider_response: Optional[dict[str, Any]] = None
    tools_called: Optional[list[dict[str, Any]]] = None


@dataclass
class ModelInfo:
    """模型信息"""

    id: str
    name: str
    provider: str
    capabilities: list[str]  # ["text", "vision", "function_calling", "code_generation"]
    context_length: int
    input_cost_per_1k: float
    output_cost_per_1k: float
    speed_score: float = 1.0  # 相对速度评分 0.0-1.0
    quality_score: float = 1.0  # 质量评分 0.0-1.0


class BaseAdapter(ABC):
    """Provider适配器基类"""

    def __init__(self, provider_name: str, config: dict[str, Any]):
        """
        初始化适配器

        Args:
            provider_name: Provider名称
            config: Provider配置
        """
        self.provider_name = provider_name
        self.config = config

        # 支持多个 base_url，自动选择可用的
        self.base_url = self._select_available_base_url(config)
        self.default_headers = config.get("default_headers", {})
        self.timeout = config.get("timeout", 30)
        self.max_retries = config.get("max_retries", 3)

        # HTTP客户端
        self._client = None

        logger.info(f"初始化{provider_name}适配器，使用 base_url: {self.base_url}")

    def _select_available_base_url(self, config: dict[str, Any]) -> str:
        """
        选择可用的 base_url

        支持配置格式：
        1. base_url: "http://host.docker.internal:11435"  # 单个URL
        2. base_url: ["http://host.docker.internal:11435", "http://localhost:11435"]  # 多个URL
        3. fallback_urls: ["http://localhost:11435"]  # 额外的fallback URLs

        Args:
            config: Provider配置

        Returns:
            第一个可用的 base_url
        """

        # 获取所有候选 URLs
        candidate_urls = []

        # 主要 base_url
        base_url = config.get("base_url", "")
        if isinstance(base_url, list):
            candidate_urls.extend(base_url)
        elif base_url:
            candidate_urls.append(base_url)

        # fallback URLs
        fallback_urls = config.get("fallback_urls", [])
        if isinstance(fallback_urls, list):
            candidate_urls.extend(fallback_urls)
        elif fallback_urls:
            candidate_urls.append(fallback_urls)

        # 如果没有配置任何URL，返回空字符串
        if not candidate_urls:
            logger.warning(f"Provider {self.provider_name} 没有配置 base_url")
            return ""

        # 测试每个URL的连通性
        for url in candidate_urls:
            if self._test_url_connectivity(url):
                logger.info(f"Provider {self.provider_name} 选择可用 URL: {url}")
                return url

        # 如果都不可用，使用第一个并发出警告
        selected_url = candidate_urls[0]
        logger.warning(
            f"Provider {self.provider_name} 所有URL都不可达，使用第一个: {selected_url}"
        )
        return selected_url

    def _test_url_connectivity(self, url: str) -> bool:
        """
        测试URL连通性

        Args:
            url: 要测试的URL

        Returns:
            是否可连通
        """
        import socket
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            host = parsed.hostname
            port = parsed.port

            if not host:
                return False

            # 默认端口
            if not port:
                port = 443 if parsed.scheme == "https" else 80

            # 处理特殊主机名
            if host == "host.docker.internal":
                # 在非Docker环境下，host.docker.internal不可用
                # 检查是否在Docker容器中运行
                if not self._is_running_in_docker():
                    logger.debug(f"非Docker环境，跳过 {url}")
                    return False

            # Socket连通性测试
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)  # 2秒超时

            try:
                result = sock.connect_ex((host, port))
                return result == 0
            finally:
                sock.close()

        except Exception as e:
            logger.debug(f"URL连通性测试失败 {url}: {e}")
            return False

    def _is_running_in_docker(self) -> bool:
        """
        检查是否在Docker容器中运行

        Returns:
            是否在Docker中运行
        """
        try:
            # 检查 /.dockerenv 文件
            import os

            if os.path.exists("/.dockerenv"):
                return True

            # 检查 /proc/1/cgroup 中是否包含 docker
            if os.path.exists("/proc/1/cgroup"):
                with open("/proc/1/cgroup") as f:
                    return "docker" in f.read()

            return False
        except Exception:
            return False

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
    async def list_models(self, api_key: str) -> list[ModelInfo]:
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

    def transform_request(self, request: ChatRequest) -> dict[str, Any]:
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

    def transform_response(self, provider_response: dict[str, Any]) -> ChatResponse:
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

    def get_auth_headers(self, api_key: str) -> dict[str, str]:
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

    def get_request_headers(
        self, channel: "Channel", request: ChatRequest
    ) -> dict[str, str]:
        """
        获取完整的请求头（包含认证和标准头）

        Args:
            channel: 渠道信息（包含API密钥）
            request: 聊天请求

        Returns:
            完整的请求头字典
        """
        # 基础请求头
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "smart-ai-router/0.3.0",
        }

        # 添加默认头
        if self.default_headers:
            headers.update(self.default_headers)
            logger.debug(f"添加默认头: {len(self.default_headers)} 个")

        # 添加认证头
        api_key = getattr(channel, "api_key", "")
        if api_key:
            auth_headers = self.get_auth_headers(api_key)
            headers.update(auth_headers)
            logger.debug(f"添加认证头: {list(auth_headers.keys())}")
        else:
            logger.warning(f"渠道 {getattr(channel, 'id', 'unknown')} 缺少 API 密钥")

        return headers

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

    def calculate_cost(
        self,
        usage: dict[str, int],
        model_info: ModelInfo,
        currency_exchange: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        计算请求成本，支持货币转换

        Args:
            usage: token使用量
            model_info: 模型信息
            currency_exchange: 货币转换配置

        Returns:
            包含成本详情的字典
        """
        from core.utils.token_counter import TokenCounter

        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        # 构建定价字典
        pricing = {
            "input": model_info.input_cost_per_1k / 1000,  # 转换为每token成本
            "output": model_info.output_cost_per_1k / 1000,
        }

        # 使用TokenCounter进行成本计算，支持货币转换
        return TokenCounter.calculate_cost(
            input_tokens, output_tokens, pricing, currency_exchange
        )

    def calculate_cost_legacy(
        self, usage: dict[str, int], model_info: ModelInfo
    ) -> float:
        """
        传统成本计算方法（保持向后兼容）

        Args:
            usage: token使用量
            model_info: 模型信息

        Returns:
            成本（美元）
        """
        result = self.calculate_cost(usage, model_info)
        return result["actual_cost"]


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
