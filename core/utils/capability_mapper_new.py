"""
能力映射器 - 新版本 (包装器实现)
保持完全的API兼容性，内部调用统一模型服务
"""

import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class CapabilityMapperWrapper:
    """能力映射器包装器 - 保持API兼容，内部使用新服务"""

    def __init__(self, config_path: Optional[str] = None):
        """保持原有初始化接口"""
        self.config_path = config_path or "config/model_capabilities.json"
        
        # 延迟导入避免循环依赖
        self._model_service = None
    
    @property
    def model_service(self):
        """懒加载模型服务"""
        if self._model_service is None:
            from core.services import get_model_service
            self._model_service = get_model_service()
        return self._model_service

    def predict_capabilities(self, model_name: str, provider: str) -> Dict[str, bool]:
        """
        预测模型能力 - 兼容原接口
        内部调用统一模型服务
        """
        try:
            capabilities = self.model_service.get_capabilities(model_name, provider)
            return capabilities.to_legacy_dict()
        except Exception as e:
            logger.warning(f"统一服务查询失败，使用基础回退: {e}")
            return self._basic_fallback(model_name, provider)
    
    def get_capability_requirements(self, request_data: Dict[str, Any]) -> Dict[str, bool]:
        """分析请求数据，确定需要的能力 - 兼容原接口"""
        return self.model_service.analyze_request_requirements(request_data)
    
    def find_compatible_models(self, 
                              models: List[str], 
                              requirements: Dict[str, bool], 
                              provider: str = "") -> List[str]:
        """从模型列表中找出兼容的模型 - 兼容原接口"""
        return self.model_service.find_compatible_models(models, requirements, provider)
    
    def add_model_override(self, model_name: str, capabilities: Dict[str, bool]) -> None:
        """添加模型能力覆盖 - 兼容原接口"""
        # TODO: 在新架构中实现覆盖机制
        logger.info(f"模型能力覆盖请求: {model_name} -> {capabilities}")
    
    def update_provider_capabilities(self, provider: str, capabilities: Dict[str, bool]) -> None:
        """更新提供商默认能力 - 兼容原接口"""
        # TODO: 在新架构中实现提供商能力更新
        logger.info(f"提供商能力更新请求: {provider} -> {capabilities}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取能力映射统计信息 - 兼容原接口"""
        stats = self.model_service.get_statistics()
        
        # 转换为原有格式
        return {
            "vision_models_count": stats.get("vision_models", 0),
            "function_calling_models_count": stats.get("function_calling_models", 0),
            "code_generation_models_count": stats.get("total_models", 0),  # 假设都支持
            "providers_count": stats.get("providers", 0),
            "model_overrides_count": 0,  # 新架构中暂未实现
            "local_patterns_count": 0    # 新架构中暂未实现
        }
    
    def save_config(self) -> None:
        """保存能力映射到配置文件 - 兼容原接口"""
        logger.info("配置保存请求 (新架构中自动管理)")
    
    def _basic_fallback(self, model_name: str, provider: str) -> Dict[str, bool]:
        """基础回退逻辑"""
        model_lower = model_name.lower()
        provider_lower = provider.lower()
        
        return {
            "vision": any(kw in model_lower for kw in ["vision", "gpt-4", "claude-3", "gemini"]),
            "function_calling": provider_lower not in ["ollama", "lmstudio"],
            "code_generation": True,
            "streaming": True
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