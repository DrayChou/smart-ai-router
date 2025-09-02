"""
模型能力映射器
维护已知模型的能力映射，减少重复检测，提供快速能力查询
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ModelCapabilityMap:
    """模型能力映射"""
    vision_models: Set[str]  # 支持视觉的模型名称模式
    function_calling_models: Set[str]  # 支持函数调用的模型名称模式
    code_generation_models: Set[str]  # 支持代码生成的模型名称模式
    streaming_models: Set[str]  # 支持流式的模型名称模式
    local_model_patterns: Set[str]  # 本地模型名称模式

    # 提供商默认能力
    provider_capabilities: Dict[str, Dict[str, bool]]

    # 具体模型的能力覆盖
    model_overrides: Dict[str, Dict[str, bool]]


class CapabilityMapper:
    """模型能力映射器"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Args:
            config_path: 能力映射配置文件路径
        """
        self.config_path = config_path or "config/model_capabilities.json"
        self.capability_map = self._load_default_capabilities()
        self._load_config()

    def _load_default_capabilities(self) -> ModelCapabilityMap:
        """加载默认能力映射（简化版，主要数据从统一注册表获取）"""
        return ModelCapabilityMap(
            # 简化的基础模式集合，复杂查询委托给统一注册表
            vision_models=set(),  # 由统一注册表处理
            function_calling_models=set(),  # 由统一注册表处理  
            code_generation_models=set(),  # 由统一注册表处理
            streaming_models=set(),  # 大部分现代模型都支持流式

            # 保留本地模型模式用于基础判断
            local_model_patterns={
                "ollama", "llama.cpp", "local", "localhost",
                "ggml", "gguf", "quantized", "4bit", "8bit",
                "alpaca", "vicuna", "wizard", "orca"
            },

            # 保留基础提供商能力用于回退
            provider_capabilities={
                "openai": {"vision": True, "function_calling": True, "code_generation": True, "streaming": True},
                "anthropic": {"vision": True, "function_calling": True, "code_generation": True, "streaming": True},
                "groq": {"vision": False, "function_calling": True, "code_generation": True, "streaming": True},
                "siliconflow": {"vision": True, "function_calling": True, "code_generation": True, "streaming": True},
                "deepseek": {"vision": False, "function_calling": True, "code_generation": True, "streaming": True},
                "moonshot": {"vision": False, "function_calling": True, "code_generation": True, "streaming": True},
                "ollama": {"vision": False, "function_calling": False, "code_generation": True, "streaming": True},
                "lmstudio": {"vision": False, "function_calling": False, "code_generation": True, "streaming": True}
            },

            # 保留关键本地模型覆盖
            model_overrides={
                "llava:latest": {"vision": True, "function_calling": False, "code_generation": False, "streaming": True},
                "cogvlm:latest": {"vision": True, "function_calling": False, "code_generation": False, "streaming": True}
            }
        )

    def _load_config(self) -> None:
        """从配置文件加载能力映射"""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                with open(config_file, encoding='utf-8') as f:
                    config_data = json.load(f)

                # 合并配置
                if "vision_models" in config_data:
                    self.capability_map.vision_models.update(config_data["vision_models"])

                if "function_calling_models" in config_data:
                    self.capability_map.function_calling_models.update(config_data["function_calling_models"])

                if "provider_capabilities" in config_data:
                    self.capability_map.provider_capabilities.update(config_data["provider_capabilities"])

                if "model_overrides" in config_data:
                    self.capability_map.model_overrides.update(config_data["model_overrides"])

                logger.info(f"已加载能力映射配置: {config_file}")
        except Exception as e:
            logger.warning(f"加载能力映射配置失败: {e}")

    def save_config(self) -> None:
        """保存能力映射到配置文件"""
        try:
            config_file = Path(self.config_path)
            config_file.parent.mkdir(parents=True, exist_ok=True)

            config_data = {
                "vision_models": list(self.capability_map.vision_models),
                "function_calling_models": list(self.capability_map.function_calling_models),
                "code_generation_models": list(self.capability_map.code_generation_models),
                "streaming_models": list(self.capability_map.streaming_models),
                "local_model_patterns": list(self.capability_map.local_model_patterns),
                "provider_capabilities": self.capability_map.provider_capabilities,
                "model_overrides": self.capability_map.model_overrides
            }

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            logger.info(f"已保存能力映射配置: {config_file}")
        except Exception as e:
            logger.error(f"保存能力映射配置失败: {e}")

    def predict_capabilities(self, model_name: str, provider: str) -> Dict[str, bool]:
        """
        预测模型能力
        
        Args:
            model_name: 模型名称
            provider: 提供商
            
        Returns:
            能力预测结果
        """
        # 优先从统一模型注册表获取数据
        try:
            from .legacy_adapters import get_capability_mapper_adapter
            adapter = get_capability_mapper_adapter()
            return adapter.predict_capabilities(model_name, provider)
        except Exception as e:
            logger.warning(f"统一模型注册表查询失败，回退到原逻辑: {e}")
        
        # 回退到原逻辑
        capabilities = {
            "vision": False,
            "function_calling": False,
            "code_generation": True,  # 默认支持
            "streaming": True  # 默认支持
        }

        model_name_lower = model_name.lower()
        provider_lower = provider.lower()

        # 检查模型特定覆盖
        if model_name in self.capability_map.model_overrides:
            capabilities.update(self.capability_map.model_overrides[model_name])
            return capabilities

        # 检查提供商默认能力
        if provider_lower in self.capability_map.provider_capabilities:
            provider_caps = self.capability_map.provider_capabilities[provider_lower]
            capabilities.update(provider_caps)

        # 简化的本地模型特殊逻辑（详细能力由统一注册表处理）
        if self._is_local_model(model_name_lower, provider_lower):
            # 本地模型通常不支持复杂功能
            if "llava" not in model_name_lower and "cogvlm" not in model_name_lower:
                capabilities["vision"] = False
            if "function" not in model_name_lower and "tool" not in model_name_lower:
                capabilities["function_calling"] = False

        return capabilities

    def _model_matches_patterns(self, model_name: str, patterns: Set[str]) -> bool:
        """检查模型名称是否匹配模式"""
        for pattern in patterns:
            if pattern.lower() in model_name:
                return True
        return False

    def _is_local_model(self, model_name: str, provider: str) -> bool:
        """判断是否为本地模型"""
        if provider in ["ollama", "lmstudio", "local"]:
            return True

        return self._model_matches_patterns(model_name, self.capability_map.local_model_patterns)

    def get_capability_requirements(self, request_data: Dict[str, Any]) -> Dict[str, bool]:
        """
        分析请求数据，确定需要的能力
        
        Args:
            request_data: 请求数据
            
        Returns:
            需要的能力字典
        """
        requirements = {
            "vision": False,
            "function_calling": False,
            "code_generation": False,
            "streaming": False
        }

        # 检查是否需要视觉能力
        messages = request_data.get("messages", [])
        for message in messages:
            content = message.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        requirements["vision"] = True
                        break

        # 检查是否需要函数调用能力
        if any(key in request_data for key in ["tools", "functions", "tool_choice", "function_call"]):
            requirements["function_calling"] = True

        # 检查是否需要代码生成（基于提示词）
        prompt_text = ""
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                prompt_text += content.lower()
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        prompt_text += item.get("text", "").lower()

        code_keywords = ["code", "function", "class", "def ", "import ", "programming", "debug", "implement"]
        if any(keyword in prompt_text for keyword in code_keywords):
            requirements["code_generation"] = True

        # 检查是否需要流式
        if request_data.get("stream", False):
            requirements["streaming"] = True

        return requirements

    def find_compatible_models(
        self,
        models: List[str],
        requirements: Dict[str, bool],
        provider: str = ""
    ) -> List[str]:
        """
        从模型列表中找出兼容的模型
        
        Args:
            models: 模型列表
            requirements: 能力需求
            provider: 提供商
            
        Returns:
            兼容的模型列表
        """
        compatible_models = []

        for model in models:
            capabilities = self.predict_capabilities(model, provider)

            # 检查是否满足所有需求
            is_compatible = True
            for req_capability, required in requirements.items():
                if required and not capabilities.get(req_capability, False):
                    is_compatible = False
                    break

            if is_compatible:
                compatible_models.append(model)

        return compatible_models

    def add_model_override(self, model_name: str, capabilities: Dict[str, bool]) -> None:
        """添加模型能力覆盖"""
        self.capability_map.model_overrides[model_name] = capabilities
        logger.info(f"已添加模型能力覆盖: {model_name} -> {capabilities}")

    def update_provider_capabilities(self, provider: str, capabilities: Dict[str, bool]) -> None:
        """更新提供商默认能力"""
        self.capability_map.provider_capabilities[provider] = capabilities
        logger.info(f"已更新提供商能力: {provider} -> {capabilities}")

    def get_statistics(self) -> Dict[str, Any]:
        """获取能力映射统计信息"""
        return {
            "vision_models_count": len(self.capability_map.vision_models),
            "function_calling_models_count": len(self.capability_map.function_calling_models),
            "code_generation_models_count": len(self.capability_map.code_generation_models),
            "providers_count": len(self.capability_map.provider_capabilities),
            "model_overrides_count": len(self.capability_map.model_overrides),
            "local_patterns_count": len(self.capability_map.local_model_patterns)
        }


# 全局实例
_capability_mapper: Optional[CapabilityMapper] = None


def get_capability_mapper() -> CapabilityMapper:
    """获取全局能力映射器实例"""
    global _capability_mapper
    if _capability_mapper is None:
        _capability_mapper = CapabilityMapper()
    return _capability_mapper
