"""
本地模型能力检测系统
检测本地模型是否支持特定能力（vision、function_calling等），不支持时自动fallback到云端
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from core.utils.smart_cache import cache_get, cache_set

logger = logging.getLogger(__name__)


@dataclass
class ModelCapabilities:
    """模型能力数据结构"""

    model_name: str
    provider: str
    base_url: str
    supports_vision: bool = False
    supports_function_calling: bool = False
    supports_code_generation: bool = True  # 默认支持代码生成
    supports_streaming: bool = True  # 默认支持流式
    max_context_length: Optional[int] = None
    tested_at: Optional[datetime] = None
    test_results: dict[str, Any] = None
    is_local: bool = False


@dataclass
class CapabilityTestRequest:
    """能力测试请求"""

    capability: str
    test_payload: dict[str, Any]
    expected_response_fields: list[str]
    timeout: float = 10.0


class LocalModelCapabilityDetector:
    """本地模型能力检测器"""

    def __init__(self, cache_ttl: int = 86400):  # 24小时缓存
        """
        Args:
            cache_ttl: 缓存时间（秒）
        """
        self.cache_ttl = cache_ttl
        self.capability_cache: dict[str, ModelCapabilities] = {}

        # 预定义能力测试案例
        self.test_cases: dict[str, CapabilityTestRequest] = {
            "vision": CapabilityTestRequest(
                capability="vision",
                test_payload={
                    "model": "test-model",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "What's in this image?"},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
                                    },
                                },
                            ],
                        }
                    ],
                    "max_tokens": 50,
                },
                expected_response_fields=["choices"],
                timeout=15.0,
            ),
            "function_calling": CapabilityTestRequest(
                capability="function_calling",
                test_payload={
                    "model": "test-model",
                    "messages": [
                        {
                            "role": "user",
                            "content": "What's the weather like in San Francisco?",
                        }
                    ],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "description": "Get the current weather",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "location": {
                                            "type": "string",
                                            "description": "The city name",
                                        }
                                    },
                                    "required": ["location"],
                                },
                            },
                        }
                    ],
                    "tool_choice": "auto",
                    "max_tokens": 50,
                },
                expected_response_fields=["choices"],
                timeout=15.0,
            ),
        }

    def _generate_cache_key(self, model_name: str, provider: str, base_url: str) -> str:
        """生成能力缓存键"""
        return f"capabilities_{provider}_{model_name}_{hash(base_url) % 10000}"

    def _is_local_provider(self, provider: str, base_url: str) -> bool:
        """判断是否为本地提供商"""
        local_indicators = [
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "local",
            "ollama",
            "lmstudio",
            "192.168.",
            "10.",
            "172.",
        ]

        provider_lower = provider.lower()
        base_url_lower = base_url.lower()

        return provider_lower in ["ollama", "lmstudio", "local"] or any(
            indicator in base_url_lower for indicator in local_indicators
        )

    async def detect_model_capabilities(
        self,
        model_name: str,
        provider: str,
        base_url: str,
        api_key: str,
        force_refresh: bool = False,
    ) -> ModelCapabilities:
        """
        检测模型能力

        Args:
            model_name: 模型名称
            provider: 提供商
            base_url: API基础URL
            api_key: API密钥
            force_refresh: 强制刷新缓存

        Returns:
            模型能力信息
        """
        cache_key = self._generate_cache_key(model_name, provider, base_url)

        # 检查缓存
        if not force_refresh:
            cached_capabilities = await self._get_cached_capabilities(cache_key)
            if cached_capabilities:
                logger.debug(f"使用缓存的能力信息: {model_name}")
                return cached_capabilities

        # 创建基础能力对象
        capabilities = ModelCapabilities(
            model_name=model_name,
            provider=provider,
            base_url=base_url,
            is_local=self._is_local_provider(provider, base_url),
            tested_at=datetime.now(),
            test_results={},
        )

        # 如果不是本地模型，使用默认云端能力
        if not capabilities.is_local:
            capabilities = self._get_cloud_provider_capabilities(capabilities)
            await self._cache_capabilities(cache_key, capabilities)
            return capabilities

        # 对本地模型进行能力测试
        logger.info(f"开始检测本地模型能力: {model_name}")

        # 测试视觉能力
        capabilities.supports_vision = await self._test_vision_capability(
            base_url, api_key, model_name
        )

        # 测试函数调用能力
        capabilities.supports_function_calling = (
            await self._test_function_calling_capability(base_url, api_key, model_name)
        )

        # 测试基础能力（代码生成、流式）
        basic_capabilities = await self._test_basic_capabilities(
            base_url, api_key, model_name
        )
        capabilities.supports_code_generation = basic_capabilities.get(
            "code_generation", True
        )
        capabilities.supports_streaming = basic_capabilities.get("streaming", True)
        capabilities.max_context_length = basic_capabilities.get("max_context_length")

        # 缓存结果
        await self._cache_capabilities(cache_key, capabilities)

        logger.info(
            f"本地模型能力检测完成: {model_name} - "
            f"Vision: {capabilities.supports_vision}, "
            f"Function: {capabilities.supports_function_calling}, "
            f"Code: {capabilities.supports_code_generation}"
        )

        return capabilities

    def _get_cloud_provider_capabilities(
        self, capabilities: ModelCapabilities
    ) -> ModelCapabilities:
        """获取云端提供商的默认能力（优先使用统一注册表）"""
        try:
            # 优先从统一注册表获取准确数据
            from core.utils.unified_model_registry import get_unified_model_registry

            registry = get_unified_model_registry()
            metadata = registry.get_model_metadata(
                capabilities.model_name, capabilities.provider
            )

            if metadata:
                capabilities.supports_vision = metadata.supports_vision
                capabilities.supports_function_calling = (
                    metadata.supports_function_calling
                )
                capabilities.supports_streaming = metadata.supports_streaming
                capabilities.supports_code_generation = True  # 默认支持
                if metadata.context_length:
                    capabilities.max_context_length = metadata.context_length
                return capabilities

        except Exception as e:
            logger.debug(f"统一注册表查询失败，使用基础推断: {e}")

        # 回退到基础推断
        provider = capabilities.provider.lower()
        model_name = capabilities.model_name.lower()

        # 简化的基础能力推断
        capabilities.supports_vision = any(
            keyword in model_name
            for keyword in ["vision", "gpt-4", "claude-3", "gemini"]
        )
        capabilities.supports_function_calling = provider not in [
            "ollama",
            "lmstudio",
        ]  # 本地模型通常不支持
        capabilities.supports_code_generation = True
        capabilities.supports_streaming = True

        return capabilities

    async def _test_vision_capability(
        self, base_url: str, api_key: str, model_name: str
    ) -> bool:
        """测试视觉能力"""
        try:
            test_case = self.test_cases["vision"]
            test_payload = test_case.test_payload.copy()
            test_payload["model"] = model_name

            headers = self._get_auth_headers(api_key)

            timeout = httpx.Timeout(test_case.timeout)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/v1/chat/completions",
                    json=test_payload,
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    # 检查响应是否包含有效内容
                    if "choices" in data and len(data["choices"]) > 0:
                        choice = data["choices"][0]
                        if "message" in choice and choice["message"].get("content"):
                            logger.debug(f"视觉能力测试成功: {model_name}")
                            return True

                logger.debug(
                    f"视觉能力测试失败: {model_name}, status: {response.status_code}"
                )
                return False

        except Exception as e:
            logger.debug(f"视觉能力测试异常: {model_name}, error: {e}")
            return False

    async def _test_function_calling_capability(
        self, base_url: str, api_key: str, model_name: str
    ) -> bool:
        """测试函数调用能力"""
        try:
            test_case = self.test_cases["function_calling"]
            test_payload = test_case.test_payload.copy()
            test_payload["model"] = model_name

            headers = self._get_auth_headers(api_key)

            timeout = httpx.Timeout(test_case.timeout)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/v1/chat/completions",
                    json=test_payload,
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    # 检查响应是否包含工具调用
                    if "choices" in data and len(data["choices"]) > 0:
                        choice = data["choices"][0]
                        if "message" in choice:
                            message = choice["message"]
                            # 检查是否有tool_calls或function_call
                            has_tools = (
                                message.get("tool_calls")
                                or message.get("function_call")
                                or "get_weather"
                                in str(message.get("content", "")).lower()
                            )
                            if has_tools:
                                logger.debug(f"函数调用能力测试成功: {model_name}")
                                return True

                logger.debug(
                    f"函数调用能力测试失败: {model_name}, status: {response.status_code}"
                )
                return False

        except Exception as e:
            logger.debug(f"函数调用能力测试异常: {model_name}, error: {e}")
            return False

    async def _test_basic_capabilities(
        self, base_url: str, api_key: str, model_name: str
    ) -> dict[str, Any]:
        """测试基础能力（代码生成、流式等）"""
        results = {
            "code_generation": True,  # 默认支持
            "streaming": True,  # 默认支持
            "max_context_length": None,
        }

        try:
            # 测试基础聊天能力
            test_payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": "Write a simple Python function to add two numbers.",
                    }
                ],
                "max_tokens": 100,
                "stream": False,
            }

            headers = self._get_auth_headers(api_key)

            timeout = httpx.Timeout(10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/v1/chat/completions",
                    json=test_payload,
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        content = (
                            data["choices"][0].get("message", {}).get("content", "")
                        )
                        # 检查是否包含代码
                        has_code = any(
                            keyword in content.lower()
                            for keyword in ["def ", "function", "```", "return"]
                        )
                        results["code_generation"] = has_code

                        # 从使用统计中推测上下文长度
                        if "usage" in data:
                            usage = data["usage"]
                            # 这只是一个估计，实际需要更复杂的测试
                            results["max_context_length"] = (
                                usage.get("total_tokens", 0) * 100
                            )

        except Exception as e:
            logger.debug(f"基础能力测试异常: {model_name}, error: {e}")

        return results

    def _get_auth_headers(self, api_key: str) -> dict[str, str]:
        """获取认证头"""
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def _get_cached_capabilities(
        self, cache_key: str
    ) -> Optional[ModelCapabilities]:
        """获取缓存的能力信息"""
        try:
            cached_data = await cache_get(cache_key)
            if cached_data:
                # 检查缓存是否过期
                if "tested_at" in cached_data:
                    tested_at = datetime.fromisoformat(cached_data["tested_at"])
                    if datetime.now() - tested_at < timedelta(seconds=self.cache_ttl):
                        return ModelCapabilities(**cached_data)
            return None
        except Exception as e:
            logger.debug(f"获取缓存能力信息失败: {e}")
            return None

    async def _cache_capabilities(
        self, cache_key: str, capabilities: ModelCapabilities
    ) -> None:
        """缓存能力信息"""
        try:
            # 转换为可序列化的字典
            cache_data = asdict(capabilities)
            if capabilities.tested_at:
                cache_data["tested_at"] = capabilities.tested_at.isoformat()

            await cache_set(cache_key, cache_data)
        except Exception as e:
            logger.debug(f"缓存能力信息失败: {e}")

    def can_handle_request(
        self, capabilities: ModelCapabilities, request_data: dict[str, Any]
    ) -> bool:
        """
        检查模型是否能处理特定请求

        Args:
            capabilities: 模型能力
            request_data: 请求数据

        Returns:
            True表示可以处理
        """
        # 检查是否需要视觉能力
        if (
            self._request_needs_vision(request_data)
            and not capabilities.supports_vision
        ):
            logger.debug(f"模型 {capabilities.model_name} 不支持视觉能力")
            return False

        # 检查是否需要函数调用能力
        if (
            self._request_needs_function_calling(request_data)
            and not capabilities.supports_function_calling
        ):
            logger.debug(f"模型 {capabilities.model_name} 不支持函数调用能力")
            return False

        # 检查上下文长度
        if capabilities.max_context_length:
            estimated_tokens = self._estimate_request_tokens(request_data)
            if estimated_tokens > capabilities.max_context_length:
                logger.debug(
                    f"请求过长 ({estimated_tokens} tokens) 超过模型上下文限制 ({capabilities.max_context_length})"
                )
                return False

        return True

    def _request_needs_vision(self, request_data: dict[str, Any]) -> bool:
        """检查请求是否需要视觉能力"""
        messages = request_data.get("messages", [])
        for message in messages:
            content = message.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        return True
        return False

    def _request_needs_function_calling(self, request_data: dict[str, Any]) -> bool:
        """检查请求是否需要函数调用能力"""
        return (
            "tools" in request_data
            or "functions" in request_data
            or "tool_choice" in request_data
            or "function_call" in request_data
        )

    def _estimate_request_tokens(self, request_data: dict[str, Any]) -> int:
        """估算请求的token数量"""
        # 简单估算：每个字符约0.25个token
        text_content = json.dumps(request_data, ensure_ascii=False)
        return int(len(text_content) * 0.25)

    async def get_fallback_channels(
        self,
        original_channel: str,
        request_data: dict[str, Any],
        available_channels: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        获取备用渠道（当本地模型不支持特定能力时）

        Args:
            original_channel: 原始渠道ID
            request_data: 请求数据
            available_channels: 可用渠道列表

        Returns:
            按优先级排序的备用渠道列表
        """
        fallback_channels = []

        # 确定需要的能力
        needs_vision = self._request_needs_vision(request_data)
        needs_function_calling = self._request_needs_function_calling(request_data)

        for channel in available_channels:
            if channel.get("id") == original_channel:
                continue  # 跳过原始渠道

            # 检测渠道能力
            capabilities = await self.detect_model_capabilities(
                channel.get("model_name", ""),
                channel.get("provider", ""),
                channel.get("base_url", ""),
                channel.get("api_key", ""),
            )

            # 检查是否满足需求
            if needs_vision and not capabilities.supports_vision:
                continue
            if needs_function_calling and not capabilities.supports_function_calling:
                continue

            # 计算优先级分数
            priority_score = self._calculate_fallback_priority(capabilities, channel)
            fallback_channels.append(
                {
                    **channel,
                    "fallback_priority": priority_score,
                    "capabilities": capabilities,
                }
            )

        # 按优先级排序
        fallback_channels.sort(key=lambda x: x["fallback_priority"], reverse=True)

        return fallback_channels

    def _calculate_fallback_priority(
        self, capabilities: ModelCapabilities, channel: dict[str, Any]
    ) -> float:
        """计算备用渠道的优先级分数"""
        score = 0.0

        # 云端模型优先级更高（通常更稳定）
        if not capabilities.is_local:
            score += 0.5

        # 已知良好的提供商
        provider = capabilities.provider.lower()
        if provider in ["openai", "anthropic"]:
            score += 0.3
        elif provider in ["groq", "siliconflow"]:
            score += 0.2

        # 渠道配置的优先级
        score += channel.get("priority", 1) * 0.1

        return score


# 全局实例
_capability_detector: Optional[LocalModelCapabilityDetector] = None


def get_capability_detector() -> LocalModelCapabilityDetector:
    """获取全局能力检测器实例"""
    global _capability_detector
    if _capability_detector is None:
        _capability_detector = LocalModelCapabilityDetector()
    return _capability_detector
