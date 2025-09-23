"""
统一异常处理模块
"""

from .base_exceptions import (
    AuthenticationException,
    BaseRouterException,
    ChannelException,
    ConfigurationException,
    ModelException,
    NetworkException,
    ParameterComparisonError,
    RoutingException,
    TagNotFoundError,
)
from .error_codes import ErrorCode, get_error_message
from .error_handler import ErrorHandler, get_error_handler, handle_errors

__all__ = [
    # 错误码
    "ErrorCode",
    "get_error_message",
    # 异常类
    "BaseRouterException",
    "ConfigurationException",
    "RoutingException",
    "ChannelException",
    "ModelException",
    "NetworkException",
    "AuthenticationException",
    # 向后兼容的异常
    "TagNotFoundError",
    "ParameterComparisonError",
    # 错误处理器
    "ErrorHandler",
    "get_error_handler",
    "handle_errors",
]
