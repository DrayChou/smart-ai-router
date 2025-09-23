"""
请求间隔管理器 - 确保渠道遵守最小请求间隔
"""

import asyncio
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class RequestIntervalManager:
    """
    请求间隔管理器 - 基于渠道ID管理请求时间间隔

    为了避免触发速率限制（特别是 OpenRouter 免费模型的 20请求/分钟 限制），
    此管理器确保每个渠道在发起新请求前等待足够的时间间隔。
    """

    def __init__(self):
        # 存储每个渠道的最后请求时间
        self._last_request_times: dict[str, float] = {}
        # 线程锁确保并发安全
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def wait_if_needed(self, channel_id: str, min_interval: int) -> bool:
        """
        如果需要，等待足够的时间间隔

        Args:
            channel_id: 渠道ID
            min_interval: 最小间隔时间(秒)，0表示无限制

        Returns:
            bool: True if waited, False if no wait was needed
        """
        if min_interval <= 0:
            return False

        async with self._locks[channel_id]:
            current_time = time.time()
            last_request_time = self._last_request_times.get(channel_id, 0)

            time_since_last = current_time - last_request_time
            wait_time = min_interval - time_since_last

            if wait_time > 0:
                logger.info(
                    f"⏳ RATE LIMIT INTERVAL: Channel '{channel_id}' waiting {wait_time:.1f}s "
                    f"(min_interval={min_interval}s, last_request={time_since_last:.1f}s ago)"
                )
                await asyncio.sleep(wait_time)

                # 更新请求时间
                self._last_request_times[channel_id] = time.time()
                return True
            else:
                # 无需等待，直接更新请求时间
                self._last_request_times[channel_id] = current_time
                return False

    def is_channel_ready(self, channel_id: str, min_interval: int) -> bool:
        """
        检查渠道是否可以立即使用（无需等待）

        Args:
            channel_id: 渠道ID
            min_interval: 最小间隔时间(秒)，0表示无限制

        Returns:
            bool: True if channel is ready to use immediately, False if needs to wait
        """
        if min_interval <= 0:
            return True

        current_time = time.time()
        last_request_time = self._last_request_times.get(channel_id, 0)
        time_since_last = current_time - last_request_time
        wait_time = min_interval - time_since_last

        return wait_time <= 0

    def record_request(self, channel_id: str):
        """
        记录请求时间（用于同步调用场景）

        Args:
            channel_id: 渠道ID
        """
        self._last_request_times[channel_id] = time.time()

    def get_remaining_wait_time(self, channel_id: str, min_interval: int) -> float:
        """
        获取剩余等待时间

        Args:
            channel_id: 渠道ID
            min_interval: 最小间隔时间(秒)

        Returns:
            float: 剩余等待时间(秒)，0表示无需等待
        """
        if min_interval <= 0:
            return 0.0

        current_time = time.time()
        last_request_time = self._last_request_times.get(channel_id, 0)
        time_since_last = current_time - last_request_time
        wait_time = max(0, min_interval - time_since_last)

        return wait_time

    def clear_channel_history(self, channel_id: str):
        """
        清除指定渠道的请求历史（用于重置或错误恢复）

        Args:
            channel_id: 渠道ID
        """
        if channel_id in self._last_request_times:
            del self._last_request_times[channel_id]
        if channel_id in self._locks:
            del self._locks[channel_id]

    def get_stats(self) -> dict:
        """
        获取管理器统计信息

        Returns:
            dict: 统计信息
        """
        current_time = time.time()
        stats = {"total_channels": len(self._last_request_times), "channels": {}}

        for channel_id, last_time in self._last_request_times.items():
            stats["channels"][channel_id] = {
                "last_request_time": last_time,
                "time_since_last": current_time - last_time,
            }

        return stats


# 全局实例
_request_interval_manager = None


def get_request_interval_manager() -> RequestIntervalManager:
    """获取全局请求间隔管理器实例"""
    global _request_interval_manager
    if _request_interval_manager is None:
        _request_interval_manager = RequestIntervalManager()
    return _request_interval_manager
