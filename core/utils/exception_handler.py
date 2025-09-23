"""
统一异常处理模块
提供一致的异常处理模式和错误分类
"""

import logging
import traceback
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, Type, Union

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """错误严重程度"""

    LOW = "low"  # 可忽略的错误，不影响核心功能
    MEDIUM = "medium"  # 需要关注但不影响服务的错误
    HIGH = "high"  # 影响功能的错误，需要立即处理
    CRITICAL = "critical"  # 系统级错误，可能导致服务不可用


class ErrorCategory(Enum):
    """错误类别"""

    NETWORK = "network"  # 网络相关错误
    AUTH = "authentication"  # 认证授权错误
    CONFIG = "configuration"  # 配置相关错误
    DATABASE = "database"  # 数据库相关错误
    EXTERNAL_API = "external_api"  # 外部API调用错误
    VALIDATION = "validation"  # 数据验证错误
    RESOURCE = "resource"  # 资源相关错误（内存、文件等）
    BUSINESS = "business"  # 业务逻辑错误
    SYSTEM = "system"  # 系统级错误


class SmartRouterException(Exception):
    """Smart Router基础异常类"""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[dict] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.category = category
        self.severity = severity
        self.context = context or {}
        self.cause = cause


class NetworkError(SmartRouterException):
    """网络相关错误"""

    def __init__(
        self,
        message: str,
        context: Optional[dict] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message, ErrorCategory.NETWORK, ErrorSeverity.HIGH, context, cause
        )


class AuthenticationError(SmartRouterException):
    """认证相关错误"""

    def __init__(
        self,
        message: str,
        context: Optional[dict] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message, ErrorCategory.AUTH, ErrorSeverity.HIGH, context, cause
        )


class ConfigurationError(SmartRouterException):
    """配置相关错误"""

    def __init__(
        self,
        message: str,
        context: Optional[dict] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message, ErrorCategory.CONFIG, ErrorSeverity.HIGH, context, cause
        )


class ExternalAPIError(SmartRouterException):
    """外部API调用错误"""

    def __init__(
        self,
        message: str,
        context: Optional[dict] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message, ErrorCategory.EXTERNAL_API, ErrorSeverity.MEDIUM, context, cause
        )


class ValidationError(SmartRouterException):
    """数据验证错误"""

    def __init__(
        self,
        message: str,
        context: Optional[dict] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message, ErrorCategory.VALIDATION, ErrorSeverity.MEDIUM, context, cause
        )


class ResourceError(SmartRouterException):
    """资源相关错误"""

    def __init__(
        self,
        message: str,
        context: Optional[dict] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message, ErrorCategory.RESOURCE, ErrorSeverity.HIGH, context, cause
        )


def safe_execute(
    operation_name: str,
    default_return: Any = None,
    reraise_exceptions: tuple = (),
    log_level: int = logging.ERROR,
    include_traceback: bool = True,
):
    """
    安全执行装饰器 - 统一异常处理

    Args:
        operation_name: 操作名称，用于日志
        default_return: 发生异常时的默认返回值
        reraise_exceptions: 需要重新抛出的异常类型
        log_level: 日志级别
        include_traceback: 是否包含堆栈跟踪
    """

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except reraise_exceptions:
                # 重新抛出指定的异常
                raise
            except SmartRouterException as e:
                # 处理自定义异常
                _log_smart_router_exception(
                    e, operation_name, log_level, include_traceback
                )
                return default_return
            except Exception as e:
                # 处理其他异常
                _log_generic_exception(e, operation_name, log_level, include_traceback)
                return default_return

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except reraise_exceptions:
                # 重新抛出指定的异常
                raise
            except SmartRouterException as e:
                # 处理自定义异常
                _log_smart_router_exception(
                    e, operation_name, log_level, include_traceback
                )
                return default_return
            except Exception as e:
                # 处理其他异常
                _log_generic_exception(e, operation_name, log_level, include_traceback)
                return default_return

        # 根据原函数是否是协程返回相应的包装器
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper

    return decorator


