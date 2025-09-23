"""
Groq Provider适配器
Groq是高性能AI推理服务，提供快速的开源模型访问
"""

from typing import Any, Dict, List

from core.utils.logger import get_logger

from ..base import ModelInfo
from .openai import OpenAIAdapter  # Groq使用OpenAI兼容API

logger = get_logger(__name__)


class GroqAdapter(OpenAIAdapter):
    """Groq适配器 - 继承OpenAI适配器因为API兼容"""

    def __init__(self, provider_name: str, config: Dict[str, Any]):
        super().__init__(provider_name, config)

        # Groq特定配置
        self.rate_limit_rpm = config.get("rate_limits", {}).get(
            "requests_per_minute", 30
        )
        self.rate_limit_rpd = config.get("rate_limits", {}).get(
            "requests_per_day", 14400
        )
        self.rate_limit_tpm = config.get("rate_limits", {}).get(
            "tokens_per_minute", 7000
        )

        logger.info(f"初始化Groq适配器，速率限制: {self.rate_limit_rpm}/min")

    def _is_chat_model(self, model_id: str) -> bool:
        """判断是否是Groq支持的聊天模型 - 基于API发现而非硬编码"""
        # 移除硬编码限制，所有从API返回的模型都应被视为可用
        # Groq API只返回它支持的模型，所以不需要客户端过滤
        return True

    def _get_model_capabilities(self, model_id: str) -> List[str]:
        """Groq模型能力映射"""
        capabilities = ["text"]

        model_lower = model_id.lower()

        # Groq支持的function calling模型
        if any(pattern in model_lower for pattern in ["llama-3.1", "llama3-groq"]):
            capabilities.append("function_calling")

        # 代码生成能力
        if any(pattern in model_lower for pattern in ["llama", "mixtral"]):
            capabilities.append("code_generation")

        # JSON模式支持
        if "llama-3" in model_lower or "mixtral" in model_lower:
            capabilities.append("json_mode")

        return capabilities

    def _get_context_length(self, model_id: str) -> int:
        """Groq模型上下文长度"""
        context_lengths = {
            "llama-3.1-405b": 131072,
            "llama-3.1-70b": 131072,
            "llama-3.1-8b": 131072,
            "llama3-70b": 8192,
            "llama3-8b": 8192,
            "mixtral-8x7b": 32768,
            "gemma-7b": 8192,
        }

        for pattern, length in context_lengths.items():
            if pattern in model_id.lower():
                return length

        return 8192  # Groq默认上下文长度

    def _get_speed_score(self, model_id: str) -> float:
        """Groq模型速度评分 - Groq以高速著称"""
        speed_scores = {
            "llama-3.1-8b": 0.98,  # 最快的小模型
            "llama3-8b": 0.95,
            "gemma-7b": 0.93,
            "llama-3.1-70b": 0.9,  # 大模型但在Groq上仍然很快
            "llama3-70b": 0.88,
            "mixtral-8x7b": 0.85,
            "llama-3.1-405b": 0.8,  # 最大模型
        }

        for pattern, score in speed_scores.items():
            if pattern in model_id.lower():
                return score

        return 0.9  # Groq默认高速度评分

    def _get_quality_score(self, model_id: str) -> float:
        """Groq模型质量评分"""
        quality_scores = {
            "llama-3.1-405b": 0.95,  # 最大最强模型
            "llama-3.1-70b": 0.9,
            "llama3-70b": 0.88,
            "mixtral-8x7b": 0.85,
            "llama-3.1-8b": 0.8,
            "llama3-8b": 0.78,
            "gemma-7b": 0.75,
        }

        for pattern, score in quality_scores.items():
            if pattern in model_id.lower():
                return score

        return 0.8  # 默认质量评分

    async def list_models(self, api_key: str) -> List[ModelInfo]:
        """获取Groq模型列表，重写以应用免费定价"""
        models = await super().list_models(api_key)

        # Groq当前是免费的，覆盖定价信息
        for model in models:
            model.input_cost_per_1k = 0.0
            model.output_cost_per_1k = 0.0

        return models

    def get_rate_limits(self) -> Dict[str, int]:
        """获取Groq速率限制信息"""
        return {
            "requests_per_minute": self.rate_limit_rpm,
            "requests_per_day": self.rate_limit_rpd,
            "tokens_per_minute": self.rate_limit_tpm,
        }
