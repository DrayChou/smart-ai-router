"""
服务层模块
按照ARCHITECTURE_OPTIMIZATION_REPORT.md规划文档实施
Phase 1: 只包含4个核心服务，遵循KISS原则

统一命名规范：
- Service: 业务逻辑服务 (统一后缀)
"""

from .router_service import RouterService, get_router_service
from .model_service import ModelService, get_model_service  
from .config_service import ConfigService, get_config_service
from .cache_service import CacheService, get_cache_service

__all__ = [
    'RouterService',
    'ModelService',
    'ConfigService', 
    'CacheService',
    'get_router_service',
    'get_model_service',
    'get_config_service',
    'get_cache_service'
]