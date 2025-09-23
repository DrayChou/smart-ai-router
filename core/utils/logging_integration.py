#!/usr/bin/env python3
"""
智能日志系统集成模块
将AIRouter的智能日志功能无缝集成到现有日志系统中
"""

import logging
from typing import Optional

from .logger import get_logger  # 现有的日志系统
from .smart_logging import SmartLogFilter, get_smart_logger


class SmartLoggingIntegration:
    """智能日志系统集成器"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.enabled = False
            self.smart_filter = None
            self.enhanced_loggers = {}
            self._initialized = True

    def enable_smart_logging(
        self,
        enable_sensitive_cleaning: bool = True,
        enable_content_truncation: bool = True,
        max_content_length: int = 500,
    ) -> None:
        """
        启用智能日志功能

        Args:
            enable_sensitive_cleaning: 是否启用敏感信息清理
            enable_content_truncation: 是否启用内容截断
            max_content_length: 最大内容长度
        """
        self.enabled = True

        # 创建智能过滤器
        self.smart_filter = SmartLogFilter(
            enable_sensitive_cleaning=enable_sensitive_cleaning,
            enable_content_truncation=enable_content_truncation,
            max_content_length=max_content_length,
        )

        # 为现有的logger添加智能过滤器
        self._enhance_existing_loggers()

        logging.getLogger("smart-ai-router").info(
            "[SMART] LOGGING ENABLED: Sensitive info cleaning, content truncation activated"
        )

    def disable_smart_logging(self) -> None:
        """禁用智能日志功能"""
        self.enabled = False
        self.smart_filter = None

        # 移除智能过滤器
        self._remove_smart_filters()

        logging.getLogger("smart-ai-router").info(
            "🔧 SMART LOGGING DISABLED: Reverted to standard logging"
        )

    def _enhance_existing_loggers(self) -> None:
        """为现有日志器添加智能过滤器"""
        if not self.smart_filter:
            return

        # 获取主要的日志器名称
        logger_names = [
            "smart-ai-router",
            "uvicorn",
            "fastapi",
            "api.anthropic",
            "api.openai",
        ]

        for logger_name in logger_names:
            logger = logging.getLogger(logger_name)

            # 为每个处理器添加智能过滤器
            for handler in logger.handlers:
                if not any(isinstance(f, SmartLogFilter) for f in handler.filters):
                    handler.addFilter(self.smart_filter)

            self.enhanced_loggers[logger_name] = logger

    def _remove_smart_filters(self) -> None:
        """移除智能过滤器"""
        for _logger_name, logger in self.enhanced_loggers.items():
            for handler in logger.handlers:
                # 移除SmartLogFilter类型的过滤器
                handler.filters = [
                    f for f in handler.filters if not isinstance(f, SmartLogFilter)
                ]

        self.enhanced_loggers.clear()

    def get_enhanced_logger(self, name: str) -> logging.Logger:
        """
        获取增强的日志器

        Args:
            name: 日志器名称

        Returns:
            logging.Logger: 增强后的日志器
        """
        if self.enabled:
            # 如果启用了智能日志，使用智能日志器
            return get_smart_logger(name)
        else:
            # 否则使用现有的日志系统
            return get_logger(name)

    def log_with_context(
        self, logger: logging.Logger, level: int, message: str, **context
    ) -> None:
        """
        带上下文的日志记录

        Args:
            logger: 日志器
            level: 日志级别
            message: 日志消息
            **context: 上下文信息
        """
        if self.enabled:
            # 创建额外的上下文信息
            extra = {}
            for key, value in context.items():
                extra[key] = value

            logger.log(level, message, extra=extra)
        else:
            # 标准日志记录
            logger.log(level, message)


# 全局集成实例
_integration = SmartLoggingIntegration()


def enable_smart_logging(**kwargs) -> None:
    """启用智能日志功能的便捷函数"""
    _integration.enable_smart_logging(**kwargs)


def disable_smart_logging() -> None:
    """禁用智能日志功能的便捷函数"""
    _integration.disable_smart_logging()


def get_enhanced_logger(name: str = None) -> logging.Logger:
    """
    获取增强日志器的便捷函数

    Args:
        name: 日志器名称

    Returns:
        logging.Logger: 增强后的日志器
    """
    if name is None:
        import inspect

        frame = inspect.currentframe().f_back
        name = frame.f_globals.get("__name__", "smart-ai-router")

    return _integration.get_enhanced_logger(name)


def is_smart_logging_enabled() -> bool:
    """检查智能日志是否启用"""
    return _integration.enabled


def log_api_request(
    logger: logging.Logger,
    method: str,
    url: str,
    headers: Optional[dict] = None,
    body: Optional[str] = None,
    **context,
) -> None:
    """
    记录API请求的便捷函数

    Args:
        logger: 日志器
        method: HTTP方法
        url: 请求URL
        headers: 请求头（会自动清理敏感信息）
        body: 请求体（会自动截断）
        **context: 额外上下文
    """
    message = f"API REQUEST: {method} {url}"

    _integration.log_with_context(
        logger,
        logging.INFO,
        message,
        api_method=method,
        api_url=url,
        api_headers=headers,
        api_body=body,
        **context,
    )


def log_api_response(
    logger: logging.Logger,
    status_code: int,
    response_time: float,
    body: Optional[str] = None,
    **context,
) -> None:
    """
    记录API响应的便捷函数

    Args:
        logger: 日志器
        status_code: HTTP状态码
        response_time: 响应时间（秒）
        body: 响应体（会自动截断）
        **context: 额外上下文
    """
    message = f"API RESPONSE: {status_code} - {response_time:.4f}s"

    _integration.log_with_context(
        logger,
        logging.INFO,
        message,
        api_status_code=status_code,
        api_response_time=response_time,
        api_response_body=body,
        **context,
    )


def log_channel_operation(
    logger: logging.Logger,
    operation: str,
    channel_id: str,
    model: str = None,
    success: bool = True,
    error: str = None,
    **context,
) -> None:
    """
    记录渠道操作的便捷函数

    Args:
        logger: 日志器
        operation: 操作类型 (request, discovery, health_check等)
        channel_id: 渠道ID
        model: 模型名称
        success: 是否成功
        error: 错误信息
        **context: 额外上下文
    """
    message = f"CHANNEL {operation.upper()}: {channel_id}"

    if model:
        message += f" -> {model}"

    if not success and error:
        message += f" - {error}"

    level = logging.INFO if success else logging.ERROR

    _integration.log_with_context(
        logger,
        level,
        message,
        channel_operation=operation,
        channel_id=channel_id,
        model=model,
        success=success,
        error=error,
        **context,
    )


def log_cost_info(
    logger: logging.Logger,
    cost: float,
    model: str,
    channel_id: str,
    tokens: dict[str, int] = None,
    **context,
) -> None:
    """
    记录成本信息的便捷函数

    Args:
        logger: 日志器
        cost: 成本金额
        model: 模型名称
        channel_id: 渠道ID
        tokens: Token统计
        **context: 额外上下文
    """
    message = f"COST TRACKING: ${cost:.6f} for {model} via {channel_id}"

    if tokens:
        message += f" (tokens: {tokens})"

    _integration.log_with_context(
        logger,
        logging.INFO,
        message,
        cost=cost,
        model=model,
        channel_id=channel_id,
        tokens=tokens,
        **context,
    )
