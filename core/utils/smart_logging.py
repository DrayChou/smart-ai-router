#!/usr/bin/env python3
"""
智能日志系统 - 基于 AIRouter 的日志过滤和优化功能
提供敏感信息保护、内容过滤、格式化等智能日志处理能力
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


class SmartLogFilter(logging.Filter):
    """
    智能日志过滤器

    功能:
    - 清理和简化日志消息
    - 移除敏感信息 (API密钥、个人信息等)
    - 截断过长内容
    - 简化错误堆栈信息
    """

    def __init__(
        self,
        enable_sensitive_cleaning: bool = True,
        enable_content_truncation: bool = True,
        max_content_length: int = 500,
    ):
        """
        初始化智能日志过滤器

        Args:
            enable_sensitive_cleaning: 是否启用敏感信息清理
            enable_content_truncation: 是否启用内容截断
            max_content_length: 最大内容长度
        """
        super().__init__()
        self.enable_sensitive_cleaning = enable_sensitive_cleaning
        self.enable_content_truncation = enable_content_truncation
        self.max_content_length = max_content_length

        # 编译正则表达式以提高性能
        self._compile_patterns()

    def _compile_patterns(self):
        """编译常用的正则表达式模式"""
        # Base64图像数据模式
        self.base64_image_pattern = re.compile(
            r"data:image/[^;]+;base64,[A-Za-z0-9+/=]{50,}", re.IGNORECASE
        )

        # 大JSON数据模式
        self.large_json_pattern = re.compile(r"\{[^{}]{200,}\}")

        # API密钥模式
        self.api_key_patterns = [
            re.compile(r"sk-[A-Za-z0-9]{10,}"),  # OpenAI style (更宽松的匹配)
            re.compile(r"Bearer [A-Za-z0-9+/]{20,}"),  # Bearer tokens
            re.compile(
                r'api[_-]?key["\s]*[:=]["\s]*[A-Za-z0-9+/]{10,}', re.IGNORECASE
            ),  # Generic API keys
        ]

        # 错误堆栈模式
        self.traceback_pattern = re.compile(
            r"Traceback \(most recent call last\):.*?(?=\n\w|\n$|\Z)", re.DOTALL
        )

        # 敏感信息模式
        self.email_pattern = re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        )
        self.ip_pattern = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

        # HTTP请求体模式（通常包含敏感信息）
        self.http_body_pattern = re.compile(
            r'"(request|response)_body":\s*"[^"]{100,}"', re.IGNORECASE
        )

    def filter(self, record: logging.LogRecord) -> bool:
        """
        过滤和清理日志记录

        Args:
            record: 日志记录

        Returns:
            bool: 是否保留此日志记录
        """
        if hasattr(record, "msg") and isinstance(record.msg, str):
            original_msg = record.msg
            cleaned_msg = original_msg

            # 1. 清理敏感信息
            if self.enable_sensitive_cleaning:
                cleaned_msg = self._clean_sensitive_info(cleaned_msg)

            # 2. 截断过长内容
            if self.enable_content_truncation:
                cleaned_msg = self._truncate_large_content(cleaned_msg)

            # 3. 简化错误堆栈
            cleaned_msg = self._simplify_tracebacks(cleaned_msg)

            # 更新消息
            record.msg = cleaned_msg

            # 可选：记录清理统计
            if len(cleaned_msg) < len(original_msg):
                reduction = len(original_msg) - len(cleaned_msg)
                if not hasattr(record, "cleaned_reduction"):
                    record.cleaned_reduction = reduction

        return True

    def _clean_sensitive_info(self, message: str) -> str:
        """清理敏感信息"""
        cleaned = message

        # 清理Base64图像数据
        cleaned = self.base64_image_pattern.sub("[IMAGE_DATA]", cleaned)

        # 清理大JSON数据
        cleaned = self.large_json_pattern.sub("[LARGE_JSON_DATA]", cleaned)

        # 清理API密钥
        for pattern in self.api_key_patterns:
            cleaned = pattern.sub("[API_KEY_REDACTED]", cleaned)

        # 清理邮箱地址
        cleaned = self.email_pattern.sub("***@***.com", cleaned)

        # 清理IP地址
        cleaned = self.ip_pattern.sub("***.***.***.***", cleaned)

        # 清理HTTP请求体
        cleaned = self.http_body_pattern.sub('"request_body": "[REDACTED]"', cleaned)

        return cleaned

    def _truncate_large_content(self, message: str) -> str:
        """截断过长内容"""
        if len(message) <= self.max_content_length:
            return message

        # 计算保留的头部和尾部长度
        head_length = int(self.max_content_length * 0.6) - 15  # 减去省略号长度
        tail_length = int(self.max_content_length * 0.4) - 15

        if head_length < 50:  # 太短直接截断
            return message[: self.max_content_length] + "... [TRUNCATED]"

        head = message[:head_length]
        tail = message[-tail_length:] if tail_length > 0 else ""

        return f"{head}... [TRUNCATED {len(message) - self.max_content_length} chars] ...{tail}"

    def _simplify_tracebacks(self, message: str) -> str:
        """简化错误堆栈信息"""
        if "Traceback" not in message:
            return message

        def simplify_traceback(match):
            full_traceback = match.group(0)
            lines = full_traceback.split("\n")

            # 找到真正的错误类型行（通常包含异常类名和冒号）
            error_line = ""
            for line in reversed(lines):
                line = line.strip()
                if (
                    line
                    and ":" in line
                    and not line.startswith("File ")
                    and not line.startswith("Traceback")
                ):
                    # 这可能是错误行，如 "ValueError: Test error"
                    error_line = line
                    break

            # 如果没找到，找最后一个非空行
            if not error_line:
                for line in reversed(lines):
                    line = line.strip()
                    if (
                        line
                        and not line.startswith("Traceback")
                        and not line.startswith("File ")
                    ):
                        error_line = line
                        break

            if error_line:
                return f"[ERROR]: {error_line}"
            else:
                return "[ERROR]: Unknown error occurred"

        return self.traceback_pattern.sub(simplify_traceback, message)


class ColoredFormatter(logging.Formatter):
    """
    带颜色的日志格式化器
    为不同日志级别添加ANSI颜色代码
    """

    # ANSI颜色代码
    COLORS = {
        "DEBUG": "\033[36m",  # 青色
        "INFO": "\033[32m",  # 绿色
        "WARNING": "\033[33m",  # 黄色
        "ERROR": "\033[31m",  # 红色
        "CRITICAL": "\033[35m",  # 紫色
        "RESET": "\033[0m",  # 重置
    }

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录，添加颜色"""
        # 添加带颜色的级别名称
        if record.levelname in self.COLORS:
            record.levelname_colored = f"{self.COLORS[record.levelname]}{record.levelname}{self.COLORS['RESET']}"
        else:
            record.levelname_colored = record.levelname

        # 格式化时间（更简洁的格式）
        record.formatted_time = datetime.fromtimestamp(record.created).strftime(
            "%H:%M:%S"
        )

        # 添加清理统计信息（如果有）
        if hasattr(record, "cleaned_reduction"):
            record.msg += f" [cleaned: -{record.cleaned_reduction} chars]"

        return super().format(record)


