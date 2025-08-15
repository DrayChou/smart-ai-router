"""
Intelligent routing engine module
智能路由引擎模块
"""

from .base import RoutingEngine, RoutingRequest, RoutingScore
from .strategies import (
    CostOptimizedStrategy,
    MultiLayerRoutingStrategy, 
    SpeedOptimizedStrategy,
)


def create_routing_engine() -> RoutingEngine:
    """创建并配置路由引擎实例"""
    engine = RoutingEngine()
    
    # 注册所有策略
    engine.register_strategy(MultiLayerRoutingStrategy())
    engine.register_strategy(CostOptimizedStrategy())
    engine.register_strategy(SpeedOptimizedStrategy())
    
    return engine


# 全局路由引擎实例
_routing_engine = None

def get_routing_engine() -> RoutingEngine:
    """获取全局路由引擎实例"""
    global _routing_engine
    if _routing_engine is None:
        _routing_engine = create_routing_engine()
    return _routing_engine


__all__ = [
    "RoutingEngine",
    "RoutingRequest", 
    "RoutingScore",
    "create_routing_engine",
    "get_routing_engine",
    "MultiLayerRoutingStrategy",
    "CostOptimizedStrategy",
    "SpeedOptimizedStrategy",
]