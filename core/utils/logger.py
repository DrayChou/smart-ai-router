"""完整的日志系统模块 - 支持持久化存储、结构化格式、日志轮换"""

import asyncio
import json
import logging
import logging.handlers
import sys
import traceback
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional, Union

try:
    import structlog

    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False

try:
    from pythonjsonlogger import jsonlogger

    JSON_LOGGER_AVAILABLE = True
except ImportError:
    JSON_LOGGER_AVAILABLE = False


@dataclass
class LogEntry:
    """结构化日志条目"""

    timestamp: str
    level: str
    logger_name: str
    message: str
    module: Optional[str] = None
    function: Optional[str] = None
    line_number: Optional[int] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    extra_data: Optional[dict[str, Any]] = None
    exception_info: Optional[str] = None
    stack_trace: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        """转换为JSON格式"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


class PersistentLogHandler:
    """持久化日志处理器 - 支持异步写入和日志轮换"""

    def __init__(
        self,
        log_file: Union[str, Path],
        max_file_size: int = 50 * 1024 * 1024,  # 50MB
        backup_count: int = 5,
        batch_size: int = 100,
        flush_interval: float = 5.0,
    ):
        self.log_file = Path(log_file)
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        # 创建日志目录
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # 内存缓冲区
        self._buffer: deque = deque()
        self._buffer_lock = Lock()
        self._last_flush = datetime.now()

        # 异步任务
        self._flush_task: Optional[asyncio.Task] = None
        self._shutdown = False

    def add_log_entry(self, entry: LogEntry) -> None:
        """添加日志条目到缓冲区"""
        with self._buffer_lock:
            self._buffer.append(entry)

            # 检查是否需要立即刷新
            now = datetime.now()
            if (
                len(self._buffer) >= self.batch_size
                or (now - self._last_flush).total_seconds() >= self.flush_interval
            ):
                self._trigger_flush()

    def _trigger_flush(self) -> None:
        """触发异步刷新"""
        if not self._flush_task or self._flush_task.done():
            try:
                loop = asyncio.get_event_loop()
                self._flush_task = loop.create_task(self._flush_buffer())
            except RuntimeError:
                # 如果没有事件循环，同步写入
                self._flush_buffer_sync()

    async def _flush_buffer(self) -> None:
        """异步刷新缓冲区到文件"""
        entries_to_write = []

        with self._buffer_lock:
            while self._buffer and len(entries_to_write) < self.batch_size:
                entries_to_write.append(self._buffer.popleft())

        if entries_to_write:
            await self._write_entries_async(entries_to_write)
            self._last_flush = datetime.now()

    def _flush_buffer_sync(self) -> None:
        """同步刷新缓冲区到文件"""
        entries_to_write = []

        with self._buffer_lock:
            while self._buffer:
                entries_to_write.append(self._buffer.popleft())

        if entries_to_write:
            self._write_entries_sync(entries_to_write)
            self._last_flush = datetime.now()

    async def _write_entries_async(self, entries: list[LogEntry]) -> None:
        """异步写入日志条目"""
        try:
            import aiofiles

            # 检查文件大小并轮换
            await self._rotate_log_if_needed()

            async with aiofiles.open(self.log_file, "a", encoding="utf-8") as f:
                for entry in entries:
                    await f.write(entry.to_json() + "\n")
                await f.flush()

        except Exception as e:
            # 异步写入失败，回退到同步写入
            print(f"Async log write failed, falling back to sync: {e}", file=sys.stderr)
            self._write_entries_sync(entries)

    def _write_entries_sync(self, entries: list[LogEntry]) -> None:
        """同步写入日志条目"""
        try:
            # 检查文件大小并轮换
            self._rotate_log_if_needed_sync()

            with open(self.log_file, "a", encoding="utf-8") as f:
                for entry in entries:
                    f.write(entry.to_json() + "\n")
                f.flush()
        except Exception as e:
            print(f"Failed to write log entries: {e}", file=sys.stderr)

    async def _rotate_log_if_needed(self) -> None:
        """异步检查并轮换日志文件"""
        if self.log_file.exists() and self.log_file.stat().st_size > self.max_file_size:
            await self._rotate_log_async()

    def _rotate_log_if_needed_sync(self) -> None:
        """同步检查并轮换日志文件"""
        if self.log_file.exists() and self.log_file.stat().st_size > self.max_file_size:
            self._rotate_log_sync()

    async def _rotate_log_async(self) -> None:
        """异步轮换日志文件"""
        try:
            import aiofiles.os

            # 删除最旧的备份文件
            oldest_backup = self.log_file.with_suffix(
                f"{self.log_file.suffix}.{self.backup_count}"
            )
            if oldest_backup.exists():
                await aiofiles.os.remove(oldest_backup)

            # 轮换现有备份文件
            for i in range(self.backup_count - 1, 0, -1):
                old_backup = self.log_file.with_suffix(f"{self.log_file.suffix}.{i}")
                new_backup = self.log_file.with_suffix(
                    f"{self.log_file.suffix}.{i + 1}"
                )
                if old_backup.exists():
                    await aiofiles.os.rename(old_backup, new_backup)

            # 将当前日志文件重命名为备份
            if self.log_file.exists():
                backup_file = self.log_file.with_suffix(f"{self.log_file.suffix}.1")
                await aiofiles.os.rename(self.log_file, backup_file)

        except Exception as e:
            print(
                f"Async log rotation failed, falling back to sync: {e}", file=sys.stderr
            )
            self._rotate_log_sync()

    def _rotate_log_sync(self) -> None:
        """同步轮换日志文件"""
        try:
            # 删除最旧的备份文件
            oldest_backup = self.log_file.with_suffix(
                f"{self.log_file.suffix}.{self.backup_count}"
            )
            if oldest_backup.exists():
                oldest_backup.unlink()

            # 轮换现有备份文件
            for i in range(self.backup_count - 1, 0, -1):
                old_backup = self.log_file.with_suffix(f"{self.log_file.suffix}.{i}")
                new_backup = self.log_file.with_suffix(
                    f"{self.log_file.suffix}.{i + 1}"
                )
                if old_backup.exists():
                    old_backup.rename(new_backup)

            # 将当前日志文件重命名为备份
            if self.log_file.exists():
                backup_file = self.log_file.with_suffix(f"{self.log_file.suffix}.1")
                self.log_file.rename(backup_file)

        except Exception as e:
            print(f"Failed to rotate log file: {e}", file=sys.stderr)

    async def shutdown(self) -> None:
        """关闭日志处理器"""
        self._shutdown = True

        # 等待刷新任务完成
        if self._flush_task and not self._flush_task.done():
            await self._flush_task

        # 最后刷新剩余日志
        await self._flush_buffer()


class SmartAILogger:
    """Smart AI Router 专用日志系统"""

    def __init__(
        self,
        config: Optional[dict[str, Any]] = None,
        log_file: Optional[Union[str, Path]] = None,
    ):
        self.config = config or {}
        self.persistent_handler: Optional[PersistentLogHandler] = None
        self.context_data: dict[str, Any] = {}

        # 设置默认日志文件
        if log_file:
            self.log_file = Path(log_file)
        else:
            self.log_file = Path("logs/smart-ai-router.log")

        self._setup_persistent_logging()
        self._setup_standard_logging()

    def _setup_persistent_logging(self) -> None:
        """设置持久化日志"""
        try:
            self.persistent_handler = PersistentLogHandler(
                log_file=self.log_file,
                max_file_size=self.config.get("max_file_size", 50 * 1024 * 1024),
                backup_count=self.config.get("backup_count", 5),
                batch_size=self.config.get("batch_size", 100),
                flush_interval=self.config.get("flush_interval", 5.0),
            )
        except Exception as e:
            print(f"Failed to setup persistent logging: {e}", file=sys.stderr)

    def _setup_standard_logging(self) -> None:
        """设置标准日志系统"""
        log_level = self.config.get("level", "INFO").upper()
        log_format = self.config.get("format", "text")  # text or json

        handlers = [logging.StreamHandler(sys.stdout)]

        # 添加文件处理器（轮换日志）
        if self.log_file:
            try:
                file_handler = logging.handlers.RotatingFileHandler(
                    self.log_file,
                    maxBytes=self.config.get("max_file_size", 50 * 1024 * 1024),
                    backupCount=self.config.get("backup_count", 5),
                    encoding="utf-8",
                )

                if log_format == "json" and JSON_LOGGER_AVAILABLE:
                    formatter = jsonlogger.JsonFormatter(
                        "%(asctime)s %(name)s %(levelname)s %(message)s"
                    )
                    file_handler.setFormatter(formatter)
                else:
                    formatter = logging.Formatter(
                        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                    )
                    file_handler.setFormatter(formatter)

                handlers.append(file_handler)
            except Exception as e:
                print(f"Failed to setup file logging: {e}", file=sys.stderr)

        # 配置structlog（如果可用）
        if STRUCTLOG_AVAILABLE:
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
            )

        # 配置根日志记录器
        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            handlers=handlers,
            force=True,  # 覆盖现有配置
        )

        # 禁用第三方库的噪音日志
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    def set_context(self, **context_data) -> None:
        """设置上下文数据（如request_id, user_id等）"""
        self.context_data.update(context_data)

    def clear_context(self) -> None:
        """清除上下文数据"""
        self.context_data.clear()

    def log(
        self,
        level: str,
        message: str,
        logger_name: str = "smart-ai-router",
        **extra_data,
    ) -> None:
        """记录日志"""
        try:
            # 获取调用信息
            frame = traceback.extract_stack()[-2]

            # 创建日志条目
            entry = LogEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                level=level.upper(),
                logger_name=logger_name,
                message=message,
                module=frame.filename,
                function=frame.name,
                line_number=frame.lineno,
                **self.context_data,
                extra_data=extra_data if extra_data else None,
            )

            # 添加异常信息（如果存在）
            if "exc_info" in extra_data and extra_data["exc_info"]:
                entry.exception_info = str(extra_data["exc_info"])
                entry.stack_trace = traceback.format_exc()

            # 发送到持久化处理器
            if self.persistent_handler:
                self.persistent_handler.add_log_entry(entry)

            # 发送到标准日志系统
            logger = logging.getLogger(logger_name)
            log_level = getattr(logging, level.upper(), logging.INFO)
            logger.log(log_level, message, extra=extra_data)

        except Exception as e:
            print(f"Failed to log message: {e}", file=sys.stderr)

    def debug(self, message: str, **extra_data) -> None:
        """记录调试日志"""
        self.log("DEBUG", message, **extra_data)

    def info(self, message: str, **extra_data) -> None:
        """记录信息日志"""
        self.log("INFO", message, **extra_data)

    def warning(self, message: str, **extra_data) -> None:
        """记录警告日志"""
        self.log("WARNING", message, **extra_data)

    def error(self, message: str, **extra_data) -> None:
        """记录错误日志"""
        self.log("ERROR", message, **extra_data)

    def critical(self, message: str, **extra_data) -> None:
        """记录严重错误日志"""
        self.log("CRITICAL", message, **extra_data)

    async def shutdown(self) -> None:
        """关闭日志系统"""
        if self.persistent_handler:
            await self.persistent_handler.shutdown()


# 全局日志实例
_global_logger: Optional[SmartAILogger] = None


def setup_logging(
    config: dict[str, Any] = None, log_file: Optional[Union[str, Path]] = None
) -> SmartAILogger:
    """
    设置全局日志系统

    Args:
        config: 日志配置字典
        log_file: 日志文件路径

    Returns:
        SmartAILogger实例
    """
    global _global_logger

    if config is None:
        config = {
            "level": "INFO",
            "format": "json",  # 默认使用JSON格式便于解析
            "max_file_size": 50 * 1024 * 1024,  # 50MB
            "backup_count": 5,
            "batch_size": 100,
            "flush_interval": 5.0,
        }

    _global_logger = SmartAILogger(config, log_file)
    return _global_logger


def get_logger(name: str = None):
    """
    获取日志记录器 - 兼容现有代码

    Args:
        name: 日志记录器名称

    Returns:
        日志记录器
    """
    if STRUCTLOG_AVAILABLE:
        return structlog.get_logger(name)
    else:
        return logging.getLogger(name or __name__)


def get_smart_logger() -> Optional[SmartAILogger]:
    """
    获取全局Smart AI Logger实例

    Returns:
        SmartAILogger实例，如果未初始化则返回None
    """
    return _global_logger


async def shutdown_logging() -> None:
    """关闭全局日志系统"""
    global _global_logger
    if _global_logger:
        await _global_logger.shutdown()
        _global_logger = None
