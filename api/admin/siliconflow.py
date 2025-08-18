# -*- coding: utf-8 -*-
"""
SiliconFlow管理API - 定价抓取和管理功能
"""
from typing import Dict, Any, Optional
import logging

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from ...core.scheduler.tasks.siliconflow_pricing import get_siliconflow_pricing_task, run_siliconflow_pricing_update
from ...core.utils.auth_manager import verify_api_key_dependency

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/siliconflow", tags=["SiliconFlow Admin"])

@router.post("/pricing/refresh")
async def refresh_siliconflow_pricing(
    force: bool = False,
    api_key_valid: bool = Depends(verify_api_key_dependency)
) -> JSONResponse:
    """
    手动刷新SiliconFlow定价信息
    
    Args:
        force: 强制重新抓取，忽略缓存
    """
    try:
        logger.info(f"开始手动刷新SiliconFlow定价 (force={force})")
        
        # 执行定价抓取
        result = await run_siliconflow_pricing_update(force=force)
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "SiliconFlow定价刷新完成",
                "data": result
            }
        )
        
    except Exception as e:
        logger.error(f"SiliconFlow定价刷新失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"定价刷新失败: {str(e)}"
        )

@router.get("/pricing/status")
async def get_siliconflow_pricing_status(
    api_key_valid: bool = Depends(verify_api_key_dependency)
) -> JSONResponse:
    """获取SiliconFlow定价状态"""
    try:
        pricing_task = get_siliconflow_pricing_task()
        stats = pricing_task.get_pricing_stats()
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "pricing_stats": stats,
                    "cache_status": {
                        "total_models": len(pricing_task.cached_pricing),
                        "last_update": pricing_task.last_update.isoformat() if pricing_task.last_update else None,
                        "needs_update": pricing_task.should_update_pricing()
                    }
                }
            }
        )
        
    except Exception as e:
        logger.error(f"获取SiliconFlow定价状态失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"获取状态失败: {str(e)}"
        )

@router.get("/pricing/models")
async def get_siliconflow_pricing_models(
    api_key_valid: bool = Depends(verify_api_key_dependency)
) -> JSONResponse:
    """获取所有SiliconFlow模型的定价信息"""
    try:
        pricing_task = get_siliconflow_pricing_task()
        all_pricing = pricing_task.get_all_pricing()
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "total_models": len(all_pricing),
                    "models": all_pricing
                }
            }
        )
        
    except Exception as e:
        logger.error(f"获取SiliconFlow模型定价失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"获取模型定价失败: {str(e)}"
        )

@router.get("/pricing/model/{model_name}")
async def get_siliconflow_model_pricing(
    model_name: str,
    api_key_valid: bool = Depends(verify_api_key_dependency)
) -> JSONResponse:
    """获取特定模型的定价信息"""
    try:
        pricing_task = get_siliconflow_pricing_task()
        pricing = await pricing_task.get_model_pricing(model_name)
        
        if pricing:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "data": {
                        "model_name": model_name,
                        "pricing": pricing
                    }
                }
            )
        else:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": f"未找到模型 '{model_name}' 的定价信息"
                }
            )
        
    except Exception as e:
        logger.error(f"获取模型 '{model_name}' 定价失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"获取模型定价失败: {str(e)}"
        )