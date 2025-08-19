# -*- coding: utf-8 -*-
"""
审计日志系统 - 专门用于记录用户行为和系统操作的审计追踪
"""
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

from core.utils.logger import get_smart_logger, SmartAILogger, LogEntry


class AuditEventType(Enum):
    """审计事件类型枚举"""
    # 认证相关
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    TOKEN_GENERATED = "auth.token.generated"
    
    # API请求相关
    API_REQUEST = "api.request"
    API_RESPONSE = "api.response"
    API_ERROR = "api.error"
    
    # 路由决策相关
    ROUTE_SELECTED = "routing.route.selected"
    ROUTE_FAILED = "routing.route.failed"
    STRATEGY_CHANGED = "routing.strategy.changed"
    
    # 配置管理相关
    CONFIG_UPDATED = "config.updated"
    CHANNEL_ENABLED = "config.channel.enabled"
    CHANNEL_DISABLED = "config.channel.disabled"
    
    # 系统操作相关
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    CACHE_CLEARED = "system.cache.cleared"
    
    # 数据操作相关
    DATA_EXPORT = "data.export"
    LOG_CLEANUP = "data.log.cleanup"
    
    # 安全相关
    SECURITY_VIOLATION = "security.violation"
    RATE_LIMIT_EXCEEDED = "security.rate_limit"


