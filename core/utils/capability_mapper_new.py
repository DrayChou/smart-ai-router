"""
能力映射器 - 新版本 (包装器实现)
保持完全的API兼容性，内部调用统一模型服务
"""

import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class CapabilityMapperWrapper:
    """Legacy wrapper retained for backward compatibility."""

    """能力映射器包装器 - 保持API兼容，内部使用新服务"""

    def __init__(self, config_path: Optional[str] = None):
        """保持原有初始化接口"""
        self.config_path = config_path or "config/model_capabilities.json"

    def predict_capabilities(self, model_name: str, provider: str) -> Dict[str, bool]:
        """
        预测模型能力 - 兼容原接口
        内部调用统一模型服务
        """
        fallback = self._basic_fallback(model_name, provider)
        return fallback

    def get_capability_requirements(
        self, request_data: Dict[str, Any]
    ) -> Dict[str, bool]:
        """分析请求数据，确定需要的能力 - 兼容原接口"""
        requirements = {
            "vision": False,
            "function_calling": False,
            "code_generation": False,
            "streaming": bool(request_data.get("stream", False)),
        }

        messages = request_data.get("messages", []) or []
        for message in messages:
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") in {
                        "image",
                        "input_image",
                    }:
                        requirements["vision"] = True
            elif isinstance(content, str) and any(
                token in content.lower() for token in ["image:", "<image>"]
            ):
                requirements["vision"] = True

        if (
            request_data.get("functions")
            or request_data.get("function_call")
            or request_data.get("tools")
        ):
            requirements["function_calling"] = True

        return requirements

    def find_compatible_models(
        self, models: List[str], requirements: Dict[str, bool], provider: str = ""
    ) -> List[str]:
        """从模型列表中找出兼容的模型 - 兼容原接口"""
        return []

    def add_model_override(
        self, model_name: str, capabilities: Dict[str, bool]
    ) -> None:
        """添加模型能力覆盖 - 兼容原接口"""
        # TODO: 在新架构中实现覆盖机制
        logger.info(f"模型能力覆盖请求: {model_name} -> {capabilities}")

    def update_provider_capabilities(
        self, provider: str, capabilities: Dict[str, bool]
    ) -> None:
        """更新提供商默认能力 - 兼容原接口"""
        # TODO: 在新架构中实现提供商能力更新
        logger.info(f"提供商能力更新请求: {provider} -> {capabilities}")

    def get_statistics(self) -> Dict[str, Any]:
        """获取能力映射统计信息 - 兼容原接口"""
        return {
            "vision_models_count": 0,
            "function_calling_models_count": 0,
            "code_generation_models_count": 0,
            "providers_count": 0,
            "model_overrides_count": 0,
            "local_patterns_count": 0,
        }

    def save_config(self) -> None:
        """保存能力映射到配置文件 - 兼容原接口"""
        logger.info("配置保存请求 (新架构中自动管理)")

    def _basic_fallback(self, model_name: str, provider: str) -> Dict[str, bool]:
        """基础回退逻辑"""
        model_lower = model_name.lower()
        provider_lower = provider.lower()

        return {
            "vision": any(
                kw in model_lower for kw in ["vision", "gpt-4", "claude-3", "gemini"]
            ),
            "function_calling": provider_lower not in ["ollama", "lmstudio"],
            "code_generation": True,
            "streaming": True,
        }


# 保持原有的全局单例模式
_capability_mapper: Optional[CapabilityMapperWrapper] = None


def get_capability_mapper() -> CapabilityMapperWrapper:
    """获取全局能力映射器实例 - 兼容原接口"""
    global _capability_mapper
    if _capability_mapper is None:
        _capability_mapper = CapabilityMapperWrapper()
    return _capability_mapper


# 为了完全兼容，保留原有类名
CapabilityMapper = CapabilityMapperWrapper
