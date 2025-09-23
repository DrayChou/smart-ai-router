"""
黑名单恢复管理器 - 自动检测和恢复被拉黑的模型-渠道组合
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import httpx

from ..config_models import Channel
from ..yaml_config import get_yaml_config_loader
from .model_channel_blacklist import (
    ErrorType,
    ModelChannelBlacklistEntry,
    get_model_blacklist_manager,
)

logger = logging.getLogger(__name__)


@dataclass
class RecoveryAttempt:
    """恢复尝试记录"""

    channel_id: str
    model_name: str
    attempted_at: datetime
    success: bool
    error_message: Optional[str] = None
    response_time: Optional[float] = None


class BlacklistRecoveryManager:
    """黑名单恢复管理器"""

    def __init__(self):
        self.config_loader = get_yaml_config_loader()
        self.blacklist_manager = get_model_blacklist_manager()
        self.recovery_history: list[RecoveryAttempt] = []

        # 恢复配置
        self.recovery_interval = 300  # 5分钟检查一次
        self.max_recovery_attempts = 3  # 每个组合最多尝试3次恢复
        self.health_check_timeout = 10  # 健康检查超时时间

        self._recovery_task: Optional[asyncio.Task] = None
        self._running = False

    async def start_recovery_service(self):
        """启动恢复服务"""
        if self._running:
            return

        self._running = True
        self._recovery_task = asyncio.create_task(self._recovery_loop())
        logger.info("🔄 Blacklist recovery service started")

    async def stop_recovery_service(self):
        """停止恢复服务"""
        if not self._running:
            return

        self._running = False
        if self._recovery_task:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass

        logger.info("🔄 Blacklist recovery service stopped")

    async def _recovery_loop(self):
        """恢复服务主循环"""
        while self._running:
            try:
                await self._perform_recovery_check()
                await asyncio.sleep(self.recovery_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Recovery loop error: {e}")
                await asyncio.sleep(60)  # 出错后等待1分钟

    async def _perform_recovery_check(self):
        """执行恢复检查"""
        logger.debug("🔄 Starting blacklist recovery check")

        # 获取黑名单统计信息
        stats = self.blacklist_manager.get_blacklist_stats()

        if stats["total_blacklisted"] == 0:
            logger.debug("🔄 No blacklisted entries to recover")
            return

        recovery_candidates = self._find_recovery_candidates()

        if not recovery_candidates:
            logger.debug("🔄 No recovery candidates found")
            return

        logger.info(f"🔄 Found {len(recovery_candidates)} recovery candidates")

        # 并发执行恢复尝试
        tasks = [
            self._attempt_recovery(channel_id, model_name, entry)
            for channel_id, model_name, entry in recovery_candidates
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for result in results if result is True)
        failed_count = len(results) - success_count

        if success_count > 0:
            logger.info(
                f"✅ Recovery completed: {success_count} successful, {failed_count} failed"
            )
        else:
            logger.debug(f"🔄 Recovery completed: 0 successful, {failed_count} failed")

    def _find_recovery_candidates(
        self,
    ) -> list[tuple[str, str, ModelChannelBlacklistEntry]]:
        """找到恢复候选项"""
        candidates = []
        current_time = datetime.now()

        for entry in self.blacklist_manager._blacklist.values():
            # 跳过永久黑名单
            if entry.is_permanent:
                continue

            # 跳过还未到期的条目
            if entry.expires_at and current_time < entry.expires_at:
                continue

            # 检查是否尝试过太多次恢复
            recent_attempts = [
                attempt
                for attempt in self.recovery_history
                if (
                    attempt.channel_id == entry.channel_id
                    and attempt.model_name == entry.model_name
                    and current_time - attempt.attempted_at < timedelta(hours=1)
                )
            ]

            if len(recent_attempts) >= self.max_recovery_attempts:
                continue

            # 根据错误类型决定是否尝试恢复
            if self._should_attempt_recovery(entry, recent_attempts):
                candidates.append((entry.channel_id, entry.model_name, entry))

        return candidates

    def _should_attempt_recovery(
        self, entry: ModelChannelBlacklistEntry, recent_attempts: list[RecoveryAttempt]
    ) -> bool:
        """判断是否应该尝试恢复"""
        # 认证错误通常不会自动恢复
        if entry.error_type == ErrorType.AUTH_ERROR:
            return False

        # 如果最近有失败的尝试，延长等待时间
        if recent_attempts:
            last_attempt = max(recent_attempts, key=lambda x: x.attempted_at)
            if not last_attempt.success:
                time_since_last = datetime.now() - last_attempt.attempted_at
                # 失败次数越多，等待时间越长
                required_wait = timedelta(minutes=30 * len(recent_attempts))
                if time_since_last < required_wait:
                    return False

        return True

    async def _attempt_recovery(
        self, channel_id: str, model_name: str, entry: ModelChannelBlacklistEntry
    ) -> bool:
        """尝试恢复特定的模型-渠道组合"""
        start_time = datetime.now()

        try:
            logger.debug(f"🔄 Attempting recovery for {model_name}@{channel_id}")

            # 获取渠道信息
            channel = self._get_channel_by_id(channel_id)
            if not channel:
                logger.warning(f"🔄 Recovery failed: Channel {channel_id} not found")
                return False

            # 执行健康检查
            success, response_time, error_msg = await self._health_check_model(
                channel, model_name
            )

            # 记录恢复尝试
            attempt = RecoveryAttempt(
                channel_id=channel_id,
                model_name=model_name,
                attempted_at=start_time,
                success=success,
                error_message=error_msg,
                response_time=response_time,
            )
            self.recovery_history.append(attempt)

            # 限制历史记录长度
            if len(self.recovery_history) > 1000:
                self.recovery_history = self.recovery_history[-500:]

            if success:
                # 恢复成功，从黑名单中移除
                await self.blacklist_manager.remove_blacklist_entry(
                    channel_id, model_name
                )
                logger.info(
                    f"✅ RECOVERY SUCCESS: {model_name}@{channel_id} is now available (response_time: {response_time:.3f}s)"
                )
                return True
            else:
                # 恢复失败，延长黑名单时间
                logger.debug(
                    f"🔄 Recovery failed for {model_name}@{channel_id}: {error_msg}"
                )
                await self._extend_blacklist(
                    entry,
                    len(
                        [
                            a
                            for a in self.recovery_history
                            if a.channel_id == channel_id
                            and a.model_name == model_name
                            and not a.success
                        ]
                    ),
                )
                return False

        except Exception as e:
            logger.error(
                f"🔄 Recovery attempt error for {model_name}@{channel_id}: {e}"
            )
            return False

    async def _health_check_model(
        self, channel: Channel, model_name: str
    ) -> tuple[bool, Optional[float], Optional[str]]:
        """对特定模型执行健康检查"""
        start_time = datetime.now()

        try:
            # 构建健康检查请求
            headers = {
                "Authorization": f"Bearer {channel.api_key}",
                "Content-Type": "application/json",
            }

            # 使用轻量级的模型列表请求进行健康检查
            check_url = f"{channel.base_url.rstrip('/')}/v1/models"

            async with httpx.AsyncClient(timeout=self.health_check_timeout) as client:
                response = await client.get(check_url, headers=headers)

                response_time = (datetime.now() - start_time).total_seconds()

                if response.status_code == 200:
                    # 检查响应中是否包含目标模型
                    try:
                        models_data = response.json()
                        available_models = [
                            model.get("id", "") for model in models_data.get("data", [])
                        ]

                        # 检查模型是否在列表中（支持模糊匹配）
                        model_available = any(
                            model_name.lower() in available_model.lower()
                            or available_model.lower() in model_name.lower()
                            for available_model in available_models
                        )

                        if model_available:
                            return True, response_time, None
                        else:
                            return (
                                False,
                                response_time,
                                f"Model {model_name} not found in available models",
                            )

                    except Exception:
                        # 如果无法解析响应，但HTTP状态正常，认为渠道可用
                        return True, response_time, None
                else:
                    return (
                        False,
                        response_time,
                        f"HTTP {response.status_code}: {response.text[:200]}",
                    )

        except httpx.TimeoutException:
            response_time = (datetime.now() - start_time).total_seconds()
            return False, response_time, "Health check timeout"
        except Exception as e:
            response_time = (datetime.now() - start_time).total_seconds()
            return False, response_time, str(e)

    def _get_channel_by_id(self, channel_id: str) -> Optional[Channel]:
        """根据ID获取渠道信息"""
        try:
            for channel in self.config_loader.get_enabled_channels():
                if channel.id == channel_id:
                    return channel
        except Exception as e:
            logger.error(f"Error getting channel {channel_id}: {e}")
        return None

    async def _extend_blacklist(
        self, entry: ModelChannelBlacklistEntry, failed_attempts: int
    ):
        """延长黑名单时间"""
        # 根据失败次数指数增长等待时间
        base_duration = entry.backoff_duration
        extended_duration = min(base_duration * (2**failed_attempts), 3600)  # 最长1小时

        # 更新过期时间
        entry.expires_at = datetime.now() + timedelta(seconds=extended_duration)
        entry.backoff_duration = extended_duration

        logger.debug(
            f"🔄 Extended blacklist for {entry.model_name}@{entry.channel_id} by {extended_duration}s"
        )

    def get_recovery_stats(self) -> dict[str, any]:
        """获取恢复统计信息"""
        recent_attempts = [
            attempt
            for attempt in self.recovery_history
            if datetime.now() - attempt.attempted_at < timedelta(hours=24)
        ]

        successful = [attempt for attempt in recent_attempts if attempt.success]
        failed = [attempt for attempt in recent_attempts if not attempt.success]

        return {
            "total_attempts_24h": len(recent_attempts),
            "successful_recoveries_24h": len(successful),
            "failed_recoveries_24h": len(failed),
            "success_rate": (
                len(successful) / len(recent_attempts) if recent_attempts else 0
            ),
            "avg_response_time": (
                sum(a.response_time for a in successful if a.response_time)
                / len(successful)
                if successful
                else 0
            ),
            "is_running": self._running,
            "recovery_interval": self.recovery_interval,
        }


# 全局单例实例
_global_recovery_manager: Optional[BlacklistRecoveryManager] = None


def get_blacklist_recovery_manager() -> BlacklistRecoveryManager:
    """获取全局黑名单恢复管理器实例"""
    global _global_recovery_manager

    if _global_recovery_manager is None:
        _global_recovery_manager = BlacklistRecoveryManager()

    return _global_recovery_manager


async def start_recovery_service():
    """启动恢复服务（用于应用启动时调用）"""
    recovery_manager = get_blacklist_recovery_manager()
    await recovery_manager.start_recovery_service()


async def stop_recovery_service():
    """停止恢复服务（用于应用关闭时调用）"""
    recovery_manager = get_blacklist_recovery_manager()
    await recovery_manager.stop_recovery_service()
