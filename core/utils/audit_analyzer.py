"""
审计日志分析工具 - 专门分析审计事件和生成审计报告
"""
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.utils.log_analyzer import LogAnalyzer, LogQuery


@dataclass
class AuditSummary:
    """审计摘要"""

    time_period: dict[str, datetime]
    total_events: int
    event_type_counts: dict[str, int]
    level_counts: dict[str, int]
    outcome_counts: dict[str, int]
    unique_users: int
    unique_ips: int
    top_users: list[dict[str, Any]]
    top_ips: list[dict[str, Any]]
    security_events: int
    failed_operations: int


@dataclass
class SecurityReport:
    """安全审计报告"""

    period: dict[str, datetime]
    total_security_events: int
    authentication_failures: int
    rate_limit_violations: int
    suspicious_activities: int
    security_violations: list[dict[str, Any]]
    ip_threat_analysis: list[dict[str, Any]]
    user_risk_analysis: list[dict[str, Any]]


@dataclass
class UserActivityReport:
    """用户活动报告"""

    user_id: str
    period: dict[str, datetime]
    total_actions: int
    action_breakdown: dict[str, int]
    resource_access: dict[str, int]
    success_rate: float
    peak_activity_times: list[str]
    security_events: int
    last_activity: Optional[datetime]


