"""
Base routing classes and interfaces (LEGACY)
基础路由类和接口（遗留/可选）

Note:
- The default runtime path is tag-based routing driven by YAML configuration
  (JSONRouter + YAMLConfigLoader).
- This module references VirtualModelGroup etc. and is kept for optional/
  advanced scenarios. It is not used in the default flow and may be removed
  in a future major version if unused.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, List, Optional

from core.models.channel import Channel
from core.models.virtual_model import VirtualModelGroup


class RoutingScore:
    """路由评分结果"""
    
    def __init__(
        self,
        channel: Channel,
        score: float,
        effective_cost: Decimal,
        speed_score: float,
        quality_score: float,
        reliability_score: float,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.channel = channel
        self.score = score  # 综合评分 (0.0-1.0, 越高越好)
        self.effective_cost = effective_cost  # 有效成本
        self.speed_score = speed_score  # 速度评分
        self.quality_score = quality_score  # 质量评分
        self.reliability_score = reliability_score  # 可靠性评分
        self.reason = reason  # 选择理由
        self.metadata = metadata or {}
        
    def __repr__(self):
        return f"<RoutingScore(channel='{self.channel.name}', score={self.score:.3f})>"


class RoutingRequest:
    """路由请求参数"""
    
    def __init__(
        self,
        model_group: VirtualModelGroup,
        prompt_tokens: int,
        required_capabilities: Optional[List[str]] = None,
        user_preferences: Optional[Dict[str, Any]] = None,
        budget_limit: Optional[Decimal] = None,
        priority: str = "balanced"  # cost, speed, quality, balanced
    ):
        self.model_group = model_group
        self.prompt_tokens = prompt_tokens
        self.required_capabilities = required_capabilities or []
        self.user_preferences = user_preferences or {}
        self.budget_limit = budget_limit
        self.priority = priority


class BaseRoutingStrategy(ABC):
    """基础路由策略抽象类"""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
    
    @abstractmethod
    async def calculate_scores(
        self,
        channels: List[Channel],
        request: RoutingRequest
    ) -> List[RoutingScore]:
        """
        计算渠道评分
        
        Args:
            channels: 候选渠道列表
            request: 路由请求参数
            
        Returns:
            评分结果列表 (按评分降序排序)
        """
        pass
    
    def filter_channels(
        self,
        channels: List[Channel],
        request: RoutingRequest
    ) -> List[Channel]:
        """
        过滤渠道 (基础过滤逻辑)
        
        Args:
            channels: 候选渠道列表
            request: 路由请求参数
            
        Returns:
            过滤后的渠道列表
        """
        filtered = []
        
        for channel in channels:
            # 检查渠道状态
            if channel.status != "active":
                continue
                
            # 检查冷却期
            if channel.cooldown_until and channel.cooldown_until > channel.created_at:
                continue
                
            # 检查每日配额
            if channel.daily_request_count >= channel.daily_request_limit:
                continue
                
            # 检查能力要求
            if request.required_capabilities:
                channel_caps = channel.capabilities or {}
                for cap in request.required_capabilities:
                    if not channel_caps.get(cap, False):
                        break
                else:
                    filtered.append(channel)
            else:
                filtered.append(channel)
                
        return filtered
    
    def calculate_effective_cost(
        self,
        channel: Channel,
        prompt_tokens: int,
        estimated_completion_tokens: int = 100
    ) -> Decimal:
        """
        计算有效成本
        
        Args:
            channel: 渠道对象
            prompt_tokens: 输入token数
            estimated_completion_tokens: 预估输出token数
            
        Returns:
            有效成本 (USD)
        """
        if not channel.input_cost_per_1k or not channel.output_cost_per_1k:
            return Decimal('999.99')  # 未知价格设为很高
            
        input_cost = (Decimal(str(prompt_tokens)) / 1000) * channel.input_cost_per_1k
        output_cost = (Decimal(str(estimated_completion_tokens)) / 1000) * channel.output_cost_per_1k
        
        return input_cost + output_cost


class RoutingEngine:
    """智能路由引擎"""
    
    def __init__(self):
        self.strategies: Dict[str, BaseRoutingStrategy] = {}
        self.default_strategy = "multi_layer"
        
    def register_strategy(self, strategy: BaseRoutingStrategy):
        """注册路由策略"""
        self.strategies[strategy.name] = strategy
        
    def get_strategy(self, name: str) -> Optional[BaseRoutingStrategy]:
        """获取路由策略"""
        return self.strategies.get(name)
        
    async def select_channel(
        self,
        channels: List[Channel],
        request: RoutingRequest,
        strategy_name: Optional[str] = None
    ) -> Optional[RoutingScore]:
        """
        选择最优渠道
        
        Args:
            channels: 候选渠道列表
            request: 路由请求参数
            strategy_name: 路由策略名称
            
        Returns:
            最优渠道的评分结果，如果没有合适渠道则返回None
        """
        strategy_name = strategy_name or self.default_strategy
        strategy = self.get_strategy(strategy_name)
        
        if not strategy:
            raise ValueError(f"未知的路由策略: {strategy_name}")
        
        # 过滤渠道
        filtered_channels = strategy.filter_channels(channels, request)
        if not filtered_channels:
            return None
            
        # 计算评分
        scores = await strategy.calculate_scores(filtered_channels, request)
        if not scores:
            return None
            
        # 返回最高分渠道
        return scores[0]
        
    async def get_ranked_channels(
        self,
        channels: List[Channel],
        request: RoutingRequest,
        strategy_name: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[RoutingScore]:
        """
        获取排序后的渠道列表
        
        Args:
            channels: 候选渠道列表
            request: 路由请求参数
            strategy_name: 路由策略名称
            limit: 返回数量限制
            
        Returns:
            排序后的渠道评分列表
        """
        strategy_name = strategy_name or self.default_strategy
        strategy = self.get_strategy(strategy_name)
        
        if not strategy:
            raise ValueError(f"未知的路由策略: {strategy_name}")
        
        # 过滤渠道
        filtered_channels = strategy.filter_channels(channels, request)
        if not filtered_channels:
            return []
            
        # 计算评分
        scores = await strategy.calculate_scores(filtered_channels, request)
        
        # 应用限制
        if limit and len(scores) > limit:
            scores = scores[:limit]
            
        return scores