class StructuredFormatter(logging.Formatter):
    """
    结构化日志格式化器
    输出JSON格式的日志，便于后续分析和处理
    """

    def format(self, record: logging.LogRecord) -> str:
        """格式化为JSON结构"""
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "function": record.funcName,
            "line": record.lineno,
            "module": record.module,
        }

        # 添加额外的上下文信息
        extra_fields = [
            "source",
            "model",
            "api_type",
            "error_type",
            "execution_time",
            "channel_id",
            "request_id",
            "cost",
            "tokens",
            "cleaned_reduction",
        ]

        for field in extra_fields:
            if hasattr(record, field):
                log_obj[field] = getattr(record, field)

        # 添加异常信息
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, ensure_ascii=False, default=str)


def setup_smart_logging(
    logger_name: str = "smart-ai-router",
    log_level: int = logging.INFO,
    console_format: str = "detailed",  # 'simple', 'detailed', 'structured'
    file_format: str = "structured",
    enable_file_logging: bool = True,
    log_file: Optional[str] = None,
    enable_sensitive_cleaning: bool = True,
    max_content_length: int = 500,
) -> logging.Logger:
    """
    设置智能日志系统

    Args:
        logger_name: 日志器名称
        log_level: 日志级别
        console_format: 控制台输出格式
        file_format: 文件输出格式
        enable_file_logging: 是否启用文件日志
        log_file: 日志文件路径
        enable_sensitive_cleaning: 是否启用敏感信息清理
        max_content_length: 最大内容长度

    Returns:
        logging.Logger: 配置好的日志器
    """

    # 获取或创建日志器
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)

    # 防止重复添加处理器
    if logger.handlers:
        return logger

    # 防止向上传播，避免重复输出
    logger.propagate = False

    # 创建智能过滤器
    smart_filter = SmartLogFilter(
        enable_sensitive_cleaning=enable_sensitive_cleaning,
        enable_content_truncation=True,
        max_content_length=max_content_length,
    )

    # 设置控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.addFilter(smart_filter)

    # 根据格式选择控制台格式化器
    if console_format == "simple":
        console_formatter = ColoredFormatter(
            "%(formatted_time)s [%(levelname_colored)s] %(message)s"
        )
    elif console_format == "detailed":
        console_formatter = ColoredFormatter(
            "%(formatted_time)s [%(levelname_colored)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s"
        )
    else:  # structured
        console_formatter = StructuredFormatter()

    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 设置文件处理器
    if enable_file_logging:
        if log_file is None:
            log_file = f"logs/{logger_name}.log"

        # 确保日志目录存在
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.addFilter(smart_filter)

        # 文件格式化器
        if file_format == "simple":
            file_formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s"
            )
        elif file_format == "detailed":
            file_formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s"
            )
        else:  # structured
            file_formatter = StructuredFormatter()

        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    # 减少第三方库的日志噪声
    noisy_loggers = [
        "httpx",
        "openai",
        "anthropic",
        "uvicorn",
        "uvicorn.access",
        "fastapi",
        "httpcore",
        "urllib3",
        "requests",
    ]

    for lib_name in noisy_loggers:
        lib_logger = logging.getLogger(lib_name)
        lib_logger.setLevel(logging.WARNING)
        lib_logger.propagate = False

    return logger


