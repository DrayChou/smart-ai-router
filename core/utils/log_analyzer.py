"""
日志分析工具 - 用于分析和查询结构化日志数据
"""

import json
import re
from collections import Counter, defaultdict
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Union


@dataclass
class LogQuery:
    """日志查询条件"""

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    log_level: Optional[str] = None
    logger_name: Optional[str] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    message_pattern: Optional[str] = None
    limit: int = 1000
    offset: int = 0


@dataclass
class LogStats:
    """日志统计信息"""

    total_entries: int
    level_counts: dict[str, int]
    logger_counts: dict[str, int]
    error_patterns: list[dict[str, Any]]
    request_stats: dict[str, Any]
    time_range: dict[str, Optional[datetime]]


class LogAnalyzer:
    """日志分析器"""

    def __init__(self, log_file: Union[str, Path]):
        self.log_file = Path(log_file)
        self.cache: dict[str, tuple[datetime, LogStats]] = {}
        self.cache_timeout = 300  # 5分钟缓存

    async def search_logs(self, query: LogQuery) -> list[dict[str, Any]]:
        """搜索日志条目"""
        results = []
        matched_count = 0

        async for entry in self._read_log_entries():
            if self._matches_query(entry, query):
                if matched_count >= query.offset:
                    results.append(entry)
                    if len(results) >= query.limit:
                        break
                matched_count += 1

        return results

    async def get_log_stats(
        self, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None
    ) -> LogStats:
        """获取日志统计信息"""
        cache_key = f"stats_{start_time}_{end_time}"

        # 检查缓存
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if (datetime.now() - cached_time).seconds < self.cache_timeout:
                return cached_data

        total_entries = 0
        level_counts: Counter[str] = Counter()
        logger_counts: Counter[str] = Counter()
        error_patterns: defaultdict[str, int] = defaultdict(int)
        request_durations = []
        request_status_codes: Counter[int] = Counter()
        first_entry_time = None
        last_entry_time = None

        async for entry in self._read_log_entries():
            entry_time = self._parse_timestamp(entry.get("timestamp"))

            # 时间范围过滤
            if start_time and entry_time and entry_time < start_time:
                continue
            if end_time and entry_time and entry_time > end_time:
                continue

            total_entries += 1

            # 更新时间范围
            if not first_entry_time or (entry_time and entry_time < first_entry_time):
                first_entry_time = entry_time
            if not last_entry_time or (entry_time and entry_time > last_entry_time):
                last_entry_time = entry_time

            # 统计日志级别
            level = entry.get("level", "UNKNOWN")
            level_counts[level] += 1

            # 统计日志来源
            logger_name = entry.get("logger_name", "unknown")
            logger_counts[logger_name] += 1

            # 分析错误模式
            if level in ["ERROR", "CRITICAL"]:
                message = entry.get("message", "")
                # 提取错误模式（移除具体的值和ID）
                pattern = re.sub(r"\b\d+\b", "<NUMBER>", message)
                pattern = re.sub(
                    r"\b[a-f0-9-]{8,}\b", "<ID>", pattern, flags=re.IGNORECASE
                )
                error_patterns[pattern] += 1

            # 分析请求统计
            extra_data = entry.get("extra_data", {})
            if "process_time" in extra_data:
                request_durations.append(float(extra_data["process_time"]))

            if "status_code" in extra_data:
                request_status_codes[extra_data["status_code"]] += 1

        # 构建统计结果
        stats = LogStats(
            total_entries=total_entries,
            level_counts=dict(level_counts),
            logger_counts=dict(logger_counts),
            error_patterns=[
                {"pattern": pattern, "count": count}
                for pattern, count in Counter(error_patterns).most_common(10)
            ],
            request_stats={
                "total_requests": len(request_durations),
                "avg_duration": (
                    sum(request_durations) / len(request_durations)
                    if request_durations
                    else 0
                ),
                "max_duration": max(request_durations) if request_durations else 0,
                "min_duration": min(request_durations) if request_durations else 0,
                "status_codes": dict(request_status_codes),
            },
            time_range={"start": first_entry_time, "end": last_entry_time},
        )

        # 缓存结果
        self.cache[cache_key] = (datetime.now(), stats)

        return stats

    async def get_error_logs(
        self, hours: int = 24, limit: int = 100
    ) -> list[dict[str, Any]]:
        """获取最近的错误日志"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        query = LogQuery(
            start_time=start_time, end_time=end_time, log_level="ERROR", limit=limit
        )

        return await self.search_logs(query)

    async def get_slow_requests(
        self, min_duration: float = 5.0, hours: int = 24, limit: int = 50
    ) -> list[dict[str, Any]]:
        """获取慢请求日志"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        slow_requests = []

        async for entry in self._read_log_entries():
            entry_time = self._parse_timestamp(entry.get("timestamp"))

            if entry_time and start_time <= entry_time <= end_time:
                extra_data = entry.get("extra_data", {})
                process_time = extra_data.get("process_time")

                if process_time and float(process_time) >= min_duration:
                    slow_requests.append(entry)

                    if len(slow_requests) >= limit:
                        break

        return slow_requests

    async def get_request_timeline(self, request_id: str) -> list[dict[str, Any]]:
        """获取特定请求的完整时间线"""
        query = LogQuery(request_id=request_id, limit=1000)
        entries = await self.search_logs(query)

        # 按时间戳排序
        entries.sort(
            key=lambda x: self._parse_timestamp(x.get("timestamp")) or datetime.min
        )

        return entries

    async def export_logs(
        self, query: LogQuery, output_file: Union[str, Path], format: str = "json"
    ) -> int:
        """导出日志到文件"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        entries = await self.search_logs(query)

        if format == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False, default=str)
        elif format == "csv":
            import csv

            if entries:
                fieldnames_set: set[str] = set()
                for entry in entries:
                    fieldnames_set.update(entry.keys())
                fieldnames = list(fieldnames_set)

                with open(output_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(entries)
        else:
            raise ValueError(f"Unsupported format: {format}")

        return len(entries)

    async def _read_log_entries(self) -> AsyncGenerator[dict[str, Any], None]:
        """异步读取日志条目"""
        try:
            import aiofiles

            if not self.log_file.exists():
                return

            async with aiofiles.open(self.log_file, encoding="utf-8") as f:
                async for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            yield entry
                        except json.JSONDecodeError:
                            # 跳过无效的JSON行
                            continue

        except ImportError:
            # 回退到同步读取
            if not self.log_file.exists():
                return

            with open(self.log_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            yield entry
                        except json.JSONDecodeError:
                            continue

    def _matches_query(self, entry: dict[str, Any], query: LogQuery) -> bool:
        """检查日志条目是否匹配查询条件"""
        # 时间范围检查
        if query.start_time or query.end_time:
            # 尝试多个时间戳字段
            entry_time = self._parse_timestamp(
                entry.get("timestamp") or entry.get("asctime")
            )
            if not entry_time:
                return False

            # 确保时间对象具有相同的时区意识
            if query.start_time:
                start_time = query.start_time
                if entry_time.tzinfo is None and start_time.tzinfo is not None:
                    # entry_time是naive的，start_time是aware的，将entry_time视为UTC
                    from datetime import timezone

                    entry_time = entry_time.replace(tzinfo=timezone.utc)
                elif entry_time.tzinfo is not None and start_time.tzinfo is None:
                    # entry_time是aware的，start_time是naive的，将start_time视为UTC
                    from datetime import timezone

                    start_time = start_time.replace(tzinfo=timezone.utc)

                if entry_time < start_time:
                    return False

            if query.end_time:
                end_time = query.end_time
                if entry_time.tzinfo is None and end_time.tzinfo is not None:
                    # entry_time是naive的，end_time是aware的，将entry_time视为UTC
                    from datetime import timezone

                    entry_time = entry_time.replace(tzinfo=timezone.utc)
                elif entry_time.tzinfo is not None and end_time.tzinfo is None:
                    # entry_time是aware的，end_time是naive的，将end_time视为UTC
                    from datetime import timezone

                    end_time = end_time.replace(tzinfo=timezone.utc)

                if entry_time > end_time:
                    return False

        # 日志级别检查
        if query.log_level and entry.get("level") != query.log_level.upper():
            return False

        # 日志来源检查
        if query.logger_name and entry.get("logger_name") != query.logger_name:
            return False

        # 请求ID检查
        if query.request_id and entry.get("request_id") != query.request_id:
            return False

        # 用户ID检查
        if query.user_id and entry.get("user_id") != query.user_id:
            return False

        # 消息模式检查
        if query.message_pattern:
            message = entry.get("message", "")
            if not re.search(query.message_pattern, message, re.IGNORECASE):
                return False

        return True

    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """解析时间戳字符串"""
        if not timestamp_str:
            return None

        try:
            # 尝试ISO格式
            if timestamp_str.endswith("Z"):
                return datetime.fromisoformat(timestamp_str[:-1] + "+00:00")
            return datetime.fromisoformat(timestamp_str)
        except ValueError:
            try:
                # 尝试Python logging的asctime格式: "2025-08-19 13:49:31,962"
                return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")
            except ValueError:
                try:
                    # 尝试其他常见格式
                    return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return None


class LogDashboard:
    """日志仪表板 - 提供日志监控和警报功能"""

    def __init__(self, log_analyzer: LogAnalyzer):
        self.analyzer = log_analyzer
        self.alert_rules: list[dict[str, Any]] = []

    async def check_alerts(self) -> list[dict[str, Any]]:
        """检查日志警报"""
        alerts = []

        # 检查错误率
        stats = await self.analyzer.get_log_stats(
            start_time=datetime.now() - timedelta(hours=1)
        )

        total_requests = stats.request_stats["total_requests"]
        error_count = stats.level_counts.get("ERROR", 0) + stats.level_counts.get(
            "CRITICAL", 0
        )

        if total_requests > 0:
            error_rate = error_count / total_requests
            if error_rate > 0.05:  # 5%错误率阈值
                alerts.append(
                    {
                        "type": "high_error_rate",
                        "severity": "warning",
                        "message": f"High error rate detected: {error_rate:.2%}",
                        "details": {
                            "error_count": error_count,
                            "total_requests": total_requests,
                            "error_rate": error_rate,
                        },
                    }
                )

        # 检查慢请求
        avg_duration = stats.request_stats["avg_duration"]
        if avg_duration > 10.0:  # 10秒阈值
            alerts.append(
                {
                    "type": "slow_requests",
                    "severity": "warning",
                    "message": f"High average response time: {avg_duration:.2f}s",
                    "details": {
                        "avg_duration": avg_duration,
                        "max_duration": stats.request_stats["max_duration"],
                    },
                }
            )

        return alerts

    async def generate_report(
        self, start_time: datetime, end_time: datetime
    ) -> dict[str, Any]:
        """生成日志报告"""
        stats = await self.analyzer.get_log_stats(start_time, end_time)
        error_logs = await self.analyzer.get_error_logs(
            hours=int((end_time - start_time).total_seconds() / 3600)
        )

        return {
            "period": {"start": start_time.isoformat(), "end": end_time.isoformat()},
            "summary": {
                "total_entries": stats.total_entries,
                "total_requests": stats.request_stats["total_requests"],
                "error_count": len(error_logs),
                "avg_response_time": stats.request_stats["avg_duration"],
            },
            "level_distribution": stats.level_counts,
            "top_errors": stats.error_patterns[:5],
            "performance": {
                "avg_duration": stats.request_stats["avg_duration"],
                "max_duration": stats.request_stats["max_duration"],
                "status_codes": stats.request_stats["status_codes"],
            },
        }
