"""
Model-Channel级别黑名单管理器
支持细粒度的模型-渠道组合黑名单，而不是整个渠道黑名单
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """错误类型枚举"""

    RATE_LIMIT = "rate_limit"  # 429 - 速率限制
    AUTH_ERROR = "auth_error"  # 401, 403 - 认证错误
    MODEL_UNAVAILABLE = "model_unavailable"  # 404 - 模型不可用
    QUOTA_EXCEEDED = "quota_exceeded"  # 402, 429 with quota - 配额用尽
    SERVER_ERROR = "server_error"  # 500+ - 服务器错误
    TIMEOUT = "timeout"  # 超时错误
    CONNECTION_ERROR = "connection_error"  # 连接错误
    UNKNOWN = "unknown"  # 未知错误


@dataclass
class ModelChannelBlacklistEntry:
    """模型-渠道黑名单条目"""

    channel_id: str
    model_name: str
    error_type: ErrorType
    error_code: int
    error_message: str
    blacklisted_at: datetime
    expires_at: Optional[datetime]
    failure_count: int = 1
    is_permanent: bool = False
    backoff_duration: int = 0  # 退避时间（秒）

    def is_expired(self) -> bool:
        """检查黑名单条目是否已过期"""
        if self.is_permanent:
            return False
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def get_remaining_time(self) -> int:
        """获取剩余黑名单时间（秒）"""
        if self.is_permanent or self.expires_at is None:
            return -1
        remaining = (self.expires_at - datetime.now()).total_seconds()
        return max(0, int(remaining))


class ErrorClassifier:
    """错误分类器，负责分析错误类型并确定退避策略"""

    # 不同错误类型的基础退避时间（秒）
    BASE_BACKOFF_TIMES = {
        ErrorType.RATE_LIMIT: 10,  # 速率限制: 10秒
        ErrorType.AUTH_ERROR: -1,  # 认证错误: 永久
        ErrorType.MODEL_UNAVAILABLE: 300,  # 模型不可用: 5分钟
        ErrorType.QUOTA_EXCEEDED: 1800,  # 配额用尽: 30分钟
        ErrorType.SERVER_ERROR: 60,  # 服务器错误: 1分钟
        ErrorType.TIMEOUT: 30,  # 超时: 30秒
        ErrorType.CONNECTION_ERROR: 30,  # 连接错误: 30秒
        ErrorType.UNKNOWN: 60,  # 未知错误: 1分钟
    }

    @classmethod
    def classify_error(
        cls, status_code: int, error_message: str
    ) -> tuple[ErrorType, int, bool]:
        """
        分类错误并返回错误类型、退避时间、是否永久

        Returns:
            tuple[ErrorType, int, bool]: (错误类型, 退避时间秒, 是否永久)
        """
        error_msg_lower = error_message.lower()

        # 根据HTTP状态码分类
        if status_code == 401:
            return ErrorType.AUTH_ERROR, -1, True
        elif status_code == 403:
            # 403可能是权限问题或临时限制
            if "rate" in error_msg_lower or "limit" in error_msg_lower:
                return (
                    ErrorType.RATE_LIMIT,
                    cls.BASE_BACKOFF_TIMES[ErrorType.RATE_LIMIT],
                    False,
                )
            return ErrorType.AUTH_ERROR, -1, True
        elif status_code == 404:
            return (
                ErrorType.MODEL_UNAVAILABLE,
                cls.BASE_BACKOFF_TIMES[ErrorType.MODEL_UNAVAILABLE],
                False,
            )
        elif status_code == 429:
            # 429可能是速率限制或配额用尽
            if "quota" in error_msg_lower or "balance" in error_msg_lower:
                return (
                    ErrorType.QUOTA_EXCEEDED,
                    cls.BASE_BACKOFF_TIMES[ErrorType.QUOTA_EXCEEDED],
                    False,
                )

            # 尝试从错误消息中提取建议等待时间
            suggested_wait = cls._extract_suggested_wait_time(error_message)
            if suggested_wait:
                return ErrorType.RATE_LIMIT, suggested_wait, False

            return (
                ErrorType.RATE_LIMIT,
                cls.BASE_BACKOFF_TIMES[ErrorType.RATE_LIMIT],
                False,
            )
        elif status_code >= 500:
            return (
                ErrorType.SERVER_ERROR,
                cls.BASE_BACKOFF_TIMES[ErrorType.SERVER_ERROR],
                False,
            )
        else:
            return ErrorType.UNKNOWN, cls.BASE_BACKOFF_TIMES[ErrorType.UNKNOWN], False

    @classmethod
    def _extract_suggested_wait_time(cls, error_message: str) -> Optional[int]:
        """从错误消息中提取建议等待时间"""
        import re

        # 常见的等待时间模式
        patterns = [
            r"retry after (\d+) seconds?",
            r"try again in (\d+) seconds?",
            r"wait (\d+) seconds?",
            r"please retry shortly, or add your own key.*?(\d+)",  # OpenRouter特定模式
        ]

        for pattern in patterns:
            match = re.search(pattern, error_message.lower())
            if match:
                wait_time = int(match.group(1))
                return min(wait_time, 300)  # 最长5分钟

        return None


class ModelChannelBlacklistManager:
    """模型-渠道级别黑名单管理器"""

    def __init__(self):
        self._blacklist: dict[str, ModelChannelBlacklistEntry] = {}
        self._lock = asyncio.Lock()
        self._channel_failure_counts: dict[str, int] = {}  # 渠道级别失败计数

    def _generate_key(self, channel_id: str, model_name: str) -> str:
        """生成模型-渠道组合键"""
        return f"{channel_id}#{model_name.lower()}"

    async def add_blacklist_entry(
        self, channel_id: str, model_name: str, error_code: int, error_message: str
    ) -> bool:
        """
        添加黑名单条目

        Args:
            channel_id: 渠道ID
            model_name: 模型名称
            error_code: HTTP错误代码
            error_message: 错误消息

        Returns:
            bool: 是否应该同时拉黑整个渠道
        """
        async with self._lock:
            key = self._generate_key(channel_id, model_name)

            # 分析错误类型
            error_type, base_duration, is_permanent = ErrorClassifier.classify_error(
                error_code, error_message
            )

            # 计算实际退避时间
            duration = base_duration
            if key in self._blacklist:
                # 已存在条目，增加失败计数并可能延长时间
                entry = self._blacklist[key]
                entry.failure_count += 1
                entry.error_message = error_message
                entry.blacklisted_at = datetime.now()

                # 指数退避：每次失败时间翻倍，最长1小时
                if not is_permanent and entry.failure_count >= 2:
                    duration = min(
                        base_duration * (2 ** (entry.failure_count - 1)), 3600
                    )

                entry.backoff_duration = duration
                entry.expires_at = (
                    None
                    if is_permanent
                    else datetime.now() + timedelta(seconds=duration)
                )

                logger.warning(
                    f"🔄 BLACKLIST UPDATED: {model_name}@{channel_id} failed {entry.failure_count} times, "
                    f"backoff: {'permanent' if is_permanent else f'{duration}s'}"
                )
            else:
                # 创建新条目
                expires_at = (
                    None
                    if is_permanent
                    else datetime.now() + timedelta(seconds=duration)
                )
                entry = ModelChannelBlacklistEntry(
                    channel_id=channel_id,
                    model_name=model_name,
                    error_type=error_type,
                    error_code=error_code,
                    error_message=error_message,
                    blacklisted_at=datetime.now(),
                    expires_at=expires_at,
                    is_permanent=is_permanent,
                    backoff_duration=duration,
                )
                self._blacklist[key] = entry

                logger.warning(
                    f"🚫 MODEL BLACKLISTED: {model_name}@{channel_id} due to {error_type.value} "
                    f"(HTTP {error_code}), backoff: {'permanent' if is_permanent else f'{duration}s'}"
                )

            # 更新渠道级别失败计数
            self._channel_failure_counts[channel_id] = (
                self._channel_failure_counts.get(channel_id, 0) + 1
            )

            # 决定是否拉黑整个渠道
            should_blacklist_channel = self._should_blacklist_entire_channel(
                channel_id, error_type
            )
            if should_blacklist_channel:
                logger.error(
                    f"🔴 CHANNEL BLACKLISTED: {channel_id} due to multiple failures or critical errors"
                )

            return should_blacklist_channel

    def is_model_blacklisted(
        self, channel_id: str, model_name: str
    ) -> tuple[bool, Optional[ModelChannelBlacklistEntry]]:
        """
        检查特定模型在特定渠道是否被拉黑

        Returns:
            tuple[bool, Optional[ModelChannelBlacklistEntry]]: (是否被拉黑, 黑名单条目)
        """
        key = self._generate_key(channel_id, model_name)

        if key not in self._blacklist:
            return False, None

        entry = self._blacklist[key]

        # 检查是否过期
        if entry.is_expired():
            del self._blacklist[key]
            logger.info(
                f"✅ BLACKLIST EXPIRED: {model_name}@{channel_id} is now available again"
            )
            return False, None

        return True, entry

    def get_blacklisted_models_for_channel(self, channel_id: str) -> list[str]:
        """获取指定渠道上所有被拉黑的模型"""
        blacklisted_models = []

        # 清理过期条目并收集当前被拉黑的模型
        expired_keys = []
        for key, entry in self._blacklist.items():
            if entry.channel_id == channel_id:
                if entry.is_expired():
                    expired_keys.append(key)
                else:
                    blacklisted_models.append(entry.model_name)

        # 清理过期条目
        for key in expired_keys:
            del self._blacklist[key]

        return blacklisted_models

    def get_available_channels_for_model(
        self, model_name: str, all_channel_ids: list[str]
    ) -> list[str]:
        """获取指定模型的可用渠道列表"""
        available_channels = []

        for channel_id in all_channel_ids:
            is_blacklisted, _ = self.is_model_blacklisted(channel_id, model_name)
            if not is_blacklisted:
                available_channels.append(channel_id)

        return available_channels

    async def remove_blacklist_entry(self, channel_id: str, model_name: str) -> bool:
        """
        移除黑名单条目（用于手动恢复或健康检查恢复）

        Returns:
            bool: 是否成功移除
        """
        async with self._lock:
            key = self._generate_key(channel_id, model_name)

            if key in self._blacklist:
                del self._blacklist[key]
                logger.info(
                    f"✅ BLACKLIST REMOVED: {model_name}@{channel_id} manually recovered"
                )
                return True

            return False

    def get_blacklist_stats(self) -> dict[str, Any]:
        """获取黑名单统计信息"""
        total_entries = len(self._blacklist)
        permanent_count = sum(
            1 for entry in self._blacklist.values() if entry.is_permanent
        )
        temporary_count = total_entries - permanent_count

        # 按渠道分组
        by_channel = {}
        for entry in self._blacklist.values():
            if entry.channel_id not in by_channel:
                by_channel[entry.channel_id] = []
            by_channel[entry.channel_id].append(
                {
                    "model": entry.model_name,
                    "error_type": entry.error_type.value,
                    "remaining_time": entry.get_remaining_time(),
                    "failure_count": entry.failure_count,
                }
            )

        # 按错误类型分组
        by_error_type = {}
        for entry in self._blacklist.values():
            error_type = entry.error_type.value
            by_error_type[error_type] = by_error_type.get(error_type, 0) + 1

        return {
            "total_blacklisted": total_entries,
            "permanent_blacklisted": permanent_count,
            "temporary_blacklisted": temporary_count,
            "by_channel": by_channel,
            "by_error_type": by_error_type,
            "channel_failure_counts": self._channel_failure_counts.copy(),
        }

    def _should_blacklist_entire_channel(
        self, channel_id: str, error_type: ErrorType
    ) -> bool:
        """判断是否应该拉黑整个渠道"""
        # 认证错误直接拉黑整个渠道
        if error_type in [ErrorType.AUTH_ERROR]:
            return True

        # 检查该渠道的总失败次数
        total_failures = self._channel_failure_counts.get(channel_id, 0)

        # 如果渠道失败次数过多，拉黑整个渠道
        if total_failures >= 5:
            return True

        # 检查该渠道被拉黑的模型比例
        channel_entries = [
            e for e in self._blacklist.values() if e.channel_id == channel_id
        ]
        if len(channel_entries) >= 3:  # 如果3个或更多模型被拉黑
            return True

        return False

    def cleanup_expired_entries(self) -> int:
        """清理过期的黑名单条目，返回清理数量"""
        expired_keys = []

        for key, entry in self._blacklist.items():
            if entry.is_expired():
                expired_keys.append(key)

        for key in expired_keys:
            entry = self._blacklist[key]
            del self._blacklist[key]
            logger.debug(
                f"🧹 CLEANUP: Removed expired blacklist entry for {entry.model_name}@{entry.channel_id}"
            )

        return len(expired_keys)


# 全局单例实例
_global_blacklist_manager: Optional[ModelChannelBlacklistManager] = None


def get_model_blacklist_manager() -> ModelChannelBlacklistManager:
    """获取全局模型黑名单管理器实例"""
    global _global_blacklist_manager

    if _global_blacklist_manager is None:
        _global_blacklist_manager = ModelChannelBlacklistManager()

    return _global_blacklist_manager
