"""
Chat completion API endpoints
聊天完成API接口
"""

import time
from fastapi import APIRouter, HTTPException

from core.exceptions import RoutingException
from core.handlers.chat_handler import ChatCompletionHandler, ChatCompletionRequest
from core.utils.logger import get_logger
# Removed duplicate log_request import - logging handled by chat_handler

logger = get_logger(__name__)

def create_chat_router(chat_handler: ChatCompletionHandler) -> APIRouter:
    """创建聊天相关的API路由"""

    router = APIRouter(prefix="/v1", tags=["chat"])

    @router.post("/chat/completions")
    async def chat_completions(request: ChatCompletionRequest):
        """聊天完成API - 核心功能"""
        start_time = time.time()
        try:
            response = await chat_handler.handle_request(request)
            
            # Single point of logging - no duplicates
            pass
            
            return response
        except RoutingException as e:
            # Record router error to status monitor
            duration_ms = (time.time() - start_time) * 1000
            from .status_monitor import log_request
            log_request(
                method="POST",
                path="/v1/chat/completions",
                status_code=e.status_code,
                duration_ms=duration_ms,
                model=request.model,
                channel=None,
                error=str(e)
            )
            logger.error(f"Router error: {e}")
            raise HTTPException(status_code=e.status_code, detail=e.message)
        except Exception as e:
            # Record unexpected error to status monitor
            duration_ms = (time.time() - start_time) * 1000
            from .status_monitor import log_request
            log_request(
                method="POST",
                path="/v1/chat/completions",
                status_code=500,
                duration_ms=duration_ms,
                model=request.model,
                channel=None,
                error=str(e)
            )
            logger.error(f"Unexpected error in chat completions: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    return router
