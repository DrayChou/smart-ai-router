"""
Health check API endpoints
健康检查API接口
"""

import time
from fastapi import APIRouter
from core.yaml_config import YAMLConfigLoader

def create_health_router(config_loader: YAMLConfigLoader) -> APIRouter:
    """创建健康检查相关的API路由"""
    
    router = APIRouter(tags=["health"])
    
    @router.get("/")
    async def root():
        """根路径健康检查"""
        return {
            "message": "Smart AI Router - Minimal Mode",
            "version": "0.3.0-minimal",
            "status": "running",
            "mode": "minimal",
            "endpoints": 8
        }

    @router.get("/health")
    async def health_check():
        """系统健康检查"""
        try:
            channel_count = len(config_loader.config.channels)
            provider_count = len(config_loader.config.providers)
            
            return {
                "status": "healthy",
                "version": "0.3.0-minimal", 
                "mode": "minimal",
                "timestamp": int(time.time()),
                "providers": provider_count,
                "channels": channel_count,
                "cache_status": "active"
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    return router