def _log_smart_router_exception(
    exception: SmartRouterException,
    operation_name: str,
    log_level: int,
    include_traceback: bool,
):
    """记录Smart Router自定义异常"""
    context_str = ""
    if exception.context:
        context_str = f", Context: {exception.context}"

    cause_str = ""
    if exception.cause:
        cause_str = f", Caused by: {exception.cause}"

    message = (
        f"[{exception.category.value.upper()}] {operation_name} failed: {exception}"
        f", Severity: {exception.severity.value}{context_str}{cause_str}"
    )

    if include_traceback:
        logger.log(log_level, message, exc_info=True)
    else:
        logger.log(log_level, message)


def _log_generic_exception(
    exception: Exception, operation_name: str, log_level: int, include_traceback: bool
):
    """记录通用异常"""
    message = f"[SYSTEM] {operation_name} failed: {exception}"

    if include_traceback:
        logger.log(log_level, message, exc_info=True)
    else:
        logger.log(log_level, message)


def handle_http_errors(func: Callable):
    """HTTP相关错误处理装饰器"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # 根据异常类型分类处理
            if "timeout" in str(e).lower():
                raise NetworkError(f"Network timeout: {e}", cause=e)
            elif "connection" in str(e).lower():
                raise NetworkError(f"Connection error: {e}", cause=e)
            elif "401" in str(e) or "unauthorized" in str(e).lower():
                raise AuthenticationError(f"Authentication failed: {e}", cause=e)
            elif "403" in str(e) or "forbidden" in str(e).lower():
                raise AuthenticationError(f"Access forbidden: {e}", cause=e)
            elif "404" in str(e) or "not found" in str(e).lower():
                raise ExternalAPIError(f"Resource not found: {e}", cause=e)
            elif "429" in str(e) or "rate limit" in str(e).lower():
                raise ExternalAPIError(f"Rate limit exceeded: {e}", cause=e)
            else:
                raise ExternalAPIError(f"HTTP error: {e}", cause=e)

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            # 根据异常类型分类处理
            if "timeout" in str(e).lower():
                raise NetworkError(f"Network timeout: {e}", cause=e)
            elif "connection" in str(e).lower():
                raise NetworkError(f"Connection error: {e}", cause=e)
            elif "401" in str(e) or "unauthorized" in str(e).lower():
                raise AuthenticationError(f"Authentication failed: {e}", cause=e)
            elif "403" in str(e) or "forbidden" in str(e).lower():
                raise AuthenticationError(f"Access forbidden: {e}", cause=e)
            elif "404" in str(e) or "not found" in str(e).lower():
                raise ExternalAPIError(f"Resource not found: {e}", cause=e)
            elif "429" in str(e) or "rate limit" in str(e).lower():
                raise ExternalAPIError(f"Rate limit exceeded: {e}", cause=e)
            else:
                raise ExternalAPIError(f"HTTP error: {e}", cause=e)

    # 根据原函数是否是协程返回相应的包装器
    import asyncio

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return wrapper


def validate_not_none(value: Any, name: str, context: Optional[dict] = None) -> Any:
    """验证值不为None"""
    if value is None:
        raise ValidationError(
            f"Required parameter '{name}' cannot be None", context=context
        )
    return value


def validate_not_empty(
    value: Union[str, list, dict], name: str, context: Optional[dict] = None
) -> Any:
    """验证值不为空"""
    if not value:
        raise ValidationError(
            f"Required parameter '{name}' cannot be empty", context=context
        )
    return value


def log_and_continue(
    operation_name: str,
    log_level: int = logging.WARNING,
    include_traceback: bool = False,
):
    """记录异常但继续执行的装饰器"""

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                message = f"{operation_name} encountered an error but continuing: {e}"
                if include_traceback:
                    logger.log(log_level, message, exc_info=True)
                else:
                    logger.log(log_level, message)
                # 继续执行，不抛出异常

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                message = f"{operation_name} encountered an error but continuing: {e}"
                if include_traceback:
                    logger.log(log_level, message, exc_info=True)
                else:
                    logger.log(log_level, message)
                # 继续执行，不抛出异常

        # 根据原函数是否是协程返回相应的包装器
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper

    return decorator
