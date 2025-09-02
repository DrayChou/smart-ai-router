"""
路由服务 - 核心路由逻辑
遵循KISS原则：整合路由、评分、筛选逻辑到单一服务
按照架构规划文档的Phase 1设计
"""
import logging
from typing import List, Optional
from ..routing_models import RoutingRequest, RoutingScore
from ..yaml_config import YAMLConfigLoader, get_yaml_config_loader
from .model_service import get_model_service
from .cache_service import get_cache_service
from .config_service import get_config_service

logger = logging.getLogger(__name__)


class RouterService:
    """路由服务 - 协调器模式，整合各子服务"""
    
    def __init__(self, config_loader: Optional[YAMLConfigLoader] = None):
        self.config_loader = config_loader or get_yaml_config_loader()
        self.model_service = get_model_service()
        self.cache_service = get_cache_service()
        self.config_service = get_config_service()
        
        logger.info("路由服务初始化完成")
    
    async def route_request(self, request: RoutingRequest) -> List[RoutingScore]:
        """处理路由请求 - 主要协调方法"""
        try:
            logger.info(f"开始路由请求，模型: {request.model}")
            
            # 1. 获取候选渠道
            candidates = await self.model_service.find_candidates(request)
            if not candidates:
                logger.warning(f"没有找到匹配模型 {request.model} 的渠道")
                return []
            
            logger.info(f"找到 {len(candidates)} 个候选渠道")
            
            # 2. 计算评分
            scores = await self.model_service.calculate_scores(candidates, request)
            if not scores:
                logger.warning("没有成功评分的渠道")
                return []
            
            # 3. 排序并返回结果
            sorted_results = sorted(scores, key=lambda x: x.total_score, reverse=True)
            
            logger.info(f"路由完成，返回 {len(sorted_results)} 个评分结果")
            return sorted_results
            
        except Exception as e:
            logger.error(f"路由请求失败: {e}", exc_info=True)
            return []
    
    def get_available_models(self) -> List[str]:
        """获取所有可用模型列表"""
        return self.model_service.get_available_models()
    
    def get_channel_info(self, channel_id: str) -> Optional[dict]:
        """获取指定渠道信息"""
        return self.model_service.get_channel_info(channel_id)


# 全局路由服务实例
_global_router_service: Optional[RouterService] = None


def get_router_service() -> RouterService:
    """获取全局路由服务实例"""
    global _global_router_service
    if _global_router_service is None:
        _global_router_service = RouterService()
    return _global_router_service