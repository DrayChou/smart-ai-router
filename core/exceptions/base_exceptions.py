"""
统一异常基类
定义所有系统异常的基础结构
"""

import traceback
from datetime import datetime
from typing import Any, Optional

from .error_codes import ErrorCode, get_error_message


class BaseRouterException(Exception):
    """路由器基础异常类"""

    def __init__(
        self,
        error_code: ErrorCode,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        self.error_code = error_code
        self.message = message or get_error_message(error_code)
        self.details = details or {}
        self.cause = cause
        self.context = context or {}
        self.timestamp = datetime.now()
        self.traceback_str = traceback.format_exc() if cause else None

        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_code": self.error_code.value,
            "message": self.message,
            "details": self.details,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "cause": str(self.cause) if self.cause else None,
            "traceback": self.traceback_str,
        }

    def __str__(self) -> str:
        return f"[{self.error_code.value}] {self.message}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(error_code={self.error_code.value}, message='{self.message}')"


class ConfigurationException(BaseRouterException):
    """配置相关异常"""

    def __init__(
        self,
        error_code: ErrorCode,
        message: Optional[str] = None,
        config_path: Optional[str] = None,
        **kwargs: Any,
    ):
        details = kwargs.get("details", {})
        if config_path:
            details["config_path"] = config_path

        super().__init__(error_code, message, details, **kwargs)


class RoutingException(BaseRouterException):
    """路由相关异常"""

    def __init__(
        self,
        error_code: ErrorCode,
        message: Optional[str] = None,
        model: Optional[str] = None,
        tags: Optional[list[str]] = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if model:
            details["model"] = model
        if tags:
            details["tags"] = tags

        super().__init__(error_code, message, details, **kwargs)


class ChannelException(BaseRouterException):
    """渠道相关异常"""

    def __init__(
        self,
        error_code: ErrorCode,
        message: Optional[str] = None,
        channel_id: Optional[str] = None,
        channel_name: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if channel_id:
            details["channel_id"] = channel_id
        if channel_name:
            details["channel_name"] = channel_name

        super().__init__(error_code, message, details, **kwargs)


class ModelException(BaseRouterException):
    """模型相关异常"""

    def __init__(
        self,
        error_code: ErrorCode,
        message: Optional[str] = None,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if model_name:
            details["model_name"] = model_name
        if provider:
            details["provider"] = provider

        super().__init__(error_code, message, details, **kwargs)


class NetworkException(BaseRouterException):
    """网络相关异常"""

    def __init__(
        self,
        error_code: ErrorCode,
        message: Optional[str] = None,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if url:
            details["url"] = url
        if status_code:
            details["status_code"] = status_code

        super().__init__(error_code, message, details, **kwargs)


class AuthenticationException(BaseRouterException):
    """认证相关异常"""

    def __init__(
        self,
        error_code: ErrorCode,
        message: Optional[str] = None,
        token: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if token:
            # 只保存token的前几位用于调试，不泄露完整token
            details["token_prefix"] = token[:8] + "..." if len(token) > 8 else token

        super().__init__(error_code, message, details, **kwargs)


# 向后兼容的异常别名
class TagNotFoundError(RoutingException):
    """标签未找到错误 - 向后兼容"""

    def __init__(self, tags: list[str], message: Optional[str] = None):
        super().__init__(error_code=ErrorCode.TAG_NOT_FOUND, message=message, tags=tags)
        # 保持原有属性以兼容现有代码
        self.tags = tags


class ParameterComparisonError(RoutingException):
    """参数量比较错误 - 向后兼容"""

    def __init__(self, query: str, message: Optional[str] = None):
        super().__init__(
            error_code=ErrorCode.PARAMETER_COMPARISON_FAILED,
            message=message,
            details={"query": query},
        )
        # 保持原有属性以兼容现有代码
        self.query = query
