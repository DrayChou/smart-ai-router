#!/usr/bin/env python3
"""
多平台定价格式转换器
将各平台的定价格式转换为统一格式
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .unified_format import (
    Architecture,
    DataSource,
    ModelCapabilityInference,
    ModelCategory,
    Pricing,
    TopProvider,
    UnifiedModelData,
    UnifiedPricingFile,
)

logger = logging.getLogger(__name__)


class BaseFormatConverter(ABC):
    """格式转换器基类"""

    def __init__(self, source_platform: str):
        self.source_platform = source_platform
        self.capability_inference = ModelCapabilityInference()

    @abstractmethod
    def convert_to_unified(self, source_data: dict[str, Any]) -> UnifiedPricingFile:
        """转换为统一格式"""
        pass

    def _extract_parameter_count(self, model_name: str) -> Optional[int]:
        """提取参数数量"""
        patterns = [
            r"(\d+(?:\.\d+)?)[bB]",  # 7b, 70B, 1.5B
            r"(\d+(?:\.\d+)?)[-_]?[bB]",  # 7-B, 7_b
            r"(\d+(?:\.\d+)?)billion",
            r"(\d+(?:\.\d+)?)B[-_]?param",
        ]

        for pattern in patterns:
            match = re.search(pattern, model_name, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                return int(value * 1e9) if value < 1000 else int(value * 1e6)
        return None

    def _extract_context_length_from_name(self, model_name: str) -> Optional[int]:
        """从名称提取上下文长度"""
        patterns = [
            r"(\d+)[kK]",  # 32k, 128K
            r"(\d+)[-_]?[kK][-_]?(?:context|ctx)",
            r"(\d+)[mM]",  # 1m, 2M (million tokens)
        ]

        for pattern in patterns:
            match = re.search(pattern, model_name, re.IGNORECASE)
            if match:
                value = int(match.group(1))
                # 判断是K还是M
                if "m" in match.group(0).lower():
                    return value * 1000000  # M tokens
                else:
                    return value * 1000  # K tokens
        return None


class OpenRouterConverter(BaseFormatConverter):
    """OpenRouter格式转换器"""

    def __init__(self) -> None:
        super().__init__("openrouter")

    def convert_to_unified(self, source_data: dict[str, Any]) -> UnifiedPricingFile:
        """转换OpenRouter格式到统一格式"""
        unified_file = UnifiedPricingFile(
            provider="openrouter",
            source="openrouter_api",
            description="OpenRouter官方API数据，包含完整的模型元数据",
        )

        models_data = source_data.get("models", {})

        for model_id, model_info in models_data.items():
            try:
                unified_model = self._convert_single_model(model_id, model_info)
                if unified_model:
                    unified_file.models[model_id] = unified_model
            except Exception as e:
                logger.warning(f"转换OpenRouter模型失败 {model_id}: {e}")

        logger.info(f"OpenRouter转换完成: {len(unified_file.models)}个模型")
        return unified_file

    def _convert_single_model(
        self, model_id: str, model_info: dict[str, Any]
    ) -> Optional[UnifiedModelData]:
        """转换单个模型"""
        raw_data = model_info.get("raw_data", {})

        # 基本信息
        unified_model = UnifiedModelData(
            id=model_id,
            canonical_slug=raw_data.get("canonical_slug"),
            hugging_face_id=raw_data.get("hugging_face_id"),
            name=raw_data.get("name", model_id),
            parameter_count=model_info.get("parameter_count"),
            context_length=model_info.get("context_length")
            or raw_data.get("context_length"),
            created=raw_data.get("created"),
            description=raw_data.get("description", ""),
            data_source=DataSource.OPENROUTER,
            last_updated=datetime.now(),
        )

        # 架构信息
        architecture_data = raw_data.get("architecture", {})
        if architecture_data:
            unified_model.architecture = Architecture(
                modality=architecture_data.get("modality", "text->text"),
                input_modalities=architecture_data.get("input_modalities", ["text"]),
                output_modalities=architecture_data.get("output_modalities", ["text"]),
                tokenizer=architecture_data.get("tokenizer"),
                instruct_type=architecture_data.get("instruct_type"),
            )

        # 定价信息
        pricing_data = raw_data.get("pricing", {})
        if pricing_data:
            unified_model.pricing = Pricing(
                prompt=float(pricing_data.get("prompt", 0)),
                completion=float(pricing_data.get("completion", 0)),
                request=float(pricing_data.get("request", 0)),
                image=float(pricing_data.get("image", 0)),
                web_search=float(pricing_data.get("web_search", 0)),
                internal_reasoning=float(pricing_data.get("internal_reasoning", 0)),
                confidence_level=1.0,  # OpenRouter数据最可信
            )

        # 顶级提供商信息
        top_provider_data = raw_data.get("top_provider", {})
        if top_provider_data:
            unified_model.top_provider = TopProvider(
                context_length=top_provider_data.get("context_length"),
                max_completion_tokens=top_provider_data.get("max_completion_tokens"),
                is_moderated=top_provider_data.get("is_moderated", False),
            )

        # 推断能力和分类
        unified_model.capabilities = (
            self.capability_inference.infer_capabilities_from_name(model_id)
        )
        unified_model.category = self.capability_inference.infer_category_from_params(
            unified_model.parameter_count, unified_model.context_length
        )

        return unified_model


class SiliconFlowConverter(BaseFormatConverter):
    """SiliconFlow格式转换器"""

    def __init__(self) -> None:
        super().__init__("siliconflow")
        self.exchange_rate = 0.14  # 人民币到美元汇率

    def convert_to_unified(self, source_data: dict[str, Any]) -> UnifiedPricingFile:
        """转换SiliconFlow格式到统一格式"""
        unified_file = UnifiedPricingFile(
            provider="siliconflow",
            source="siliconflow_html_parsed",
            description="SiliconFlow HTML解析数据，包含127个真实模型信息",
        )

        models_data = source_data.get("models", {})
        exchange_rate = source_data.get("exchange_rate_to_usd", self.exchange_rate)

        for model_id, model_info in models_data.items():
            try:
                unified_model = self._convert_single_model(
                    model_id, model_info, exchange_rate
                )
                if unified_model:
                    unified_file.models[model_id] = unified_model
            except Exception as e:
                logger.warning(f"转换SiliconFlow模型失败 {model_id}: {e}")

        logger.info(f"SiliconFlow转换完成: {len(unified_file.models)}个模型")
        return unified_file

    def _convert_single_model(
        self, model_id: str, model_info: dict[str, Any], exchange_rate: float
    ) -> Optional[UnifiedModelData]:
        """转换单个模型"""
        # 价格转换: 元/M tokens → USD/token
        input_price_yuan_per_m = model_info.get("input_price_per_m", 0.0)
        output_price_yuan_per_m = model_info.get("output_price_per_m", 0.0)

        input_price_usd_per_token = (input_price_yuan_per_m * exchange_rate) / 1_000_000
        output_price_usd_per_token = (
            output_price_yuan_per_m * exchange_rate
        ) / 1_000_000

        # 基本信息
        unified_model = UnifiedModelData(
            id=model_id,
            name=model_info.get("display_name", model_id),
            parameter_count=self._extract_parameter_count(model_id),
            context_length=model_info.get("context_length"),
            description=model_info.get("description", ""),
            data_source=DataSource.SILICONFLOW,
            last_updated=datetime.now(),
        )

        # 架构信息推断
        modality = "text->text"
        input_modalities = ["text"]
        output_modalities = ["text"]

        # 检查多模态能力
        if model_info.get("vision_support", False):
            modality = "text+image->text"
            input_modalities.append("image")

        if model_info.get("type") == "audio":
            if model_info.get("subType") == "text-to-speech":
                modality = "text->audio"
                output_modalities = ["audio"]
            elif model_info.get("subType") == "speech-to-text":
                modality = "audio->text"
                input_modalities = ["audio"]

        unified_model.architecture = Architecture(
            modality=modality,
            input_modalities=input_modalities,
            output_modalities=output_modalities,
        )

        # 定价信息
        is_free = input_price_yuan_per_m == 0 and output_price_yuan_per_m == 0
        unified_model.pricing = Pricing(
            prompt=input_price_usd_per_token,
            completion=output_price_usd_per_token,
            original_currency="CNY",
            exchange_rate=exchange_rate,
            confidence_level=0.9,  # SiliconFlow数据较可信
        )

        # 能力和分类
        capabilities = model_info.get("capabilities", [])
        if not capabilities:
            capabilities = self.capability_inference.infer_capabilities_from_name(
                model_id
            )

        # 添加SiliconFlow特定能力
        if model_info.get("function_call_support", False):
            capabilities.append("function_calling")
        if model_info.get("vision_support", False):
            capabilities.append("vision")
        if model_info.get("json_mode_support", False):
            capabilities.append("json_mode")

        unified_model.capabilities = list(set(capabilities))  # 去重

        # 分类推断
        category = model_info.get("category", "standard")
        if category == "free" or is_free:
            unified_model.category = ModelCategory.FREE
        elif category == "premium":
            unified_model.category = ModelCategory.PREMIUM
        elif category == "vision":
            unified_model.category = ModelCategory.VISION
        else:
            unified_model.category = (
                self.capability_inference.infer_category_from_params(
                    unified_model.parameter_count, unified_model.context_length
                )
            )

        return unified_model


class FormatConverterFactory:
    """格式转换器工厂"""

    _converters = {
        "openrouter": OpenRouterConverter,
        "siliconflow": SiliconFlowConverter,
    }

    @classmethod
    def get_converter(cls, platform: str) -> BaseFormatConverter:
        """获取指定平台的转换器"""
        if platform not in cls._converters:
            raise ValueError(
                f"不支持的平台: {platform}, 支持的平台: {list(cls._converters.keys())}"
            )

        return cls._converters[platform]()

    @classmethod
    def register_converter(cls, platform: str, converter_class: type) -> None:
        """注册新的转换器"""
        cls._converters[platform] = converter_class
        logger.info(f"注册转换器: {platform} -> {converter_class.__name__}")


def convert_platform_to_unified(
    source_file: Path, platform: str, output_file: Path
) -> UnifiedPricingFile:
    """将平台特定格式转换为统一格式"""
    logger.info(f"开始转换 {platform} 格式: {source_file} -> {output_file}")

    # 加载源数据
    with open(source_file, encoding="utf-8") as f:
        source_data = json.load(f)

    # 获取转换器并转换
    converter = FormatConverterFactory.get_converter(platform)
    unified_file = converter.convert_to_unified(source_data)

    # 保存转换结果
    output_file.parent.mkdir(parents=True, exist_ok=True)
    unified_file.save_to_file(output_file)

    logger.info(f"转换完成: {len(unified_file.models)}个模型已保存到 {output_file}")
    return unified_file


if __name__ == "__main__":
    # 测试转换器
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent

    # SiliconFlow转换功能已集成到 parse_siliconflow_unified.py
    # 这里的测试代码已过时，删除避免混淆
    print("SiliconFlow转换功能已迁移到 scripts/parse_siliconflow_unified.py")

    # 测试OpenRouter转换
    openrouter_file = project_root / "cache/channels/openrouter_1.json"
    if openrouter_file.exists():
        output_file = project_root / "config/pricing/openrouter_unified.json"
        try:
            unified_file = convert_platform_to_unified(
                openrouter_file, "openrouter", output_file
            )
            print(f"OpenRouter转换成功: {len(unified_file.models)}个模型")
        except Exception as e:
            print(f"OpenRouter转换失败: {e}")
