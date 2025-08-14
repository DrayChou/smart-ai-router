"""日志系统模块"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict

import structlog


def setup_logging(config: Dict[str, Any] = None) -> None:
    """
    设置日志系统

    Args:
        config: 日志配置字典
    """
    if config is None:
        config = {}

    # 日志配置
    log_level = config.get("level", "INFO").upper()
    log_format = config.get("format", "text")  # text or json
    log_file = config.get("file", None)

    # 创建日志目录
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # 配置 structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_ctor_key=True,
    )

    # 配置标准 logging
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
        + ([logging.FileHandler(log_file)] if log_file else []),
    )

    # 禁用一些第三方库的日志
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str = None) -> structlog.BoundLogger:
    """
    获取日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        结构化日志记录器
    """
    return structlog.get_logger(name)
