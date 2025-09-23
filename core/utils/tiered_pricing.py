#!/usr/bin/env python3
"""
阶梯定价计算器
支持豆包模型的复杂阶梯定价逻辑
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class PricingResult:
    """定价计算结果"""

    input_price: float
    output_price: float
    tier_info: str
    is_batch: bool = False
    cache_hit_price: Optional[float] = None
    cache_storage_price: Optional[float] = None


class TieredPricingCalculator:
    """阶梯定价计算器"""

    def __init__(self, pricing_config_path: str = None):
        """初始化定价计算器"""
        if pricing_config_path is None:
            pricing_config_path = "cache/doubao_pricing_accurate.json"

        self.config_path = Path(pricing_config_path)
        self.pricing_data = self._load_pricing_config()

    def _load_pricing_config(self) -> dict[str, Any]:
        """加载定价配置"""
        try:
            if not self.config_path.exists():
                logger.error(f"定价配置文件不存在: {self.config_path}")
                return {"models": {}}

            with open(self.config_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载定价配置失败: {e}")
            return {"models": {}}

    def get_model_pricing(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int = 0,
        use_batch: bool = False,
    ) -> Optional[PricingResult]:
        """
        获取模型定价

        Args:
            model_name: 模型名称
            input_tokens: 输入token数量
            output_tokens: 输出token数量
            use_batch: 是否使用批量推理价格

        Returns:
            PricingResult 或 None
        """
        model_config = self.pricing_data.get("models", {}).get(model_name)
        if not model_config:
            logger.warning(f"模型 {model_name} 未找到定价配置")
            return None

        pricing_type = model_config.get("pricing_type", "fixed")

        if pricing_type == "fixed":
            return self._calculate_fixed_pricing(model_config, use_batch)
        elif pricing_type == "tiered":
            return self._calculate_tiered_pricing(model_config, input_tokens, use_batch)
        elif pricing_type == "tiered_complex":
            return self._calculate_complex_tiered_pricing(
                model_config, input_tokens, output_tokens, use_batch
            )
        else:
            logger.error(f"不支持的定价类型: {pricing_type}")
            return None

    def _calculate_fixed_pricing(
        self, model_config: dict[str, Any], use_batch: bool
    ) -> PricingResult:
        """计算固定定价"""
        pricing_key = "batch_pricing" if use_batch else "online_pricing"
        pricing_config = model_config.get(
            pricing_key, model_config.get("online_pricing", {})
        )

        return PricingResult(
            input_price=pricing_config.get("input_price", 0.0),
            output_price=pricing_config.get("output_price", 0.0),
            tier_info="固定定价",
            is_batch=use_batch,
        )

    def _calculate_tiered_pricing(
        self, model_config: dict[str, Any], input_tokens: int, use_batch: bool
    ) -> Optional[PricingResult]:
        """计算阶梯定价（基于输入长度）"""
        tiered_config = model_config.get("tiered_pricing", {})
        tiers = tiered_config.get("tiers", [])

        # 找到匹配的价格档位
        for tier in tiers:
            input_min = tier.get("input_min", 0)
            input_max = tier.get("input_max")

            if input_max is None:  # 无上限
                if input_tokens >= input_min:
                    return self._create_pricing_result_from_tier(tier, use_batch)
            else:
                if input_min <= input_tokens <= input_max:
                    return self._create_pricing_result_from_tier(tier, use_batch)

        logger.warning(f"未找到匹配的价格档位，输入长度: {input_tokens}")
        return None

    def _calculate_complex_tiered_pricing(
        self,
        model_config: dict[str, Any],
        input_tokens: int,
        output_tokens: int,
        use_batch: bool,
    ) -> Optional[PricingResult]:
        """计算复杂阶梯定价（基于输入+输出长度）"""
        tiered_config = model_config.get("tiered_pricing", {})
        tiers = tiered_config.get("tiers", [])

        # 找到匹配的价格档位
        for tier in tiers:
            if self._matches_complex_condition(tier, input_tokens, output_tokens):
                return self._create_pricing_result_from_tier(tier, use_batch)

        logger.warning(
            f"未找到匹配的复杂价格档位，输入: {input_tokens}, 输出: {output_tokens}"
        )
        return None

    def _matches_complex_condition(
        self, tier: dict[str, Any], input_tokens: int, output_tokens: int
    ) -> bool:
        """检查是否匹配复杂条件"""
        # 检查输入长度条件
        input_min = tier.get("input_min", 0)
        input_max = tier.get("input_max")

        input_match = input_tokens >= input_min
        if input_max is not None:
            input_match = input_match and input_tokens <= input_max

        if not input_match:
            return False

        # 检查输出长度条件（如果存在）
        output_min = tier.get("output_min")
        output_max = tier.get("output_max")

        if output_min is None and output_max is None:
            # 没有输出长度限制
            return True

        if output_min is not None:
            if output_tokens < output_min:
                return False

        if output_max is not None:
            if output_tokens > output_max:
                return False

        return True

    def _create_pricing_result_from_tier(
        self, tier: dict[str, Any], use_batch: bool
    ) -> PricingResult:
        """从价格档位创建定价结果"""
        pricing_key = "batch_pricing" if use_batch else "online_pricing"
        pricing_config = tier.get(pricing_key, tier.get("online_pricing", {}))

        return PricingResult(
            input_price=pricing_config.get("input_price", 0.0),
            output_price=pricing_config.get("output_price", 0.0),
            tier_info=tier.get("condition", "未知档位"),
            is_batch=use_batch,
        )

    def calculate_cost(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        use_batch: bool = False,
    ) -> Optional[tuple[float, str]]:
        """
        计算总成本

        Returns:
            (总成本, 档位信息) 或 None
        """
        pricing_result = self.get_model_pricing(
            model_name, input_tokens, output_tokens, use_batch
        )
        if not pricing_result:
            return None

        # 转换为千token单价
        input_cost = (input_tokens / 1000000) * pricing_result.input_price
        output_cost = (output_tokens / 1000000) * pricing_result.output_price
        total_cost = input_cost + output_cost

        cost_info = f"{pricing_result.tier_info} - 输入:{input_cost:.6f}元 + 输出:{output_cost:.6f}元"

        return total_cost, cost_info

    def get_model_info(self, model_name: str) -> Optional[dict[str, Any]]:
        """获取模型基本信息"""
        return self.pricing_data.get("models", {}).get(model_name)

    def list_supported_models(self) -> list[str]:
        """获取支持的模型列表"""
        return list(self.pricing_data.get("models", {}).keys())

    def get_pricing_summary(self, model_name: str) -> Optional[dict[str, Any]]:
        """获取模型定价摘要"""
        model_config = self.pricing_data.get("models", {}).get(model_name)
        if not model_config:
            return None

        pricing_type = model_config.get("pricing_type", "fixed")
        summary = {
            "model_name": model_name,
            "display_name": model_config.get("display_name"),
            "pricing_type": pricing_type,
            "category": model_config.get("category"),
            "context_length": model_config.get("context_length"),
            "free_quota": model_config.get("free_quota"),
            "capabilities": model_config.get("capabilities", []),
        }

        if pricing_type == "fixed":
            summary["online_pricing"] = model_config.get("online_pricing")
            summary["batch_pricing"] = model_config.get("batch_pricing")
        else:
            summary["tiered_pricing"] = model_config.get("tiered_pricing", {})

        return summary


# 全局实例
_pricing_calculator: Optional[TieredPricingCalculator] = None


def get_pricing_calculator() -> TieredPricingCalculator:
    """获取全局定价计算器实例"""
    global _pricing_calculator
    if _pricing_calculator is None:
        _pricing_calculator = TieredPricingCalculator()
    return _pricing_calculator


def calculate_doubao_cost(
    model_name: str, input_tokens: int, output_tokens: int = 0, use_batch: bool = False
) -> Optional[tuple[float, str]]:
    """便捷函数：计算豆包模型成本"""
    calculator = get_pricing_calculator()
    return calculator.calculate_cost(model_name, input_tokens, output_tokens, use_batch)


if __name__ == "__main__":
    # 测试代码
    calculator = TieredPricingCalculator()

    # 测试固定定价
    print("=== 固定定价测试 ===")
    cost, info = calculator.calculate_cost("deepseek-v3.1", 10000, 5000)
    print(f"deepseek-v3.1: {cost:.6f}元 ({info})")

    # 测试阶梯定价
    print("\n=== 阶梯定价测试 ===")
    test_cases = [
        (20000, 5000),  # 第一档
        (50000, 5000),  # 第二档
        (150000, 5000),  # 第三档
    ]

    for input_tokens, output_tokens in test_cases:
        cost, info = calculator.calculate_cost(
            "doubao-seed-1.6-vision", input_tokens, output_tokens
        )
        print(
            f"doubao-seed-1.6-vision ({input_tokens//1000}k输入): {cost:.6f}元 ({info})"
        )

    # 测试复杂阶梯定价
    print("\n=== 复杂阶梯定价测试 ===")
    complex_cases = [
        (20000, 100),  # 低输出档
        (20000, 5000),  # 高输出档
    ]

    for input_tokens, output_tokens in complex_cases:
        cost, info = calculator.calculate_cost(
            "doubao-seed-1.6", input_tokens, output_tokens
        )
        print(
            f"doubao-seed-1.6 ({input_tokens//1000}k输入, {output_tokens}输出): {cost:.6f}元 ({info})"
        )
