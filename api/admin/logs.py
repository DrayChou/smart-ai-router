# -*- coding: utf-8 -*-
"""
日志管理API - 提供日志查询、分析和管理功能
"""
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Query, Body
from pydantic import BaseModel, Field

from core.utils.log_analyzer import LogAnalyzer, LogQuery, LogDashboard
from core.auth import get_admin_auth_dependency


# --- Pydantic Models ---

class LogSearchRequest(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    log_level: Optional[str] = None
    logger_name: Optional[str] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    message_pattern: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class LogExportRequest(BaseModel):
    query: LogSearchRequest
    format: str = Field(default="json", pattern="^(json|csv)$")


class AlertCheckResponse(BaseModel):
    alerts: List[Dict[str, Any]]
    checked_at: datetime


class LogStatsResponse(BaseModel):
    total_entries: int
    level_counts: Dict[str, int]
    logger_counts: Dict[str, int]
    error_patterns: List[Dict[str, Any]]
    request_stats: Dict[str, Any]
    time_range: Dict[str, Optional[datetime]]


# --- Router Setup ---

router = APIRouter(prefix="/v1/admin/logs", tags=["日志管理"])


# --- Global Dependencies ---

def get_log_analyzer() -> LogAnalyzer:
    """获取日志分析器实例"""
    log_file = Path("logs/smart-ai-router.log")
    return LogAnalyzer(log_file)


def get_log_dashboard(analyzer: LogAnalyzer = Depends(get_log_analyzer)) -> LogDashboard:
    """获取日志仪表板实例"""
    return LogDashboard(analyzer)


# --- API Endpoints ---

@router.get("/stats", response_model=LogStatsResponse)
async def get_log_statistics(
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    analyzer: LogAnalyzer = Depends(get_log_analyzer),
    _: bool = Depends(get_admin_auth_dependency)
):
    """
    获取日志统计信息
    
    - **start_time**: 统计开始时间 (可选)
    - **end_time**: 统计结束时间 (可选)
    
    返回日志的各种统计信息，包括级别分布、错误模式等。
    """
    try:
        stats = await analyzer.get_log_stats(start_time, end_time)
        return LogStatsResponse(
            total_entries=stats.total_entries,
            level_counts=stats.level_counts,
            logger_counts=stats.logger_counts,
            error_patterns=stats.error_patterns,
            request_stats=stats.request_stats,
            time_range=stats.time_range
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取日志统计失败: {str(e)}")


@router.post("/search")
async def search_logs(
    request: LogSearchRequest,
    analyzer: LogAnalyzer = Depends(get_log_analyzer),
    _: bool = Depends(get_admin_auth_dependency)
):
    """
    搜索日志条目
    
    支持多种搜索条件组合：
    - 时间范围过滤
    - 日志级别过滤
    - 请求ID和用户ID过滤
    - 消息内容模式匹配
    """
    try:
        query = LogQuery(
            start_time=request.start_time,
            end_time=request.end_time,
            log_level=request.log_level,
            logger_name=request.logger_name,
            request_id=request.request_id,
            user_id=request.user_id,
            message_pattern=request.message_pattern,
            limit=request.limit,
            offset=request.offset
        )
        
        results = await analyzer.search_logs(query)
        
        return {
            "total": len(results),
            "limit": request.limit,
            "offset": request.offset,
            "entries": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索日志失败: {str(e)}")


@router.get("/errors")
async def get_recent_errors(
    hours: int = Query(24, ge=1, le=168, description="时间范围（小时）"),
    limit: int = Query(100, ge=1, le=1000, description="返回条目数限制"),
    analyzer: LogAnalyzer = Depends(get_log_analyzer),
    _: bool = Depends(get_admin_auth_dependency)
):
    """
    获取最近的错误日志
    
    - **hours**: 时间范围，默认24小时
    - **limit**: 返回的错误日志条目数限制
    """
    try:
        error_logs = await analyzer.get_error_logs(hours=hours, limit=limit)
        
        return {
            "time_range": f"最近 {hours} 小时",
            "total_errors": len(error_logs),
            "errors": error_logs
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取错误日志失败: {str(e)}")


@router.get("/slow-requests")
async def get_slow_requests(
    min_duration: float = Query(5.0, ge=0.1, description="最小响应时间（秒）"),
    hours: int = Query(24, ge=1, le=168, description="时间范围（小时）"),
    limit: int = Query(50, ge=1, le=500, description="返回条目数限制"),
    analyzer: LogAnalyzer = Depends(get_log_analyzer),
    _: bool = Depends(get_admin_auth_dependency)
):
    """
    获取慢请求日志
    
    - **min_duration**: 最小响应时间阈值（秒）
    - **hours**: 时间范围
    - **limit**: 返回条目数限制
    """
    try:
        slow_requests = await analyzer.get_slow_requests(
            min_duration=min_duration,
            hours=hours,
            limit=limit
        )
        
        return {
            "criteria": {
                "min_duration": min_duration,
                "time_range": f"最近 {hours} 小时"
            },
            "total_slow_requests": len(slow_requests),
            "requests": slow_requests
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取慢请求日志失败: {str(e)}")


@router.get("/request/{request_id}/timeline")
async def get_request_timeline(
    request_id: str,
    analyzer: LogAnalyzer = Depends(get_log_analyzer),
    _: bool = Depends(get_admin_auth_dependency)
):
    """
    获取特定请求的完整时间线
    
    - **request_id**: 请求ID
    
    返回该请求从开始到结束的所有相关日志条目。
    """
    try:
        timeline = await analyzer.get_request_timeline(request_id)
        
        if not timeline:
            raise HTTPException(status_code=404, detail=f"未找到请求ID {request_id} 的日志")
        
        return {
            "request_id": request_id,
            "total_entries": len(timeline),
            "timeline": timeline
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取请求时间线失败: {str(e)}")


@router.post("/export")
async def export_logs(
    request: LogExportRequest,
    analyzer: LogAnalyzer = Depends(get_log_analyzer),
    _: bool = Depends(get_admin_auth_dependency)
):
    """
    导出日志到文件
    
    支持JSON和CSV格式导出。
    """
    try:
        # 生成导出文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs_export_{timestamp}.{request.format}"
        output_path = Path("exports") / filename
        
        query = LogQuery(
            start_time=request.query.start_time,
            end_time=request.query.end_time,
            log_level=request.query.log_level,
            logger_name=request.query.logger_name,
            request_id=request.query.request_id,
            user_id=request.query.user_id,
            message_pattern=request.query.message_pattern,
            limit=request.query.limit,
            offset=request.query.offset
        )
        
        exported_count = await analyzer.export_logs(query, output_path, request.format)
        
        return {
            "export_file": str(output_path),
            "exported_entries": exported_count,
            "format": request.format,
            "created_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出日志失败: {str(e)}")


@router.get("/alerts", response_model=AlertCheckResponse)
async def check_log_alerts(
    dashboard: LogDashboard = Depends(get_log_dashboard),
    _: bool = Depends(get_admin_auth_dependency)
):
    """
    检查日志警报
    
    检查系统是否存在异常情况，如高错误率、慢请求等。
    """
    try:
        alerts = await dashboard.check_alerts()
        
        return AlertCheckResponse(
            alerts=alerts,
            checked_at=datetime.now()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检查日志警报失败: {str(e)}")


@router.get("/report")
async def generate_log_report(
    start_time: datetime = Query(..., description="报告开始时间"),
    end_time: datetime = Query(..., description="报告结束时间"),
    dashboard: LogDashboard = Depends(get_log_dashboard),
    _: bool = Depends(get_admin_auth_dependency)
):
    """
    生成日志报告
    
    - **start_time**: 报告开始时间
    - **end_time**: 报告结束时间
    
    生成指定时间范围内的详细日志分析报告。
    """
    try:
        if end_time <= start_time:
            raise HTTPException(status_code=400, detail="结束时间必须晚于开始时间")
        
        # 检查时间范围是否过大（最多30天）
        if (end_time - start_time).days > 30:
            raise HTTPException(status_code=400, detail="时间范围不能超过30天")
        
        report = await dashboard.generate_report(start_time, end_time)
        
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成日志报告失败: {str(e)}")


@router.delete("/cleanup")
async def cleanup_old_logs(
    days: int = Query(30, ge=7, le=365, description="保留天数"),
    _: bool = Depends(get_admin_auth_dependency)
):
    """
    清理旧日志文件
    
    - **days**: 保留最近N天的日志，默认30天
    
    删除超过指定天数的日志文件以释放磁盘空间。
    """
    try:
        logs_dir = Path("logs")
        if not logs_dir.exists():
            return {"message": "日志目录不存在", "deleted_files": []}
        
        cutoff_time = datetime.now() - timedelta(days=days)
        deleted_files = []
        
        for log_file in logs_dir.glob("*.log.*"):
            try:
                file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if file_mtime < cutoff_time:
                    log_file.unlink()
                    deleted_files.append(str(log_file))
            except Exception as e:
                print(f"Failed to delete {log_file}: {e}")
        
        return {
            "message": f"清理完成，删除了 {len(deleted_files)} 个旧日志文件",
            "cutoff_date": cutoff_time.isoformat(),
            "deleted_files": deleted_files
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清理日志失败: {str(e)}")


@router.get("/health")
async def get_logging_health(
    analyzer: LogAnalyzer = Depends(get_log_analyzer),
    _: bool = Depends(get_admin_auth_dependency)
):
    """
    获取日志系统健康状态
    
    检查日志文件状态、磁盘使用情况等。
    """
    try:
        log_file = analyzer.log_file
        health_info = {
            "log_file_exists": log_file.exists(),
            "log_file_path": str(log_file),
            "log_file_size": 0,
            "log_file_modified": None,
            "logs_directory_size": 0,
            "backup_files_count": 0
        }
        
        if log_file.exists():
            stat = log_file.stat()
            health_info.update({
                "log_file_size": stat.st_size,
                "log_file_modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        
        # 检查日志目录
        logs_dir = log_file.parent
        if logs_dir.exists():
            total_size = sum(f.stat().st_size for f in logs_dir.glob("*") if f.is_file())
            backup_count = len(list(logs_dir.glob("*.log.*")))
            
            health_info.update({
                "logs_directory_size": total_size,
                "backup_files_count": backup_count
            })
        
        return health_info
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取日志健康状态失败: {str(e)}")