class AuditAnalyzer:
    """审计日志分析器"""

    def __init__(self, log_analyzer: LogAnalyzer):
        self.log_analyzer = log_analyzer
        self.cache = {}
        self.cache_timeout = 300  # 5分钟缓存

    async def get_audit_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[list[str]] = None,
        user_ids: Optional[list[str]] = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """获取审计事件"""
        # 构建查询
        query = LogQuery(
            start_time=start_time,
            end_time=end_time,
            message_pattern="AUDIT:",
            limit=limit,
        )

        # 搜索日志
        log_entries = await self.log_analyzer.search_logs(query)

        # 提取审计事件
        audit_events = []
        for entry in log_entries:
            # 检查多个可能的位置
            audit_data = entry.get("audit_event") or entry.get("extra_data", {}).get(
                "audit_event"
            )
            if audit_data:
                # 过滤事件类型
                if event_types and audit_data.get("event_type") not in event_types:
                    continue

                # 过滤用户ID
                if user_ids and audit_data.get("user_id") not in user_ids:
                    continue

                audit_events.append(
                    {
                        **audit_data,
                        "log_timestamp": entry.get("timestamp") or entry.get("asctime"),
                        "log_level": entry.get("level") or entry.get("levelname"),
                    }
                )

        return audit_events

    async def generate_audit_summary(
        self, start_time: datetime, end_time: datetime
    ) -> AuditSummary:
        """生成审计摘要"""
        cache_key = f"audit_summary_{start_time}_{end_time}"

        # 检查缓存
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if (datetime.now() - cached_time).seconds < self.cache_timeout:
                return cached_data

        # 获取审计事件
        events = await self.get_audit_events(start_time, end_time, limit=10000)

        # 统计分析
        event_type_counts = Counter()
        level_counts = Counter()
        outcome_counts = Counter()
        user_activity = defaultdict(int)
        ip_activity = defaultdict(int)
        security_events = 0
        failed_operations = 0

        for event in events:
            event_type = event.get("event_type", "unknown")
            level = event.get("level", "low")
            outcome = event.get("outcome", "unknown")
            user_id = event.get("user_id")
            ip_address = event.get("ip_address")

            event_type_counts[event_type] += 1
            level_counts[level] += 1
            outcome_counts[outcome] += 1

            if user_id:
                user_activity[user_id] += 1

            if ip_address:
                ip_activity[ip_address] += 1

            # 统计安全事件
            if any(
                sec_type in event_type
                for sec_type in ["security", "login.failure", "rate_limit", "violation"]
            ):
                security_events += 1

            # 统计失败操作
            if outcome in ["failure", "error", "violation"]:
                failed_operations += 1

        # 构建摘要
        summary = AuditSummary(
            time_period={"start": start_time, "end": end_time},
            total_events=len(events),
            event_type_counts=dict(event_type_counts.most_common(10)),
            level_counts=dict(level_counts),
            outcome_counts=dict(outcome_counts),
            unique_users=len(user_activity),
            unique_ips=len(ip_activity),
            top_users=[
                {"user_id": user, "activity_count": count}
                for user, count in Counter(user_activity).most_common(10)
            ],
            top_ips=[
                {"ip_address": ip, "activity_count": count}
                for ip, count in Counter(ip_activity).most_common(10)
            ],
            security_events=security_events,
            failed_operations=failed_operations,
        )

        # 缓存结果
        self.cache[cache_key] = (datetime.now(), summary)

        return summary

    async def generate_security_report(
        self, start_time: datetime, end_time: datetime
    ) -> SecurityReport:
        """生成安全审计报告"""
        # 获取安全相关事件
        security_event_types = [
            "auth.login.failure",
            "security.violation",
            "security.rate_limit",
            "security.suspicious",
        ]

        events = await self.get_audit_events(
            start_time, end_time, event_types=security_event_types, limit=5000
        )

        # 分析安全事件
        auth_failures = 0
        rate_limit_violations = 0
        suspicious_activities = 0
        security_violations = []
        ip_threats = defaultdict(lambda: {"count": 0, "severity": "low", "events": []})
        user_risks = defaultdict(lambda: {"count": 0, "risk_score": 0, "events": []})

        for event in events:
            event_type = event.get("event_type", "")
            ip_address = event.get("ip_address", "unknown")
            user_id = event.get("user_id")
            severity = event.get("details", {}).get("severity", "low")

            # 分类统计
            if "login.failure" in event_type:
                auth_failures += 1
            elif "rate_limit" in event_type:
                rate_limit_violations += 1
            elif "suspicious" in event_type:
                suspicious_activities += 1

            # 记录高风险事件
            if event.get("level") in ["high", "critical"]:
                security_violations.append(
                    {
                        "timestamp": event.get("timestamp"),
                        "event_type": event_type,
                        "user_id": user_id,
                        "ip_address": ip_address,
                        "description": event.get("error_message", "Security violation"),
                        "severity": severity,
                    }
                )

            # IP威胁分析
            ip_threats[ip_address]["count"] += 1
            ip_threats[ip_address]["events"].append(event_type)
            if severity == "high":
                ip_threats[ip_address]["severity"] = "high"

            # 用户风险分析
            if user_id:
                user_risks[user_id]["count"] += 1
                user_risks[user_id]["events"].append(event_type)

                # 计算风险评分
                risk_score = 0
                if "failure" in event_type:
                    risk_score += 1
                if "violation" in event_type:
                    risk_score += 3
                if severity == "high":
                    risk_score += 2

                user_risks[user_id]["risk_score"] += risk_score

        # 构建报告
        report = SecurityReport(
            period={"start": start_time, "end": end_time},
            total_security_events=len(events),
            authentication_failures=auth_failures,
            rate_limit_violations=rate_limit_violations,
            suspicious_activities=suspicious_activities,
            security_violations=security_violations[:50],  # 限制返回数量
            ip_threat_analysis=[
                {
                    "ip_address": ip,
                    "threat_count": data["count"],
                    "severity": data["severity"],
                    "event_types": list(set(data["events"])),
                }
                for ip, data in sorted(
                    ip_threats.items(), key=lambda x: x[1]["count"], reverse=True
                )[:20]
            ],
            user_risk_analysis=[
                {
                    "user_id": user,
                    "risk_events": data["count"],
                    "risk_score": data["risk_score"],
                    "event_types": list(set(data["events"])),
                }
                for user, data in sorted(
                    user_risks.items(), key=lambda x: x[1]["risk_score"], reverse=True
                )[:20]
            ],
        )

        return report

    async def generate_user_activity_report(
        self, user_id: str, start_time: datetime, end_time: datetime
    ) -> UserActivityReport:
        """生成用户活动报告"""
        # 获取用户事件
        events = await self.get_audit_events(
            start_time, end_time, user_ids=[user_id], limit=5000
        )

        if not events:
            return UserActivityReport(
                user_id=user_id,
                period={"start": start_time, "end": end_time},
                total_actions=0,
                action_breakdown={},
                resource_access={},
                success_rate=0.0,
                peak_activity_times=[],
                security_events=0,
                last_activity=None,
            )

        # 分析用户活动
        action_counts = Counter()
        resource_counts = Counter()
        success_count = 0
        security_events = 0
        activity_hours = defaultdict(int)
        timestamps = []

        for event in events:
            action = event.get("action", "unknown")
            resource = event.get("resource", "unknown")
            outcome = event.get("outcome", "unknown")
            timestamp_str = event.get("timestamp")

            action_counts[action] += 1
            resource_counts[resource] += 1

            if outcome == "success":
                success_count += 1

            # 统计安全事件
            event_type = event.get("event_type", "")
            if any(
                sec_type in event_type
                for sec_type in ["security", "violation", "failure"]
            ):
                security_events += 1

            # 分析活动时间模式
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    )
                    timestamps.append(timestamp)
                    activity_hours[timestamp.hour] += 1
                except ValueError:
                    pass

        # 计算成功率
        success_rate = (success_count / len(events)) * 100 if events else 0

        # 找出活跃时间段
        peak_hours = sorted(activity_hours.items(), key=lambda x: x[1], reverse=True)[
            :3
        ]
        peak_activity_times = [
            f"{hour:02d}:00-{hour+1:02d}:00" for hour, _ in peak_hours
        ]

        # 最后活动时间
        last_activity = max(timestamps) if timestamps else None

        return UserActivityReport(
            user_id=user_id,
            period={"start": start_time, "end": end_time},
            total_actions=len(events),
            action_breakdown=dict(action_counts.most_common(10)),
            resource_access=dict(resource_counts.most_common(10)),
            success_rate=round(success_rate, 2),
            peak_activity_times=peak_activity_times,
            security_events=security_events,
            last_activity=last_activity,
        )

    async def detect_anomalies(
        self, start_time: datetime, end_time: datetime
    ) -> list[dict[str, Any]]:
        """检测异常活动模式"""
        events = await self.get_audit_events(start_time, end_time, limit=10000)

        anomalies = []

        # 按用户分组分析
        user_activities = defaultdict(list)
        for event in events:
            user_id = event.get("user_id")
            if user_id:
                user_activities[user_id].append(event)

        for user_id, user_events in user_activities.items():
            # 检测异常登录模式
            login_failures = [
                e for e in user_events if "login.failure" in e.get("event_type", "")
            ]

            if len(login_failures) > 5:  # 5次以上登录失败
                anomalies.append(
                    {
                        "type": "excessive_login_failures",
                        "severity": "high",
                        "user_id": user_id,
                        "failure_count": len(login_failures),
                        "description": f"User {user_id} had {len(login_failures)} login failures",
                    }
                )

            # 检测大量API调用
            api_requests = [
                e for e in user_events if e.get("event_type") == "api.request"
            ]

            if len(api_requests) > 1000:  # 单用户超过1000次API调用
                anomalies.append(
                    {
                        "type": "excessive_api_usage",
                        "severity": "medium",
                        "user_id": user_id,
                        "request_count": len(api_requests),
                        "description": f"User {user_id} made {len(api_requests)} API requests",
                    }
                )

        # 按IP分组分析
        ip_activities = defaultdict(list)
        for event in events:
            ip_address = event.get("ip_address")
            if ip_address and ip_address != "unknown":
                ip_activities[ip_address].append(event)

        for ip_address, ip_events in ip_activities.items():
            # 检测来自单一IP的大量请求
            if len(ip_events) > 500:  # 单IP超过500次请求
                unique_users = len(
                    {e.get("user_id") for e in ip_events if e.get("user_id")}
                )

                anomalies.append(
                    {
                        "type": "high_volume_from_single_ip",
                        "severity": "medium",
                        "ip_address": ip_address,
                        "request_count": len(ip_events),
                        "unique_users": unique_users,
                        "description": f"IP {ip_address} generated {len(ip_events)} requests from {unique_users} users",
                    }
                )

        return anomalies

    async def export_audit_report(
        self,
        start_time: datetime,
        end_time: datetime,
        output_file: Path,
        format: str = "json",
    ) -> dict[str, Any]:
        """导出完整审计报告"""
        # 生成各种报告
        summary = await self.generate_audit_summary(start_time, end_time)
        security_report = await self.generate_security_report(start_time, end_time)
        anomalies = await self.detect_anomalies(start_time, end_time)

        # 构建完整报告
        full_report = {
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                },
                "report_type": "audit_report",
                "format": format,
            },
            "summary": summary,
            "security": security_report,
            "anomalies": anomalies,
        }

        # 导出文件
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(full_report, f, indent=2, ensure_ascii=False, default=str)
        else:
            raise ValueError(f"Unsupported format: {format}")

        return {
            "output_file": str(output_file),
            "report_size": len(json.dumps(full_report, default=str)),
            "events_analyzed": summary.total_events,
            "security_events": security_report.total_security_events,
            "anomalies_detected": len(anomalies),
        }
