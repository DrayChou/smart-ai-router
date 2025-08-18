# -*- coding: utf-8 -*-
"""
Authentication middleware for Smart AI Router
"""

import logging
from typing import Callable, Optional
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    API Token认证中间件
    
    检查请求的Authorization头是否包含正确的Token
    """
    
    def __init__(
        self, 
        app, 
        enabled: bool = False,
        api_token: Optional[str] = None
    ):
        super().__init__(app)
        self.enabled = enabled
        self.api_token = api_token
        
        # 不需要认证的路径
        self.excluded_paths = {
            "/health",
            "/docs", 
            "/openapi.json",
            "/redoc"
        }
        
        logger.info(f"Authentication middleware initialized: enabled={enabled}")
        if enabled and api_token:
            logger.info(f"API Token authentication enabled with token: {api_token[:8]}...")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        处理请求认证
        """
        # 如果认证未启用，直接通过
        if not self.enabled:
            return await call_next(request)
            
        # 检查是否是排除的路径
        if request.url.path in self.excluded_paths:
            return await call_next(request)
            
        # 检查Authorization头
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return self._create_auth_error("Missing Authorization header")
            
        # 检查Token格式 (支持 "Bearer token" 和直接 "token" 两种格式)
        token = self._extract_token(auth_header)
        if not token:
            return self._create_auth_error("Invalid Authorization header format")
            
        # 验证Token
        if token != self.api_token:
            logger.warning(f"Invalid API token attempted: {token[:8]}... from {request.client.host}")
            return self._create_auth_error("Invalid API token")
            
        # Token验证通过，继续处理请求
        logger.debug(f"API token validated successfully for {request.url.path}")
        return await call_next(request)
    
    def _extract_token(self, auth_header: str) -> Optional[str]:
        """
        从Authorization头中提取Token
        
        支持以下格式:
        - Bearer <token>
        - <token>
        """
        auth_header = auth_header.strip()
        
        # Bearer token格式
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()
            
        # 直接token格式
        return auth_header
    
    def _create_auth_error(self, message: str) -> JSONResponse:
        """
        创建认证错误响应
        """
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": message,
                    "type": "authentication_error",
                    "code": "invalid_api_token"
                }
            }
        )