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
from core.services import get_model_service

from core.utils.memory_index import get_memory_index

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
    tags: Optional[List[str]] = None
    priority: Optional[int] = None
    capabilities: Optional[List[str]] = None
    cost_per_token: Optional[ChannelCost] = None
    # 渠道特定的模型信息覆盖
    channel_context_length: Optional[int] = None
    channel_capabilities: Optional[ModelCapabilities] = None
    # 渠道特定的tags（从渠道配置或模型分析得出）
    channel_tags: Optional[List[str]] = None

class ModelInfo(BaseModel):
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
        """返回所有可用的模型，包含详细信息"""
        model_service = get_model_service()
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

        for model_id in sorted(list(all_models)):
            # 获取模型的详细信息（使用新的服务架构）
            base_model_info = model_service.get_model_info(model_id)
            
            # 构建基础能力信息
            capabilities = None
            if base_model_info and base_model_info.capabilities:
                capabilities = ModelCapabilities(
                    supports_vision=base_model_info.capabilities.supports_vision,
                    supports_function_calling=base_model_info.capabilities.supports_function_calling,
                    supports_code_generation=base_model_info.capabilities.supports_code_generation,
                    supports_streaming=base_model_info.capabilities.supports_streaming
                )

            # 获取模型支持的所有渠道
            channel_list = []
            channel_ids = model_channels_map.get(model_id, [])

            for channel_id in channel_ids:
                if channel_id in channels:
                    channel = channels[channel_id]
                    
                    # 获取该渠道对该模型的特定信息（可能包含覆盖）
                    channel_model_info = model_service.get_model_info(model_id, channel_id=channel_id)

                    # 构建成本信息（应用汇率折扣）
                    cost_info = None
                    if hasattr(channel, 'cost_per_token') and channel.cost_per_token:
                        try:
                            # 优先使用增强的CostEstimator（包含汇率折扣）
                            from core.utils.cost_estimator import CostEstimator
                            estimator = CostEstimator()
                            model_pricing = estimator._get_model_pricing(channel.id, model_id)
                            
                            if model_pricing and 'input' in model_pricing and 'output' in model_pricing:
                                cost_info = ChannelCost(
                                    input=model_pricing['input'],
                                    output=model_pricing['output']
                                )
                                logger.info(f"💰 MODELS API: Applied currency discount for {channel.id} | {model_id} | input: ${model_pricing['input']:,.6f}, output: ${model_pricing['output']:,.6f}")
                            else:
                                # 回退到静态定价
                                cost_info = ChannelCost(
                                    input=channel.cost_per_token.get('input'),
                                    output=channel.cost_per_token.get('output')
                                )
                        except Exception as e:
                            logger.warning(f"Cost estimation failed for {channel.id}, using static pricing: {e}")
                            # 回退到静态定价
                            cost_info = ChannelCost(
                                input=channel.cost_per_token.get('input'),
                                output=channel.cost_per_token.get('output')
                            )

                    # 构建渠道特定的能力信息和tags
                    channel_capabilities = None
                    channel_context = None
                    channel_specific_tags = [channel.id]  # 至少包含渠道ID
                    
                    # 添加渠道名称作为标签（如果与ID不同）
                    if channel.name and channel.name.lower() != channel.id.lower():
                        channel_specific_tags.append(channel.name.lower())
                    
                    if channel_model_info:
                        if channel_model_info.capabilities:
                            channel_capabilities = ModelCapabilities(
                                supports_vision=channel_model_info.capabilities.supports_vision,
                                supports_function_calling=channel_model_info.capabilities.supports_function_calling,
                                supports_code_generation=channel_model_info.capabilities.supports_code_generation,
                                supports_streaming=channel_model_info.capabilities.supports_streaming
                            )
                        if channel_model_info.specs and channel_model_info.specs.context_length:
                            channel_context = channel_model_info.specs.context_length
                        # 添加渠道模型特定的tags（如果有的话）
                        if channel_model_info.tags:
                            channel_specific_tags.extend(channel_model_info.tags)

                    channel_list.append(ChannelInfo(
                        id=channel.id,
                        name=channel.name,
                        provider=getattr(channel, 'provider', None),
                        tags=getattr(channel, 'tags', None),
                        priority=getattr(channel, 'priority', None),
                        capabilities=getattr(channel, 'capabilities', None),
                        cost_per_token=cost_info,
                        channel_context_length=channel_context,
                        channel_capabilities=channel_capabilities,
                        channel_tags=channel_specific_tags
                    ))

            # 构建模型基础信息
            parameter_count = None
            parameter_size_text = None
            context_length = None
            context_text = None
            input_price = None
            output_price = None
            model_tags = None

            if base_model_info:
                if base_model_info.specs:
                    parameter_count = base_model_info.specs.parameter_count
                    parameter_size_text = base_model_info.specs.parameter_size_text
                    context_length = base_model_info.specs.context_length
                    context_text = base_model_info.specs.context_text
                if base_model_info.pricing:
                    input_price = base_model_info.pricing.input_price
                    output_price = base_model_info.pricing.output_price
                if base_model_info.tags:
                    model_tags = list(base_model_info.tags)
            
            # 从内存索引获取模型的自动提取tags（如果没有从base_model_info获取到）
            if not model_tags and memory_index:
                try:
                    # 不使用渠道的provider字段，因为它表示API协议兼容性而非模型提供商
                    # 让标签生成器从模型名称本身推断真实的提供商信息
                    extracted_tags = memory_index._generate_model_tags(model_id, "")
                    if extracted_tags:
                        # 过滤掉空字符串标签
                        model_tags = [tag for tag in extracted_tags if tag and tag.strip()]
                except Exception as e:
                    logger.debug(f"Failed to get tags for model {model_id}: {e}")
                    pass

            models_data.append(ModelInfo(
                id=model_id,
                created=current_time,
                owned_by="smart-ai-router",
                name=model_id,
                model_type="model_group" if model_id.startswith("auto:") or model_id.startswith("tag:") else "model",
                available=True,
                
                # 模型详细信息
                parameter_count=parameter_count,
                parameter_size_text=parameter_size_text,
                context_length=context_length,
                context_text=context_text,
                capabilities=capabilities,
                input_price=input_price,
                output_price=output_price,
                tags=model_tags,
                
                # 渠道信息
                channels=channel_list if channel_list else None,
                channel_count=len(channel_list) if channel_list else 0
            ))

        return ModelsResponse(data=models_data, total_models=len(models_data))

    return router
