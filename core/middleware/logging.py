"""
日志中间件 - 自动记录API请求和响应
"""
import json
import time
import uuid
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse

from core.utils.logger import get_smart_logger


class LoggingMiddleware(BaseHTTPMiddleware):
    """API请求/响应日志中间件"""

    def __init__(
        self,
        app,
        log_requests: bool = True,
        log_responses: bool = True,
        log_request_body: bool = False,
        log_response_body: bool = False,
        max_body_size: int = 1024 * 10,  # 10KB
        skip_paths: Optional[set] = None,
    ):
        super().__init__(app)
        self.log_requests = log_requests
        self.log_responses = log_responses
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.max_body_size = max_body_size
        self.skip_paths = skip_paths or {
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
        }
        self.logger = get_smart_logger()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 生成请求ID
        request_id = str(uuid.uuid4())

        # 跳过某些路径
        if request.url.path in self.skip_paths:
            return await call_next(request)

        # 设置日志上下文
        if self.logger:
            self.logger.set_context(request_id=request_id)

        # 记录请求开始时间
        start_time = time.time()

        # 记录请求信息
        if self.log_requests:
            await self._log_request(request, request_id)

        # 处理请求
        try:
            response = await call_next(request)

            # 计算处理时间
            process_time = time.time() - start_time

            # 记录响应信息
            if self.log_responses:
                await self._log_response(request, response, request_id, process_time)

            # 添加请求ID到响应头
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # 记录异常
            process_time = time.time() - start_time
            if self.logger:
                self.logger.error(
                    f"Request failed: {str(e)}",
                    request_id=request_id,
                    method=request.method,
                    url=str(request.url),
                    process_time=process_time,
                    exc_info=e,
                )
            raise
        finally:
            # 清除日志上下文
            if self.logger:
                self.logger.clear_context()

    async def _log_request(self, request: Request, request_id: str) -> None:
        """记录请求信息"""
        try:
            request_data = {
                "method": request.method,
                "url": str(request.url),
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "headers": self._filter_headers(dict(request.headers)),
                "client_ip": self._get_client_ip(request),
                "user_agent": request.headers.get("user-agent"),
            }

            # 记录请求体（如果启用）
            if self.log_request_body and request.method in ["POST", "PUT", "PATCH"]:
                body = await self._read_request_body(request)
                if body:
                    request_data["body"] = body

            if self.logger:
                self.logger.info(
                    f"API Request: {request.method} {request.url.path}", **request_data
                )

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to log request: {e}")

    async def _log_response(
        self, request: Request, response: Response, request_id: str, process_time: float
    ) -> None:
        """记录响应信息"""
        try:
            response_data = {
                "status_code": response.status_code,
                "process_time": round(process_time, 4),
                "response_size": self._get_response_size(response),
            }

            # 记录响应头
            if hasattr(response, "headers"):
                response_data["headers"] = self._filter_headers(dict(response.headers))

            # 记录响应体（如果启用且不是流式响应）
            if (
                self.log_response_body
                and not isinstance(response, StreamingResponse)
                and response.status_code < 400
            ):
                body = await self._read_response_body(response)
                if body:
                    response_data["body"] = body

            # 确定日志级别
            if response.status_code >= 500:
                log_level = "error"
            elif response.status_code >= 400:
                log_level = "warning"
            else:
                log_level = "info"

            if self.logger:
                message = f"API Response: {response.status_code} - {process_time:.4f}s"
                getattr(self.logger, log_level)(message, **response_data)

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to log response: {e}")

    async def _read_request_body(self, request: Request) -> Optional[str]:
        """读取请求体"""
        try:
            body = await request.body()
            if len(body) > self.max_body_size:
                return f"<Body too large: {len(body)} bytes>"

            if body:
                try:
                    # 尝试解析为JSON
                    json.loads(body.decode("utf-8"))
                    return body.decode("utf-8")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return f"<Binary data: {len(body)} bytes>"

            return None

        except Exception:
            return "<Failed to read body>"

    async def _read_response_body(self, response: Response) -> Optional[str]:
        """读取响应体"""
        try:
            if hasattr(response, "body") and response.body:
                body = response.body
                if len(body) > self.max_body_size:
                    return f"<Body too large: {len(body)} bytes>"

                try:
                    if isinstance(body, bytes):
                        return body.decode("utf-8")
                    return str(body)
                except UnicodeDecodeError:
                    return f"<Binary data: {len(body)} bytes>"

            return None

        except Exception:
            return "<Failed to read response body>"

    def _filter_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """过滤敏感的请求头"""
        sensitive_headers = {
            "authorization",
            "cookie",
            "x-api-key",
            "x-auth-token",
            "x-access-token",
            "bearer",
            "api-key",
        }

        filtered = {}
        for key, value in headers.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_headers):
                # 只显示前几个字符
                if len(value) > 8:
                    filtered[key] = f"{value[:8]}***"
                else:
                    filtered[key] = "***"
            else:
                filtered[key] = value

        return filtered

    def _get_client_ip(self, request: Request) -> str:
        """获取客户端IP地址"""
        # 检查代理头
        for header in ["x-forwarded-for", "x-real-ip", "x-client-ip"]:
            if header in request.headers:
                ip = request.headers[header].split(",")[0].strip()
                if ip:
                    return ip

        # 使用客户端地址
        if hasattr(request, "client") and request.client:
            return request.client.host

        return "unknown"

    def _get_response_size(self, response: Response) -> Optional[int]:
        """获取响应大小"""
        try:
            if hasattr(response, "body") and response.body:
                if isinstance(response.body, bytes):
                    return len(response.body)
                elif isinstance(response.body, str):
                    return len(response.body.encode("utf-8"))

            # 检查Content-Length头
            if hasattr(response, "headers") and "content-length" in response.headers:
                return int(response.headers["content-length"])

            return None

        except Exception:
            return None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """请求上下文中间件 - 为每个请求设置唯一ID和用户信息"""

    def __init__(self, app):
        super().__init__(app)
        self.logger = get_smart_logger()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 生成或获取请求ID
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        # 获取用户信息（从认证头）
        user_id = self._extract_user_id(request)

        # 设置日志上下文
        if self.logger:
            context = {"request_id": request_id}
            if user_id:
                context["user_id"] = user_id
            self.logger.set_context(**context)

        try:
            # 将请求ID添加到request state
            request.state.request_id = request_id
            if user_id:
                request.state.user_id = user_id

            response = await call_next(request)

            # 添加请求ID到响应头
            response.headers["X-Request-ID"] = request_id

            return response

        finally:
            # 清除日志上下文
            if self.logger:
                self.logger.clear_context()

    def _extract_user_id(self, request: Request) -> Optional[str]:
        """从请求中提取用户ID"""
        try:
            # 从Authorization头提取（简化实现）
            auth_header = request.headers.get("authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:]
                # 这里可以解析JWT token或查询数据库
                # 目前返回token的前8位作为用户标识
                return f"user_{token[:8]}"

            return None

        except Exception:
            return None
