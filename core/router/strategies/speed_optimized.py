"""
Speed-optimized routing strategy
速度优化路由策略
"""

from decimal import Decimal
from typing import List

from core.router.base import BaseRoutingStrategy, RoutingRequest, RoutingScore
from core.models.channel import Channel


class SpeedOptimizedStrategy(BaseRoutingStrategy):
    """速度优化路由策略"""
    
    def __init__(self):
        super().__init__(
            name="speed_optimized",
            description="优先选择响应速度最快的可用渠道"
        )
    
    async def calculate_scores(
        self,
        channels: List[Channel],
        request: RoutingRequest
    ) -> List[RoutingScore]:
        """按速度排序计算评分"""
        scores = []
        
        for channel in channels:
            effective_cost = self.calculate_effective_cost(
                channel, request.prompt_tokens
            )
            
            # 获取速度相关指标
            performance_scores = channel.performance_scores or {}
            speed_score = float(performance_scores.get("speed_score", 0.5))
            
            # 考虑健康度和最近成功情况
            reliability_score = float(channel.health_score or 0.8)
            
            # 如果最近有成功请求，提升速度评分
            if channel.last_success_at and channel.last_error_at:
                if channel.last_success_at > channel.last_error_at:
                    speed_score = min(1.0, speed_score * 1.2)
            elif channel.last_success_at:
                speed_score = min(1.0, speed_score * 1.1)
            
            # 综合评分：70% 速度 + 20% 可靠性 + 10% 成本考虑
            cost_factor = 1.0 / (1.0 + float(effective_cost)) if effective_cost > 0 else 1.0
            combined_score = 0.7 * speed_score + 0.2 * reliability_score + 0.1 * cost_factor
            
            score = RoutingScore(
                channel=channel,
                score=combined_score,
                effective_cost=effective_cost,
                speed_score=speed_score,
                quality_score=float(performance_scores.get("quality_score", 0.5)),
                reliability_score=reliability_score,
                reason=f"速度最优 (评分: {speed_score:.2f})",
                metadata={
                    "strategy": self.name,
                    "base_speed_score": float(performance_scores.get("speed_score", 0.5)),
                    "adjusted_speed_score": speed_score
                }
            )
            
            scores.append(score)
        
        # 按评分降序排序
        scores.sort(key=lambda x: x.score, reverse=True)
        return scores