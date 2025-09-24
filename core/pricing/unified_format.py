#!/usr/bin/env python3
"""
统一定价数据格式定义
以OpenRouter格式为标准，支持所有平台的数据转换
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ModelCategory(Enum):
    """模型分类枚举"""

    FREE = "free"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    XLARGE = "xlarge"
    PREMIUM = "premium"
    VISION = "vision"
    CODE = "code"
    REASONING = "reasoning"


class DataSource(Enum):
    """数据来源枚举"""

    OPENROUTER = "openrouter"
    SILICONFLOW = "siliconflow"
    DOUBAO = "doubao"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    BASE_PRICING = "base_pricing"
    ML_PREDICTION = "ml_prediction"


@dataclass
class Architecture:
    """模型架构信息"""

    modality: str = "text->text"
    input_modalities: list[str] = field(default_factory=lambda: ["text"])
    output_modalities: list[str] = field(default_factory=lambda: ["text"])
    tokenizer: Optional[str] = None
    instruct_type: Optional[str] = None


@dataclass
class Pricing:
    """标准化定价信息 (USD per token)"""

    prompt: float = 0.0
    completion: float = 0.0
    request: float = 0.0
    image: float = 0.0
    web_search: float = 0.0
    internal_reasoning: float = 0.0

    # 元数据
    original_currency: str = "USD"
    exchange_rate: float = 1.0
    is_promotional: bool = False
    confidence_level: float = 1.0  # 0-1, 1=完全准确


@dataclass
class TopProvider:
    """顶级提供商信息"""

    context_length: Optional[int] = None
    max_completion_tokens: Optional[int] = None
    is_moderated: bool = False


@dataclass
class UnifiedModelData:
    """统一模型数据格式"""

    # 基本标识
    id: str
    canonical_slug: Optional[str] = None
    hugging_face_id: Optional[str] = None
    name: Optional[str] = None

    # 技术参数
    parameter_count: Optional[int] = None  # 参数数量
    context_length: Optional[int] = None
    created: Optional[int] = None  # 创建时间戳

    # 架构和能力
    architecture: Optional[Architecture] = None
    capabilities: list[str] = field(default_factory=list)

    # 定价信息
    pricing: Optional[Pricing] = None

    # 提供商信息
    top_provider: Optional[TopProvider] = None

    # 描述和分类
    description: Optional[str] = None
    category: ModelCategory = ModelCategory.MEDIUM

    # 元数据
    data_source: DataSource = DataSource.OPENROUTER
    last_updated: Optional[datetime] = None
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        result: dict[str, Any] = {}
        for field_name, field_value in self.__dict__.items():
            if field_value is None:
                continue
            elif isinstance(field_value, (Architecture, Pricing, TopProvider)):
                result[field_name] = field_value.__dict__
            elif isinstance(field_value, (ModelCategory, DataSource)):
                result[field_name] = field_value.value
            elif isinstance(field_value, datetime):
                result[field_name] = field_value.isoformat()
            else:
                result[field_name] = field_value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UnifiedModelData":
        """从字典创建实例"""
        # 处理嵌套对象
        if "architecture" in data and isinstance(data["architecture"], dict):
            data["architecture"] = Architecture(**data["architecture"])
        if "pricing" in data and isinstance(data["pricing"], dict):
            data["pricing"] = Pricing(**data["pricing"])
        if "top_provider" in data and isinstance(data["top_provider"], dict):
            data["top_provider"] = TopProvider(**data["top_provider"])

        # 处理枚举
        if "category" in data and isinstance(data["category"], str):
            data["category"] = ModelCategory(data["category"])
        if "data_source" in data and isinstance(data["data_source"], str):
            data["data_source"] = DataSource(data["data_source"])

        # 处理日期时间
        if "last_updated" in data and isinstance(data["last_updated"], str):
            data["last_updated"] = datetime.fromisoformat(data["last_updated"])

        return cls(**data)


@dataclass
class UnifiedPricingFile:
    """统一定价文件格式"""

    provider: str
    source: str
    currency: str = "USD"
    unit: str = "per_million_tokens"  # 🔧 默认使用更直观的百万token单位
    format_version: str = "2.0"
    last_updated: datetime = field(default_factory=datetime.now)
    description: str = ""
    models: dict[str, UnifiedModelData] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "provider": self.provider,
            "source": self.source,
            "currency": self.currency,
            "unit": self.unit,
            "format_version": self.format_version,
            "last_updated": self.last_updated.isoformat(),
            "description": self.description,
            "models": {k: v.to_dict() for k, v in self.models.items()},
        }

    def save_to_file(self, file_path: Path) -> None:
        """保存到JSON文件"""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_from_file(cls, file_path: Path) -> "UnifiedPricingFile":
        """从JSON文件加载"""
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        # 转换模型数据
        models = {}
        for model_id, model_data in data.get("models", {}).items():
            models[model_id] = UnifiedModelData.from_dict(model_data)

        return cls(
            provider=data["provider"],
            source=data["source"],
            currency=data.get("currency", "USD"),
            unit=data.get("unit", "per_token"),
            format_version=data.get("format_version", "2.0"),
            last_updated=(
                datetime.fromisoformat(data["last_updated"])
                if "last_updated" in data
                else datetime.now()
            ),
            description=data.get("description", ""),
            models=models,
        )


class ModelCapabilityInference:
    """模型能力推理工具"""

    @staticmethod
    def infer_capabilities_from_name(model_name: str) -> list[str]:
        """从模型名称推断能力"""
        capabilities = []
        name_lower = model_name.lower()

        # 基本能力推断
        if any(x in name_lower for x in ["chat", "instruct", "assistant"]):
            capabilities.append("chat")
        if any(x in name_lower for x in ["code", "coder", "programming"]):
            capabilities.append("code")
        if any(x in name_lower for x in ["vision", "visual", "4o", "4v", "multimodal"]):
            capabilities.append("vision")
        if any(x in name_lower for x in ["reasoning", "think", "o1", "reason"]):
            capabilities.append("reasoning")
        if any(x in name_lower for x in ["function", "tool", "call"]):
            capabilities.append("function_calling")

        return capabilities

    @staticmethod
    def infer_category_from_params(
        parameter_count: Optional[int], context_length: Optional[int]
    ) -> ModelCategory:
        """从参数和上下文推断分类"""
        if parameter_count:
            if parameter_count >= 400e9:  # 400B+
                return ModelCategory.XLARGE
            elif parameter_count >= 70e9:  # 70B+
                return ModelCategory.LARGE
            elif parameter_count >= 13e9:  # 13B+
                return ModelCategory.MEDIUM
            else:  # <13B
                return ModelCategory.SMALL

        # 基于上下文长度的备用推断
        if context_length and context_length >= 200000:  # 200K+
            return ModelCategory.LARGE

        return ModelCategory.MEDIUM


if __name__ == "__main__":
    # 测试统一格式
    model = UnifiedModelData(
        id="test/model-7b",
        name="Test Model 7B",
        parameter_count=7000000000,
        context_length=32768,
        architecture=Architecture(
            modality="text->text", input_modalities=["text"], output_modalities=["text"]
        ),
        pricing=Pricing(prompt=0.001, completion=0.002),
        capabilities=["chat", "code"],
        category=ModelCategory.SMALL,
        data_source=DataSource.OPENROUTER,
    )

    print("[PASS] 统一格式测试成功")
    print(f"模型: {model.name}")
    print(f"参数: {model.parameter_count/1e9:.1f}B")
    print(f"能力: {model.capabilities}")
