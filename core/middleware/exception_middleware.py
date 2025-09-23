"""
FastAPI exception middleware for unified error handling
"""

import logging
import time
from typing import Any, Dict

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.exceptions import RoutingException
from core.utils.exception_handler import (
    AuthenticationError,
    ConfigurationError,
    ErrorCategory,
    ErrorSeverity,
    ExternalAPIError,
    NetworkError,
    ResourceError,
    SmartRouterException,
    ValidationError,
)

logger = logging.getLogger(__name__)


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """统一异常处理中间件"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        try:
            response = await call_next(request)
            return response
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return await self._handle_exception(request, e, duration_ms)

    async def _handle_exception(
        self, request: Request, exc: Exception, duration_ms: float
    ) -> JSONResponse:
        """处理异常并返回统一格式的错误响应"""

        # 确定错误类型和响应
        if isinstance(exc, HTTPException):
            # 处理FastAPI HTTPException
            status_code = exc.status_code
            error_response = {
                "error": exc.detail,
                "status_code": exc.status_code,
                "error_type": "HTTPException",
                "request_id": self._generate_request_id(),
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round(duration_ms, 2),
            }
        elif isinstance(exc, SmartRouterException):
            status_code = self._get_status_code_for_exception(exc)
            error_response = self._create_error_response(exc, request, duration_ms)
        elif isinstance(exc, RoutingException):
            # 兼容现有的RoutingException
            status_code = exc.status_code
            error_response = {
                "error": {
                    "type": "routing_error",
                    "message": exc.message,
                    "category": "routing",
                    "severity": "medium",
                    "request_id": getattr(request.state, "request_id", None),
                    "duration_ms": duration_ms,
                }
            }
        elif isinstance(exc, HTTPException):
            # FastAPI HTTPException
            status_code = exc.status_code
            error_response = {
                "error": {
                    "type": "http_error",
                    "message": exc.detail,
                    "category": "validation" if status_code == 422 else "system",
                    "severity": "medium",
                    "request_id": getattr(request.state, "request_id", None),
                    "duration_ms": duration_ms,
                }
            }
        else:
            # 未知异常
            status_code = 500
            error_response = {
                "error": {
                    "type": "internal_error",
                    "message": "Internal server error",
                    "category": "system",
                    "severity": "critical",
                    "request_id": getattr(request.state, "request_id", None),
                    "duration_ms": duration_ms,
                }
            }
            logger.error(f"Unhandled exception: {exc}", exc_info=True)

        # 记录错误日志
        self._log_error(request, exc, status_code, duration_ms)

        # 记录到状态监控
        await self._log_to_status_monitor(request, status_code, duration_ms, exc)

        return JSONResponse(status_code=status_code, content=error_response)

    def _get_status_code_for_exception(self, exc: SmartRouterException) -> int:
        """根据异常类型确定HTTP状态码"""
        if isinstance(exc, AuthenticationError):
            return 401
        elif isinstance(exc, ValidationError):
            return 422
        elif isinstance(exc, ConfigurationError):
            return 500
        elif isinstance(exc, NetworkError):
            return 503
        elif isinstance(exc, ExternalAPIError):
            return 502
        elif isinstance(exc, ResourceError):
            return 507
        else:
            return 500

    def _create_error_response(
        self, exc: SmartRouterException, request: Request, duration_ms: float
    ) -> Dict[str, Any]:
        """创建统一的错误响应格式"""
        return {
            "error": {
                "type": exc.__class__.__name__.lower(),
                "message": str(exc),
                "category": exc.category.value,
                "severity": exc.severity.value,
                "context": exc.context,
                "request_id": getattr(request.state, "request_id", None),
                "duration_ms": duration_ms,
            }
        }

    def _log_error(
        self, request: Request, exc: Exception, status_code: int, duration_ms: float
    ):
        """记录错误日志"""
        logger.error(
            f"Request failed: {request.method} {request.url.path}",
            extra={
                "exception": str(exc),
                "status_code": status_code,
                "duration_ms": duration_ms,
                "request_id": getattr(request.state, "request_id", None),
                "user_agent": request.headers.get("user-agent"),
                "remote_addr": request.client.host if request.client else None,
            },
        )

    async def _log_to_status_monitor(
        self, request: Request, status_code: int, duration_ms: float, exc: Exception
    ):
        """记录到状态监控"""
        try:
            from api.status_monitor import log_request

            # 提取模型信息
            model = None
            if hasattr(request.state, "model"):
                model = request.state.model
            elif request.method == "POST" and request.url.path.endswith(
                "/chat/completions"
            ):
                # 尝试从请求体中提取模型信息（已经解析过的情况）
                model = getattr(request.state, "parsed_model", None)

            log_request(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
                model=model,
                channel=getattr(request.state, "channel", None),
                error=str(exc),
            )
        except Exception as log_exc:
            logger.warning(f"Failed to log to status monitor: {log_exc}")


# 便利函数，用于在API路由中手动处理异常
def handle_api_exception(exc: Exception, request: Request = None) -> HTTPException:
    """将异常转换为FastAPI HTTPException"""
    if isinstance(exc, SmartRouterException):
        status_code = ExceptionHandlerMiddleware()._get_status_code_for_exception(exc)
        detail = {
            "type": exc.__class__.__name__.lower(),
            "message": str(exc),
            "category": exc.category.value,
            "severity": exc.severity.value,
            "context": exc.context,
        }
        return HTTPException(status_code=status_code, detail=detail)
    elif isinstance(exc, RoutingException):
        return HTTPException(status_code=exc.status_code, detail=exc.message)
    else:
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return HTTPException(status_code=500, detail="Internal server error")
