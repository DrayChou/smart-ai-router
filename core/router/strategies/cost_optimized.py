"""
Cost-optimized routing strategy
成本优化路由策略
"""

from decimal import Decimal
from typing import List

from core.router.base import BaseRoutingStrategy, RoutingRequest, RoutingScore
from core.models.channel import Channel


class CostOptimizedStrategy(BaseRoutingStrategy):
    """成本优化路由策略"""
    
    def __init__(self):
        super().__init__(
            name="cost_optimized",
            description="优先选择成本最低的可用渠道"
        )
    
    async def calculate_scores(
        self,
        channels: List[Channel],
        request: RoutingRequest
    ) -> List[RoutingScore]:
        """按成本排序计算评分"""
        scores = []
        costs = []
        
        # 先计算所有渠道的成本
        for channel in channels:
            effective_cost = self.calculate_effective_cost(
                channel, request.prompt_tokens
            )
            costs.append(effective_cost)
        
        # 找出最低和最高成本用于归一化
        if costs:
            min_cost = min(costs)
            max_cost = max(costs)
            cost_range = max_cost - min_cost if max_cost > min_cost else Decimal('1.0')
        else:
            min_cost = max_cost = cost_range = Decimal('1.0')
        
        for i, channel in enumerate(channels):
            effective_cost = costs[i]
            
            # 成本评分：成本越低评分越高
            if cost_range > 0:
                cost_score = float(1.0 - float(effective_cost - min_cost) / float(cost_range))
            else:
                cost_score = 1.0
            
            # 基础的可靠性检查
            reliability_score = float(channel.health_score or 0.8)
            
            # 综合评分：80% 成本 + 20% 可靠性
            combined_score = 0.8 * cost_score + 0.2 * reliability_score
            
            score = RoutingScore(
                channel=channel,
                score=combined_score,
                effective_cost=effective_cost,
                speed_score=float(channel.performance_scores.get("speed_score", 0.5) if channel.performance_scores else 0.5),
                quality_score=float(channel.performance_scores.get("quality_score", 0.5) if channel.performance_scores else 0.5),
                reliability_score=reliability_score,
                reason=f"成本最优 (${effective_cost:.4f})",
                metadata={
                    "strategy": self.name,
                    "cost_rank": i + 1,
                    "cost_score": cost_score
                }
            )
            
            scores.append(score)
        
        # 按评分降序排序
        scores.sort(key=lambda x: x.score, reverse=True)
        return scores