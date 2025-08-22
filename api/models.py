"""
Models API endpoints
模型列表API接口
"""

import time
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from core.json_router import JSONRouter
from core.utils.logger import get_logger
from core.yaml_config import YAMLConfigLoader

logger = get_logger(__name__)

# --- Response Models ---

class ChannelCost(BaseModel):
    input: Optional[float] = None
    output: Optional[float] = None

class ChannelInfo(BaseModel):
    id: str
    name: str
    provider: Optional[str] = None
    tags: Optional[List[str]] = None
    priority: Optional[int] = None
    capabilities: Optional[List[str]] = None
    cost_per_token: Optional[ChannelCost] = None

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
    channels: Optional[List[ChannelInfo]] = None

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
        model_channels_map = {}  # 记录模型对应的所有渠道信息

        # 1. 从路由器获取配置模型
        configured_models = json_router.get_available_models()
        all_models.update(configured_models)

        # 2. 从模型发现缓存获取物理模型和对应的渠道信息
        model_cache = config_loader.get_model_cache()
        if model_cache:
            for cache_key, discovery_data in model_cache.items():
                channel_id = discovery_data.get("channel_id", cache_key)
                for model_name in discovery_data.get("models", []):
                    all_models.add(model_name)
                    # 记录模型对应的所有渠道信息
                    if model_name not in model_channels_map:
                        model_channels_map[model_name] = []
                    if channel_id not in model_channels_map[model_name]:
                        model_channels_map[model_name].append(channel_id)

        # 3. 构建响应
        models_data = []
        current_time = int(time.time())

        # 获取渠道映射
        channels_list = config_loader.config.channels or []
        channels = {channel.id: channel for channel in channels_list}

        for model_id in sorted(list(all_models)):
            # 获取模型支持的所有渠道
            channel_list = []
            channel_ids = model_channels_map.get(model_id, [])

            for channel_id in channel_ids:
                if channel_id in channels:
                    channel = channels[channel_id]

                    # 构建成本信息
                    cost_info = None
                    if hasattr(channel, 'cost_per_token') and channel.cost_per_token:
                        cost_info = ChannelCost(
                            input=channel.cost_per_token.get('input'),
                            output=channel.cost_per_token.get('output')
                        )

                    channel_list.append(ChannelInfo(
                        id=channel.id,
                        name=channel.name,
                        provider=getattr(channel, 'provider', None),
                        tags=getattr(channel, 'tags', None),
                        priority=getattr(channel, 'priority', None),
                        capabilities=getattr(channel, 'capabilities', None),
                        cost_per_token=cost_info
                    ))

            models_data.append(ModelInfo(
                id=model_id,
                created=current_time,
                owned_by="smart-ai-router",
                name=model_id,
                model_type="model_group" if model_id.startswith("auto:") or model_id.startswith("tag:") else "model",
                available=True,
                channels=channel_list if channel_list else None,
                channel_count=len(channel_list) if channel_list else 0
            ))

        return ModelsResponse(data=models_data, total_models=len(models_data))

    return router
