"""
Models API endpoints
模型列表API接口
"""

import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from core.json_router import get_router
from core.utils.logger import get_logger
from core.utils.memory_index import get_memory_index
from core.yaml_config import YAMLConfigLoader

logger = get_logger(__name__)

# --- Response Models ---


class ChannelCost(BaseModel):
    input: Optional[float] = None
    output: Optional[float] = None


class ModelCapabilities(BaseModel):
    supports_vision: bool = False
    supports_function_calling: bool = False
    supports_code_generation: bool = False
    supports_streaming: bool = False


class ChannelInfo(BaseModel):
    id: str
    name: str
    provider: Optional[str] = None
    tags: Optional[list[str]] = None
    priority: Optional[int] = None
    capabilities: Optional[list[str]] = None
    cost_per_token: Optional[ChannelCost] = None
    # 渠道特定的模型信息覆盖
    channel_context_length: Optional[int] = None
    channel_capabilities: Optional[ModelCapabilities] = None
    # 渠道特定的tags（从渠道配置或模型分析得出）
    channel_tags: Optional[list[str]] = None


class ModelInfo(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: str
    object: str = "model"
    created: int
    owned_by: str
    name: Optional[str] = None
    model_type: str = "model"
    available: bool = True

    # 模型基础信息
    parameter_count: Optional[int] = None  # 参数数量(百万)
    parameter_size_text: Optional[str] = None  # "7b", "70b"等
    context_length: Optional[int] = None  # 上下文长度
    context_text: Optional[str] = None  # "32k", "128k"等

    # 模型能力
    capabilities: Optional[ModelCapabilities] = None

    # 定价信息
    input_price: Optional[float] = None
    output_price: Optional[float] = None

    # 渠道和标签信息
    channel_count: Optional[int] = None
    tags: Optional[list[str]] = None
    channels: Optional[list[ChannelInfo]] = None


class ModelsResponse(BaseModel):
    object: str = "list"
    data: list[ModelInfo]
    total_models: int = 0


# 创建路由器
router = APIRouter(prefix="/v1", tags=["models"])


def create_models_router(config_loader: YAMLConfigLoader) -> APIRouter:
    json_router = get_router()
    """创建模型相关的API路由"""

    @router.get("/models", response_model=ModelsResponse)
    async def list_models() -> ModelsResponse:
        """返回所有可用的模型，包含详细信息"""
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

        # 获取渠道映射和内存索引（用于tags提取）
        channels_list = config_loader.config.channels or []
        channels = {channel.id: channel for channel in channels_list}
        memory_index = get_memory_index()

        for model_id in sorted(all_models):
            aggregated_tags: set[str] = set()
            channel_list: list[ChannelInfo] = []
            channel_ids = model_channels_map.get(model_id, [])
            parameter_count: Optional[int] = None
            context_length: Optional[int] = None
            model_capabilities: Optional[ModelCapabilities] = None

            for channel_id in channel_ids:
                channel = channels.get(channel_id)
                if not channel:
                    continue

                model_info = memory_index.get_model_info(channel_id, model_id)
                if not model_info:
                    continue

                aggregated_tags.update(model_info.tags)

                specs = model_info.specs or {}
                parameter_count = parameter_count or specs.get("parameter_count")
                context_length = context_length or specs.get("context_length")

                channel_caps = None
                if model_info.capabilities:
                    channel_caps = ModelCapabilities(
                        supports_vision=model_info.capabilities.get("vision", False),
                        supports_function_calling=model_info.capabilities.get(
                            "function_calling", False
                        ),
                        supports_code_generation=model_info.capabilities.get(
                            "code_generation", False
                        ),
                        supports_streaming=model_info.capabilities.get(
                            "streaming", False
                        ),
                    )
                    if model_capabilities is None:
                        model_capabilities = channel_caps

                cost_info = None
                if model_info.pricing:
                    input_cost = model_info.pricing.get(
                        "input"
                    ) or model_info.pricing.get("prompt")
                    output_cost = model_info.pricing.get(
                        "output"
                    ) or model_info.pricing.get("completion")
                    if input_cost is not None or output_cost is not None:
                        cost_info = ChannelCost(input=input_cost, output=output_cost)

                channel_list.append(
                    ChannelInfo(
                        id=channel.id,
                        name=channel.name,
                        provider=channel.provider,
                        tags=channel.tags,
                        priority=getattr(channel, "priority", None),
                        capabilities=getattr(channel, "capabilities", None),
                        cost_per_token=cost_info,
                        channel_context_length=specs.get("context_length"),
                        channel_capabilities=channel_caps,
                        channel_tags=sorted(model_info.tags),
                    )
                )

            if not channel_list:
                continue

            owner = channel_list[0].provider or "smart-ai-router"
            models_data.append(
                ModelInfo(
                    id=model_id,
                    created=current_time,
                    owned_by=owner,
                    name=model_id,
                    model_type=(
                        "model_group"
                        if model_id.startswith("auto:") or model_id.startswith("tag:")
                        else "model"
                    ),
                    available=True,
                    parameter_count=parameter_count,
                    context_length=context_length,
                    capabilities=model_capabilities,
                    tags=sorted(aggregated_tags),
                    channels=channel_list,
                    channel_count=len(channel_list),
                )
            )

        return ModelsResponse(data=models_data, total_models=len(models_data))

    return router
