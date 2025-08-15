"""
基于JSON配置的轻量路由引擎
"""
import random
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import time
import logging

from .config_loader import ConfigLoader, ChannelConfig, get_config_loader

logger = logging.getLogger(__name__)

@dataclass
class RoutingScore:
    """路由评分结果"""
    channel: ChannelConfig
    total_score: float
    cost_score: float
    speed_score: float
    quality_score: float
    reliability_score: float
    reason: str

@dataclass
class RoutingRequest:
    """路由请求"""
    model: str
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    functions: Optional[List[Dict[str, Any]]] = None
    required_capabilities: List[str] = None

class JSONRouter:
    """基于JSON配置的路由器"""
    
    def __init__(self, config_loader: Optional[ConfigLoader] = None):
        self.config = config_loader or get_config_loader()
        self.routing_config = self.config.get_routing_config()
        
    def route_request(self, request: RoutingRequest) -> Optional[RoutingScore]:
        """路由请求到最合适的渠道"""
        try:
            # 1. 获取候选渠道
            candidates = self._get_candidate_channels(request)
            if not candidates:
                logger.warning(f"没有找到适合模型 {request.model} 的渠道")
                return None
            
            # 2. 过滤渠道
            filtered_candidates = self._filter_channels(candidates, request)
            if not filtered_candidates:
                logger.warning(f"过滤后没有可用渠道")
                return None
            
            # 3. 计算评分并排序
            scored_channels = self._score_channels(filtered_candidates, request)
            if not scored_channels:
                return None
            
            # 4. 返回最佳渠道
            best_channel = scored_channels[0]
            logger.info(f"选择渠道: {best_channel.channel.name} (评分: {best_channel.total_score:.3f})")
            
            return best_channel
            
        except Exception as e:
            logger.error(f"路由请求失败: {e}")
            return None
    
    def _get_candidate_channels(self, request: RoutingRequest) -> List[ChannelConfig]:
        """获取候选渠道"""
        # 如果是虚拟模型组，获取组内渠道
        if request.model.startswith("auto:") or request.model in ["gpt-4o", "claude-3.5"]:
            return self.config.get_channels_for_group(request.model)
        
        # 如果是具体模型名，找对应渠道
        channels = self.config.get_channels_by_model(request.model)
        if channels:
            return channels
        
        # 模糊匹配
        all_channels = self.config.get_enabled_channels()
        matched_channels = []
        for channel in all_channels:
            if request.model.lower() in channel.model_name.lower():
                matched_channels.append(channel)
        
        return matched_channels
    
    def _filter_channels(self, channels: List[ChannelConfig], request: RoutingRequest) -> List[ChannelConfig]:
        """过滤渠道"""
        filtered = []
        
        for channel in channels:
            # 检查是否启用
            if not channel.enabled:
                continue
            
            # 检查API密钥
            if not channel.api_key or len(channel.api_key.strip()) == 0:
                continue
            
            # 检查健康状态
            health_score = self.config.runtime_state.health_scores.get(channel.id, 1.0)
            if health_score < 0.3:  # 健康分数太低
                continue
            
            # 检查能力要求
            if request.required_capabilities:
                if not all(cap in channel.capabilities for cap in request.required_capabilities):
                    continue
            
            # 检查function calling
            if request.functions and "function_calling" not in channel.capabilities:
                continue
            
            filtered.append(channel)
        
        return filtered
    
    def _score_channels(self, channels: List[ChannelConfig], request: RoutingRequest) -> List[RoutingScore]:
        """计算渠道评分"""
        scored_channels = []
        
        # 获取路由策略
        strategy = self._get_routing_strategy(request.model)
        
        for channel in channels:
            # 计算各项评分
            cost_score = self._calculate_cost_score(channel, request)
            speed_score = self._calculate_speed_score(channel)
            quality_score = self._calculate_quality_score(channel)
            reliability_score = self._calculate_reliability_score(channel)
            
            # 根据策略计算总分
            total_score = self._calculate_total_score(
                strategy, cost_score, speed_score, quality_score, reliability_score
            )
            
            routing_score = RoutingScore(
                channel=channel,
                total_score=total_score,
                cost_score=cost_score,
                speed_score=speed_score,
                quality_score=quality_score,
                reliability_score=reliability_score,
                reason=f"成本:{cost_score:.2f} 速度:{speed_score:.2f} 质量:{quality_score:.2f} 可靠性:{reliability_score:.2f}"
            )
            
            scored_channels.append(routing_score)
        
        # 按总分排序
        scored_channels.sort(key=lambda x: x.total_score, reverse=True)
        
        return scored_channels
    
    def _get_routing_strategy(self, model: str) -> List[Dict[str, Any]]:
        """获取路由策略"""
        # 如果是模型组，使用组的策略
        group = self.config.get_model_group(model)
        if group and group.routing_strategy:
            return group.routing_strategy
        
        # 默认平衡策略
        return [
            {"field": "effective_cost", "order": "asc", "weight": 0.3},
            {"field": "speed_score", "order": "desc", "weight": 0.3},
            {"field": "quality_score", "order": "desc", "weight": 0.2},
            {"field": "reliability_score", "order": "desc", "weight": 0.2}
        ]
    
    def _calculate_cost_score(self, channel: ChannelConfig, request: RoutingRequest) -> float:
        """计算成本评分(0-1，越低成本越高分)"""
        pricing = channel.pricing
        if not pricing:
            return 0.5
        
        # 估算token数量
        input_tokens = self._estimate_tokens(request.messages)
        max_output_tokens = request.max_tokens or 1000
        
        # 计算成本
        input_cost = pricing.get("input_cost_per_1k", 0.001) * input_tokens / 1000
        output_cost = pricing.get("output_cost_per_1k", 0.002) * max_output_tokens / 1000
        total_cost = (input_cost + output_cost) * pricing.get("effective_multiplier", 1.0)
        
        # 转换为评分 (成本越低分数越高)
        # 假设最高成本为0.1美元
        max_cost = 0.1
        score = max(0, 1 - (total_cost / max_cost))
        
        return min(1.0, score)
    
    def _calculate_speed_score(self, channel: ChannelConfig) -> float:
        """计算速度评分"""
        return channel.performance.get("speed_score", 0.8)
    
    def _calculate_quality_score(self, channel: ChannelConfig) -> float:
        """计算质量评分"""
        return channel.performance.get("quality_score", 0.8)
    
    def _calculate_reliability_score(self, channel: ChannelConfig) -> float:
        """计算可靠性评分"""
        # 基础可靠性分数
        base_score = channel.performance.get("reliability_score", 0.9)
        
        # 结合实时健康状态
        health_score = self.config.runtime_state.health_scores.get(channel.id, 1.0)
        
        # 综合评分
        return (base_score * 0.7 + health_score * 0.3)
    
    def _calculate_total_score(self, strategy: List[Dict[str, Any]], 
                             cost_score: float, speed_score: float, 
                             quality_score: float, reliability_score: float) -> float:
        """根据策略计算总评分"""
        total_score = 0.0
        score_map = {
            "effective_cost": cost_score,
            "speed_score": speed_score,
            "quality_score": quality_score,
            "reliability_score": reliability_score
        }
        
        for rule in strategy:
            field = rule.get("field", "")
            weight = rule.get("weight", 0.0)
            order = rule.get("order", "desc")
            
            if field in score_map:
                score = score_map[field]
                # 如果是ascending order，需要反转分数
                if order == "asc":
                    score = 1.0 - score
                
                total_score += score * weight
        
        return total_score
    
    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """估算token数量(简单估算)"""
        total_chars = 0
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
        
        # 粗略估算: 4个字符约等于1个token
        return max(1, total_chars // 4)
    
    def get_available_models(self) -> List[str]:
        """获取可用模型列表"""
        models = set()
        
        # 添加虚拟模型组
        for group_name, group in self.config.model_groups.items():
            if group.enabled:
                models.add(group_name)
        
        # 添加具体模型
        for channel in self.config.get_enabled_channels():
            models.add(channel.model_name)
        
        return sorted(list(models))
    
    def update_channel_health(self, channel_id: str, success: bool, latency: Optional[float] = None):
        """更新渠道健康状态"""
        current_health = self.config.runtime_state.health_scores.get(channel_id, 1.0)
        
        if success:
            # 成功时略微提升健康分数
            new_health = min(1.0, current_health * 1.01 + 0.01)
        else:
            # 失败时降低健康分数
            new_health = max(0.0, current_health * 0.9 - 0.1)
        
        self.config.update_channel_health(channel_id, new_health)
        
        # 如果健康分数过低，记录警告
        if new_health < 0.3:
            logger.warning(f"渠道 {channel_id} 健康分数过低: {new_health:.3f}")

# 全局路由器实例
_router: Optional[JSONRouter] = None

def get_router() -> JSONRouter:
    """获取全局路由器实例"""
    global _router
    if _router is None:
        _router = JSONRouter()
    return _router