"""
Chat completion API endpoints
聊天完成API接口
"""

from fastapi import APIRouter, HTTPException
from core.handlers.chat_handler import ChatCompletionHandler, ChatCompletionRequest
from core.exceptions import RouterException
from core.utils.logger import get_logger

logger = get_logger(__name__)

def create_chat_router(chat_handler: ChatCompletionHandler) -> APIRouter:
    """创建聊天相关的API路由"""
    
    router = APIRouter(prefix="/v1", tags=["chat"])
    
    @router.post("/chat/completions")
    async def chat_completions(request: ChatCompletionRequest):
        """聊天完成API - 核心功能"""
        try:
            return await chat_handler.handle_request(request)
        except RouterException as e:
            logger.error(f"Router error: {e}")
            raise HTTPException(status_code=e.status_code, detail=e.message)
        except Exception as e:
            logger.error(f"Unexpected error in chat completions: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    
    return router