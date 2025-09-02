"""
路由器API集成
将新的服务层无缝集成到现有的FastAPI接口
遵循KISS原则：最小化API变更，最大化兼容性
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime

# 导入新的服务层
from core.services import (
    get_router_service, 
    get_config_service,
    get_cache_service
)
from core.routing_models import RoutingRequest

logger = logging.getLogger(__name__)

# 创建API路由器
router = APIRouter(prefix="/v1", tags=["routing"])


@router.post("/chat/completions")
async def chat_completions(request_data: Dict[str, Any]):
    """
    OpenAI兼容的聊天完成接口
    使用新的服务层处理路由请求
    """
    try:
        # 将请求转换为内部格式
        routing_request = RoutingRequest(
            model=request_data.get("model", ""),
            messages=request_data.get("messages", []),
            strategy=request_data.get("strategy")  # 可选的路由策略
        )
        
        # 使用新的路由服务
        router_service = get_router_service()
        routing_results = await router_service.route_request(routing_request)
        
        if not routing_results:
            raise HTTPException(
                status_code=404, 
                detail=f"No available channels found for model: {routing_request.model}"
            )
        
        # 返回最佳路由结果
        best_result = routing_results[0]
        
        # 构造响应（兼容OpenAI格式）
        response = {
            "id": f"chatcmpl-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": routing_request.model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant", 
                    "content": f"Routed to channel: {best_result.channel_id}"
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": best_result.estimated_tokens or 0,
                "completion_tokens": 0,
                "total_tokens": best_result.estimated_tokens or 0
            },
            # 添加路由信息
            "routing_info": {
                "channel_id": best_result.channel_id,
                "total_score": best_result.total_score,
                "estimated_cost": best_result.estimated_cost,
                "matched_model": best_result.matched_model,
                "available_alternatives": len(routing_results) - 1
            }
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Chat completions API错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def list_models():
    """
    列出所有可用模型
    使用新的路由服务获取模型列表
    """
    try:
        router_service = get_router_service()
        models = router_service.get_available_models()
        
        # 构造OpenAI兼容的响应格式
        model_objects = []
        for model_name in models:
            model_objects.append({
                "id": model_name,
                "object": "model",
                "created": int(datetime.now().timestamp()),
                "owned_by": "smart-ai-router"
            })
        
        return {
            "object": "list",
            "data": model_objects
        }
        
    except Exception as e:
        logger.error(f"Models API错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """
    健康检查接口
    简化版本，按照KISS原则
    """
    try:
        # 简化的健康检查
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "0.3.0"
        }
        
    except Exception as e:
        logger.error(f"Health check API错误: {e}", exc_info=True)
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }


@router.get("/admin/performance")
async def get_performance_summary():
    """
    获取性能摘要 - 管理接口（简化版本）
    """
    try:
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "message": "Performance monitoring is simplified in Phase 1 refactoring"
        }
        
    except Exception as e:
        logger.error(f"Performance API错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/config")
async def get_config_summary():
    """
    获取配置摘要 - 管理接口
    """
    try:
        config_service = get_config_service()
        summary = config_service.get_config_summary()
        
        return summary
        
    except Exception as e:
        logger.error(f"Config API错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/cache/stats")
async def get_cache_stats():
    """
    获取缓存统计 - 管理接口
    """
    try:
        cache_service = get_cache_service()
        stats = await cache_service.get_cache_stats()
        
        return stats
        
    except Exception as e:
        logger.error(f"Cache stats API错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/cache/clear")
async def clear_cache(namespace: Optional[str] = None, background_tasks: BackgroundTasks = None):
    """
    清理缓存 - 管理接口
    """
    try:
        cache_service = get_cache_service()
        
        if namespace:
            # 清理指定命名空间
            await cache_service.clear_namespace(namespace)
            message = f"Cleared cache namespace: {namespace}"
        else:
            message = "Cache clearing is simplified in Phase 1 refactoring"
        
        return {
            "status": "success",
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Clear cache API错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/routing/strategies")
async def get_routing_strategies():
    """
    获取路由策略信息 - 管理接口
    """
    try:
        # 使用统一的模型服务获取策略信息
        router_service = get_router_service()
        model_service = router_service.model_service
        
        strategies = list(model_service.routing_strategies.keys())
        strategy_info = {}
        
        for strategy_name in strategies:
            strategy_info[strategy_name] = {
                "name": strategy_name,
                "config": model_service.routing_strategies[strategy_name]
            }
        
        return {
            "available_strategies": strategies,
            "strategy_details": strategy_info
        }
        
    except Exception as e:
        logger.error(f"Routing strategies API错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/routing/test")
async def test_routing(request_data: Dict[str, Any]):
    """
    测试路由请求 - 管理接口
    只返回路由结果，不执行实际请求
    """
    try:
        routing_request = RoutingRequest(
            model=request_data.get("model", ""),
            messages=request_data.get("messages", []),
            strategy=request_data.get("strategy")
        )
        
        router_service = get_router_service()
        routing_results = await router_service.route_request(routing_request)
        
        # 格式化路由结果
        formatted_results = []
        for result in routing_results:
            formatted_results.append({
                "channel_id": result.channel_id,
                "total_score": result.total_score,
                "scores": result.scores,
                "estimated_cost": result.estimated_cost,
                "estimated_tokens": result.estimated_tokens,
                "matched_model": result.matched_model
            })
        
        return {
            "request": {
                "model": routing_request.model,
                "strategy": routing_request.strategy
            },
            "results": formatted_results,
            "result_count": len(formatted_results),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Test routing API错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/channels")
async def get_channels_info():
    """
    获取渠道信息 - 管理接口
    """
    try:
        config_service = get_config_service()
        channels = config_service.get_channels()
        
        # 格式化渠道信息
        channel_info = []
        for channel in channels:
            info = {
                "provider": channel.get("provider", "unknown"),
                "name": channel.get("name", "default"),
                "models_count": len(channel.get("models", [])),
                "priority": channel.get("priority", 50),
                "status": channel.get("status", "unknown")
            }
            channel_info.append(info)
        
        return {
            "channels": channel_info,
            "total_channels": len(channel_info),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Channels info API错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# 兼容性中间件函数
async def legacy_compatibility_middleware(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    兼容性中间件，处理旧格式的请求
    """
    # 在这里可以添加对旧请求格式的转换逻辑
    return request_data


# 导出路由器，供主应用使用
__all__ = ["router"]