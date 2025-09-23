"""
Authentication Module - API Token和Admin Token验证
"""

import logging
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

from core.utils.thread_safe_singleton import get_or_create_global

logger = logging.getLogger(__name__)


def generate_secure_token() -> str:
    """生成安全的随机token"""
    return secrets.token_urlsafe(32)


def get_or_generate_api_token(config_token: Optional[str] = None) -> str:
    """获取或生成API token"""
    if config_token:
        return config_token

    def _create_api_token():
        token = generate_secure_token()
        logger.info(f"🔑 Generated API Token: {token}")
        return token

    return get_or_create_global("_generated_api_token", _create_api_token)


def get_or_generate_admin_token(config_token: Optional[str] = None) -> str:
    """获取或生成Admin token"""
    if config_token:
        return config_token

    def _create_admin_token():
        token = generate_secure_token()
        logger.info(f"[KEY] Generated Admin Token: {token}")
        return token

    return get_or_create_global("_generated_admin_token", _create_admin_token)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """API Token认证中间件"""

    def __init__(self, app, enabled: bool = False, api_token: Optional[str] = None):
        super().__init__(app)
        self.enabled = enabled
        self.api_token = get_or_generate_api_token(api_token) if enabled else None

    async def dispatch(self, request: Request, call_next):
        # 如果认证未启用，直接通过
        if not self.enabled:
            return await call_next(request)

        # 跳过某些路径的认证
        skip_paths = {"/", "/health", "/docs", "/redoc", "/openapi.json"}
        if request.url.path in skip_paths:
            return await call_next(request)

        # 检查admin接口路径 - 这些由AdminAuthDependency处理，跳过中间件认证
        if request.url.path.startswith("/v1/admin/"):
            return await call_next(request)

        # 检查Authorization header
        authorization = request.headers.get("Authorization")
        if not authorization:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=401, content={"error": "Authorization header missing"}
            )

        # 验证Bearer token
        if not authorization.startswith("Bearer "):
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=401, content={"error": "Invalid authorization format"}
            )

        token = authorization[7:]  # 移除"Bearer "前缀
        if token != self.api_token:
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=401, content={"error": "Invalid API token"})

        return await call_next(request)


# FastAPI依赖注入用于Admin认证
security = HTTPBearer()


class AdminAuthDependency:
    """Admin Token认证依赖"""

    def __init__(self, config_loader):
        self.config_loader = config_loader
        self._admin_token = None
        self._initialize_admin_token()

    def _initialize_admin_token(self):
        """初始化Admin Token"""
        try:
            admin_config = self.config_loader.config.auth.admin
            if admin_config.enabled:
                self._admin_token = get_or_generate_admin_token(
                    admin_config.admin_token
                )
                logger.info("[AUTH] Admin authentication enabled")
            else:
                logger.info("[AUTH] Admin authentication disabled")
        except Exception as e:
            logger.warning(f"Failed to initialize admin token: {e}")
            self._admin_token = None

    def __call__(
        self, credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> bool:
        """验证Admin Token"""
        # 如果admin认证未启用，直接通过
        admin_config = getattr(self.config_loader.config.auth, "admin", None)
        if not admin_config or not admin_config.enabled:
            return True

        # 检查token
        if not self._admin_token:
            logger.error("Admin token not initialized")
            raise HTTPException(
                status_code=500, detail="Admin authentication not configured"
            )

        if credentials.credentials != self._admin_token:
            logger.warning(
                f"Invalid admin token attempt: {credentials.credentials[:8]}..."
            )
            raise HTTPException(status_code=403, detail="Invalid admin token")

        return True


def get_admin_auth_dependency():
    """获取Admin认证依赖实例"""
    from core.utils.thread_safe_singleton import get_global

    admin_auth = get_global("admin_auth_dependency")
    if admin_auth is None:
        raise HTTPException(
            status_code=500, detail="Admin authentication not initialized"
        )
    return admin_auth


def initialize_admin_auth(config_loader):
    """初始化Admin认证依赖"""
    from core.utils.thread_safe_singleton import set_global

    admin_auth = AdminAuthDependency(config_loader)
    set_global("admin_auth_dependency", admin_auth)
    return admin_auth