def create_context_logger(
    base_logger: logging.Logger, **context
) -> logging.LoggerAdapter:
    """
    创建带上下文信息的日志适配器

    Args:
        base_logger: 基础日志器
        **context: 上下文信息

    Returns:
        logging.LoggerAdapter: 带上下文的日志适配器
    """

    class ContextAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            # 将上下文信息添加到日志记录中
            for key, value in self.extra.items():
                if "extra" not in kwargs:
                    kwargs["extra"] = {}
                kwargs["extra"][key] = value
            return msg, kwargs

    return ContextAdapter(base_logger, context)


def get_smart_logger(name: str = None) -> logging.Logger:
    """
    获取智能日志器的便捷函数

    Args:
        name: 日志器名称，如果为None则使用调用者的模块名

    Returns:
        logging.Logger: 智能日志器
    """
    if name is None:
        import inspect

        frame = inspect.currentframe().f_back
        name = frame.f_globals.get("__name__", "smart-ai-router")

    # 检查是否已经设置过
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_smart_logging(name)

    return logger


# 便捷的全局函数
def log_with_context(level: int, message: str, **context):
    """
    带上下文的日志记录便捷函数

    Args:
        level: 日志级别
        message: 日志消息
        **context: 上下文信息
    """
    logger = get_smart_logger()

    # 创建临时的上下文适配器
    context_logger = create_context_logger(logger, **context)
    context_logger.log(level, message)


# 便捷函数别名
def log_info(message: str, **context):
    """INFO级别日志的便捷函数"""
    log_with_context(logging.INFO, message, **context)


def log_error(message: str, **context):
    """ERROR级别日志的便捷函数"""
    log_with_context(logging.ERROR, message, **context)


def log_debug(message: str, **context):
    """DEBUG级别日志的便捷函数"""
    log_with_context(logging.DEBUG, message, **context)
