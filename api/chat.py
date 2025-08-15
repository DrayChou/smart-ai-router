"""聊天接口 - 兼容OpenAI API格式"""

import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.manager import get_channel_manager
from core.providers import ChatRequest as ProviderChatRequest, get_provider_registry
from core.router import get_routing_engine, RoutingRequest
from core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class ChatMessage(BaseModel):
    """聊天消息"""
    role: str
    content: str


class ChatRequestModel(BaseModel):
    """聊天请求模型"""
    model: str
    messages: List[ChatMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = 1.0
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    system: Optional[str] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    user: Optional[str] = None


class Usage(BaseModel):
    """Token使用统计"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Choice(BaseModel):
    """聊天响应选择"""
    index: int
    message: Dict[str, Any]
    finish_reason: str


class ChatResponse(BaseModel):
    """聊天响应"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Optional[Usage] = None


async def get_api_key_from_request() -> str:
    """从请求中提取API密钥（模拟）"""
    # TODO: 实现实际的API密钥验证
    return "demo-key"


@router.post("/chat/completions", response_model=ChatResponse)
async def chat_completions(
    request: ChatRequestModel,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_api_key_from_request)
) -> Dict[str, Any]:
    """
    聊天完成接口 - 智能路由核心功能
    
    自动根据模型组配置选择最优的物理模型和渠道
    """
    request_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    start_time = time.time()
    
    logger.info(f"接收到聊天请求: {request_id}, 模型: {request.model}")
    
    try:
        # 1. 获取渠道管理器和路由引擎
        channel_manager = get_channel_manager()
        routing_engine = get_routing_engine()
        provider_registry = get_provider_registry()
        
        # 2. 获取指定模型组的所有可用渠道
        channels = await channel_manager.get_channels_for_model_group(
            request.model, db
        )
        
        if not channels:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"模型组 '{request.model}' 未找到或没有可用渠道"
            )
        
        # 3. 创建路由请求
        # 估算输入token数（简单计算）
        prompt_tokens = sum(len(msg.content.split()) for msg in request.messages)
        
        # 推断能力要求
        required_capabilities = []
        if request.tools:
            required_capabilities.append("function_calling")
        
        # 获取模型组配置
        from sqlalchemy import select
        from core.models.virtual_model import VirtualModelGroup
        
        model_group_result = await db.execute(
            select(VirtualModelGroup).where(VirtualModelGroup.name == request.model)
        )
        model_group = model_group_result.scalar_one_or_none()
        
        if not model_group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"模型组 '{request.model}' 不存在"
            )
        
        routing_request = RoutingRequest(
            model_group=model_group,
            prompt_tokens=prompt_tokens,
            required_capabilities=required_capabilities,
            priority="balanced"  # 可以从请求中推断或配置
        )
        
        # 4. 选择最优渠道
        best_score = await routing_engine.select_channel(channels, routing_request)
        
        if not best_score:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="当前没有可用的渠道，请稍后重试"
            )
        
        selected_channel = best_score.channel
        logger.info(
            f"选择渠道: {selected_channel.name} "
            f"(评分: {best_score.score:.3f}, 原因: {best_score.reason})"
        )
        
        # 5. 获取Provider适配器
        from sqlalchemy import select
        from core.models.provider import Provider
        
        provider_result = await db.execute(
            select(Provider).where(Provider.id == selected_channel.provider_id)
        )
        provider_data = provider_result.scalar_one_or_none()
        
        if not provider_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Provider未找到: {selected_channel.provider_id}"
            )
        
        # 创建适配器实例
        adapter = provider_registry.create_adapter(
            provider_data.name,
            provider_data.adapter_class,
            {
                "base_url": provider_data.base_url,
                "auth_type": provider_data.auth_type,
                "timeout": 30
            }
        )
        
        # 6. 获取API密钥（简化实现）
        channel_api_keys = selected_channel.api_keys
        if not channel_api_keys:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"渠道 {selected_channel.name} 没有可用的API密钥"
            )
        
        channel_api_key = channel_api_keys[0].key_value  # 简化：使用第一个可用密钥
        
        # 7. 转换请求格式
        provider_request = ProviderChatRequest(
            model=selected_channel.model_name,
            messages=[msg.dict() for msg in request.messages],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=request.stream,
            tools=request.tools,
            tool_choice=request.tool_choice,
            system=request.system
        )
        
        # 8. 发送请求到Provider
        if request.stream:
            # 流式响应
            async def stream_response():
                try:
                    async for chunk in adapter.chat_completions_stream(
                        provider_request, channel_api_key
                    ):
                        yield f"data: {chunk}\n\n"
                    yield "data: [DONE]\n\n"
                    
                    # 更新渠道使用统计
                    await channel_manager.update_channel_usage(
                        selected_channel.id, success=True, session=db
                    )
                except Exception as e:
                    logger.error(f"流式请求失败: {e}")
                    # 更新失败统计
                    await channel_manager.update_channel_usage(
                        selected_channel.id, success=False, session=db
                    )
                    yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
            
            return StreamingResponse(
                stream_response(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )
        else:
            # 非流式响应
            provider_response = await adapter.chat_completions(
                provider_request, channel_api_key
            )
            
            # 更新渠道使用统计
            await channel_manager.update_channel_usage(
                selected_channel.id, success=True, session=db
            )
            
            # 9. 转换为标准响应格式
            response = ChatResponse(
                id=request_id,
                created=int(time.time()),
                model=request.model,  # 返回虚拟模型名称
                choices=[
                    Choice(
                        index=0,
                        message={
                            "role": "assistant",
                            "content": provider_response.content
                        },
                        finish_reason=provider_response.finish_reason
                    )
                ],
                usage=Usage(
                    prompt_tokens=provider_response.usage.get("prompt_tokens", prompt_tokens),
                    completion_tokens=provider_response.usage.get("completion_tokens", 0),
                    total_tokens=provider_response.usage.get("total_tokens", prompt_tokens)
                )
            )
            
            # 10. 记录请求日志
            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(
                f"请求完成: {request_id}, 延迟: {latency_ms}ms, "
                f"渠道: {selected_channel.name}, 成本: ${best_score.effective_cost:.4f}"
            )
            
            return response.dict()
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"聊天请求处理失败: {e}", exc_info=True)
        
        # 如果有选中的渠道，更新失败统计
        if 'selected_channel' in locals():
            await channel_manager.update_channel_usage(
                selected_channel.id, success=False, error_type="server_error", session=db
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部服务器错误: {str(e)}"
        )


@router.get("/models")
async def list_models(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    列出可用的虚拟模型组
    """
    try:
        from sqlalchemy import select
        from core.models.virtual_model import VirtualModelGroup
        
        # 查询所有活跃的虚拟模型组
        result = await db.execute(
            select(VirtualModelGroup).where(VirtualModelGroup.status == "active")
        )
        model_groups = result.scalars().all()
        
        models = []
        for group in model_groups:
            models.append({
                "id": group.name,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "smart-ai-router",
                "description": group.display_name or group.description or group.name
            })
        
        return {
            "object": "list",
            "data": models
        }
        
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        # 返回默认模型列表
        return {
            "object": "list",
            "data": [
                {
                    "id": "auto:balanced",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "smart-ai-router",
                    "description": "智能平衡模型组 - 自动选择最优渠道"
                }
            ]
        }