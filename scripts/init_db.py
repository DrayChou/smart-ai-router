#!/usr/bin/env python3
"""
数据库初始化脚本
- 创建必要的Provider记录
- 初始化默认Model Group配置
- 创建示例Channel和API Key记录
"""
import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.database import get_db_session, init_db
from core.models.api_key import ApiKey
from core.models.channel import Channel
from core.models.model_group import ModelGroupChannel, VirtualModelGroup
from core.models.provider import Provider
from core.utils.logger import get_logger

logger = get_logger(__name__)


async def create_default_providers():
    """创建默认的Provider记录"""
    providers_data = [
        {
            "name": "openai",
            "display_name": "OpenAI Official",
            "type": "official",
            "adapter_class": "OpenAIAdapter",
            "base_url": "https://api.openai.com",
            "auth_type": "bearer",
            "pricing_config": {
                "default_input_cost": 0.03,  # GPT-4默认价格
                "default_output_cost": 0.06,
                "models": {
                    "gpt-4o": {"input": 0.005, "output": 0.015},
                    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
                    "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
                },
            },
            "capability_mapping": {
                "gpt-4o": ["text", "vision", "function_calling", "json_mode"],
                "gpt-4o-mini": ["text", "function_calling", "json_mode"],
                "gpt-3.5-turbo": ["text", "function_calling", "json_mode"],
            },
            "status": "active",
        },
        {
            "name": "anthropic",
            "display_name": "Anthropic Official",
            "type": "official",
            "adapter_class": "AnthropicAdapter",
            "base_url": "https://api.anthropic.com",
            "auth_type": "x-api-key",
            "pricing_config": {
                "default_input_cost": 0.015,
                "default_output_cost": 0.075,
                "models": {
                    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
                    "claude-3-5-haiku-20241022": {"input": 0.001, "output": 0.005},
                    "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
                },
            },
            "capability_mapping": {
                "claude-3-5-sonnet-20241022": [
                    "text",
                    "vision",
                    "function_calling",
                    "code_generation",
                ],
                "claude-3-5-haiku-20241022": ["text", "function_calling"],
                "claude-3-opus-20240229": ["text", "vision", "function_calling"],
            },
            "status": "active",
        },
        {
            "name": "groq",
            "display_name": "Groq (Free Tier)",
            "type": "aggregator",
            "adapter_class": "GroqAdapter",
            "base_url": "https://api.groq.com",
            "auth_type": "bearer",
            "pricing_config": {
                "default_input_cost": 0.0,  # 免费
                "default_output_cost": 0.0,
                "models": {
                    "llama-3.1-8b-instant": {"input": 0.0, "output": 0.0},
                    "llama-3.1-70b-versatile": {"input": 0.0, "output": 0.0},
                    "mixtral-8x7b-32768": {"input": 0.0, "output": 0.0},
                },
            },
            "capability_mapping": {
                "llama-3.1-8b-instant": ["text", "function_calling"],
                "llama-3.1-70b-versatile": ["text", "function_calling"],
                "mixtral-8x7b-32768": ["text", "function_calling"],
            },
            "rate_limits": {
                "requests_per_minute": 30,
                "requests_per_day": 14400,
                "tokens_per_minute": 7000,
            },
            "status": "active",
        },
    ]

    async with get_db_session() as session:
        for provider_data in providers_data:
            # 检查是否已存在
            existing = await session.get(Provider, provider_data["name"])
            if not existing:
                provider = Provider(**provider_data)
                session.add(provider)
                logger.info(f"创建Provider: {provider_data['name']}")
            else:
                logger.info(f"Provider已存在: {provider_data['name']}")

        await session.commit()


async def create_default_model_groups():
    """创建默认的Model Group配置"""
    model_groups_data = [
        {
            "name": "auto:free",
            "display_name": "免费模型组",
            "description": "包含所有免费AI模型，按速度和可用性智能路由",
            "routing_strategy": [
                {"field": "effective_cost", "order": "asc", "weight": 1.0},
                {"field": "speed_score", "order": "desc", "weight": 0.9},
                {"field": "health_score", "order": "desc", "weight": 0.8},
            ],
            "filters": {
                "max_cost_per_1k": 0.001,  # 几乎免费
                "min_quality_score": 0.6,
                "required_capabilities": [],
                "supports_streaming": True,
            },
            "budget_limits": {
                "daily_budget": 0.0,  # 完全免费
                "max_cost_per_request": 0.0,
            },
            "status": "active",
        },
        {
            "name": "auto:fast",
            "display_name": "快速模型组",
            "description": "注重响应速度的模型组合，适合实时对话场景",
            "routing_strategy": [
                {"field": "speed_score", "order": "desc", "weight": 1.0},
                {"field": "effective_cost", "order": "asc", "weight": 0.7},
                {"field": "health_score", "order": "desc", "weight": 0.9},
            ],
            "filters": {
                "max_cost_per_1k": 5.0,
                "min_quality_score": 0.7,
                "required_capabilities": ["text"],
                "max_latency_ms": 3000,
                "supports_streaming": True,
            },
            "budget_limits": {"daily_budget": 10.0, "max_cost_per_request": 1.0},
            "status": "active",
        },
        {
            "name": "auto:smart",
            "display_name": "智能模型组",
            "description": "质量优先的高端模型组合，适合复杂推理任务",
            "routing_strategy": [
                {"field": "quality_score", "order": "desc", "weight": 1.0},
                {"field": "capability_score", "order": "desc", "weight": 0.9},
                {"field": "effective_cost", "order": "asc", "weight": 0.5},
            ],
            "filters": {
                "max_cost_per_1k": 20.0,
                "min_quality_score": 0.8,
                "required_capabilities": ["text", "function_calling"],
                "optional_capabilities": ["vision", "code_generation"],
            },
            "budget_limits": {"daily_budget": 50.0, "max_cost_per_request": 5.0},
            "status": "active",
        },
    ]

    async with get_db_session() as session:
        for mg_data in model_groups_data:
            # 检查是否已存在
            existing = await session.get(VirtualModelGroup, mg_data["name"])
            if not existing:
                model_group = VirtualModelGroup(**mg_data)
                session.add(model_group)
                logger.info(f"创建Model Group: {mg_data['name']}")
            else:
                logger.info(f"Model Group已存在: {mg_data['name']}")

        await session.commit()


