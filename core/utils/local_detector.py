"""
本地模型检测器
专门负责本地模型的实时能力检测
遵循KISS原则，只做本地检测，不处理云端逻辑
"""

import asyncio
import logging
from typing import Optional

import httpx

from ..models.model_info import (
    DataSource,
    ModelInfo,
    ModelPricing,
)

logger = logging.getLogger(__name__)


class LocalModelDetector:
    """本地模型实时能力检测器"""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    async def detect_capabilities(
        self, model_name: str, provider: str, base_url: str, api_key: str = ""
    ) -> ModelInfo:
        """检测本地模型能力"""

        if not self._is_local_provider(provider, base_url):
            raise ValueError(f"不是本地提供商: {provider}, {base_url}")

        logger.info(f"开始检测本地模型能力: {model_name}")

        # 创建基础模型信息
        model_info = ModelInfo(
            model_id=model_name,
            provider=provider,
            is_local=True,
            data_source=DataSource.LOCAL_DETECTION,
        )

        # 并行检测各种能力
        vision_task = self._test_vision_capability(base_url, api_key, model_name)
        function_task = self._test_function_calling_capability(
            base_url, api_key, model_name
        )

        try:
            vision_result, function_result = await asyncio.gather(
                vision_task, function_task, return_exceptions=True
            )

            # 设置检测结果
            if isinstance(vision_result, bool):
                model_info.capabilities.supports_vision = vision_result
            if isinstance(function_result, bool):
                model_info.capabilities.supports_function_calling = function_result

            # 默认能力设置
            model_info.capabilities.supports_code_generation = True
            model_info.capabilities.supports_streaming = True

            # 本地模型通常是免费的
            model_info.pricing = ModelPricing(is_free=True)

        except Exception as e:
            logger.warning(f"本地模型能力检测失败: {e}")
            # 使用基础推断
            self._apply_basic_local_inference(model_info)

        logger.info(
            f"本地模型检测完成: {model_name} - Vision: {model_info.capabilities.supports_vision}, Function: {model_info.capabilities.supports_function_calling}"
        )

        return model_info

    def _is_local_provider(self, provider: str, base_url: str) -> bool:
        """判断是否为本地提供商"""
        local_indicators = [
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "192.168.",
            "10.",
            "172.",
            ":11434",  # Ollama默认端口
            ":1234",  # LMStudio默认端口
        ]

        provider_lower = provider.lower()
        base_url_lower = base_url.lower()

        return provider_lower in ["ollama", "lmstudio", "local"] or any(
            indicator in base_url_lower for indicator in local_indicators
        )

    async def _test_vision_capability(
        self, base_url: str, api_key: str, model_name: str
    ) -> bool:
        """测试视觉能力"""
        try:
            # 简单的视觉测试请求
            test_payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "测试"},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:image/png;base64,iVBORw0KGgoAAAANSU"
                                },
                            },
                        ],
                    }
                ],
                "max_tokens": 10,
            }

            headers = self._get_auth_headers(api_key)

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{base_url}/v1/chat/completions",
                    json=test_payload,
                    headers=headers,
                )

                # 如果返回200或者特定的错误码，说明支持视觉
                return response.status_code in [200, 400]  # 400可能是格式问题但支持接口

        except Exception:
            return False

    async def _test_function_calling_capability(
        self, base_url: str, api_key: str, model_name: str
    ) -> bool:
        """测试函数调用能力"""
        try:
            # 简单的函数调用测试
            test_payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "测试"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "test_function",
                            "description": "测试函数",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
                "max_tokens": 10,
            }

            headers = self._get_auth_headers(api_key)

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{base_url}/v1/chat/completions",
                    json=test_payload,
                    headers=headers,
                )

                return response.status_code in [200, 400]

        except Exception:
            return False

    def _get_auth_headers(self, api_key: str) -> dict[str, str]:
        """获取认证头"""
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _apply_basic_local_inference(self, model_info: ModelInfo) -> None:
        """应用基础本地模型推断"""
        model_lower = model_info.model_id.lower()
        provider_lower = model_info.provider.lower()

        # 基于名称推断视觉能力
        vision_models = ["llava", "cogvlm", "minicpm-v", "qwen-vl", "yi-vl"]
        model_info.capabilities.supports_vision = any(
            vm in model_lower for vm in vision_models
        )

        # 基于名称推断函数调用能力
        function_models = ["hermes", "mixtral", "qwen"]
        if provider_lower == "ollama":
            # Ollama大部分模型不支持函数调用
            model_info.capabilities.supports_function_calling = any(
                fm in model_lower for fm in function_models
            )
        else:
            # 其他本地提供商可能支持
            model_info.capabilities.supports_function_calling = True

        # 默认能力
        model_info.capabilities.supports_code_generation = True
        model_info.capabilities.supports_streaming = True


# 全局单例
_local_detector: Optional[LocalModelDetector] = None


def get_local_detector() -> LocalModelDetector:
    """获取全局本地检测器实例"""
    global _local_detector
    if _local_detector is None:
        _local_detector = LocalModelDetector()
    return _local_detector
