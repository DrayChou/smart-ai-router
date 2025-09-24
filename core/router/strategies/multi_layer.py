"""
Multi-layer routing strategy
多层路由策略实现
"""

from decimal import Decimal
from typing import Any

from core.models.channel import Channel
from core.router.base import BaseRoutingStrategy, RoutingRequest, RoutingScore


class MultiLayerRoutingStrategy(BaseRoutingStrategy):
    """多层路由策略"""

    def __init__(self):
        super().__init__(
            name="multi_layer", description="支持多因子组合排序的智能路由策略"
        )

    async def calculate_scores(
        self, channels: list[Channel], request: RoutingRequest
    ) -> list[RoutingScore]:
        """计算多层评分"""
        scores = []

        for channel in channels:
            # 计算有效成本
            effective_cost = self.calculate_effective_cost(
                channel, request.prompt_tokens
            )

            # 获取性能评分
            speed_score = self._get_speed_score(channel)
            quality_score = self._get_quality_score(channel)
            reliability_score = self._get_reliability_score(channel)

            # 计算综合评分
            combined_score = self._calculate_combined_score(
                channel=channel,
                effective_cost=effective_cost,
                speed_score=speed_score,
                quality_score=quality_score,
                reliability_score=reliability_score,
                request=request,
            )

            score = RoutingScore(
                channel=channel,
                score=combined_score,
                effective_cost=effective_cost,
                speed_score=speed_score,
                quality_score=quality_score,
                reliability_score=reliability_score,
                reason=self._generate_reason(channel, request.priority),
                metadata={
                    "strategy": self.name,
                    "priority": request.priority,
                    "routing_strategy": request.model_group.routing_strategy,
                },
            )

            scores.append(score)

        # 按评分降序排序
        scores.sort(key=lambda x: x.score, reverse=True)
        return scores

    def _get_speed_score(self, channel: Channel) -> float:
        """获取速度评分"""
        # 从性能评分中获取速度评分，默认为健康度评分
        performance_scores: dict[str, Any] = channel.performance_scores or {}
        return float(performance_scores.get("speed_score", channel.health_score or 0.8))

    def _get_quality_score(self, channel: Channel) -> float:
        """获取质量评分"""
        performance_scores: dict[str, Any] = channel.performance_scores or {}
        return float(performance_scores.get("quality_score", 0.8))

    def _get_reliability_score(self, channel: Channel) -> float:
        """获取可靠性评分"""
        # 基于健康度和最近错误情况计算可靠性
        base_score = float(channel.health_score or 0.8)

        # 如果最近有错误，降低评分
        if channel.last_error_at:
            if (
                not channel.last_success_at
                or channel.last_error_at > channel.last_success_at
            ):
                base_score *= 0.7  # 最近有错误，降低30%

        return min(1.0, max(0.0, base_score))

    def _calculate_combined_score(
        self,
        channel: Channel,
        effective_cost: Decimal,
        speed_score: float,
        quality_score: float,
        reliability_score: float,
        request: RoutingRequest,
    ) -> float:
        """计算综合评分"""

        # 根据模型组的路由策略计算评分
        routing_strategy: list[dict[str, Any]] = (
            request.model_group.routing_strategy or []
        )
        if not routing_strategy:
            # 默认策略：平衡成本和质量
            routing_strategy = [
                {"field": "effective_cost", "order": "asc", "weight": 0.4},
                {"field": "reliability_score", "order": "desc", "weight": 0.3},
                {"field": "speed_score", "order": "desc", "weight": 0.2},
                {"field": "quality_score", "order": "desc", "weight": 0.1},
            ]

        # 根据优先级调整权重
        adjusted_strategy = self._adjust_weights_by_priority(
            routing_strategy, request.priority
        )

        total_score = 0.0
        total_weight = 0.0

        # 归一化值映射
        values = {
            "effective_cost": float(effective_cost),
            "speed_score": speed_score,
            "quality_score": quality_score,
            "reliability_score": reliability_score,
            "health_score": float(channel.health_score or 0.8),
            "priority": float(channel.priority or 1),
            "weight": float(channel.weight or 1.0),
        }

        for strategy_item in adjusted_strategy:
            field = strategy_item.get("field", "effective_cost")
            order = strategy_item.get("order", "asc")  # asc or desc
            weight = float(strategy_item.get("weight", 1.0))

            if field not in values:
                continue

            raw_value = values[field]

            # 根据字段类型进行归一化
            if field == "effective_cost":
                # 成本越低越好，使用倒数归一化
                normalized_value = 1.0 / (1.0 + raw_value) if raw_value > 0 else 1.0
            elif field == "priority":
                # 优先级数字越小越好
                normalized_value = 1.0 / (1.0 + raw_value) if raw_value > 0 else 1.0
            else:
                # 其他评分已经是0-1之间
                normalized_value = min(1.0, max(0.0, raw_value))

            # 根据排序方向调整
            if order == "asc":
                # 对于asc (成本、优先级)，值越小越好，但归一化后已经处理
                score_contribution = normalized_value
            else:
                # 对于desc (质量、速度、可靠性)，值越大越好
                score_contribution = normalized_value

            total_score += score_contribution * weight
            total_weight += weight

        # 归一化总分
        if total_weight > 0:
            final_score = total_score / total_weight
        else:
            final_score = 0.5  # 默认中等评分

        return min(1.0, max(0.0, final_score))

    def _adjust_weights_by_priority(
        self, strategy: list[dict[str, Any]], priority: str
    ) -> list[dict[str, Any]]:
        """根据用户优先级调整权重"""

        if priority == "cost":
            # 成本优先：增加成本权重
            for item in strategy:
                if item.get("field") == "effective_cost":
                    item["weight"] = float(item.get("weight", 1.0)) * 2.0
        elif priority == "speed":
            # 速度优先：增加速度权重
            for item in strategy:
                if item.get("field") == "speed_score":
                    item["weight"] = float(item.get("weight", 1.0)) * 2.0
        elif priority == "quality":
            # 质量优先：增加质量权重
            for item in strategy:
                if item.get("field") == "quality_score":
                    item["weight"] = float(item.get("weight", 1.0)) * 2.0
        # balanced 保持原权重

        return strategy

    def _generate_reason(self, channel: Channel, priority: str) -> str:
        """生成选择理由"""
        reasons = []

        if priority == "cost":
            reasons.append("成本优化")
        elif priority == "speed":
            reasons.append("速度优化")
        elif priority == "quality":
            reasons.append("质量优化")
        else:
            reasons.append("平衡策略")

        # 添加渠道特点
        if channel.health_score and channel.health_score >= 0.9:
            reasons.append("高可靠性")
        if channel.priority and channel.priority <= 2:
            reasons.append("高优先级")

        return "，".join(reasons)