async def create_sample_channels():
    """创建示例Channel记录"""
    # 只有在设置了API密钥时才创建Channel
    sample_channels = []

    # OpenAI示例
    if os.getenv("OPENAI_API_KEY"):
        sample_channels.append(
            {
                "provider_name": "openai",
                "name": "OpenAI GPT-4o Mini",
                "model_name": "gpt-4o-mini",
                "endpoint": "https://api.openai.com/v1/chat/completions",
                "priority": 1,
                "weight": 10,
                "input_cost_per_1k": 0.00015,
                "output_cost_per_1k": 0.0006,
                "daily_request_limit": 1000,
                "status": "active",
                "api_key": os.getenv("OPENAI_API_KEY"),
            }
        )

    # Groq示例
    if os.getenv("GROQ_API_KEY"):
        sample_channels.append(
            {
                "provider_name": "groq",
                "name": "Groq Llama-3.1-8B",
                "model_name": "llama-3.1-8b-instant",
                "endpoint": "https://api.groq.com/openai/v1/chat/completions",
                "priority": 1,
                "weight": 10,
                "input_cost_per_1k": 0.0,
                "output_cost_per_1k": 0.0,
                "daily_request_limit": 10000,
                "status": "active",
                "api_key": os.getenv("GROQ_API_KEY"),
            }
        )

    if not sample_channels:
        logger.info("未设置API密钥，跳过创建示例Channel")
        return

    async with get_db_session() as session:
        for channel_data in sample_channels:
            api_key = channel_data.pop("api_key")
            provider_name = channel_data.pop("provider_name")

            # 获取Provider ID
            provider = await session.get(Provider, provider_name)
            if not provider:
                logger.warning(f"Provider不存在: {provider_name}")
                continue

            channel_data["provider_id"] = provider.id

            # 创建Channel
            channel = Channel(**channel_data)
            session.add(channel)
            await session.flush()  # 获取channel.id

            # 创建API Key
            api_key_obj = ApiKey(
                channel_id=channel.id,
                key_name=f"{channel.name} API Key",
                key_value=api_key,  # 在生产环境中应该加密
                status="active",
            )
            session.add(api_key_obj)

            logger.info(f"创建Channel: {channel.name}")

        await session.commit()


async def setup_model_group_mappings():
    """设置Model Group和Channel的映射关系"""
    async with get_db_session() as session:
        # 获取所有活跃的Channel
        from sqlalchemy import select

        channels = await session.execute(
            select(Channel).where(Channel.status == "active")
        )
        channels = channels.scalars().all()

        if not channels:
            logger.info("没有活跃的Channel，跳过设置Model Group映射")
            return

        # 为每个Model Group添加合适的Channel
        mappings = [
            {
                "model_group_name": "auto:free",
                "channel_filter": lambda c: c.input_cost_per_1k == 0.0,  # 免费模型
                "priority": 1,
                "speed_score": 0.8,
                "quality_score": 0.6,
            },
            {
                "model_group_name": "auto:fast",
                "channel_filter": lambda c: True,  # 所有模型
                "priority": 2,
                "speed_score": 0.9,
                "quality_score": 0.7,
            },
            {
                "model_group_name": "auto:smart",
                "channel_filter": lambda c: c.input_cost_per_1k > 0.001,  # 收费模型
                "priority": 3,
                "speed_score": 0.7,
                "quality_score": 0.9,
            },
        ]

        for mapping in mappings:
            model_group = await session.get(
                VirtualModelGroup, mapping["model_group_name"]
            )
            if not model_group:
                continue

            for channel in channels:
                if mapping["channel_filter"](channel):
                    # 检查映射是否已存在
                    existing = await session.execute(
                        select(ModelGroupChannel).where(
                            ModelGroupChannel.model_group_id == model_group.id,
                            ModelGroupChannel.channel_id == channel.id,
                        )
                    )
                    if existing.scalar():
                        continue

                    # 创建映射
                    mg_channel = ModelGroupChannel(
                        model_group_id=model_group.id,
                        channel_id=channel.id,
                        priority=mapping["priority"],
                        speed_score=mapping["speed_score"],
                        quality_score=mapping["quality_score"],
                        reliability_score=1.0,
                        enabled=True,
                    )
                    session.add(mg_channel)
                    logger.info(f"添加映射: {model_group.name} -> {channel.name}")

        await session.commit()


async def main():
    """主函数"""
    logger.info("开始数据库初始化...")

    try:
        # 初始化数据库连接
        await init_db()

        # 创建默认数据
        await create_default_providers()
        await create_default_model_groups()
        await create_sample_channels()
        await setup_model_group_mappings()

        logger.info("数据库初始化完成!")

    except Exception as e:
        logger.error(f"数据库初始化失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
