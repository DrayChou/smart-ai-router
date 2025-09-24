"""
统一模型注册表 - 基于OpenRouter数据的单一真实来源配置管理
遵循KISS原则：OpenRouter基础 → 提供商覆盖 → 渠道特定覆盖
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """数据来源类型"""

    OPENROUTER = "openrouter"
    PROVIDER_OVERRIDE = "provider_override"
    CHANNEL_OVERRIDE = "channel_override"
    STATIC_CONFIG = "static_config"
    API_TEST = "api_test"


@dataclass
class ModelMetadata:
    """统一模型元数据结构"""

    # 基本信息
    model_id: str
    provider: str
    canonical_name: Optional[str] = None

    # 模型规格 (来自OpenRouter或推断)
    parameter_count: Optional[int] = None  # 百万参数
    context_length: Optional[int] = None
    max_output_tokens: Optional[int] = None

    # 多模态能力 (OpenRouter标准)
    modality: Optional[str] = None  # "text+image->text"
    input_modalities: list[str] = field(default_factory=list)  # ["text", "image"]
    output_modalities: list[str] = field(default_factory=list)  # ["text"]

    # API能力支持
    supported_parameters: list[str] = field(
        default_factory=list
    )  # ["tools", "function_calling"]
    supports_streaming: bool = True
    supports_function_calling: bool = False
    supports_vision: bool = False
    supports_audio: bool = False

    # 定价信息 ($/1M tokens)
    pricing_input: Optional[float] = None
    pricing_output: Optional[float] = None
    pricing_image: Optional[float] = None  # $/image
    pricing_audio: Optional[float] = None  # $/second
    is_free: bool = False

    # 质量和性能评分 (0-1)
    quality_score: float = 0.5
    speed_score: float = 0.5  # 0-1, higher=faster
    reliability_score: float = 0.8

    # 元数据
    created_timestamp: Optional[int] = None
    is_deprecated: bool = False
    tags: set[str] = field(default_factory=set)  # 自动从model_id提取的标签

    # 数据来源追踪
    data_source: DataSource = DataSource.OPENROUTER
    confidence: float = 0.8
    last_updated: Optional[datetime] = None

    def __post_init__(self) -> None:
        """后处理初始化"""
        if self.last_updated is None:
            self.last_updated = datetime.now()

        # 从modality推断能力
        self._infer_capabilities_from_modality()

        # 自动生成标签
        self._generate_tags()

    def _infer_capabilities_from_modality(self) -> None:
        """从modality字段推断基本能力"""
        if self.modality:
            # 解析输入输出模态
            if "image" in self.modality:
                self.supports_vision = True
                if "image" not in self.input_modalities:
                    self.input_modalities.append("image")

            if "audio" in self.modality:
                self.supports_audio = True
                if "audio" not in self.input_modalities:
                    self.input_modalities.append("audio")

        # 从supported_parameters推断功能
        if self.supported_parameters:
            if any(
                param in self.supported_parameters
                for param in ["tools", "function_calling", "tool_choice"]
            ):
                self.supports_function_calling = True

    def _generate_tags(self) -> None:
        """从模型ID自动生成标签"""
        if not self.model_id:
            return

        import re

        # 使用多种分隔符拆分
        separators = r"[:/\-_@,]"
        parts = re.split(separators, self.model_id.lower())

        for part in parts:
            part = part.strip()
            if part and len(part) > 0:
                self.tags.add(part)

        # 添加能力标签
        if self.supports_vision:
            self.tags.add("vision")
        if self.supports_function_calling:
            self.tags.add("function_calling")
        if self.is_free:
            self.tags.add("free")

    def matches_tags(self, required_tags: list[str]) -> bool:
        """检查是否匹配所有必需标签"""
        if not required_tags:
            return True
        return all(tag.lower() in self.tags for tag in required_tags)

    def to_legacy_capability_format(self) -> dict[str, bool]:
        """转换为旧版capability_mapper格式"""
        return {
            "vision": self.supports_vision,
            "function_calling": self.supports_function_calling,
            "code_generation": True,  # 默认支持
            "streaming": self.supports_streaming,
        }


class UnifiedModelRegistry:
    """统一模型注册表"""

    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # 配置文件路径
        self.openrouter_file = self.cache_dir / "channels" / "openrouter_1.json"
        self.provider_overrides_file = self.cache_dir / "provider_overrides.json"
        self.channel_overrides_file = self.cache_dir / "channel_overrides.json"

        # 内存缓存
        self._models: dict[str, ModelMetadata] = {}
        self._provider_overrides: dict[str, dict[str, Any]] = {}
        self._channel_overrides: dict[str, dict[str, Any]] = {}
        self._tags_index: dict[str, set[str]] = {}  # tag -> model_ids

        # 加载数据
        self._load_all_data()

    def _load_all_data(self) -> None:
        """加载所有配置数据"""
        logger.info("正在加载统一模型注册表数据...")

        # 1. 加载OpenRouter基础数据
        openrouter_count = self._load_openrouter_data()

        # 2. 加载提供商覆盖配置
        provider_count = self._load_provider_overrides()

        # 3. 加载渠道特定覆盖
        channel_count = self._load_channel_overrides()

        # 4. 构建标签索引
        self._build_tags_index()

        logger.info(
            f"统一模型注册表加载完成: OpenRouter={openrouter_count}, "
            f"提供商覆盖={provider_count}, 渠道覆盖={channel_count}, "
            f"总模型数={len(self._models)}, 总标签数={len(self._tags_index)}"
        )

    def _load_openrouter_data(self) -> int:
        """加载OpenRouter基础数据"""
        if not self.openrouter_file.exists():
            logger.warning(f"OpenRouter数据文件不存在: {self.openrouter_file}")
            return 0

        try:
            with open(self.openrouter_file, encoding="utf-8") as f:
                data = json.load(f)

            models_data = data.get("models", {})
            count = 0

            for model_id, model_info in models_data.items():
                try:
                    metadata = self._parse_openrouter_model(model_id, model_info)
                    self._models[model_id] = metadata
                    count += 1
                except Exception as e:
                    logger.warning(f"解析OpenRouter模型失败 {model_id}: {e}")

            logger.info(f"成功加载OpenRouter数据: {count}个模型")
            return count

        except Exception as e:
            logger.error(f"加载OpenRouter数据失败: {e}")
            return 0

    def _parse_openrouter_model(
        self, model_id: str, model_info: dict[str, Any]
    ) -> ModelMetadata:
        """解析OpenRouter模型数据"""
        raw_data = model_info.get("raw_data", {})

        # 提取基本信息
        provider = model_id.split("/")[0] if "/" in model_id else "unknown"

        # 提取架构信息
        architecture = raw_data.get("architecture", {})
        modality = architecture.get("modality", "")
        input_modalities = architecture.get("input_modalities", [])
        output_modalities = architecture.get("output_modalities", [])

        # 提取定价信息
        pricing = raw_data.get("pricing", {})
        pricing_input = float(pricing.get("prompt", 0)) * 1000  # 转换为$/1M tokens
        pricing_output = float(pricing.get("completion", 0)) * 1000
        pricing_image = float(pricing.get("image", 0))
        is_free = pricing_input == 0 and pricing_output == 0

        # 提取性能信息
        context_length = model_info.get("context_length") or raw_data.get(
            "context_length"
        )
        parameter_count = model_info.get("parameter_count")
        max_output_tokens = raw_data.get("top_provider", {}).get(
            "max_completion_tokens"
        )

        # 提取支持的参数
        supported_parameters = raw_data.get("supported_parameters", [])

        # 推断质量评分（基于参数量和提供商）
        quality_score = self._estimate_quality_score(
            model_id, parameter_count, provider
        )
        speed_score = self._estimate_speed_score(model_id, parameter_count)

        return ModelMetadata(
            model_id=model_id,
            provider=provider,
            canonical_name=raw_data.get("name"),
            parameter_count=parameter_count,
            context_length=context_length,
            max_output_tokens=max_output_tokens,
            modality=modality,
            input_modalities=input_modalities,
            output_modalities=output_modalities,
            supported_parameters=supported_parameters,
            supports_streaming=True,  # 大部分模型支持
            pricing_input=pricing_input,
            pricing_output=pricing_output,
            pricing_image=pricing_image,
            is_free=is_free,
            quality_score=quality_score,
            speed_score=speed_score,
            created_timestamp=raw_data.get("created"),
            data_source=DataSource.OPENROUTER,
            confidence=0.95,  # OpenRouter数据可信度高
        )

    def _estimate_quality_score(
        self, model_id: str, parameter_count: Optional[int], provider: str
    ) -> float:
        """估算模型质量评分"""
        model_lower = model_id.lower()

        # 基于知名模型的质量评分
        if any(x in model_lower for x in ["gpt-4o", "gpt-4-turbo"]):
            return 0.95
        elif "gpt-4" in model_lower and "mini" not in model_lower:
            return 0.90
        elif "gpt-4o-mini" in model_lower or "gpt-4-mini" in model_lower:
            return 0.75
        elif "claude-3-opus" in model_lower or "claude-3.5-sonnet" in model_lower:
            return 0.94
        elif "claude-3-sonnet" in model_lower:
            return 0.85
        elif "claude-3-haiku" in model_lower:
            return 0.75

        # 基于参数量估算
        if parameter_count:
            if parameter_count >= 400000:  # 400B+
                return 0.90
            elif parameter_count >= 70000:  # 70B+
                return 0.85
            elif parameter_count >= 30000:  # 30B+
                return 0.75
            elif parameter_count >= 7000:  # 7B+
                return 0.65

        # 基于提供商默认质量
        provider_quality = {
            "openai": 0.85,
            "anthropic": 0.80,
            "google": 0.75,
            "meta": 0.70,
            "qwen": 0.65,
        }

        return provider_quality.get(provider, 0.50)

    def _estimate_speed_score(
        self, model_id: str, parameter_count: Optional[int]
    ) -> float:
        """估算模型速度评分"""
        model_lower = model_id.lower()

        # 基于已知速度特征
        if "mini" in model_lower or "fast" in model_lower:
            return 0.9
        elif "turbo" in model_lower:
            return 0.8
        elif "flash" in model_lower:
            return 0.85

        # 基于参数量估算（参数越少通常越快）
        if parameter_count:
            if parameter_count <= 8000:  # 8B以下
                return 0.9
            elif parameter_count <= 30000:  # 30B以下
                return 0.7
            elif parameter_count <= 70000:  # 70B以下
                return 0.5
            else:  # 70B+
                return 0.3

        return 0.6  # 默认中等速度

    def _load_provider_overrides(self) -> int:
        """加载提供商覆盖配置"""
        if not self.provider_overrides_file.exists():
            # 创建默认提供商覆盖配置
            default_overrides = {
                "siliconflow": {
                    "pricing_multiplier": 0.1,  # SiliconFlow便宜10倍
                    "free_models": ["qwen2.5-coder-7b-instruct", "internlm2.5-7b-chat"],
                    "quality_boost": 0.0,
                },
                "groq": {
                    "pricing_multiplier": 0.0,  # Groq基本免费
                    "speed_boost": 0.3,  # Groq速度提升
                    "free_models": ["*"],  # 所有模型免费
                },
                "ollama": {
                    "pricing_multiplier": 0.0,  # 本地模型免费
                    "speed_boost": 0.1,
                    "free_models": ["*"],
                    "supports_vision_override": False,  # 大部分本地模型不支持视觉
                },
            }

            self.provider_overrides_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.provider_overrides_file, "w", encoding="utf-8") as f:
                json.dump(default_overrides, f, indent=2, ensure_ascii=False)

        try:
            with open(self.provider_overrides_file, encoding="utf-8") as f:
                self._provider_overrides = json.load(f)

            logger.info(
                f"成功加载提供商覆盖配置: {len(self._provider_overrides)}个提供商"
            )
            return len(self._provider_overrides)
        except Exception as e:
            logger.error(f"加载提供商覆盖配置失败: {e}")
            return 0

    def _load_channel_overrides(self) -> int:
        """加载渠道特定覆盖配置"""
        if not self.channel_overrides_file.exists():
            return 0

        try:
            with open(self.channel_overrides_file, encoding="utf-8") as f:
                self._channel_overrides = json.load(f)

            logger.info(f"成功加载渠道覆盖配置: {len(self._channel_overrides)}个渠道")
            return len(self._channel_overrides)
        except Exception as e:
            logger.error(f"加载渠道覆盖配置失败: {e}")
            return 0

    def _build_tags_index(self) -> None:
        """构建标签索引"""
        self._tags_index.clear()

        for model_id, metadata in self._models.items():
            for tag in metadata.tags:
                if tag not in self._tags_index:
                    self._tags_index[tag] = set()
                self._tags_index[tag].add(model_id)

        logger.debug(f"构建标签索引完成: {len(self._tags_index)}个标签")

    def get_model_metadata(
        self, model_id: str, provider: str = "", channel_id: str = ""
    ) -> Optional[ModelMetadata]:
        """获取模型元数据（应用所有覆盖层）"""
        base_metadata = self._models.get(model_id)
        if not base_metadata:
            return None

        # 复制基础数据
        metadata = ModelMetadata(**asdict(base_metadata))

        # 应用提供商覆盖
        if provider:
            self._apply_provider_overrides(metadata, provider)

        # 应用渠道覆盖
        if channel_id:
            self._apply_channel_overrides(metadata, channel_id)

        return metadata

    def _apply_provider_overrides(self, metadata: ModelMetadata, provider: str) -> None:
        """应用提供商覆盖"""
        provider_config = self._provider_overrides.get(provider, {})
        if not provider_config:
            return

        # 价格覆盖
        pricing_multiplier = provider_config.get("pricing_multiplier", 1.0)
        if pricing_multiplier != 1.0:
            if metadata.pricing_input:
                metadata.pricing_input *= pricing_multiplier
            if metadata.pricing_output:
                metadata.pricing_output *= pricing_multiplier

        # 免费模型覆盖
        free_models = provider_config.get("free_models", [])
        if "*" in free_models or metadata.model_id in free_models:
            metadata.pricing_input = 0.0
            metadata.pricing_output = 0.0
            metadata.is_free = True
            metadata.tags.add("free")

        # 性能提升
        speed_boost = provider_config.get("speed_boost", 0.0)
        if speed_boost:
            metadata.speed_score = min(1.0, metadata.speed_score + speed_boost)

        quality_boost = provider_config.get("quality_boost", 0.0)
        if quality_boost:
            metadata.quality_score = min(1.0, metadata.quality_score + quality_boost)

        # 能力覆盖
        if "supports_vision_override" in provider_config:
            metadata.supports_vision = provider_config["supports_vision_override"]

    def _apply_channel_overrides(
        self, metadata: ModelMetadata, channel_id: str
    ) -> None:
        """应用渠道特定覆盖"""
        channel_config = self._channel_overrides.get(channel_id, {})
        if not channel_config:
            return

        # 直接覆盖指定字段
        for field, value in channel_config.items():
            if hasattr(metadata, field):
                setattr(metadata, field, value)

    def find_models_by_tags(
        self, tags: list[str], provider: str = ""
    ) -> list[ModelMetadata]:
        """根据标签查找模型"""
        if not tags:
            return list(self._models.values())

        # 找到匹配所有标签的模型ID
        matching_ids = None
        for tag in tags:
            tag_lower = tag.lower()
            tag_model_ids = self._tags_index.get(tag_lower, set())

            if matching_ids is None:
                matching_ids = tag_model_ids.copy()
            else:
                matching_ids &= tag_model_ids

        if not matching_ids:
            return []

        # 返回模型元数据
        results = []
        for model_id in matching_ids:
            metadata = self.get_model_metadata(model_id, provider)
            if metadata:
                results.append(metadata)

        return results

    def get_free_models(self, provider: str = "") -> list[ModelMetadata]:
        """获取免费模型列表"""
        return self.find_models_by_tags(["free"], provider)

    def get_vision_models(self, provider: str = "") -> list[ModelMetadata]:
        """获取支持视觉的模型"""
        return [m for m in self._models.values() if m.supports_vision]

    def reload_data(self) -> None:
        """重新加载所有数据"""
        logger.info("重新加载统一模型注册表...")
        self._models.clear()
        self._provider_overrides.clear()
        self._channel_overrides.clear()
        self._tags_index.clear()
        self._load_all_data()

    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息"""
        free_count = len([m for m in self._models.values() if m.is_free])
        vision_count = len([m for m in self._models.values() if m.supports_vision])
        function_count = len(
            [m for m in self._models.values() if m.supports_function_calling]
        )

        return {
            "total_models": len(self._models),
            "free_models": free_count,
            "vision_models": vision_count,
            "function_calling_models": function_count,
            "providers": len({m.provider for m in self._models.values()}),
            "tags": len(self._tags_index),
            "provider_overrides": len(self._provider_overrides),
            "channel_overrides": len(self._channel_overrides),
        }


# 全局实例
_unified_registry: Optional[UnifiedModelRegistry] = None


def get_unified_model_registry() -> UnifiedModelRegistry:
    """获取全局统一模型注册表实例"""
    global _unified_registry
    if _unified_registry is None:
        _unified_registry = UnifiedModelRegistry()
    return _unified_registry


def reload_unified_registry() -> None:
    """重新加载统一注册表（用于配置更新后）"""
    global _unified_registry
    if _unified_registry:
        _unified_registry.reload_data()