class AuditLevel(Enum):
    """审计日志级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """审计事件数据结构"""
    event_type: AuditEventType
    level: AuditLevel
    timestamp: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    resource: Optional[str] = None
    action: Optional[str] = None
    outcome: str = "success"
    details: Optional[Dict[str, Any]] = None
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['event_type'] = self.event_type.value
        data['level'] = self.level.value
        return {k: v for k, v in data.items() if v is not None}


class AuditLogger:
    """审计日志记录器"""
    
    def __init__(self, smart_logger: Optional[SmartAILogger] = None):
        self.smart_logger = smart_logger or get_smart_logger()
        self.context: Dict[str, Any] = {}
        
    def set_context(self, **context_data) -> None:
        """设置审计上下文信息"""
        self.context.update(context_data)
    
    def clear_context(self) -> None:
        """清除审计上下文"""
        self.context.clear()
    
    def log_event(
        self,
        event_type: AuditEventType,
        level: AuditLevel = AuditLevel.LOW,
        outcome: str = "success",
        resource: Optional[str] = None,
        action: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        **extra_context
    ) -> None:
        """记录审计事件"""
        try:
            # 合并上下文数据
            context = {**self.context, **extra_context}
            
            # 创建审计事件
            audit_event = AuditEvent(
                event_type=event_type,
                level=level,
                timestamp=datetime.now(timezone.utc).isoformat(),
                user_id=context.get('user_id'),
                session_id=context.get('session_id'),
                request_id=context.get('request_id'),
                ip_address=context.get('ip_address'),
                user_agent=context.get('user_agent'),
                resource=resource,
                action=action,
                outcome=outcome,
                details=details,
                before_state=before_state,
                after_state=after_state,
                error_message=error_message
            )
            
            # 使用Smart Logger记录
            if self.smart_logger:
                log_level = self._get_log_level(level)
                message = f"AUDIT: {event_type.value} - {outcome}"
                
                getattr(self.smart_logger, log_level)(
                    message,
                    audit_event=audit_event.to_dict(),
                    **context
                )
            
        except Exception as e:
            # 审计日志记录失败不应影响业务流程
            if self.smart_logger:
                self.smart_logger.error(f"Failed to log audit event: {e}")
    
    def _get_log_level(self, audit_level: AuditLevel) -> str:
        """将审计级别映射到日志级别"""
        mapping = {
            AuditLevel.LOW: "info",
            AuditLevel.MEDIUM: "info",
            AuditLevel.HIGH: "warning",
            AuditLevel.CRITICAL: "error"
        }
        return mapping.get(audit_level, "info")
    
    # --- 认证审计方法 ---
    
    def log_login_success(self, user_id: str, ip_address: str, user_agent: str) -> None:
        """记录成功登录"""
        self.log_event(
            AuditEventType.LOGIN_SUCCESS,
            AuditLevel.MEDIUM,
            resource="authentication",
            action="login",
            details={"login_method": "token"},
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    def log_login_failure(self, ip_address: str, user_agent: str, reason: str) -> None:
        """记录登录失败"""
        self.log_event(
            AuditEventType.LOGIN_FAILURE,
            AuditLevel.HIGH,
            outcome="failure",
            resource="authentication",
            action="login",
            details={"failure_reason": reason},
            error_message=reason,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    def log_token_generated(self, token_type: str = "api") -> None:
        """记录Token生成"""
        self.log_event(
            AuditEventType.TOKEN_GENERATED,
            AuditLevel.HIGH,
            resource="authentication",
            action="token_generate",
            details={"token_type": token_type}
        )
    
    # --- API审计方法 ---
    
    def log_api_request(
        self,
        method: str,
        path: str,
        status_code: int,
        process_time: float,
        request_size: Optional[int] = None,
        response_size: Optional[int] = None
    ) -> None:
        """记录API请求"""
        outcome = "success" if 200 <= status_code < 400 else "error"
        level = AuditLevel.LOW if outcome == "success" else AuditLevel.MEDIUM
        
        self.log_event(
            AuditEventType.API_REQUEST,
            level,
            outcome=outcome,
            resource="api",
            action=f"{method} {path}",
            details={
                "method": method,
                "path": path,
                "status_code": status_code,
                "process_time": process_time,
                "request_size": request_size,
                "response_size": response_size
            }
        )
    
    def log_api_error(
        self,
        method: str,
        path: str,
        error_code: int,
        error_message: str,
        process_time: float
    ) -> None:
        """记录API错误"""
        self.log_event(
            AuditEventType.API_ERROR,
            AuditLevel.HIGH,
            outcome="error",
            resource="api",
            action=f"{method} {path}",
            details={
                "method": method,
                "path": path,
                "error_code": error_code,
                "process_time": process_time
            },
            error_message=error_message
        )
    
    # --- 路由审计方法 ---
    
    def log_route_selected(
        self,
        model: str,
        selected_channel: str,
        strategy: str,
        alternatives: List[str]
    ) -> None:
        """记录路由选择"""
        self.log_event(
            AuditEventType.ROUTE_SELECTED,
            AuditLevel.LOW,
            resource="routing",
            action="route_select",
            details={
                "requested_model": model,
                "selected_channel": selected_channel,
                "strategy": strategy,
                "alternatives_count": len(alternatives),
                "alternatives": alternatives[:5]
            }
        )
    
    def log_route_failed(
        self,
        model: str,
        failed_channel: str,
        error_reason: str,
        fallback_channel: Optional[str] = None
    ) -> None:
        """记录路由失败"""
        self.log_event(
            AuditEventType.ROUTE_FAILED,
            AuditLevel.MEDIUM,
            outcome="failure",
            resource="routing",
            action="route_attempt",
            details={
                "requested_model": model,
                "failed_channel": failed_channel,
                "fallback_channel": fallback_channel,
                "error_reason": error_reason
            },
            error_message=error_reason
        )
    
    def log_strategy_change(self, old_strategy: str, new_strategy: str) -> None:
        """记录路由策略变更"""
        self.log_event(
            AuditEventType.STRATEGY_CHANGED,
            AuditLevel.HIGH,
            resource="routing",
            action="strategy_change",
            before_state={"strategy": old_strategy},
            after_state={"strategy": new_strategy}
        )
    
    # --- 配置管理审计方法 ---
    
    def log_config_update(
        self,
        config_section: str,
        changes: Dict[str, Any],
        before_values: Optional[Dict[str, Any]] = None
    ) -> None:
        """记录配置更新"""
        self.log_event(
            AuditEventType.CONFIG_UPDATED,
            AuditLevel.HIGH,
            resource="configuration",
            action="config_update",
            details={
                "config_section": config_section,
                "changes": changes
            },
            before_state=before_values,
            after_state=changes
        )
    
    def log_channel_status_change(
        self,
        channel_id: str,
        enabled: bool,
        reason: Optional[str] = None
    ) -> None:
        """记录渠道状态变更"""
        event_type = AuditEventType.CHANNEL_ENABLED if enabled else AuditEventType.CHANNEL_DISABLED
        action = "enable" if enabled else "disable"
        
        self.log_event(
            event_type,
            AuditLevel.MEDIUM,
            resource="channel",
            action=f"channel_{action}",
            details={
                "channel_id": channel_id,
                "enabled": enabled,
                "reason": reason
            }
        )
    
    # --- 系统操作审计方法 ---
    
    def log_system_startup(self, version: str, config_info: Dict[str, Any]) -> None:
        """记录系统启动"""
        self.log_event(
            AuditEventType.SYSTEM_STARTUP,
            AuditLevel.MEDIUM,
            resource="system",
            action="startup",
            details={
                "version": version,
                "config_info": config_info
            }
        )
    
    def log_system_shutdown(self, uptime_seconds: float) -> None:
        """记录系统关闭"""
        self.log_event(
            AuditEventType.SYSTEM_SHUTDOWN,
            AuditLevel.MEDIUM,
            resource="system",
            action="shutdown",
            details={"uptime_seconds": uptime_seconds}
        )
    
    def log_cache_cleared(self, cache_type: str, entries_count: int) -> None:
        """记录缓存清理"""
        self.log_event(
            AuditEventType.CACHE_CLEARED,
            AuditLevel.LOW,
            resource="cache",
            action="clear",
            details={
                "cache_type": cache_type,
                "entries_count": entries_count
            }
        )
    
    # --- 数据操作审计方法 ---
    
    def log_data_export(
        self,
        export_type: str,
        records_count: int,
        format: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> None:
        """记录数据导出"""
        self.log_event(
            AuditEventType.DATA_EXPORT,
            AuditLevel.HIGH,
            resource="data",
            action="export",
            details={
                "export_type": export_type,
                "records_count": records_count,
                "format": format,
                "filters": filters
            }
        )
    
    def log_data_cleanup(
        self,
        cleanup_type: str,
        deleted_count: int,
        criteria: Dict[str, Any]
    ) -> None:
        """记录数据清理"""
        self.log_event(
            AuditEventType.LOG_CLEANUP,
            AuditLevel.MEDIUM,
            resource="data",
            action="cleanup",
            details={
                "cleanup_type": cleanup_type,
                "deleted_count": deleted_count,
                "criteria": criteria
            }
        )
    
    # --- 安全审计方法 ---
    
    def log_security_violation(
        self,
        violation_type: str,
        severity: str,
        description: str,
        ip_address: str
    ) -> None:
        """记录安全违规"""
        level = AuditLevel.CRITICAL if severity == "high" else AuditLevel.HIGH
        
        self.log_event(
            AuditEventType.SECURITY_VIOLATION,
            level,
            outcome="violation",
            resource="security",
            action="violation",
            details={
                "violation_type": violation_type,
                "severity": severity,
                "description": description
            },
            ip_address=ip_address,
            error_message=description
        )
    
    def log_rate_limit_exceeded(
        self,
        endpoint: str,
        limit: int,
        window: str,
        ip_address: str
    ) -> None:
        """记录速率限制超限"""
        self.log_event(
            AuditEventType.RATE_LIMIT_EXCEEDED,
            AuditLevel.MEDIUM,
            outcome="blocked",
            resource="rate_limit",
            action="limit_exceeded",
            details={
                "endpoint": endpoint,
                "limit": limit,
                "window": window
            },
            ip_address=ip_address
        )


# 全局审计记录器实例
_global_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> Optional[AuditLogger]:
    """获取全局审计记录器"""
    return _global_audit_logger


def initialize_audit_logger(smart_logger: Optional[SmartAILogger] = None) -> AuditLogger:
    """初始化全局审计记录器"""
    global _global_audit_logger
    _global_audit_logger = AuditLogger(smart_logger)
    return _global_audit_logger