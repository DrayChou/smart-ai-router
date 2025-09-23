"""
Channel management system
渠道管理系统
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db_session
from core.models.channel import Channel
from core.models.model_group import ModelGroupChannel
from core.models.virtual_model import VirtualModelGroup
from core.utils.logger import get_logger

logger = get_logger(__name__)


class ChannelManager:
    """渠道管理器"""

    def __init__(self):
        pass

    async def get_channels_for_model_group(
        self, model_group_name: str, session: Optional[AsyncSession] = None
    ) -> List[Channel]:
        """获取模型组的所有可用渠道"""

        async def _get_channels(db_session: AsyncSession) -> List[Channel]:
            # 查询模型组
            model_group_result = await db_session.execute(
                select(VirtualModelGroup).where(
                    VirtualModelGroup.name == model_group_name
                )
            )
            model_group = model_group_result.scalar_one_or_none()

            if not model_group:
                logger.warning(f"模型组不存在: {model_group_name}")
                return []

            # 查询模型组关联的渠道
            channels_result = await db_session.execute(
                select(Channel)
                .join(ModelGroupChannel)
                .where(
                    and_(
                        ModelGroupChannel.model_group_id == model_group.id,
                        ModelGroupChannel.enabled == True,
                        Channel.status == "active",
                    )
                )
                .order_by(Channel.priority, Channel.id)
            )

            channels = channels_result.scalars().all()
            return list(channels)

        if session:
            return await _get_channels(session)
        else:
            async with get_db_session() as db_session:
                return await _get_channels(db_session)

    async def get_channel_by_id(
        self, channel_id: int, session: Optional[AsyncSession] = None
    ) -> Optional[Channel]:
        """根据ID获取渠道"""

        async def _get_channel(db_session: AsyncSession) -> Optional[Channel]:
            result = await db_session.execute(
                select(Channel).where(Channel.id == channel_id)
            )
            return result.scalar_one_or_none()

        if session:
            return await _get_channel(session)
        else:
            async with get_db_session() as db_session:
                return await _get_channel(db_session)

    async def update_channel_usage(
        self,
        channel_id: int,
        success: bool = True,
        error_type: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """更新渠道使用统计"""

        async def _update_usage(db_session: AsyncSession):
            channel = await self.get_channel_by_id(channel_id, db_session)
            if not channel:
                return

            # 更新请求计数
            channel.daily_request_count = (channel.daily_request_count or 0) + 1

            if success:
                channel.last_success_at = datetime.utcnow()
                # 提升健康度
                current_health = float(channel.health_score or 0.8)
                channel.health_score = min(1.0, current_health + 0.01)
            else:
                channel.last_error_at = datetime.utcnow()
                # 降低健康度
                current_health = float(channel.health_score or 0.8)
                channel.health_score = max(0.0, current_health - 0.05)

                # 根据错误类型设置冷却期
                if error_type == "rate_limit_exceeded":
                    channel.cooldown_until = datetime.utcnow() + timedelta(minutes=5)
                    channel.status = "cooling"
                elif error_type == "quota_exceeded":
                    channel.status = "quota_exceeded"
                elif error_type == "invalid_api_key":
                    channel.status = "disabled"

            await db_session.commit()

        if session:
            await _update_usage(session)
        else:
            async with get_db_session() as db_session:
                await _update_usage(db_session)

    async def check_channel_cooldowns(self) -> None:
        """检查并恢复冷却期结束的渠道"""
        async with get_db_session() as session:
            # 查询冷却期结束的渠道
            now = datetime.utcnow()
            result = await session.execute(
                select(Channel).where(
                    and_(Channel.status == "cooling", Channel.cooldown_until <= now)
                )
            )

            channels = result.scalars().all()

            for channel in channels:
                channel.status = "active"
                channel.cooldown_until = None
                logger.info(f"渠道 {channel.name} 冷却期结束，重新激活")

            await session.commit()

    async def reset_daily_quotas(self) -> None:
        """重置每日配额"""
        async with get_db_session() as session:
            # 重置所有渠道的每日配额
            result = await session.execute(
                select(Channel).where(Channel.daily_request_count > 0)
            )

            channels = result.scalars().all()

            for channel in channels:
                channel.daily_request_count = 0
                channel.quota_reset_date = datetime.utcnow().date()

                # 如果状态是quota_exceeded，恢复为active
                if channel.status == "quota_exceeded":
                    channel.status = "active"

            logger.info(f"重置了 {len(channels)} 个渠道的每日配额")
            await session.commit()

    async def get_channel_health_report(self) -> dict:
        """获取渠道健康状况报告"""
        async with get_db_session() as session:
            # 统计各种状态的渠道数量
            result = await session.execute(select(Channel.status, Channel.health_score))

            channels = result.all()

            status_count = {}
            health_scores = []

            for status, health_score in channels:
                status_count[status] = status_count.get(status, 0) + 1
                if health_score:
                    health_scores.append(float(health_score))

            avg_health = sum(health_scores) / len(health_scores) if health_scores else 0

            return {
                "total_channels": len(channels),
                "status_distribution": status_count,
                "average_health_score": round(avg_health, 3),
                "healthy_channels": len([h for h in health_scores if h >= 0.8]),
                "unhealthy_channels": len([h for h in health_scores if h < 0.5]),
            }


# 全局渠道管理器实例
_channel_manager = None


def get_channel_manager() -> ChannelManager:
    """获取全局渠道管理器实例"""
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = ChannelManager()
    return _channel_manager
