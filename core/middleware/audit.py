"""
审计日志中间件 - 自动记录API请求和响应的审计信息
"""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.utils.audit_logger import AuditEventType, AuditLevel, get_audit_logger


class AuditMiddleware(BaseHTTPMiddleware):
    """审计日志中间件"""

    def __init__(
        self,
        app,
        audit_api_requests: bool = True,
        audit_admin_requests: bool = True,
        audit_auth_failures: bool = True,
        skip_paths: set = None,
    ):
        super().__init__(app)
        self.audit_api_requests = audit_api_requests
        self.audit_admin_requests = audit_admin_requests
        self.audit_auth_failures = audit_auth_failures
        self.skip_paths = skip_paths or {
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
        }
        self.audit_logger = get_audit_logger()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 跳过不需要审计的路径
        if request.url.path in self.skip_paths:
            return await call_next(request)

        # 如果审计日志器未初始化，直接通过
        if not self.audit_logger:
            return await call_next(request)

        # 记录请求开始时间
        start_time = time.time()

        # 提取客户端信息
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")

        # 设置审计上下文
        context = {
            "ip_address": client_ip,
            "user_agent": user_agent,
        }

        # 从request state获取请求ID和用户ID（由其他中间件设置）
        if hasattr(request.state, "request_id"):
            context["request_id"] = request.state.request_id
        if hasattr(request.state, "user_id"):
            context["user_id"] = request.state.user_id

        self.audit_logger.set_context(**context)

        try:
            # 处理请求
            response = await call_next(request)

            # 计算处理时间
            process_time = time.time() - start_time

            # 记录审计日志
            await self._audit_request(request, response, process_time)

            return response

        except Exception as e:
            # 记录错误审计
            process_time = time.time() - start_time
            await self._audit_error(request, str(e), process_time)
            raise
        finally:
            # 清除审计上下文
            self.audit_logger.clear_context()

    async def _audit_request(
        self, request: Request, response: Response, process_time: float
    ) -> None:
        """审计正常请求"""
        try:
            path = request.url.path
            method = request.method
            status_code = response.status_code

            # 确定是否需要审计此请求
            should_audit = False

            if self.audit_api_requests and self._is_api_request(path):
                should_audit = True
            elif self.audit_admin_requests and self._is_admin_request(path):
                should_audit = True

            if not should_audit:
                return

            # 获取请求和响应大小
            request_size = self._get_request_size(request)
            response_size = self._get_response_size(response)

            # 记录API请求审计
            self.audit_logger.log_api_request(
                method=method,
                path=path,
                status_code=status_code,
                process_time=process_time,
                request_size=request_size,
                response_size=response_size,
            )

            # 特殊处理认证失败
            if status_code == 401 and self.audit_auth_failures:
                client_ip = self._get_client_ip(request)
                user_agent = request.headers.get("user-agent", "unknown")

                self.audit_logger.log_login_failure(
                    ip_address=client_ip,
                    user_agent=user_agent,
                    reason="Invalid or missing authentication credentials",
                )

            # 特殊处理管理操作
            if self._is_admin_request(path) and method in ["POST", "PUT", "DELETE"]:
                self._audit_admin_operation(request, method, path, status_code)

        except Exception:
            # 审计记录失败不应影响业务流程
            pass

    async def _audit_error(
        self, request: Request, error_message: str, process_time: float
    ) -> None:
        """审计错误请求"""
        try:
            if self.audit_api_requests:
                self.audit_logger.log_api_error(
                    method=request.method,
                    path=request.url.path,
                    error_code=500,
                    error_message=error_message,
                    process_time=process_time,
                )
        except Exception:
            pass

    def _audit_admin_operation(
        self, request: Request, method: str, path: str, status_code: int
    ) -> None:
        """审计管理操作"""
        try:
            # 根据路径确定操作类型
            operation_details = self._extract_admin_operation(method, path)

            if operation_details and status_code < 400:
                # 记录管理操作的详细信息
                self.audit_logger.log_event(
                    AuditEventType.CONFIG_UPDATED,
                    AuditLevel.HIGH,
                    resource="admin",
                    action=operation_details["action"],
                    details=operation_details,
                )

        except Exception:
            pass

    def _extract_admin_operation(self, method: str, path: str) -> dict:
        """从请求路径提取管理操作信息"""
        operations = {
            ("POST", "/v1/admin/routing/strategy"): {
                "action": "change_routing_strategy",
                "resource_type": "routing_strategy",
            },
            ("POST", "/v1/admin/siliconflow/pricing/refresh"): {
                "action": "refresh_pricing",
                "resource_type": "pricing_data",
            },
            ("DELETE", "/v1/admin/logs/cleanup"): {
                "action": "cleanup_logs",
                "resource_type": "log_files",
            },
            ("POST", "/v1/admin/logs/export"): {
                "action": "export_logs",
                "resource_type": "log_data",
            },
        }

        key = (method, path)
        if key in operations:
            return operations[key]

        # 通用管理操作检测
        if "/admin/" in path:
            return {
                "action": f"{method.lower()}_{path.split('/')[-1]}",
                "resource_type": "admin_resource",
            }

        return None

    def _is_api_request(self, path: str) -> bool:
        """判断是否为API请求"""
        api_prefixes = ["/v1/chat/", "/v1/models", "/v1/embeddings"]
        return any(path.startswith(prefix) for prefix in api_prefixes)

    def _is_admin_request(self, path: str) -> bool:
        """判断是否为管理请求"""
        return path.startswith("/v1/admin/")

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

    def _get_request_size(self, request: Request) -> int:
        """获取请求大小"""
        try:
            content_length = request.headers.get("content-length")
            if content_length:
                return int(content_length)
        except (ValueError, TypeError):
            pass

        return 0

    def _get_response_size(self, response: Response) -> int:
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

        except (ValueError, TypeError):
            pass

        return 0


