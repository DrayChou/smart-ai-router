"""
Models API endpoints
模型列表API接口
"""

import time
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.yaml_config import YAMLConfigLoader
from core.json_router import JSONRouter
from core.utils.logger import get_logger

logger = get_logger(__name__)

# --- Response Models ---

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str
    name: Optional[str] = None
    model_type: str = "model"
    available: bool = True
    parameter_count: Optional[int] = None
    context_length: Optional[int] = None
    input_price: Optional[float] = None
    output_price: Optional[float] = None
    channel_count: Optional[int] = None
    tags: Optional[List[str]] = None

class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]
    total_models: int = 0

# 创建路由器
router = APIRouter(prefix="/v1", tags=["models"])

def create_models_router(config_loader: YAMLConfigLoader, json_router: JSONRouter) -> APIRouter:
    """创建模型相关的API路由"""
    
    @router.get("/models", response_model=ModelsResponse)
    async def list_models() -> ModelsResponse:
        """返回所有可用的模型"""
        all_models = set()

        # 1. 从路由器获取配置模型
        configured_models = json_router.get_available_models()
        all_models.update(configured_models)

        # 2. 从模型发现缓存获取物理模型
        model_cache = config_loader.get_model_cache()
        if model_cache:
            for channel_id, discovery_data in model_cache.items():
                for model_name in discovery_data.get("models", []):
                    all_models.add(model_name)

        # 3. 构建响应
        models_data = []
        current_time = int(time.time())
        
        for model_id in sorted(list(all_models)):
            models_data.append(ModelInfo(
                id=model_id,
                created=current_time,
                owned_by="smart-ai-router",
                name=model_id,
                model_type="model_group" if model_id.startswith("auto:") or model_id.startswith("tag:") else "model",
                available=True
            ))

        return ModelsResponse(data=models_data, total_models=len(models_data))
    
    return router