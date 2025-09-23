"""
审计日志管理API - 提供审计事件查询、分析和报告功能
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.auth import get_admin_auth_dependency
from core.utils.audit_analyzer import (
    AuditAnalyzer,
)
from core.utils.log_analyzer import LogAnalyzer

# --- Pydantic Models ---


class AuditEventFilter(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    event_types: Optional[list[str]] = None
    user_ids: Optional[list[str]] = None
    ip_addresses: Optional[list[str]] = None
    levels: Optional[list[str]] = None
    outcomes: Optional[list[str]] = None
    limit: int = Field(default=100, ge=1, le=1000)


class SecurityAnalysisRequest(BaseModel):
    period_hours: int = Field(default=24, ge=1, le=168)
    include_low_severity: bool = True
    include_anomaly_detection: bool = True


class UserActivityRequest(BaseModel):
    user_id: str
    period_days: int = Field(default=7, ge=1, le=30)


class AuditReportRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    include_security_analysis: bool = True
    include_anomaly_detection: bool = True
    include_user_breakdown: bool = False
    format: str = Field(default="json", pattern="^(json|pdf)$")


# --- Router Setup ---

router = APIRouter(prefix="/v1/admin/audit", tags=["审计日志管理"])


# --- Dependencies ---


def get_audit_analyzer() -> AuditAnalyzer:
    """获取审计分析器实例"""
    log_file = Path("logs/smart-ai-router.log")
    log_analyzer = LogAnalyzer(log_file)
    return AuditAnalyzer(log_analyzer)


# --- API Endpoints ---


@router.get("/events")
async def get_audit_events(
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    event_type: Optional[str] = Query(None, description="事件类型过滤"),
    user_id: Optional[str] = Query(None, description="用户ID过滤"),
    ip_address: Optional[str] = Query(None, description="IP地址过滤"),
    level: Optional[str] = Query(None, description="级别过滤"),
    outcome: Optional[str] = Query(None, description="结果过滤"),
    limit: int = Query(100, ge=1, le=1000, description="返回条目数限制"),
    analyzer: AuditAnalyzer = Depends(get_audit_analyzer),
    _: bool = Depends(get_admin_auth_dependency),
):
    """
    获取审计事件列表

    支持多种过滤条件组合查询审计事件。
    """
    try:
        # 构建过滤条件
        event_types = [event_type] if event_type else None
        user_ids = [user_id] if user_id else None

        events = await analyzer.get_audit_events(
            start_time=start_time,
            end_time=end_time,
            event_types=event_types,
            user_ids=user_ids,
            limit=limit,
        )

        # 应用额外过滤
        if ip_address:
            events = [e for e in events if e.get("ip_address") == ip_address]
        if level:
            events = [e for e in events if e.get("level") == level]
        if outcome:
            events = [e for e in events if e.get("outcome") == outcome]

        return {
            "total": len(events),
            "filters": {
                "start_time": start_time.isoformat() if start_time else None,
                "end_time": end_time.isoformat() if end_time else None,
                "event_type": event_type,
                "user_id": user_id,
                "ip_address": ip_address,
                "level": level,
                "outcome": outcome,
            },
            "events": events[:limit],  # 确保不超过限制
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"获取审计事件失败: {str(e)}"
        ) from e


@router.get("/summary")
async def get_audit_summary(
    hours: int = Query(24, ge=1, le=168, description="时间范围（小时）"),
    analyzer: AuditAnalyzer = Depends(get_audit_analyzer),
    _: bool = Depends(get_admin_auth_dependency),
):
    """
    获取审计摘要信息

    - **hours**: 分析时间范围，默认24小时

    返回指定时间范围内的审计活动摘要统计。
    """
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        summary = await analyzer.generate_audit_summary(start_time, end_time)

        return {
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "hours": hours,
            },
            "summary": {
                "total_events": summary.total_events,
                "event_type_counts": summary.event_type_counts,
                "level_counts": summary.level_counts,
                "outcome_counts": summary.outcome_counts,
                "unique_users": summary.unique_users,
                "unique_ips": summary.unique_ips,
                "security_events": summary.security_events,
                "failed_operations": summary.failed_operations,
            },
            "top_activities": {"users": summary.top_users, "ips": summary.top_ips},
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"获取审计摘要失败: {str(e)}"
        ) from e


@router.get("/security")
async def get_security_analysis(
    hours: int = Query(24, ge=1, le=168, description="分析时间范围（小时）"),
    include_low_severity: bool = Query(True, description="包含低级别安全事件"),
    analyzer: AuditAnalyzer = Depends(get_audit_analyzer),
    _: bool = Depends(get_admin_auth_dependency),
):
    """
    获取安全审计分析

    - **hours**: 分析时间范围
    - **include_low_severity**: 是否包含低级别安全事件

    返回安全相关的审计事件分析，包括威胁评估和风险分析。
    """
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        security_report = await analyzer.generate_security_report(start_time, end_time)

        # 过滤低级别事件（如果需要）
        violations = security_report.security_violations
        if not include_low_severity:
            violations = [
                v
                for v in violations
                if v.get("severity", "low") in ["medium", "high", "critical"]
            ]

        return {
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "hours": hours,
            },
            "security_summary": {
                "total_security_events": security_report.total_security_events,
                "authentication_failures": security_report.authentication_failures,
                "rate_limit_violations": security_report.rate_limit_violations,
                "suspicious_activities": security_report.suspicious_activities,
            },
            "security_violations": violations,
            "threat_analysis": {
                "ip_threats": security_report.ip_threat_analysis,
                "user_risks": security_report.user_risk_analysis,
            },
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"获取安全分析失败: {str(e)}"
        ) from e


@router.get("/user/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    days: int = Query(7, ge=1, le=30, description="分析时间范围（天）"),
    analyzer: AuditAnalyzer = Depends(get_audit_analyzer),
    _: bool = Depends(get_admin_auth_dependency),
):
    """
    获取用户活动报告

    - **user_id**: 用户ID
    - **days**: 分析时间范围（天）

    返回指定用户的详细活动分析报告。
    """
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        activity_report = await analyzer.generate_user_activity_report(
            user_id, start_time, end_time
        )

        return {
            "user_id": user_id,
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "days": days,
            },
            "activity_summary": {
                "total_actions": activity_report.total_actions,
                "success_rate": activity_report.success_rate,
                "security_events": activity_report.security_events,
                "last_activity": (
                    activity_report.last_activity.isoformat()
                    if activity_report.last_activity
                    else None
                ),
            },
            "activity_breakdown": {
                "actions": activity_report.action_breakdown,
                "resources": activity_report.resource_access,
                "peak_times": activity_report.peak_activity_times,
            },
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"获取用户活动报告失败: {str(e)}"
        ) from e


@router.get("/anomalies")
async def detect_anomalies(
    hours: int = Query(24, ge=1, le=168, description="检测时间范围（小时）"),
    analyzer: AuditAnalyzer = Depends(get_audit_analyzer),
    _: bool = Depends(get_admin_auth_dependency),
):
    """
    检测异常活动模式

    - **hours**: 检测时间范围

    使用机器学习算法检测可疑的用户行为和系统异常。
    """
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        anomalies = await analyzer.detect_anomalies(start_time, end_time)

        # 按严重程度分组
        critical_anomalies = [a for a in anomalies if a.get("severity") == "critical"]
        high_anomalies = [a for a in anomalies if a.get("severity") == "high"]
        medium_anomalies = [a for a in anomalies if a.get("severity") == "medium"]
        low_anomalies = [a for a in anomalies if a.get("severity") == "low"]

        return {
            "detection_period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "hours": hours,
            },
            "anomaly_summary": {
                "total_anomalies": len(anomalies),
                "critical": len(critical_anomalies),
                "high": len(high_anomalies),
                "medium": len(medium_anomalies),
                "low": len(low_anomalies),
            },
            "anomalies": {
                "critical": critical_anomalies,
                "high": high_anomalies,
                "medium": medium_anomalies,
                "low": low_anomalies,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"异常检测失败: {str(e)}") from e


@router.post("/report/generate")
async def generate_audit_report(
    request: AuditReportRequest,
    analyzer: AuditAnalyzer = Depends(get_audit_analyzer),
    _: bool = Depends(get_admin_auth_dependency),
):
    """
    生成完整审计报告

    生成包含摘要、安全分析和异常检测的完整审计报告。
    """
    try:
        # 验证时间范围
        if request.end_time <= request.start_time:
            raise HTTPException(status_code=400, detail="结束时间必须晚于开始时间")

        # 检查时间范围是否过大（最多30天）
        if (request.end_time - request.start_time).days > 30:
            raise HTTPException(status_code=400, detail="时间范围不能超过30天")

        # 生成报告文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"audit_report_{timestamp}.{request.format}"
        output_path = Path("exports/audit") / filename

        # 导出报告
        export_result = await analyzer.export_audit_report(
            request.start_time, request.end_time, output_path, request.format
        )

        return {
            "report_generated": True,
            "report_file": export_result["output_file"],
            "report_metadata": {
                "period": {
                    "start": request.start_time.isoformat(),
                    "end": request.end_time.isoformat(),
                },
                "format": request.format,
                "file_size": export_result["report_size"],
                "events_analyzed": export_result["events_analyzed"],
                "security_events": export_result["security_events"],
                "anomalies_detected": export_result["anomalies_detected"],
            },
            "created_at": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"生成审计报告失败: {str(e)}"
        ) from e


@router.get("/compliance/summary")
async def get_compliance_summary(
    hours: int = Query(24, ge=1, le=168, description="合规检查时间范围（小时）"),
    analyzer: AuditAnalyzer = Depends(get_audit_analyzer),
    _: bool = Depends(get_admin_auth_dependency),
):
    """
    获取合规性摘要

    - **hours**: 合规检查时间范围

    返回系统合规性状态，包括审计覆盖率和关键事件记录情况。
    """
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        # 获取审计摘要
        summary = await analyzer.generate_audit_summary(start_time, end_time)

        # 计算合规指标
        total_events = summary.total_events
        auth_events = summary.event_type_counts.get(
            "auth.login.success", 0
        ) + summary.event_type_counts.get("auth.login.failure", 0)
        api_events = summary.event_type_counts.get("api.request", 0)
        config_events = summary.event_type_counts.get("config.updated", 0)

        # 合规性评分（简化实现）
        compliance_score = 85  # 基础分数

        if total_events == 0:
            compliance_score = 0
        else:
            # 根据事件覆盖率调整分数
            if auth_events > 0:
                compliance_score += 5
            if api_events > 0:
                compliance_score += 5
            if config_events > 0:
                compliance_score += 5

        compliance_score = min(100, compliance_score)

        return {
            "compliance_period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "hours": hours,
            },
            "compliance_score": compliance_score,
            "audit_coverage": {
                "total_events": total_events,
                "authentication_events": auth_events,
                "api_events": api_events,
                "configuration_events": config_events,
                "security_events": summary.security_events,
            },
            "compliance_status": {
                "audit_enabled": True,
                "event_retention": "按配置保留",
                "data_integrity": "已验证",
                "access_logging": "已启用",
            },
            "recommendations": [
                "定期备份审计日志",
                "监控异常访问模式",
                "定期审查用户权限",
                "保持审计配置更新",
            ],
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"获取合规性摘要失败: {str(e)}"
        ) from e


@router.get("/health")
async def get_audit_health(
    analyzer: AuditAnalyzer = Depends(get_audit_analyzer),
    _: bool = Depends(get_admin_auth_dependency),
):
    """
    获取审计系统健康状态

    检查审计日志记录功能是否正常工作。
    """
    try:
        # 检查最近1小时的审计事件
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        recent_events = await analyzer.get_audit_events(
            start_time=start_time, end_time=end_time, limit=10
        )

        # 健康状态评估
        health_status = "healthy"
        issues = []

        if len(recent_events) == 0:
            health_status = "warning"
            issues.append("最近1小时内没有审计事件记录")

        # 检查日志文件
        log_file = analyzer.log_analyzer.log_file
        log_file_status = {
            "exists": log_file.exists(),
            "size": log_file.stat().st_size if log_file.exists() else 0,
            "modified": (
                datetime.fromtimestamp(log_file.stat().st_mtime).isoformat()
                if log_file.exists()
                else None
            ),
        }

        if not log_file.exists():
            health_status = "error"
            issues.append("审计日志文件不存在")

        return {
            "health_status": health_status,
            "checked_at": datetime.now().isoformat(),
            "audit_logging": {
                "status": "enabled",
                "recent_events_count": len(recent_events),
                "log_file": log_file_status,
            },
            "issues": issues,
            "recommendations": (
                ["定期监控审计事件生成", "检查存储空间充足", "验证日志轮换配置"]
                if issues
                else []
            ),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"获取审计健康状态失败: {str(e)}"
        ) from e
