"""
Chat completion API endpoints
聊天完成API接口
"""

import time
from fastapi import APIRouter, HTTPException

from core.exceptions import RoutingException
from core.handlers.chat_handler import ChatCompletionHandler, ChatCompletionRequest
from core.utils.logger import get_logger
from core.utils.exception_handler import ExternalAPIError, ValidationError
# Removed duplicate log_request import - logging handled by chat_handler

logger = get_logger(__name__)

def create_chat_router(chat_handler: ChatCompletionHandler) -> APIRouter:
    """创建聊天相关的API路由"""

    router = APIRouter(prefix="/v1", tags=["chat"])

    @router.post("/chat/completions")
    async def chat_completions(request: ChatCompletionRequest):
        """聊天完成API - 核心功能"""
        # 统一异常处理现在由 ExceptionHandlerMiddleware 处理
        # 无需在这里手动捕获异常，中间件会自动处理并记录到状态监控
        response = await chat_handler.handle_request(request)
        return response

    return router
