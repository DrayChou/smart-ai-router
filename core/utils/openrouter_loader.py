"""
OpenRouter数据加载器
负责加载和解析OpenRouter模型数据
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from ..models.model_info import ModelInfo, create_model_info_from_openrouter

logger = logging.getLogger(__name__)


class OpenRouterDataLoader:
    """OpenRouter数据加载器"""
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.openrouter_file = self.cache_dir / "channels" / "openrouter.free.json"
        self._models_cache: Optional[Dict[str, ModelInfo]] = None
    
    def load_models(self) -> Dict[str, ModelInfo]:
        """加载所有模型数据"""
        if self._models_cache is not None:
            return self._models_cache
        
        models = {}
        
        if not self.openrouter_file.exists():
            logger.warning(f"OpenRouter数据文件不存在: {self.openrouter_file}")
            self._models_cache = models
            return models
        
        try:
            with open(self.openrouter_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            openrouter_models = data.get("models", {})
            logger.info(f"开始加载 {len(openrouter_models)} 个OpenRouter模型")
            
            for model_id, model_data in openrouter_models.items():
                try:
                    model_info = create_model_info_from_openrouter(model_data)
                    models[model_id] = model_info
                except Exception as e:
                    logger.warning(f"解析模型失败 {model_id}: {e}")
                    continue
            
            logger.info(f"✅ 成功加载 {len(models)} 个模型")
            
        except Exception as e:
            logger.error(f"加载OpenRouter数据失败: {e}")
        
        self._models_cache = models
        return models
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取数据统计信息"""
        models = self.load_models()
        
        total_models = len(models)
        free_models = len([m for m in models.values() if m.pricing.is_free])
        vision_models = len([m for m in models.values() if m.capabilities.supports_vision])
        function_models = len([m for m in models.values() if m.capabilities.supports_function_calling])
        
        providers = set(m.provider for m in models.values() if m.provider)
        
        # 统计所有标签
        all_tags = set()
        for model in models.values():
            all_tags.update(model.extract_tags_from_name())
        
        return {
            "total_models": total_models,
            "free_models": free_models,
            "vision_models": vision_models,
            "function_calling_models": function_models,
            "providers": len(providers),
            "tags": len(all_tags),
            "provider_overrides": 0,  # 还未实现
            "channel_overrides": 0    # 还未实现
        }
    
    def clear_cache(self) -> None:
        """清除缓存，强制重新加载"""
        self._models_cache = None


# 全局单例
_openrouter_loader: Optional[OpenRouterDataLoader] = None


def get_openrouter_loader() -> OpenRouterDataLoader:
    """获取全局OpenRouter加载器实例"""
    global _openrouter_loader
    if _openrouter_loader is None:
        _openrouter_loader = OpenRouterDataLoader()
    return _openrouter_loader