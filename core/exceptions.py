"""
Unified exception hierarchy for Smart AI Router
"""
from typing import Any, Optional

from fastapi.responses import JSONResponse


class RouterException(Exception):
    """基础路由器异常"""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class ChannelException(RouterException):
    """渠道相关异常"""

    def __init__(
        self,
        channel_id: str,
        message: str,
        status_code: int = 503,
        details: Optional[dict[str, Any]] = None,
    ):
        self.channel_id = channel_id
        super().__init__(message, status_code, details)


class ChannelUnavailableException(ChannelException):
    """渠道不可用异常"""

    def __init__(self, channel_id: str, reason: str = "Channel unavailable"):
        super().__init__(
            channel_id=channel_id,
            message=f"Channel '{channel_id}' is unavailable: {reason}",
            status_code=503,
        )


class AllChannelsFailedException(RouterException):
    """所有渠道失败异常"""

    def __init__(
        self, model: str, attempts: int, last_error: Optional[Exception] = None
    ):
        self.model = model
        self.attempts = attempts
        self.last_error = last_error

        message = f"All {attempts} available channels failed for model '{model}'"
        if last_error:
            message += f". Last error: {str(last_error)}"

        super().__init__(
            message,
            status_code=503,
            details={
                "model": model,
                "attempts": attempts,
                "last_error": str(last_error) if last_error else None,
            },
        )


class NoChannelsFoundException(RouterException):
    """无可用渠道异常"""

    def __init__(self, model: str):
        self.model = model
        super().__init__(
            message=f"No available channels found for model '{model}'",
            status_code=503,
            details={"model": model},
        )


class AuthenticationException(ChannelException):
    """认证异常"""

    def __init__(self, channel_id: str, message: str = "Authentication failed"):
        super().__init__(
            channel_id=channel_id,
            message=f"Authentication failed for channel '{channel_id}': {message}",
            status_code=401,
        )


class RateLimitException(ChannelException):
    """速率限制异常"""

    def __init__(self, channel_id: str, retry_after: Optional[int] = None):
        message = f"Rate limit exceeded for channel '{channel_id}'"
        if retry_after:
            message += f". Retry after {retry_after} seconds"

        super().__init__(
            channel_id=channel_id,
            message=message,
            status_code=429,
            details={"retry_after": retry_after},
        )


class ModelNotSupportedException(RouterException):
    """模型不支持异常"""

    def __init__(self, model: str, channel_id: Optional[str] = None):
        self.model = model
        self.channel_id = channel_id

        message = f"Model '{model}' is not supported"
        if channel_id:
            message += f" by channel '{channel_id}'"

        super().__init__(
            message, status_code=400, details={"model": model, "channel_id": channel_id}
        )


class ErrorHandler:
    """统一错误处理器"""

    @staticmethod
    def handle_httpx_error(error: Exception, channel_id: str) -> ChannelException:
        """处理httpx相关错误"""
        import httpx

        if isinstance(error, httpx.HTTPStatusError):
            status_code = error.response.status_code
            error_text = (
                error.response.text if hasattr(error.response, "text") else str(error)
            )

            if status_code in [401, 403]:
                return AuthenticationException(channel_id, error_text[:200])
            elif status_code == 429:
                # 尝试从响应头提取retry_after
                retry_after = None
                if hasattr(error.response, "headers"):
                    retry_after = error.response.headers.get("retry-after")
                    if retry_after:
                        try:
                            retry_after = int(retry_after)
                        except ValueError:
                            retry_after = None
                return RateLimitException(channel_id, retry_after)
            elif status_code == 400:
                # 可能是模型不支持
                if "model" in error_text.lower() or "not found" in error_text.lower():
                    return ModelNotSupportedException("unknown", channel_id)
                return ChannelException(
                    channel_id, f"Bad request: {error_text[:200]}", status_code
                )
            else:
                return ChannelException(
                    channel_id, f"HTTP {status_code}: {error_text[:200]}", status_code
                )

        elif isinstance(error, httpx.RequestError):
            return ChannelUnavailableException(
                channel_id, f"Network error: {str(error)}"
            )
        else:
            return ChannelException(channel_id, f"Unknown error: {str(error)}")

    @staticmethod
    def create_error_response(
        error: RouterException, execution_time: Optional[float] = None
    ) -> JSONResponse:
        """创建统一的错误响应"""
        headers = {
            "X-Router-Status": "error",
            "X-Router-Error-Type": error.__class__.__name__,
        }

        if execution_time is not None:
            headers["X-Router-Time"] = f"{execution_time:.3f}s"

        # 添加特定错误类型的头信息
        if isinstance(error, AllChannelsFailedException):
            headers.update(
                {
                    "X-Router-Status": "all-channels-failed",
                    "X-Router-Attempts": str(error.attempts),
                    "X-Router-Model-Requested": error.model,
                }
            )
        elif isinstance(error, NoChannelsFoundException):
            headers.update(
                {
                    "X-Router-Status": "no-channels-found",
                    "X-Router-Model-Requested": error.model,
                }
            )
        elif isinstance(error, ChannelException):
            headers["X-Router-Channel-ID"] = error.channel_id

        # 添加详细信息到头部（如果有的话）
        for key, value in error.details.items():
            if isinstance(value, (str, int, float)):
                headers[f"X-Router-Detail-{key.replace('_', '-')}"] = str(value)

        return JSONResponse(
            status_code=error.status_code,
            content={"detail": error.message, "error_type": error.__class__.__name__},
            headers=headers,
        )

    @staticmethod
    def should_blacklist_channel(error: RouterException) -> bool:
        """判断是否应该将渠道加入黑名单"""
        if isinstance(error, AuthenticationException):
            return True
        elif isinstance(error, ModelNotSupportedException):
            return False  # 模型不支持不意味着渠道不可用
        elif isinstance(error, RateLimitException):
            return False  # 速率限制是临时的
        elif isinstance(error, ChannelException) and error.status_code in [401, 403]:
            return True
        return False

    @staticmethod
    def get_retry_delay(error: RouterException) -> Optional[int]:
        """获取重试延迟时间（秒）"""
        if isinstance(error, RateLimitException):
            return error.details.get("retry_after", 60)  # 默认60秒
        elif isinstance(error, ChannelUnavailableException):
            return 30  # 网络错误等30秒后重试
        return None  # 不建议重试
