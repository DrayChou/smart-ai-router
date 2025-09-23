"""
统一错误处理器
提供错误恢复和日志记录功能
"""

import asyncio
from functools import wraps
from typing import Any, Callable, Optional

from ..utils.logger import get_logger
from .base_exceptions import BaseRouterException, ChannelException, RoutingException
from .error_codes import ErrorCode

logger = get_logger(__name__)


class ErrorHandler:
    """统一错误处理器"""

    def __init__(self):
        self.error_stats = {
            "total_errors": 0,
            "error_by_code": {},
            "error_by_type": {},
            "recovery_attempts": 0,
            "recovery_successes": 0,
        }

    def handle_exception(
        self,
        exception: Exception,
        context: Optional[dict[str, Any]] = None,
        attempt_recovery: bool = True,
    ) -> Optional[Any]:
        """处理异常的主要方法"""

        # 更新错误统计
        self._update_error_stats(exception)

        # 记录错误
        self._log_error(exception, context)

        # 尝试错误恢复
        if attempt_recovery and isinstance(exception, BaseRouterException):
            recovery_result = self._attempt_recovery(exception, context)
            if recovery_result is not None:
                return recovery_result

        # 如果无法恢复，重新抛出异常
        raise exception

    def _update_error_stats(self, exception: Exception) -> None:
        """更新错误统计"""
        self.error_stats["total_errors"] += 1

        if isinstance(exception, BaseRouterException):
            error_code = exception.error_code.value
            self.error_stats["error_by_code"][error_code] = (
                self.error_stats["error_by_code"].get(error_code, 0) + 1
            )

        exception_type = type(exception).__name__
        self.error_stats["error_by_type"][exception_type] = (
            self.error_stats["error_by_type"].get(exception_type, 0) + 1
        )

    def _log_error(
        self, exception: Exception, context: Optional[dict[str, Any]] = None
    ) -> None:
        """记录错误日志"""
        if isinstance(exception, BaseRouterException):
            error_dict = exception.to_dict()
            if context:
                error_dict["context"].update(context)

            logger.error(
                f"Router Error [{exception.error_code.value}]: {exception.message}",
                extra={"error_details": error_dict},
            )
        else:
            logger.error(
                f"Unexpected Error: {str(exception)}",
                exc_info=True,
                extra={"context": context or {}},
            )

    def _attempt_recovery(
        self, exception: BaseRouterException, context: Optional[dict[str, Any]] = None
    ) -> Optional[Any]:
        """尝试错误恢复"""
        self.error_stats["recovery_attempts"] += 1

        try:
            if isinstance(exception, RoutingException):
                return self._recover_routing_error(exception, context)
            elif isinstance(exception, ChannelException):
                return self._recover_channel_error(exception, context)
            else:
                return self._recover_generic_error(exception, context)

        except Exception as recovery_error:
            logger.warning(f"Error recovery failed: {recovery_error}")
            return None

    def _recover_routing_error(
        self, exception: RoutingException, context: Optional[dict[str, Any]] = None
    ) -> Optional[Any]:
        """恢复路由错误"""
        if exception.error_code == ErrorCode.TAG_NOT_FOUND:
            # 尝试建议相似的标签
            return self._suggest_similar_tags(exception.details.get("tags", []))

        elif exception.error_code == ErrorCode.MODEL_NOT_FOUND:
            # 尝试建议相似的模型
            return self._suggest_similar_models(exception.details.get("model"))

        elif exception.error_code == ErrorCode.NO_AVAILABLE_CHANNELS:
            # 尝试启用备用渠道
            return self._enable_backup_channels(context)

        return None

    def _recover_channel_error(
        self, exception: ChannelException, context: Optional[dict[str, Any]] = None
    ) -> Optional[Any]:
        """恢复渠道错误"""
        if exception.error_code == ErrorCode.CHANNEL_TIMEOUT:
            # 标记渠道为不健康，触发故障转移
            channel_id = exception.details.get("channel_id")
            if channel_id:
                self._mark_channel_unhealthy(channel_id)
                return {"fallback_triggered": True, "channel_id": channel_id}

        elif exception.error_code == ErrorCode.API_KEY_INVALID:
            # 尝试刷新API密钥
            return self._refresh_api_key(exception.details.get("channel_id"))

        return None

    def _recover_generic_error(
        self, exception: BaseRouterException, context: Optional[dict[str, Any]] = None
    ) -> Optional[Any]:
        """恢复通用错误"""
        # 通用恢复策略
        if exception.error_code == ErrorCode.RATE_LIMIT_EXCEEDED:
            return {"retry_after": 60, "suggestion": "请稍后重试"}

        return None

    def _suggest_similar_tags(self, tags: list) -> dict[str, Any]:
        """建议相似的标签"""
        # 简化实现 - 实际可以使用模糊匹配算法
        suggestions = []
        common_tags = ["free", "fast", "quality", "local", "gpt", "claude"]

        for tag in tags:
            for common_tag in common_tags:
                if tag.lower() in common_tag or common_tag in tag.lower():
                    suggestions.append(common_tag)

        self.error_stats["recovery_successes"] += 1
        return {
            "type": "tag_suggestions",
            "original_tags": tags,
            "suggestions": list(set(suggestions)),
        }

    def _suggest_similar_models(self, model: str) -> dict[str, Any]:
        """建议相似的模型"""
        # 简化实现
        suggestions = []
        if model:
            if "gpt" in model.lower():
                suggestions = ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"]
            elif "claude" in model.lower():
                suggestions = ["claude-3-sonnet", "claude-3-opus", "claude-3-haiku"]
            elif "gemini" in model.lower():
                suggestions = ["gemini-pro", "gemini-1.5-pro"]

        self.error_stats["recovery_successes"] += 1
        return {
            "type": "model_suggestions",
            "original_model": model,
            "suggestions": suggestions,
        }

    def _enable_backup_channels(
        self, context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """启用备用渠道"""
        # 简化实现
        self.error_stats["recovery_successes"] += 1
        return {"type": "backup_channels_enabled", "message": "已尝试启用备用渠道"}

    def _mark_channel_unhealthy(self, channel_id: str) -> None:
        """标记渠道为不健康"""
        logger.warning(f"Marking channel {channel_id} as unhealthy due to timeout")
        # 实际实现需要更新渠道健康状态

    def _refresh_api_key(self, channel_id: str) -> Optional[dict[str, Any]]:
        """刷新API密钥"""
        # 简化实现
        logger.info(f"Attempting to refresh API key for channel {channel_id}")
        return {
            "type": "api_key_refresh_attempted",
            "channel_id": channel_id,
            "message": "已尝试刷新API密钥",
        }

    def get_error_stats(self) -> dict[str, Any]:
        """获取错误统计"""
        return self.error_stats.copy()

    def reset_stats(self) -> None:
        """重置错误统计"""
        self.error_stats = {
            "total_errors": 0,
            "error_by_code": {},
            "error_by_type": {},
            "recovery_attempts": 0,
            "recovery_successes": 0,
        }


# 全局错误处理器实例
_global_error_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """获取全局错误处理器实例"""
    global _global_error_handler
    if _global_error_handler is None:
        _global_error_handler = ErrorHandler()
    return _global_error_handler


def handle_errors(
    attempt_recovery: bool = True, reraise: bool = True, return_on_error: Any = None
):
    """错误处理装饰器"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_handler = get_error_handler()
                context = {
                    "function": func.__name__,
                    "args": str(args)[:100],  # 限制长度避免日志过长
                    "kwargs": str(kwargs)[:100],
                }

                try:
                    recovery_result = error_handler.handle_exception(
                        e, context, attempt_recovery
                    )
                    return recovery_result
                except Exception:
                    if reraise:
                        raise
                    return return_on_error

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                error_handler = get_error_handler()
                context = {
                    "function": func.__name__,
                    "args": str(args)[:100],
                    "kwargs": str(kwargs)[:100],
                }

                try:
                    recovery_result = error_handler.handle_exception(
                        e, context, attempt_recovery
                    )
                    return recovery_result
                except Exception:
                    if reraise:
                        raise
                    return return_on_error

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator
