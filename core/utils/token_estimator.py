#!/usr/bin/env python3
"""
Token预估优化模块
实现请求前token估算和模型选择优化
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logging.warning("tiktoken不可用，将使用简单估算方法")

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """任务复杂度枚举"""

    SIMPLE = "simple"  # 简单对话、翻译
    MODERATE = "moderate"  # 文档总结、问答
    COMPLEX = "complex"  # 代码生成、分析
    EXPERT = "expert"  # 专业研究、复杂推理


@dataclass
class TokenEstimate:
    """Token估算结果"""

    input_tokens: int
    estimated_output_tokens: int
    total_tokens: int
    confidence: float  # 估算置信度 (0-1)
    task_complexity: TaskComplexity


@dataclass
class ModelRecommendation:
    """模型推荐结果"""

    model_name: str
    channel_id: str
    estimated_cost: float
    estimated_time: float  # 预计响应时间(秒)
    quality_score: float  # 质量评分 (0-1)
    reason: str  # 推荐理由
    combined_score: float = 0.0  # 综合评分 (用于排序)


class TokenEstimator:
    """Token预估器"""

    def __init__(self) -> None:
        # 初始化tiktoken编码器
        self.encoders = {}
        if TIKTOKEN_AVAILABLE:
            try:
                self.encoders["gpt-4"] = tiktoken.encoding_for_model("gpt-4")
                self.encoders["gpt-3.5"] = tiktoken.encoding_for_model("gpt-3.5-turbo")
                self.encoders["default"] = tiktoken.get_encoding("cl100k_base")
            except Exception as e:
                logger.warning(f"tiktoken初始化失败: {e}")

        # 复杂度关键词映射
        self.complexity_keywords = {
            TaskComplexity.SIMPLE: [
                "hi",
                "hello",
                "translate",
                "翻译",
                "你好",
                "简单",
                "simple",
                "what",
                "how are you",
                "谢谢",
                "thank",
            ],
            TaskComplexity.MODERATE: [
                "summarize",
                "总结",
                "explain",
                "解释",
                "analyze",
                "分析",
                "compare",
                "比较",
                "list",
                "列出",
                "describe",
                "描述",
            ],
            TaskComplexity.COMPLEX: [
                "code",
                "代码",
                "programming",
                "编程",
                "algorithm",
                "算法",
                "design",
                "设计",
                "implement",
                "实现",
                "debug",
                "调试",
                "optimize",
                "优化",
                "architecture",
                "架构",
            ],
            TaskComplexity.EXPERT: [
                "research",
                "研究",
                "thesis",
                "论文",
                "academic",
                "学术",
                "scientific",
                "科学",
                "mathematical",
                "数学",
                "proof",
                "证明",
                "complex analysis",
                "复杂分析",
                "deep dive",
                "深入",
            ],
        }

        # 输出Token倍数（根据任务复杂度）
        self.output_multipliers = {
            TaskComplexity.SIMPLE: 0.5,  # 输出通常比输入短
            TaskComplexity.MODERATE: 1.0,  # 输出大致等于输入
            TaskComplexity.COMPLEX: 2.0,  # 输出通常比输入长
            TaskComplexity.EXPERT: 3.0,  # 专家级任务输出更长
        }

    def estimate_input_tokens(
        self, messages: list[dict[str, str]], model_family: str = "gpt"
    ) -> int:
        """估算输入tokens数量"""

        # 拼接所有消息内容
        full_text = ""
        for message in messages:
            content = message.get("content", "")
            role = message.get("role", "user")
            # 添加角色和格式开销
            full_text += f"{role}: {content}\n"

        if TIKTOKEN_AVAILABLE and full_text:
            try:
                # 根据模型族选择编码器
                encoder_key = "default"
                if "gpt-4" in model_family.lower():
                    encoder_key = "gpt-4"
                elif "gpt-3.5" in model_family.lower() or "gpt" in model_family.lower():
                    encoder_key = "gpt-3.5"

                encoder = self.encoders.get(encoder_key, self.encoders.get("default"))
                if encoder:
                    tokens = len(encoder.encode(full_text))
                    # 添加格式开销（约10%）
                    return int(tokens * 1.1)
            except Exception as e:
                logger.warning(f"tiktoken编码失败: {e}")

        # 回退到简单估算：中文约2字符/token，英文约4字符/token
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", full_text))
        english_chars = len(full_text) - chinese_chars

        estimated_tokens = (chinese_chars // 2) + (english_chars // 4)

        # 添加格式开销和最小值
        return max(estimated_tokens + 50, 10)

    def detect_task_complexity(self, messages: list[dict[str, str]]) -> TaskComplexity:
        """检测任务复杂度"""

        # 拼接所有消息内容用于分析
        full_content = " ".join([msg.get("content", "").lower() for msg in messages])

        # 统计各复杂度的关键词出现次数
        complexity_scores = {}
        for complexity, keywords in self.complexity_keywords.items():
            score = sum(1 for keyword in keywords if keyword in full_content)
            complexity_scores[complexity] = score

        # 找到得分最高的复杂度
        if complexity_scores:
            max_complexity = max(complexity_scores, key=complexity_scores.get)
            if complexity_scores[max_complexity] > 0:
                return max_complexity

        # 根据文本长度进一步判断
        text_length = len(full_content)
        if text_length > 2000:
            return TaskComplexity.COMPLEX
        elif text_length > 500:
            return TaskComplexity.MODERATE
        else:
            return TaskComplexity.SIMPLE

    def estimate_output_tokens(
        self, input_tokens: int, complexity: TaskComplexity
    ) -> tuple[int, float]:
        """估算输出tokens数量"""

        multiplier = self.output_multipliers[complexity]
        estimated_tokens = int(input_tokens * multiplier)

        # 设置合理的范围
        min_output = max(10, input_tokens // 10)  # 至少10个token
        max_output = input_tokens * 4  # 最多4倍输入

        estimated_tokens = max(min_output, min(estimated_tokens, max_output))

        # 计算置信度（基于复杂度和输入长度）
        confidence = 0.7  # 基础置信度
        if complexity in [TaskComplexity.SIMPLE, TaskComplexity.MODERATE]:
            confidence += 0.2
        if input_tokens < 500:  # 短输入更容易预测
            confidence += 0.1

        confidence = min(confidence, 0.95)  # 最高95%置信度

        return estimated_tokens, confidence

    def estimate_tokens(
        self, messages: list[dict[str, str]], model_family: str = "gpt"
    ) -> TokenEstimate:
        """完整的token估算"""

        # 估算输入tokens
        input_tokens = self.estimate_input_tokens(messages, model_family)

        # 检测任务复杂度
        complexity = self.detect_task_complexity(messages)

        # 估算输出tokens
        output_tokens, confidence = self.estimate_output_tokens(
            input_tokens, complexity
        )

        return TokenEstimate(
            input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            confidence=confidence,
            task_complexity=complexity,
        )


class ModelOptimizer:
    """模型优化器"""

    def __init__(self) -> None:
        # 模型能力评分（0-1，越高越好）
        self.model_quality_scores = {
            # GPT系列
            "gpt-4": 0.95,
            "gpt-4o": 0.93,
            "gpt-4-turbo": 0.92,
            "gpt-4o-mini": 0.75,
            "gpt-3.5-turbo": 0.70,
            # Claude系列
            "claude-3-opus": 0.94,
            "claude-3-sonnet": 0.85,
            "claude-3-haiku": 0.75,
            # 其他模型
            "llama-3.1-70b": 0.80,
            "llama-3.1-8b": 0.65,
            "qwen2.5-72b": 0.78,
            "qwen2.5-32b": 0.73,
            "qwen2.5-14b": 0.68,
            "qwen2.5-7b": 0.60,
        }

        # 模型速度评分（tokens/秒，用于计算响应时间）
        self.model_speed_scores = {
            "gpt-4o-mini": 150,
            "gpt-3.5-turbo": 120,
            "claude-3-haiku": 100,
            "llama-3.1-8b": 200,  # 本地模型通常更快
            "qwen2.5-7b": 180,
            "groq": 300,  # Groq特别快
        }

    def get_model_quality_score(self, model_name: str) -> float:
        """获取模型质量评分"""
        model_name_lower = model_name.lower()

        # 精确匹配
        for model_key, score in self.model_quality_scores.items():
            if model_key in model_name_lower:
                return score

        # 模糊匹配
        if "gpt-4" in model_name_lower:
            if "mini" in model_name_lower:
                return 0.75
            return 0.90
        elif "gpt-3.5" in model_name_lower or "gpt3.5" in model_name_lower:
            return 0.70
        elif "claude-3" in model_name_lower:
            if "opus" in model_name_lower:
                return 0.94
            elif "sonnet" in model_name_lower:
                return 0.85
            elif "haiku" in model_name_lower:
                return 0.75
            return 0.80
        elif "llama" in model_name_lower:
            if "70b" in model_name_lower or "72b" in model_name_lower:
                return 0.80
            elif "8b" in model_name_lower or "7b" in model_name_lower:
                return 0.60
            return 0.70
        elif "qwen" in model_name_lower:
            if any(size in model_name_lower for size in ["70b", "72b"]):
                return 0.78
            elif any(size in model_name_lower for size in ["30b", "32b"]):
                return 0.73
            elif any(size in model_name_lower for size in ["14b", "13b"]):
                return 0.68
            elif any(size in model_name_lower for size in ["7b", "8b"]):
                return 0.60
            return 0.65

        # 默认评分
        return 0.50

    def get_model_speed_score(self, model_name: str, provider: str = "") -> float:
        """获取模型速度评分（tokens/秒）"""
        model_name_lower = model_name.lower()
        provider_lower = provider.lower()

        # Provider特殊处理
        if "groq" in provider_lower:
            return 300  # Groq特别快
        elif "local" in provider_lower or "ollama" in provider_lower:
            return 200  # 本地模型通常较快

        # 模型匹配
        for model_key, speed in self.model_speed_scores.items():
            if model_key in model_name_lower:
                return speed

        # 根据模型类型估算
        if "mini" in model_name_lower or any(
            size in model_name_lower for size in ["7b", "8b"]
        ):
            return 150  # 小模型更快
        elif any(size in model_name_lower for size in ["70b", "72b"]):
            return 50  # 大模型较慢

        return 80  # 默认速度

    def calculate_estimated_cost(
        self, tokens_estimate: TokenEstimate, input_price: float, output_price: float
    ) -> float:
        """计算预估成本"""
        if input_price == 0 and output_price == 0:
            return 0.0  # 免费模型

        # 价格通常是每1M tokens的价格，转换为每token价格
        input_cost_per_token = input_price / 1000000
        output_cost_per_token = output_price / 1000000

        total_cost = (
            tokens_estimate.input_tokens * input_cost_per_token
            + tokens_estimate.estimated_output_tokens * output_cost_per_token
        )

        return total_cost

    def recommend_models(
        self,
        tokens_estimate: TokenEstimate,
        available_channels: list[dict[str, Any]],
        optimization_strategy: str = "balanced",
    ) -> list[ModelRecommendation]:
        """推荐最佳模型"""

        recommendations = []

        for channel in available_channels:
            channel_id = channel.get("id", "")
            model_name = channel.get("model_name", "")
            provider = channel.get("provider", "")

            # 获取定价信息
            input_price = channel.get("input_price", 0)
            output_price = channel.get("output_price", 0)

            # 计算预估成本
            estimated_cost = self.calculate_estimated_cost(
                tokens_estimate, input_price, output_price
            )

            # 获取质量和速度评分
            quality_score = self.get_model_quality_score(model_name)
            speed_score = self.get_model_speed_score(model_name, provider)

            # 计算预估响应时间
            estimated_time = tokens_estimate.estimated_output_tokens / max(
                speed_score, 10
            )

            # 根据任务复杂度调整质量要求
            if tokens_estimate.task_complexity == TaskComplexity.EXPERT:
                quality_score *= 1.2  # 专家任务需要更高质量
            elif tokens_estimate.task_complexity == TaskComplexity.SIMPLE:
                quality_score *= 0.9  # 简单任务可以降低质量要求

            quality_score = min(quality_score, 1.0)

            # 生成推荐理由
            reason_parts = []
            if estimated_cost == 0:
                reason_parts.append("免费")
            elif estimated_cost < 0.001:
                reason_parts.append("低成本")

            if quality_score > 0.85:
                reason_parts.append("高质量")
            elif quality_score > 0.70:
                reason_parts.append("中等质量")

            if speed_score > 150:
                reason_parts.append("快速响应")
            elif speed_score < 60:
                reason_parts.append("较慢")

            if (
                tokens_estimate.task_complexity == TaskComplexity.EXPERT
                and quality_score > 0.80
            ):
                reason_parts.append("适合复杂任务")

            reason = "、".join(reason_parts) or "通用选择"

            recommendation = ModelRecommendation(
                model_name=model_name,
                channel_id=channel_id,
                estimated_cost=estimated_cost,
                estimated_time=estimated_time,
                quality_score=quality_score,
                reason=reason,
            )

            recommendations.append(recommendation)

        # 根据优化策略排序
        if optimization_strategy == "cost_first":
            # 成本优先：免费 > 低成本 > 性价比
            recommendations.sort(
                key=lambda x: (x.estimated_cost, -x.quality_score, x.estimated_time)
            )
        elif optimization_strategy == "quality_first":
            # 质量优先：高质量 > 速度 > 成本
            recommendations.sort(
                key=lambda x: (-x.quality_score, x.estimated_time, x.estimated_cost)
            )
        elif optimization_strategy == "speed_first":
            # 速度优先：快速 > 质量 > 成本
            recommendations.sort(
                key=lambda x: (x.estimated_time, -x.quality_score, x.estimated_cost)
            )
        else:  # balanced
            # 平衡策略：综合评分
            for rec in recommendations:
                # 计算综合评分（越低越好）
                cost_score = min(rec.estimated_cost * 10000, 1.0)  # 成本归一化
                time_score = min(rec.estimated_time / 10, 1.0)  # 时间归一化
                quality_score = (
                    1.0 - rec.quality_score
                )  # 质量归一化（越高越好转换为越低越好）

                rec.combined_score = (
                    cost_score * 0.4 + time_score * 0.3 + quality_score * 0.3
                )

            recommendations.sort(key=lambda x: x.combined_score)

        return recommendations


# 全局实例
_token_estimator = None
_model_optimizer = None


def get_token_estimator() -> TokenEstimator:
    """获取Token预估器实例"""
    global _token_estimator
    if _token_estimator is None:
        _token_estimator = TokenEstimator()
    return _token_estimator


def get_model_optimizer() -> ModelOptimizer:
    """获取模型优化器实例"""
    global _model_optimizer
    if _model_optimizer is None:
        _model_optimizer = ModelOptimizer()
    return _model_optimizer
