"""
模型信息数据结构
遵循KISS原则的简单数据模型
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DataSource(Enum):
    """数据来源"""

    OPENROUTER = "openrouter"
    PROVIDER_OVERRIDE = "provider_override"
    CHANNEL_OVERRIDE = "channel_override"
    LOCAL_DETECTION = "local_detection"
    BASIC_INFERENCE = "basic_inference"


@dataclass
class ModelCapabilities:
    """模型能力信息"""

    supports_vision: bool = False
    supports_function_calling: bool = False
    supports_code_generation: bool = True  # 默认支持
    supports_streaming: bool = True  # 默认支持

    def to_legacy_dict(self) -> dict[str, bool]:
        """转换为旧版格式（兼容现有代码）"""
        return {
            "vision": self.supports_vision,
            "function_calling": self.supports_function_calling,
            "code_generation": self.supports_code_generation,
            "streaming": self.supports_streaming,
        }


@dataclass
class ModelSpecs:
    """模型规格信息"""

    parameter_count: Optional[int] = None  # 参数数量 (百万)
    context_length: Optional[int] = None  # 上下文长度
    parameter_size_text: Optional[str] = None  # "8b", "70b" 等
    context_text: Optional[str] = None  # "128k", "32k" 等

    def format_parameter_size(self) -> str:
        """格式化参数大小"""
        if not self.parameter_count:
            return "unknown"
        if self.parameter_count >= 1000:
            return f"{self.parameter_count//1000}b"
        return f"{self.parameter_count}m"

    def format_context_length(self) -> str:
        """格式化上下文长度"""
        if not self.context_length:
            return "unknown"
        if self.context_length >= 1000:
            return f"{self.context_length//1000}k"
        return str(self.context_length)


@dataclass
class ModelPricing:
    """模型定价信息"""

    input_price: Optional[float] = None  # 输入价格 (per token)
    output_price: Optional[float] = None  # 输出价格 (per token)
    is_free: bool = False  # 是否免费

    @property
    def pricing_input(self) -> float:
        """兼容旧接口"""
        return self.input_price or 0.0

    @property
    def pricing_output(self) -> float:
        """兼容旧接口"""
        return self.output_price or 0.0


@dataclass
class ModelInfo:
    """完整的模型信息 - 统一数据结构"""

    # 基础信息
    model_id: str
    provider: str = ""
    display_name: Optional[str] = None

    # 能力信息
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)

    # 规格信息
    specs: ModelSpecs = field(default_factory=ModelSpecs)

    # 定价信息
    pricing: ModelPricing = field(default_factory=ModelPricing)

    # 元信息
    tags: set[str] = field(default_factory=set)
    quality_score: float = 0.5
    data_source: DataSource = DataSource.BASIC_INFERENCE
    is_local: bool = False

    # OpenRouter原始数据（用于调试）
    modality: Optional[str] = None
    input_modalities: list[str] = field(default_factory=list)
    output_modalities: list[str] = field(default_factory=list)

    def extract_tags_from_name(self) -> set[str]:
        """从模型名称自动提取标签"""
        import re

        # 分割符号
        separators = r"[:/\\-_@,]"
        parts = re.split(separators, self.model_id.lower())

        tags = set()
        for part in parts:
            part = part.strip()
            if part and len(part) > 0:
                tags.add(part)

        # 添加能力标签
        if self.capabilities.supports_vision:
            tags.add("vision")
        if self.capabilities.supports_function_calling:
            tags.add("function_calling")
        if self.pricing.is_free:
            tags.add("free")

        return tags

    def matches_tags(self, required_tags: list[str]) -> bool:
        """检查是否匹配所有必需标签"""
        if not required_tags:
            return True

        model_tags = self.tags or self.extract_tags_from_name()
        model_tags_lower = {tag.lower() for tag in model_tags}

        for required_tag in required_tags:
            if required_tag.lower() not in model_tags_lower:
                return False

        return True

    def update_from_provider_override(self, provider_overrides: dict[str, Any]) -> None:
        """应用提供商级别覆盖"""
        if pricing := provider_overrides.get("pricing"):
            if pricing.get("input_price") is not None:
                self.pricing.input_price = pricing["input_price"]
            if pricing.get("output_price") is not None:
                self.pricing.output_price = pricing["output_price"]
            if pricing.get("is_free") is not None:
                self.pricing.is_free = pricing["is_free"]

        if capabilities := provider_overrides.get("capabilities"):
            if "supports_vision" in capabilities:
                self.capabilities.supports_vision = capabilities["supports_vision"]
            if "supports_function_calling" in capabilities:
                self.capabilities.supports_function_calling = capabilities[
                    "supports_function_calling"
                ]

        self.data_source = DataSource.PROVIDER_OVERRIDE


# 工厂函数，简化创建
def create_model_info_from_openrouter(openrouter_data: dict[str, Any]) -> ModelInfo:
    """从OpenRouter数据创建ModelInfo"""
    model_id = openrouter_data.get("id", "")

    # 解析能力信息
    capabilities = ModelCapabilities()

    # 从modality字段推断能力
    input_modalities = openrouter_data.get("input_modalities", [])
    if "image" in input_modalities:
        capabilities.supports_vision = True

    # 从supported_parameters推断函数调用能力
    supported_params = openrouter_data.get("supported_parameters", [])
    if "tools" in supported_params or "functions" in supported_params:
        capabilities.supports_function_calling = True

    # 解析定价信息
    pricing = ModelPricing()
    pricing_info = openrouter_data.get("pricing", {})
    if pricing_info:
        pricing.input_price = pricing_info.get("prompt")
        pricing.output_price = pricing_info.get("completion")
        # 判断是否免费
        pricing.is_free = (
            pricing.input_price == 0
            and pricing.output_price == 0
            and pricing_info.get("prompt") == 0
        )

    # 解析规格信息
    specs = ModelSpecs()
    if context_length := openrouter_data.get("context_length"):
        specs.context_length = context_length
        specs.context_text = (
            f"{context_length//1000}k"
            if context_length >= 1000
            else str(context_length)
        )

    return ModelInfo(
        model_id=model_id,
        provider=openrouter_data.get("provider", ""),
        display_name=openrouter_data.get("name"),
        capabilities=capabilities,
        specs=specs,
        pricing=pricing,
        quality_score=0.8,  # OpenRouter数据质量较高
        data_source=DataSource.OPENROUTER,
        modality=openrouter_data.get("modality"),
        input_modalities=input_modalities,
        output_modalities=openrouter_data.get("output_modalities", []),
    )