class SecurityAuditMiddleware(BaseHTTPMiddleware):
    """安全审计中间件 - 专门检测和记录安全相关事件"""

    def __init__(
        self, app, rate_limit_check: bool = True, suspicious_pattern_check: bool = True
    ):
        super().__init__(app)
        self.rate_limit_check = rate_limit_check
        self.suspicious_pattern_check = suspicious_pattern_check
        self.audit_logger = get_audit_logger()

        # 记录IP访问频率（简单实现）
        self.ip_requests = {}
        self.max_requests_per_minute = 60

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.audit_logger:
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        # 设置审计上下文
        self.audit_logger.set_context(ip_address=client_ip)

        try:
            # 检查安全违规
            await self._check_security_violations(request)

            response = await call_next(request)
            return response

        finally:
            self.audit_logger.clear_context()

    async def _check_security_violations(self, request: Request) -> None:
        """检查安全违规"""
        try:
            client_ip = self._get_client_ip(request)

            # 检查速率限制
            if self.rate_limit_check:
                await self._check_rate_limit(request, client_ip)

            # 检查可疑模式
            if self.suspicious_pattern_check:
                await self._check_suspicious_patterns(request, client_ip)

        except Exception:
            pass

    async def _check_rate_limit(self, request: Request, client_ip: str) -> None:
        """检查速率限制"""
        current_time = time.time()

        # 清理旧记录
        cutoff_time = current_time - 60  # 1分钟前
        for ip in list(self.ip_requests.keys()):
            self.ip_requests[ip] = [
                req_time for req_time in self.ip_requests[ip] if req_time > cutoff_time
            ]
            if not self.ip_requests[ip]:
                del self.ip_requests[ip]

        # 记录当前请求
        if client_ip not in self.ip_requests:
            self.ip_requests[client_ip] = []
        self.ip_requests[client_ip].append(current_time)

        # 检查是否超限
        request_count = len(self.ip_requests[client_ip])
        if request_count > self.max_requests_per_minute:
            self.audit_logger.log_rate_limit_exceeded(
                endpoint=request.url.path,
                limit=self.max_requests_per_minute,
                window="1 minute",
                ip_address=client_ip,
            )

    async def _check_suspicious_patterns(
        self, request: Request, client_ip: str
    ) -> None:
        """检查可疑访问模式"""
        path = request.url.path.lower()
        user_agent = request.headers.get("user-agent", "").lower()

        # 检查可疑路径
        suspicious_paths = [
            "/admin/",
            "/.env",
            "/config",
            "/backup",
            "/database",
            "/secret",
            "/../",
            "/./",
        ]

        for suspicious in suspicious_paths:
            if suspicious in path:
                self.audit_logger.log_security_violation(
                    violation_type="suspicious_path_access",
                    severity="medium",
                    description=f"Access to suspicious path: {path}",
                    ip_address=client_ip,
                )
                break

        # 检查可疑User-Agent
        suspicious_agents = [
            "sqlmap",
            "nmap",
            "nikto",
            "burp",
            "scanner",
            "bot",
            "crawler",
            "spider",
        ]

        for suspicious in suspicious_agents:
            if suspicious in user_agent:
                self.audit_logger.log_security_violation(
                    violation_type="suspicious_user_agent",
                    severity="low",
                    description=f"Suspicious user agent: {user_agent[:100]}",
                    ip_address=client_ip,
                )
                break

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
