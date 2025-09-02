"""
旧版API兼容适配器
保持现有三个模块的API接口不变，内部调用统一模型注册表
遵循KISS原则：零破坏性变更，渐进式迁移
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from .unified_model_registry import get_unified_model_registry, ModelMetadata
from .model_analyzer import ModelSpecs  # 保持原有类型
from .local_model_capabilities import ModelCapabilities as LegacyModelCapabilities

logger = logging.getLogger(__name__)


class CapabilityMapperAdapter:
    """capability_mapper.py的兼容适配器"""
    
    def __init__(self):
        self.registry = get_unified_model_registry()
    
    def predict_capabilities(self, model_name: str, provider: str) -> Dict[str, bool]:
        """兼容原capability_mapper.predict_capabilities接口"""
        metadata = self.registry.get_model_metadata(model_name, provider)
        
        if metadata:
            return metadata.to_legacy_capability_format()
        
        # 回退到基础推断
        return self._fallback_capability_prediction(model_name, provider)
    
    def _fallback_capability_prediction(self, model_name: str, provider: str) -> Dict[str, bool]:
        """回退能力预测"""
        model_lower = model_name.lower()
        provider_lower = provider.lower()
        
        capabilities = {
            "vision": False,
            "function_calling": False,
            "code_generation": True,
            "streaming": True
        }
        
        # 基础视觉模型判断
        vision_keywords = ["vision", "gpt-4", "claude-3", "gemini", "qwen-vl", "llava"]
        if any(keyword in model_lower for keyword in vision_keywords):
            capabilities["vision"] = True
        
        # 基础函数调用判断
        if provider_lower in ["openai", "anthropic", "groq"]:
            capabilities["function_calling"] = True
        
        return capabilities
    
    def get_capability_requirements(self, request_data: Dict[str, Any]) -> Dict[str, bool]:
        """兼容原get_capability_requirements接口"""
        requirements = {
            "vision": False,
            "function_calling": False,
            "code_generation": False,
            "streaming": False
        }
        
        # 检查视觉需求
        messages = request_data.get("messages", [])
        for message in messages:
            content = message.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        requirements["vision"] = True
                        break
        
        # 检查函数调用需求
        if any(key in request_data for key in ["tools", "functions", "tool_choice", "function_call"]):
            requirements["function_calling"] = True
        
        # 检查流式需求
        if request_data.get("stream", False):
            requirements["streaming"] = True
        
        return requirements
    
    def find_compatible_models(self, models: List[str], requirements: Dict[str, bool], provider: str = "") -> List[str]:
        """兼容原find_compatible_models接口"""
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


class ModelAnalyzerAdapter:
    """model_analyzer.py的兼容适配器"""
    
    def __init__(self):
        self.registry = get_unified_model_registry()
    
    def analyze_model(self, model_name: str, model_data: Dict[str, Any] = None) -> ModelSpecs:
        """兼容原analyze_model接口"""
        metadata = self.registry.get_model_metadata(model_name)
        
        if metadata:
            return ModelSpecs(
                model_name=metadata.model_id,
                parameter_count=metadata.parameter_count,
                context_length=metadata.context_length,
                parameter_size_text=self._format_parameter_size(metadata.parameter_count),
                context_text=self._format_context_length(metadata.context_length)
            )
        
        # 回退到基础分析
        return self._fallback_model_analysis(model_name, model_data)
    
    def _fallback_model_analysis(self, model_name: str, model_data: Dict[str, Any] = None) -> ModelSpecs:
        """回退模型分析"""
        specs = ModelSpecs(model_name=model_name)
        
        # 从model_data提取
        if model_data:
            specs.context_length = model_data.get('context_length')
            specs.parameter_count = model_data.get('parameter_count')
        
        # 基础推断
        if not specs.parameter_count:
            specs.parameter_count = self._infer_parameter_count(model_name)
        
        if not specs.context_length:
            specs.context_length = self._infer_context_length(model_name)
        
        return specs
    
    def _infer_parameter_count(self, model_name: str) -> Optional[int]:
        """推断参数数量"""
        model_lower = model_name.lower()
        
        # 简化的参数推断
        if '70b' in model_lower or '72b' in model_lower:
            return 70000
        elif '30b' in model_lower or '32b' in model_lower:
            return 30000
        elif '8b' in model_lower or '7b' in model_lower:
            return 8000
        elif 'mini' in model_lower:
            return 8000
        elif 'gpt-4' in model_lower:
            return 1760000  # 1.76T
        
        return None
    
    def _infer_context_length(self, model_name: str) -> Optional[int]:
        """推断上下文长度"""
        model_lower = model_name.lower()
        
        # 从名称中提取上下文信息
        if '128k' in model_lower:
            return 128000
        elif '32k' in model_lower:
            return 32000
        elif '8k' in model_lower:
            return 8000
        elif 'gpt-4o' in model_lower or 'claude-3' in model_lower:
            return 128000
        
        return 8192  # 默认值
    
    def _format_parameter_size(self, parameter_count: Optional[int]) -> Optional[str]:
        """格式化参数大小"""
        if not parameter_count:
            return None
        
        if parameter_count >= 1000:
            return f"{parameter_count//1000}b"
        else:
            return f"{parameter_count}m"
    
    def _format_context_length(self, context_length: Optional[int]) -> Optional[str]:
        """格式化上下文长度"""
        if not context_length:
            return None
        
        if context_length >= 1000:
            return f"{context_length//1000}k"
        else:
            return str(context_length)
    
    def batch_analyze_models(self, models_data: Dict[str, Any]) -> Dict[str, ModelSpecs]:
        """兼容原batch_analyze_models接口"""
        results = {}
        
        for model_name, model_info in models_data.items():
            specs = self.analyze_model(model_name, model_info)
            results[model_name] = specs
        
        return results
    
    def extract_tags_from_model_name(self, model_name: str) -> List[str]:
        """兼容原extract_tags_from_model_name接口"""
        metadata = self.registry.get_model_metadata(model_name)
        
        if metadata and metadata.tags:
            return list(metadata.tags)
        
        # 回退到基础标签提取
        import re
        separators = r'[:/\-_@,]'
        parts = re.split(separators, model_name.lower())
        
        tags = []
        for part in parts:
            part = part.strip()
            if part and len(part) > 0:
                tags.append(part)
        
        return tags


class LocalModelCapabilitiesAdapter:
    """local_model_capabilities.py的兼容适配器"""
    
    def __init__(self):
        self.registry = get_unified_model_registry()
    
    async def detect_model_capabilities(self, 
                                      model_name: str,
                                      provider: str, 
                                      base_url: str,
                                      api_key: str,
                                      force_refresh: bool = False) -> LegacyModelCapabilities:
        """兼容原detect_model_capabilities接口"""
        
        # 首先从统一注册表获取
        metadata = self.registry.get_model_metadata(model_name, provider)
        
        if metadata and not force_refresh and not self._is_local_provider(provider, base_url):
            # 云端模型直接返回统一注册表数据
            return LegacyModelCapabilities(
                model_name=metadata.model_id,
                provider=metadata.provider,
                base_url=base_url,
                supports_vision=metadata.supports_vision,
                supports_function_calling=metadata.supports_function_calling,
                supports_code_generation=True,
                supports_streaming=metadata.supports_streaming,
                max_context_length=metadata.context_length,
                is_local=False
            )
        
        # 本地模型或强制刷新，进行实际测试
        if self._is_local_provider(provider, base_url):
            # 这里应该调用原来的实际测试逻辑
            # 为了简化，先返回基础能力
            return LegacyModelCapabilities(
                model_name=model_name,
                provider=provider,
                base_url=base_url,
                supports_vision=self._test_local_vision(model_name),
                supports_function_calling=self._test_local_function_calling(model_name),
                supports_code_generation=True,
                supports_streaming=True,
                is_local=True
            )
        
        # 回退到基础云端能力
        return self._get_basic_cloud_capabilities(model_name, provider, base_url)
    
    def _is_local_provider(self, provider: str, base_url: str) -> bool:
        """判断是否为本地提供商"""
        local_indicators = [
            "localhost", "127.0.0.1", "0.0.0.0",
            "local", "ollama", "lmstudio",
            "192.168.", "10.", "172."
        ]
        
        provider_lower = provider.lower()
        base_url_lower = base_url.lower()
        
        return (
            provider_lower in ["ollama", "lmstudio", "local"] or
            any(indicator in base_url_lower for indicator in local_indicators)
        )
    
    def _test_local_vision(self, model_name: str) -> bool:
        """测试本地模型视觉能力（简化版）"""
        vision_models = ["llava", "cogvlm", "minicpm-v", "qwen-vl"]
        model_lower = model_name.lower()
        return any(vm in model_lower for vm in vision_models)
    
    def _test_local_function_calling(self, model_name: str) -> bool:
        """测试本地模型函数调用能力（简化版）"""
        # 大部分本地模型不支持标准函数调用
        function_models = ["hermes", "mistral", "qwen"]
        model_lower = model_name.lower()
        return any(fm in model_lower for fm in function_models)
    
    def _get_basic_cloud_capabilities(self, model_name: str, provider: str, base_url: str) -> LegacyModelCapabilities:
        """获取基础云端能力"""
        model_lower = model_name.lower()
        provider_lower = provider.lower()
        
        supports_vision = False
        supports_function_calling = True
        
        # 基础视觉判断
        if provider_lower in ["openai", "anthropic", "google"]:
            if any(keyword in model_lower for keyword in ["gpt-4", "claude-3", "gemini"]):
                supports_vision = True
        
        return LegacyModelCapabilities(
            model_name=model_name,
            provider=provider,
            base_url=base_url,
            supports_vision=supports_vision,
            supports_function_calling=supports_function_calling,
            supports_code_generation=True,
            supports_streaming=True,
            is_local=False
        )


# 全局适配器实例
_capability_mapper_adapter: Optional[CapabilityMapperAdapter] = None
_model_analyzer_adapter: Optional[ModelAnalyzerAdapter] = None
_local_capabilities_adapter: Optional[LocalModelCapabilitiesAdapter] = None


def get_capability_mapper_adapter() -> CapabilityMapperAdapter:
    """获取capability_mapper适配器"""
    global _capability_mapper_adapter
    if _capability_mapper_adapter is None:
        _capability_mapper_adapter = CapabilityMapperAdapter()
    return _capability_mapper_adapter


def get_model_analyzer_adapter() -> ModelAnalyzerAdapter:
    """获取model_analyzer适配器"""
    global _model_analyzer_adapter
    if _model_analyzer_adapter is None:
        _model_analyzer_adapter = ModelAnalyzerAdapter()
    return _model_analyzer_adapter


def get_local_capabilities_adapter() -> LocalModelCapabilitiesAdapter:
    """获取local_model_capabilities适配器"""
    global _local_capabilities_adapter
    if _local_capabilities_adapter is None:
        _local_capabilities_adapter = LocalModelCapabilitiesAdapter()
    return _local_capabilities_adapter