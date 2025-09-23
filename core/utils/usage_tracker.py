#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用情况跟踪器 - 收集和记录每次API调用的成本信息
"""

import asyncio
import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class UsageRecord:
    """单次使用记录"""

    # 基础信息
    timestamp: str  # ISO格式时间戳
    request_id: str  # 唯一请求ID
    session_id: Optional[str]  # 会话ID（可选）

    # 模型和渠道信息
    model: str  # 请求的模型名称
    channel_id: str  # 使用的渠道ID
    channel_name: str  # 渠道名称
    provider: str  # 提供商名称

    # Token使用情况
    input_tokens: int  # 实际输入tokens
    output_tokens: int  # 实际输出tokens
    total_tokens: int  # 总tokens

    # 成本信息
    input_cost: float  # 输入成本（USD）
    output_cost: float  # 输出成本（USD）
    total_cost: float  # 总成本（USD）
    cost_currency: str = "USD"  # 成本货币

    # 请求信息
    request_type: str = "chat"  # 请求类型 (chat, embedding等)
    status: str = "success"  # 请求状态
    error_message: Optional[str] = None  # 错误信息（如果有）

    # 性能信息
    response_time_ms: Optional[int] = None  # 响应时间毫秒

    # 额外信息
    user_agent: Optional[str] = None  # 用户代理
    client_ip: Optional[str] = None  # 客户端IP
    tags: Optional[List[str]] = None  # 标签信息


class UsageTracker:
    """使用情况跟踪器"""

    def __init__(self, logs_dir: str = "logs"):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(exist_ok=True)
        self._write_lock = Lock()

        # 当前日期，用于日志轮换
        self._current_date = date.today()
        self._current_file_path = self._get_daily_log_file()

    def _get_daily_log_file(self, target_date: Optional[date] = None) -> Path:
        """获取每日日志文件路径"""
        if target_date is None:
            target_date = date.today()

        filename = f"usage_{target_date.strftime('%Y%m%d')}.jsonl"
        return self.logs_dir / filename

    def _check_date_rotation(self):
        """检查是否需要日志轮换"""
        today = date.today()
        if today != self._current_date:
            self._current_date = today
            self._current_file_path = self._get_daily_log_file()

    def record_usage(self, record: UsageRecord):
        """记录使用情况（同步）"""
        try:
            with self._write_lock:
                self._check_date_rotation()

                # 转换为JSON字符串
                record_dict = asdict(record)
                json_line = json.dumps(record_dict, ensure_ascii=False)

                # 追加到文件
                with open(self._current_file_path, "a", encoding="utf-8") as f:
                    f.write(json_line + "\n")

                logger.debug(
                    f"记录使用情况: {record.request_id}, 成本: ${record.total_cost:.6f}"
                )

        except Exception as e:
            logger.error(f"记录使用情况失败: {e}")

    async def record_usage_async(self, record: UsageRecord):
        """记录使用情况（异步）"""
        # 在线程池中执行同步操作
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.record_usage, record)

    def get_daily_stats(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """获取每日统计"""
        if target_date is None:
            target_date = date.today()

        log_file = self._get_daily_log_file(target_date)
        if not log_file.exists():
            return self._empty_stats()

        stats = {
            "date": target_date.isoformat(),
            "total_requests": 0,
            "total_cost": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "providers": {},
            "channels": {},
            "models": {},
            "avg_cost_per_request": 0.0,
            "avg_cost_per_1k_tokens": 0.0,
        }

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        record = json.loads(line.strip())
                        self._update_stats(stats, record)
                    except json.JSONDecodeError as e:
                        logger.warning(f"解析日志行失败: {e}")
                        continue

            # 计算平均值
            if stats["total_requests"] > 0:
                stats["avg_cost_per_request"] = (
                    stats["total_cost"] / stats["total_requests"]
                )
            if stats["total_tokens"] > 0:
                stats["avg_cost_per_1k_tokens"] = (
                    stats["total_cost"] / stats["total_tokens"]
                ) * 1000

        except Exception as e:
            logger.error(f"读取每日统计失败: {e}")
            return self._empty_stats()

        return stats

    def get_weekly_stats(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """获取本周统计"""
        if target_date is None:
            target_date = date.today()

        # 获取本周的开始日期（周一）
        days_since_monday = target_date.weekday()
        week_start = target_date - timedelta(days=days_since_monday)

        weekly_stats = self._empty_stats()
        weekly_stats["week_start"] = week_start.isoformat()
        weekly_stats["week_end"] = (week_start + timedelta(days=6)).isoformat()

        # 汇总本周每天的数据
        for i in range(7):
            day = week_start + timedelta(days=i)
            if day > target_date:  # 不统计未来的日期
                break

            daily_stats = self.get_daily_stats(day)
            self._merge_stats(weekly_stats, daily_stats)

        return weekly_stats

    def get_monthly_stats(
        self, year: Optional[int] = None, month: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取本月统计"""
        if year is None or month is None:
            today = date.today()
            year = today.year
            month = today.month

        monthly_stats = self._empty_stats()
        monthly_stats["year"] = year
        monthly_stats["month"] = month

        # 汇总本月每天的数据
        from calendar import monthrange

        _, days_in_month = monthrange(year, month)

        for day in range(1, days_in_month + 1):
            target = date(year, month, day)
            if target > date.today():  # 不统计未来的日期
                break

            daily_stats = self.get_daily_stats(target)
            self._merge_stats(monthly_stats, daily_stats)

        return monthly_stats

    def _empty_stats(self) -> Dict[str, Any]:
        """返回空统计结构"""
        return {
            "total_requests": 0,
            "total_cost": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "providers": {},
            "channels": {},
            "models": {},
            "avg_cost_per_request": 0.0,
            "avg_cost_per_1k_tokens": 0.0,
        }

    def _update_stats(self, stats: Dict[str, Any], record: Dict[str, Any]):
        """更新统计数据"""
        stats["total_requests"] += 1
        stats["total_cost"] += record.get("total_cost", 0.0)
        stats["total_input_tokens"] += record.get("input_tokens", 0)
        stats["total_output_tokens"] += record.get("output_tokens", 0)
        stats["total_tokens"] += record.get("total_tokens", 0)

        if record.get("status") == "success":
            stats["successful_requests"] += 1
        else:
            stats["failed_requests"] += 1

        # 按提供商统计
        provider = record.get("provider", "unknown")
        if provider not in stats["providers"]:
            stats["providers"][provider] = {"requests": 0, "cost": 0.0, "tokens": 0}
        stats["providers"][provider]["requests"] += 1
        stats["providers"][provider]["cost"] += record.get("total_cost", 0.0)
        stats["providers"][provider]["tokens"] += record.get("total_tokens", 0)

        # 按渠道统计
        channel = record.get("channel_name", "unknown")
        if channel not in stats["channels"]:
            stats["channels"][channel] = {"requests": 0, "cost": 0.0, "tokens": 0}
        stats["channels"][channel]["requests"] += 1
        stats["channels"][channel]["cost"] += record.get("total_cost", 0.0)
        stats["channels"][channel]["tokens"] += record.get("total_tokens", 0)

        # 按模型统计
        model = record.get("model", "unknown")
        if model not in stats["models"]:
            stats["models"][model] = {"requests": 0, "cost": 0.0, "tokens": 0}
        stats["models"][model]["requests"] += 1
        stats["models"][model]["cost"] += record.get("total_cost", 0.0)
        stats["models"][model]["tokens"] += record.get("total_tokens", 0)

    def _merge_stats(self, target_stats: Dict[str, Any], source_stats: Dict[str, Any]):
        """合并统计数据"""
        target_stats["total_requests"] += source_stats["total_requests"]
        target_stats["total_cost"] += source_stats["total_cost"]
        target_stats["total_input_tokens"] += source_stats["total_input_tokens"]
        target_stats["total_output_tokens"] += source_stats["total_output_tokens"]
        target_stats["total_tokens"] += source_stats["total_tokens"]
        target_stats["successful_requests"] += source_stats["successful_requests"]
        target_stats["failed_requests"] += source_stats["failed_requests"]

        # 合并子统计
        for category in ["providers", "channels", "models"]:
            for key, value in source_stats[category].items():
                if key not in target_stats[category]:
                    target_stats[category][key] = {
                        "requests": 0,
                        "cost": 0.0,
                        "tokens": 0,
                    }
                target_stats[category][key]["requests"] += value["requests"]
                target_stats[category][key]["cost"] += value["cost"]
                target_stats[category][key]["tokens"] += value["tokens"]

        # 重新计算平均值
        if target_stats["total_requests"] > 0:
            target_stats["avg_cost_per_request"] = (
                target_stats["total_cost"] / target_stats["total_requests"]
            )
        if target_stats["total_tokens"] > 0:
            target_stats["avg_cost_per_1k_tokens"] = (
                target_stats["total_cost"] / target_stats["total_tokens"]
            ) * 1000

    def archive_old_logs(self, days_to_keep: int = 30):
        """归档旧日志文件"""
        try:
            from datetime import timedelta

            cutoff_date = date.today() - timedelta(days=days_to_keep)

            archive_dir = self.logs_dir / "archive"
            archive_dir.mkdir(exist_ok=True)

            for log_file in self.logs_dir.glob("usage_*.jsonl"):
                try:
                    # 从文件名解析日期
                    date_str = log_file.stem.split("_")[
                        1
                    ]  # usage_20250824.jsonl -> 20250824
                    file_date = datetime.strptime(date_str, "%Y%m%d").date()

                    if file_date < cutoff_date:
                        # 移动到归档目录
                        archive_path = archive_dir / log_file.name
                        log_file.rename(archive_path)
                        logger.info(f"归档日志文件: {log_file.name}")

                except (ValueError, IndexError) as e:
                    logger.warning(f"解析日志文件日期失败 {log_file.name}: {e}")
                    continue

        except Exception as e:
            logger.error(f"归档日志文件失败: {e}")


# 全局实例
_usage_tracker = None


def get_usage_tracker() -> UsageTracker:
    """获取全局使用跟踪器实例"""
    global _usage_tracker
    if _usage_tracker is None:
        _usage_tracker = UsageTracker()
    return _usage_tracker


def create_usage_record(
    model: str,
    channel_id: str,
    channel_name: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    input_cost: float,
    output_cost: float,
    request_id: Optional[str] = None,
    session_id: Optional[str] = None,
    request_type: str = "chat",
    status: str = "success",
    error_message: Optional[str] = None,
    response_time_ms: Optional[int] = None,
    user_agent: Optional[str] = None,
    client_ip: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> UsageRecord:
    """创建使用记录"""
    if request_id is None:
        request_id = str(uuid.uuid4())

    return UsageRecord(
        timestamp=datetime.utcnow().isoformat() + "Z",
        request_id=request_id,
        session_id=session_id,
        model=model,
        channel_id=channel_id,
        channel_name=channel_name,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        input_cost=input_cost,
        output_cost=output_cost,
        total_cost=input_cost + output_cost,
        request_type=request_type,
        status=status,
        error_message=error_message,
        response_time_ms=response_time_ms,
        user_agent=user_agent,
        client_ip=client_ip,
        tags=tags,
    )
