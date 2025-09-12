# -*- coding: utf-8 -*-
"""
渠道评分器
从json_router.py中提取的渠道评分功能
"""
import logging
from typing import List, Dict, Any, Optional

from .models import ChannelCandidate, RoutingRequest, RoutingScore
from ..config_models import Channel

logger = logging.getLogger(__name__)


class ChannelScorer:
    """渠道评分器"""

    def __init__(self, config_loader, model_analyzer):
        self.config_loader = config_loader
        self.model_analyzer = model_analyzer

    async def score_channels(
        self, channels: List[ChannelCandidate], request: RoutingRequest
    ) -> List[RoutingScore]:
        """对渠道进行评分和排序"""
        if not channels:
            return []

        logger.info(f"📊 SCORING: Processing {len(channels)} channels")

        # 选择评分策略
        if len(channels) <= 10:
            return await self._score_channels_individual(channels, request)
        else:
            return await self._score_channels_batch(channels, request)

    async def _score_channels_individual(
        self, channels: List[ChannelCandidate], request: RoutingRequest
    ) -> List[RoutingScore]:
        """单个渠道评分方式（用于小数量渠道）"""
        logger.info(
            f"📊 SCORING: Using individual scoring for {len(channels)} channels"
        )

        scored_channels = []
        strategy = self._get_routing_strategy(request)

        for candidate in channels:
            channel = candidate.channel
            cost_score = self._calculate_cost_score(channel, request)
            speed_score = self._calculate_speed_score(channel)
            quality_score = self._calculate_quality_score(
                channel, candidate.matched_model
            )
            reliability_score = self._calculate_reliability_score(channel)
            parameter_score = self._calculate_parameter_score(
                channel, candidate.matched_model
            )
            context_score = self._calculate_context_score(
                channel, candidate.matched_model
            )
            free_score = self._calculate_free_score(channel, candidate.matched_model)
            local_score = self._calculate_local_score(channel, candidate.matched_model)

            total_score = self._calculate_total_score(
                strategy,
                cost_score,
                speed_score,
                quality_score,
                reliability_score,
                parameter_score,
                context_score,
                free_score,
                local_score,
            )

            scored_channels.append(
                RoutingScore(
                    channel=channel,
                    total_score=total_score,
                    cost_score=cost_score,
                    speed_score=speed_score,
                    quality_score=quality_score,
                    reliability_score=reliability_score,
                    reason=f"cost:{cost_score:.2f} speed:{speed_score:.2f} quality:{quality_score:.2f} reliability:{reliability_score:.2f}",
                    matched_model=candidate.matched_model,
                    parameter_score=parameter_score,
                    context_score=context_score,
                    free_score=free_score,
                )
            )

        scored_channels = self._hierarchical_sort(scored_channels)

        logger.info(
            f"🏆 INDIVIDUAL SCORING RESULT: Processed {len(scored_channels)} channels"
        )
        return scored_channels

    async def _score_channels_batch(
        self, channels: List[ChannelCandidate], request: RoutingRequest
    ) -> List[RoutingScore]:
        """批量渠道评分方式（用于大数量渠道）"""
        logger.info(f"📊 SCORING: Using batch scoring for {len(channels)} channels")

        # 这里可以实现批量评分优化
        # 暂时使用个别评分方式
        return await self._score_channels_individual(channels, request)

    def _get_routing_strategy(self, request: RoutingRequest) -> List[Dict[str, Any]]:
        """获取路由策略"""
        strategy_name = request.strategy or "balanced"

        strategies = {
            "cost_first": [
                {"metric": "cost", "weight": 0.4, "direction": "desc"},
                {"metric": "quality", "weight": 0.3, "direction": "asc"},
                {"metric": "reliability", "weight": 0.2, "direction": "asc"},
                {"metric": "speed", "weight": 0.1, "direction": "asc"},
            ],
            "quality_first": [
                {"metric": "quality", "weight": 0.4, "direction": "asc"},
                {"metric": "reliability", "weight": 0.3, "direction": "asc"},
                {"metric": "speed", "weight": 0.2, "direction": "asc"},
                {"metric": "cost", "weight": 0.1, "direction": "desc"},
            ],
            "speed_first": [
                {"metric": "speed", "weight": 0.4, "direction": "asc"},
                {"metric": "reliability", "weight": 0.3, "direction": "asc"},
                {"metric": "quality", "weight": 0.2, "direction": "asc"},
                {"metric": "cost", "weight": 0.1, "direction": "desc"},
            ],
            "balanced": [
                {"metric": "quality", "weight": 0.25, "direction": "asc"},
                {"metric": "cost", "weight": 0.25, "direction": "desc"},
                {"metric": "reliability", "weight": 0.25, "direction": "asc"},
                {"metric": "speed", "weight": 0.25, "direction": "asc"},
            ],
        }

        return strategies.get(strategy_name, strategies["balanced"])

    def _calculate_cost_score(self, channel: Channel, request: RoutingRequest) -> float:
        """计算成本评分"""
        # 简化的成本评分实现
        try:
            if hasattr(channel, "cost_per_token") and channel.cost_per_token:
                input_cost = channel.cost_per_token.get("input", 0.0)
                output_cost = channel.cost_per_token.get("output", 0.0)
                avg_cost = (input_cost + output_cost) / 2

                # 成本越低分数越高
                if avg_cost <= 0.001:
                    return 100.0
                elif avg_cost <= 0.01:
                    return 80.0
                elif avg_cost <= 0.05:
                    return 60.0
                else:
                    return 40.0
            return 70.0  # 默认中等评分
        except Exception:
            return 70.0

    def _calculate_speed_score(self, channel: Channel) -> float:
        """计算速度评分"""
        # 简化的速度评分实现
        try:
            if hasattr(channel, "performance") and channel.performance:
                latency = channel.performance.get("avg_latency_ms", 1000)
                if latency <= 500:
                    return 100.0
                elif latency <= 1000:
                    return 80.0
                elif latency <= 2000:
                    return 60.0
                else:
                    return 40.0
            return 70.0  # 默认中等评分
        except Exception:
            return 70.0

    def _calculate_quality_score(
        self, channel: Channel, matched_model: Optional[str] = None
    ) -> float:
        """计算质量评分"""
        # 简化的质量评分实现
        try:
            model_name = matched_model or channel.model_name
            if not model_name:
                return 50.0

            # 基于模型名称的简单质量评估
            model_lower = model_name.lower()
            if any(
                keyword in model_lower
                for keyword in ["gpt-4", "claude-3", "gemini-pro"]
            ):
                return 95.0
            elif any(
                keyword in model_lower for keyword in ["gpt-3.5", "claude-2", "gemini"]
            ):
                return 85.0
            elif any(keyword in model_lower for keyword in ["llama", "qwen", "yi"]):
                return 75.0
            else:
                return 65.0
        except Exception:
            return 65.0

    def _calculate_reliability_score(self, channel: Channel) -> float:
        """计算可靠性评分"""
        try:
            # 获取健康评分
            health_scores = self.config_loader.runtime_state.health_scores
            health_score = health_scores.get(channel.id, 1.0)
            return health_score * 100.0
        except Exception:
            return 80.0

    def _calculate_parameter_score(
        self, channel: Channel, matched_model: Optional[str] = None
    ) -> float:
        """计算参数量评分"""
        # 简化实现
        return 70.0

    def _calculate_context_score(
        self, channel: Channel, matched_model: Optional[str] = None
    ) -> float:
        """计算上下文评分"""
        # 简化实现
        return 70.0

    def _calculate_free_score(
        self, channel: Channel, matched_model: Optional[str] = None
    ) -> float:
        """计算免费评分"""
        # 简化实现
        return 50.0

    def _calculate_local_score(
        self, channel: Channel, matched_model: Optional[str] = None
    ) -> float:
        """计算本地评分"""
        # 简化实现
        return 50.0

    def _calculate_total_score(
        self,
        strategy: List[Dict[str, Any]],
        cost_score: float,
        speed_score: float,
        quality_score: float,
        reliability_score: float,
        parameter_score: float,
        context_score: float,
        free_score: float,
        local_score: float,
    ) -> float:
        """计算总评分"""
        scores = {
            "cost": cost_score,
            "speed": speed_score,
            "quality": quality_score,
            "reliability": reliability_score,
            "parameter": parameter_score,
            "context": context_score,
            "free": free_score,
            "local": local_score,
        }

        total_score = 0.0
        for metric_config in strategy:
            metric = metric_config["metric"]
            weight = metric_config["weight"]
            direction = metric_config["direction"]

            score = scores.get(metric, 70.0)
            if direction == "desc":
                score = 100.0 - score  # 反转分数

            total_score += score * weight

        return min(100.0, max(0.0, total_score))

    def _hierarchical_sort(
        self, scored_channels: List[RoutingScore]
    ) -> List[RoutingScore]:
        """分层排序"""
        # 简化的排序实现
        return sorted(scored_channels, key=lambda x: x.total_score, reverse=True)
