#!/usr/bin/env python3
"""
渠道监控器 - 监控渠道余额和状态，提供余额不足提醒
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ChannelAlert:
    """渠道告警记录"""

    channel_id: str
    channel_name: str
    alert_type: str  # 'quota_exhausted', 'low_balance', 'api_error'
    message: str
    timestamp: str
    details: Optional[dict] = None


class ChannelMonitor:
    """渠道监控器"""

    def __init__(self, alerts_file: str = "logs/channel_alerts.jsonl"):
        self.alerts_file = Path(alerts_file)
        self.alerts_file.parent.mkdir(exist_ok=True)

        # 已通知的渠道，避免重复通知
        self._notified_channels: set[str] = set()

        # 渠道错误计数，用于判断是否需要告警
        self._error_counts: dict[str, int] = {}
        self._last_error_time: dict[str, datetime] = {}

        # 配置
        self.max_errors_before_alert = 3  # 连续错误次数阈值
        self.error_time_window = timedelta(minutes=5)  # 错误时间窗口
        self.cooldown_period = timedelta(hours=1)  # 告警冷却期

    def record_channel_error(
        self,
        channel_id: str,
        channel_name: str,
        error_type: str,
        error_message: str,
        details: Optional[dict] = None,
    ):
        """记录渠道错误"""
        current_time = datetime.utcnow()

        # 更新错误计数
        if channel_id not in self._error_counts:
            self._error_counts[channel_id] = 0

        # 检查是否在时间窗口内
        if channel_id in self._last_error_time:
            time_diff = current_time - self._last_error_time[channel_id]
            if time_diff > self.error_time_window:
                # 重置计数器
                self._error_counts[channel_id] = 0

        self._error_counts[channel_id] += 1
        self._last_error_time[channel_id] = current_time

        # 判断是否需要告警
        if self._should_alert(channel_id, error_type):
            self._send_alert(
                channel_id, channel_name, error_type, error_message, details
            )

    def record_quota_exhausted(
        self, channel_id: str, channel_name: str, details: Optional[dict] = None
    ):
        """记录配额用完"""
        message = f"渠道 {channel_name} 配额已用完"
        self._send_alert(channel_id, channel_name, "quota_exhausted", message, details)

    def record_low_balance(
        self,
        channel_id: str,
        channel_name: str,
        remaining_balance: float,
        details: Optional[dict] = None,
    ):
        """记录余额不足"""
        message = f"渠道 {channel_name} 余额不足，剩余: ${remaining_balance:.4f}"
        alert_details = {"remaining_balance": remaining_balance}
        if details:
            alert_details.update(details)
        self._send_alert(
            channel_id, channel_name, "low_balance", message, alert_details
        )

    def record_api_key_invalid(
        self, channel_id: str, channel_name: str, details: Optional[dict] = None
    ):
        """记录API密钥无效"""
        message = f"渠道 {channel_name} API密钥无效或已过期"
        self._send_alert(channel_id, channel_name, "api_key_invalid", message, details)

    def _should_alert(self, channel_id: str, error_type: str) -> bool:
        """判断是否应该发送告警"""
        # 配额用完或API密钥无效立即告警
        if error_type in ["quota_exhausted", "api_key_invalid", "low_balance"]:
            return not self._is_in_cooldown(channel_id)

        # 其他错误需要达到阈值
        error_count = self._error_counts.get(channel_id, 0)
        return error_count >= self.max_errors_before_alert and not self._is_in_cooldown(
            channel_id
        )

    def _is_in_cooldown(self, channel_id: str) -> bool:
        """检查是否在冷却期内"""
        if channel_id not in self._notified_channels:
            return False

        # 这里简化处理，实际可以记录更详细的冷却时间
        # 当前实现：一旦通知过就不再重复通知（直到手动清除）
        return True

    def _send_alert(
        self,
        channel_id: str,
        channel_name: str,
        alert_type: str,
        message: str,
        details: Optional[dict] = None,
    ):
        """发送告警"""
        try:
            alert = ChannelAlert(
                channel_id=channel_id,
                channel_name=channel_name,
                alert_type=alert_type,
                message=message,
                timestamp=datetime.utcnow().isoformat() + "Z",
                details=details,
            )

            # 记录到文件
            self._write_alert_to_file(alert)

            # 记录到日志
            logger.warning(f"渠道告警: {message}")

            # 标记为已通知
            self._notified_channels.add(channel_id)

            # 这里可以扩展其他通知方式
            # - 发送邮件
            # - 发送Webhook
            # - 发送到消息队列
            self._send_console_notification(alert)

        except Exception as e:
            logger.error(f"发送告警失败: {e}")

    def _write_alert_to_file(self, alert: ChannelAlert):
        """写入告警到文件"""
        try:
            alert_dict = {
                "channel_id": alert.channel_id,
                "channel_name": alert.channel_name,
                "alert_type": alert.alert_type,
                "message": alert.message,
                "timestamp": alert.timestamp,
                "details": alert.details,
            }

            json_line = json.dumps(alert_dict, ensure_ascii=False)

            with open(self.alerts_file, "a", encoding="utf-8") as f:
                f.write(json_line + "\n")

        except Exception as e:
            logger.error(f"写入告警文件失败: {e}")

    def _send_console_notification(self, alert: ChannelAlert):
        """发送控制台通知"""
        print(f"\n{'='*60}")
        print("🚨 渠道告警通知")
        print(f"{'='*60}")
        print(f"时间: {alert.timestamp}")
        print(f"渠道: {alert.channel_name} ({alert.channel_id})")
        print(f"类型: {alert.alert_type}")
        print(f"消息: {alert.message}")
        if alert.details:
            print(f"详情: {json.dumps(alert.details, ensure_ascii=False, indent=2)}")
        print(f"{'='*60}\n")

    def get_recent_alerts(self, hours: int = 24) -> list[ChannelAlert]:
        """获取最近的告警"""
        if not self.alerts_file.exists():
            return []

        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        alerts = []

        try:
            with open(self.alerts_file, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        alert_dict = json.loads(line.strip())
                        alert_time = datetime.fromisoformat(
                            alert_dict["timestamp"].replace("Z", "+00:00")
                        )

                        if alert_time >= cutoff_time:
                            alert = ChannelAlert(
                                channel_id=alert_dict["channel_id"],
                                channel_name=alert_dict["channel_name"],
                                alert_type=alert_dict["alert_type"],
                                message=alert_dict["message"],
                                timestamp=alert_dict["timestamp"],
                                details=alert_dict.get("details"),
                            )
                            alerts.append(alert)

                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"解析告警记录失败: {e}")
                        continue

        except Exception as e:
            logger.error(f"读取告警文件失败: {e}")

        return alerts

    def clear_channel_notifications(self, channel_id: str):
        """清除渠道的通知状态（允许重新发送告警）"""
        self._notified_channels.discard(channel_id)
        if channel_id in self._error_counts:
            del self._error_counts[channel_id]
        if channel_id in self._last_error_time:
            del self._last_error_time[channel_id]

        logger.info(f"已清除渠道 {channel_id} 的通知状态")

    def clear_all_notifications(self):
        """清除所有通知状态"""
        self._notified_channels.clear()
        self._error_counts.clear()
        self._last_error_time.clear()

        logger.info("已清除所有渠道的通知状态")

    def get_channel_status(self) -> dict[str, dict]:
        """获取渠道状态概览"""
        return {
            "notified_channels": list(self._notified_channels),
            "error_counts": dict(self._error_counts),
            "last_error_times": {
                k: v.isoformat() + "Z" for k, v in self._last_error_time.items()
            },
        }


# 全局实例
_channel_monitor = None


def get_channel_monitor() -> ChannelMonitor:
    """获取全局渠道监控器实例"""
    global _channel_monitor
    if _channel_monitor is None:
        _channel_monitor = ChannelMonitor()
    return _channel_monitor


def check_api_error_and_alert(
    channel_id: str, channel_name: str, status_code: int, error_message: str
):
    """检查API错误并发送相应告警"""
    monitor = get_channel_monitor()

    if status_code == 401:
        # API密钥无效
        monitor.record_api_key_invalid(
            channel_id,
            channel_name,
            {"status_code": status_code, "error_message": error_message},
        )
    elif status_code == 429:
        # 可能是配额用完或速率限制
        if "quota" in error_message.lower() or "balance" in error_message.lower():
            monitor.record_quota_exhausted(
                channel_id,
                channel_name,
                {"status_code": status_code, "error_message": error_message},
            )
        else:
            monitor.record_channel_error(
                channel_id,
                channel_name,
                "rate_limit",
                error_message,
                {"status_code": status_code},
            )
    elif status_code >= 500:
        # 服务器错误
        monitor.record_channel_error(
            channel_id,
            channel_name,
            "server_error",
            error_message,
            {"status_code": status_code},
        )
    else:
        # 其他错误
        monitor.record_channel_error(
            channel_id,
            channel_name,
            "api_error",
            error_message,
            {"status_code": status_code},
        )
