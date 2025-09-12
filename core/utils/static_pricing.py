#!/usr/bin/env python3
"""
动态2层定价系统加载器

实现完全动态的渠道定价文件加载，支持任意渠道扩展。
架构：第1层渠道专属定价 → 第2层OpenRouter基准定价回退
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .tiered_pricing import get_pricing_calculator, TieredPricingCalculator

logger = logging.getLogger(__name__)


@dataclass
class StaticPricingResult:
    """静态定价结果"""

    input_price: float
    output_price: float
    provider: str
    model_id: str
    pricing_info: str
    is_free: bool = False


class UnifiedStaticPricingLoader:
    """动态2层定价系统加载器"""

    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.pricing_dir = Path("config/pricing")

        # 第2层：OpenRouter基准数据库
        self.base_pricing_file = self.pricing_dir / "base_pricing_unified.json"
        self.base_pricing_data = self._load_base_pricing()

        # 第1层：渠道专属定价缓存（动态加载）
        self.channel_pricing_cache: Dict[str, Dict[str, Any]] = {}

        # 特殊处理器（豆包阶梯定价）
        self.doubao_calculator = get_pricing_calculator()

    def _load_base_pricing(self) -> Dict[str, Any]:
        """加载第2层OpenRouter基准定价数据"""
        try:
            if not self.base_pricing_file.exists():
                logger.warning(
                    f"OpenRouter基准定价文件不存在: {self.base_pricing_file}"
                )
                return {"models": {}}

            # 导入统一格式加载器
            project_root = Path(__file__).parent.parent.parent
            sys.path.insert(0, str(project_root))

            from core.pricing.unified_format import UnifiedPricingFile

            unified_data = UnifiedPricingFile.load_from_file(self.base_pricing_file)
            logger.info(f"加载OpenRouter基准定价: {len(unified_data.models)} 个模型")
            return {
                "models": unified_data.models,
                "metadata": {
                    "provider": unified_data.provider,
                    "source": unified_data.source,
                    "description": unified_data.description,
                },
            }

        except Exception as e:
            logger.error(f"加载OpenRouter基准定价失败: {e}")
            return {"models": {}}

    def get_model_pricing(
        self,
        provider_name: str,
        model_name: str,
        input_tokens: int = 10000,
        output_tokens: int = 2000,
    ) -> Optional[StaticPricingResult]:
        """2层定价系统统一入口"""

        # 第1层：优先查询渠道专属定价
        result = self._query_channel_pricing(
            provider_name, model_name, input_tokens, output_tokens
        )
        if result:
            return result

        # 第2层：回退策略
        # 豆包特殊回退：优先尝试阶梯定价计算器
        if "doubao" in provider_name.lower() or "bytedance" in provider_name.lower():
            result = self._query_doubao_pricing(model_name, input_tokens, output_tokens)
            if result:
                result.pricing_info += " (阶梯定价回退)"
                return result
        
        # 通用回退：OpenRouter基准定价
        result = self._query_base_pricing(model_name)
        if result:
            result.pricing_info += " (基准定价回退)"
            return result

        return None

    def _query_channel_pricing(
        self, provider_name: str, model_name: str, input_tokens: int, output_tokens: int
    ) -> Optional[StaticPricingResult]:
        """第1层：渠道专属定价查询"""

        provider_lower = provider_name.lower()

        # 通用处理：动态文件名查询（优先统一格式文件）
        # 尝试多种文件名格式
        possible_files = [
            self.pricing_dir / f"{provider_lower}_price.json",
            self.pricing_dir / f"{provider_lower}_pricing.json",
            self.pricing_dir / f"{provider_lower}_unified.json",
            self.pricing_dir / f"{provider_lower}.json",
        ]

        channel_file = None
        for file_path in possible_files:
            if file_path.exists():
                channel_file = file_path
                break

        if not channel_file:
            logger.debug(
                f"渠道专属定价文件不存在: {provider_lower} (尝试了 {len(possible_files)} 个文件名)"
            )
            return None

        # 动态加载渠道定价数据
        pricing_data = self._load_channel_pricing(provider_lower, channel_file)
        if not pricing_data:
            return None

        return self._extract_pricing_from_unified_format(
            pricing_data, model_name, provider_lower
        )

    def _load_channel_pricing(
        self, provider_key: str, file_path: Path
    ) -> Dict[str, Any]:
        """动态加载渠道定价数据（带缓存）"""
        if provider_key in self.channel_pricing_cache:
            return self.channel_pricing_cache[provider_key]

        try:
            if not file_path.exists():
                return {}

            # 统一格式加载
            project_root = Path(__file__).parent.parent.parent
            sys.path.insert(0, str(project_root))
            from core.pricing.unified_format import UnifiedPricingFile

            unified_data = UnifiedPricingFile.load_from_file(file_path)

            pricing_data = {
                "models": unified_data.models,
                "metadata": {
                    "provider": unified_data.provider,
                    "source": unified_data.source,
                    "description": unified_data.description,
                },
            }

            # 缓存数据
            self.channel_pricing_cache[provider_key] = pricing_data
            logger.info(
                f"加载渠道定价: {provider_key} ({len(unified_data.models)} 个模型) - {file_path.name}"
            )

            return pricing_data

        except Exception as e:
            logger.error(f"加载渠道定价失败 {file_path}: {e}")
            return {}

    def _extract_pricing_from_unified_format(
        self, pricing_data: Dict[str, Any], model_name: str, provider_name: str
    ) -> Optional[StaticPricingResult]:
        """从统一格式中提取定价信息（消除重复代码）"""

        models = pricing_data.get("models", {})
        model_data = models.get(model_name)

        # 模糊匹配
        if not model_data:
            for cached_model, data in models.items():
                if (
                    model_name.lower() in cached_model.lower()
                    or cached_model.lower() in model_name.lower()
                ):
                    model_data = data
                    break

        if not model_data:
            return None

        # 统一价格提取逻辑
        if hasattr(model_data, "pricing") and model_data.pricing:
            input_price = model_data.pricing.prompt * 1000  # USD/1K tokens
            output_price = model_data.pricing.completion * 1000
        else:
            pricing = (
                getattr(model_data, "pricing", {})
                if hasattr(model_data, "pricing")
                else model_data.get("pricing", {})
            )
            if isinstance(pricing, dict):
                input_price = pricing.get("prompt", 0.0) * 1000
                output_price = pricing.get("completion", 0.0) * 1000
            else:
                input_price = 0.0
                output_price = 0.0

        # 获取类别
        category = (
            model_data.category.value
            if hasattr(model_data, "category")
            else model_data.get("category", "未知")
        )

        return StaticPricingResult(
            input_price=input_price,
            output_price=output_price,
            provider=provider_name,
            model_id=model_name,
            pricing_info=f"渠道专属 - {category}",
            is_free=(input_price == 0.0 and output_price == 0.0),
        )

    def _query_doubao_pricing(
        self, model_name: str, input_tokens: int, output_tokens: int
    ) -> Optional[StaticPricingResult]:
        """豆包阶梯定价查询（特殊处理器）"""
        try:
            # 使用阶梯定价计算器
            pricing_result = self.doubao_calculator.get_model_pricing(
                model_name, input_tokens, output_tokens
            )

            if not pricing_result:
                return None

            return StaticPricingResult(
                input_price=pricing_result.input_price,
                output_price=pricing_result.output_price,
                provider="doubao",
                model_id=model_name,
                pricing_info=f"阶梯定价 - {pricing_result.tier_info}",
                is_free=(
                    pricing_result.input_price == 0.0
                    and pricing_result.output_price == 0.0
                ),
            )

        except Exception as e:
            logger.error(f"获取豆包定价失败 ({model_name}): {e}")
            return None

    def _query_base_pricing(self, model_name: str) -> Optional[StaticPricingResult]:
        """第2层：OpenRouter基准定价查询"""
        return self._extract_pricing_from_unified_format(
            self.base_pricing_data, model_name, "openrouter_base"
        )

    def list_siliconflow_models(self) -> Dict[str, Any]:
        """列出SiliconFlow模型（兼容性方法）"""
        siliconflow_data = self._load_channel_pricing(
            "siliconflow", self.pricing_dir / "siliconflow_unified.json"
        )
        return siliconflow_data.get("models", {})

    def list_base_pricing_models(self) -> Dict[str, Any]:
        """列出所有基础定价模型"""
        return self.base_pricing_data.get("models", {})

    def list_doubao_models(self) -> list:
        """列出所有豆包模型"""
        return self.doubao_calculator.list_supported_models()

    def get_free_models(
        self, provider: Optional[str] = None
    ) -> Dict[str, StaticPricingResult]:
        """获取免费模型列表"""
        free_models = {}

        # 检查特定渠道或所有渠道
        if provider:
            provider_lower = provider.lower()
            pricing_data = self._load_channel_pricing(
                provider_lower, self.pricing_dir / f"{provider_lower}_unified.json"
            )

            if pricing_data:
                for model_name, model_data in pricing_data.get("models", {}).items():
                    try:
                        if hasattr(model_data, "pricing") and model_data.pricing:
                            is_free = (
                                model_data.pricing.prompt == 0.0
                                and model_data.pricing.completion == 0.0
                            )
                        else:
                            pricing = (
                                getattr(model_data, "pricing", {})
                                if hasattr(model_data, "pricing")
                                else model_data.get("pricing", {})
                            )
                            if isinstance(pricing, dict):
                                is_free = (
                                    pricing.get("prompt", 0.0) == 0.0
                                    and pricing.get("completion", 0.0) == 0.0
                                )
                            else:
                                is_free = False

                        if is_free:
                            result = self._extract_pricing_from_unified_format(
                                pricing_data, model_name, provider_lower
                            )
                            if result:
                                free_models[f"{provider_lower}:{model_name}"] = result
                    except Exception as e:
                        logger.debug(f"检查免费模型失败 {model_name}: {e}")
                        continue

        # 豆包免费模型
        if provider is None or "doubao" in provider.lower():
            for model_name in self.doubao_calculator.list_supported_models():
                result = self._query_doubao_pricing(model_name, 10000, 2000)
                if result and result.is_free:
                    free_models[f"doubao:{model_name}"] = result

        return free_models


# 保持兼容性 - 使用统一格式加载器
StaticPricingLoader = UnifiedStaticPricingLoader

# 全局实例
_static_pricing_loader: Optional[UnifiedStaticPricingLoader] = None


def get_static_pricing_loader() -> UnifiedStaticPricingLoader:
    """获取全局动态定价加载器实例"""
    global _static_pricing_loader
    if _static_pricing_loader is None:
        _static_pricing_loader = UnifiedStaticPricingLoader()
    return _static_pricing_loader


def get_provider_pricing(
    provider_name: str,
    model_name: str,
    input_tokens: int = 10000,
    output_tokens: int = 2000,
) -> Optional[Tuple[float, float, str]]:
    """便捷函数：获取提供商模型定价"""
    loader = get_static_pricing_loader()
    result = loader.get_model_pricing(
        provider_name, model_name, input_tokens, output_tokens
    )

    if result:
        return (
            result.input_price / 1000000,  # 转换为每token价格
            result.output_price / 1000000,
            result.pricing_info,
        )
    return None


if __name__ == "__main__":
    # 测试代码
    loader = UnifiedStaticPricingLoader()

    # 测试动态加载
    print("=== 动态2层定价系统测试 ===")
    test_cases = [
        ("siliconflow", "Qwen/Qwen2.5-7B-Instruct"),
        ("doubao", "doubao-pro-4k"),
        ("openai", "gpt-4o-mini"),
        ("unknown_provider", "some-model"),
    ]

    for provider, model in test_cases:
        result = loader.get_model_pricing(provider, model)
        if result:
            print(
                f"{provider}/{model}: 输入 {result.input_price} USD/K tokens, 输出 {result.output_price} USD/K tokens ({result.pricing_info})"
            )
        else:
            print(f"{provider}/{model}: 未找到定价")

    # 测试免费模型
    print("\n=== 免费模型列表 ===")
    free_models = loader.get_free_models()
    print(f"共找到 {len(free_models)} 个免费模型")
    for model_key, result in list(free_models.items())[:5]:  # 显示前5个
        print(f"{model_key}: {result.pricing_info}")
