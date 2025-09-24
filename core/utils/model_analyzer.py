"""
模型分析工具 - 提取参数数量、上下文长度等信息
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelSpecs:
    """模型规格信息"""

    model_name: str
    parameter_count: Optional[int] = None  # 参数数量（以百万为单位）
    context_length: Optional[int] = None  # 上下文长度
    parameter_size_text: Optional[str] = None  # 原始参数文本，如 "7b", "270m"
    context_text: Optional[str] = None  # 原始上下文文本，如 "32k", "128k"

    def __post_init__(self) -> None:
        """后处理，计算数值"""
        if self.parameter_size_text and not self.parameter_count:
            self.parameter_count = self._parse_parameter_size(self.parameter_size_text)
        if self.context_text and not self.context_length:
            self.context_length = self._parse_context_length(self.context_text)

    def _parse_parameter_size(self, size_text: str) -> Optional[int]:
        """解析参数大小文本为数值（百万参数）"""
        try:
            size_text = size_text.lower().strip()
            if "b" in size_text:  # billions
                return int(float(size_text.replace("b", "")) * 1000)
            elif "m" in size_text:  # millions
                return int(float(size_text.replace("m", "")))
            elif "k" in size_text:  # thousands (rare)
                return int(float(size_text.replace("k", "")) / 1000)
        except (ValueError, TypeError):
            pass
        return None

    def _parse_context_length(self, context_text: str) -> Optional[int]:
        """解析上下文长度文本为数值"""
        try:
            context_text = context_text.lower().strip()
            if "k" in context_text:
                return int(float(context_text.replace("k", "")) * 1000)
            elif "m" in context_text:
                return int(float(context_text.replace("m", "")) * 1000000)
            else:
                return int(context_text)
        except (ValueError, TypeError):
            pass
        return None


class ModelAnalyzer:
    """模型分析器"""

    # 参数大小模式（优先级从高到低）
    PARAMETER_PATTERNS = [
        # 明确的参数模式
        r"(\d+\.?\d*)b(?:illions?)?(?:\W|$)",  # 70b, 8b, 1.5b
        r"(\d+\.?\d*)m(?:illions?)?(?:\W|$)",  # 270m, 400m
        r"(\d+\.?\d*)k(?:ilo)?(?:\W|$)",  # 500k (rare)
        # 模型名称中的参数模式
        r"-(\d+\.?\d*)b-",  # model-7b-instruct
        r"-(\d+\.?\d*)m-",  # model-270m-chat
        r"_(\d+\.?\d*)b_",  # model_8b_v1
        r"_(\d+\.?\d*)m_",  # model_400m_base
        # 较宽松的模式
        r"(\d+)b(?!it|yte)",  # 避免匹配 bit, byte
        r"(\d+)m(?!in|ax)",  # 避免匹配 min, max
    ]

    # 上下文长度模式
    CONTEXT_PATTERNS = [
        r"(\d+\.?\d*)k(?:tok|token|ctx|context)?(?:\W|$)",  # 32k, 128k
        r"(\d+\.?\d*)m(?:tok|token|ctx|context)?(?:\W|$)",  # 2m (rare)
        r"-(\d+\.?\d*)k-",  # model-32k-chat
        r"_(\d+\.?\d*)k_",  # model_128k_v1
        r"(\d+)k(?!ey|now)",  # 避免匹配 key, know
    ]

    # 精简的回退参数映射（统一注册表优先，仅用于极端情况）
    KNOWN_MODEL_PARAMS = {
        # 核心常用模型
        "gpt-4o": 1760000,  # 1.76T
        "gpt-4o-mini": 8000,  # 8B
        "claude-3-haiku": 9000,  # 9B
        "llama-3.1-8b": 8000,  # 8B
        "gemma-3-270m": 270,  # 270M
    }

    # 精简的回退上下文映射（统一注册表优先，仅用于极端情况）
    KNOWN_MODEL_CONTEXT = {
        # 核心常用模型
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "claude-3-haiku": 200000,
        "llama-3.1-8b": 131072,  # 128k
        "gemma-3-270m": 8192,
        # 默认回退值
        "default": 8192,  # 8k 默认
    }

    def analyze_model(
        self, model_name: str, model_data: dict[str, Any] = None
    ) -> ModelSpecs:
        """分析单个模型，提取参数和上下文信息"""

        # 优先从统一模型注册表获取数据
        try:
            from .legacy_adapters import get_model_analyzer_adapter

            adapter = get_model_analyzer_adapter()
            return adapter.analyze_model(model_name, model_data)
        except Exception as e:
            logger.warning(f"统一模型注册表查询失败，回退到原逻辑: {e}")

        # 回退到原逻辑
        specs = ModelSpecs(model_name=model_name)

        # 1. 从API返回的数据中提取（最准确）
        if model_data:
            if "context_length" in model_data:
                specs.context_length = model_data["context_length"]
                specs.context_text = f"{specs.context_length}"

            # 有些API返回参数信息
            if "parameters" in model_data:
                specs.parameter_count = model_data["parameters"]
            elif "parameter_count" in model_data:
                specs.parameter_count = model_data["parameter_count"]

        # 2. 从已知映射中查找
        model_key = self._normalize_model_name(model_name)
        if not specs.parameter_count and model_key in self.KNOWN_MODEL_PARAMS:
            specs.parameter_count = self.KNOWN_MODEL_PARAMS[model_key]
            logger.debug(
                f"Found known parameter count for {model_name}: {specs.parameter_count}M"
            )

        if not specs.context_length:
            if model_key in self.KNOWN_MODEL_CONTEXT:
                specs.context_length = self.KNOWN_MODEL_CONTEXT[model_key]
                logger.debug(
                    f"Found known context length for {model_name}: {specs.context_length}"
                )
            else:
                # 使用默认值
                specs.context_length = self.KNOWN_MODEL_CONTEXT["default"]
                logger.debug(
                    f"Using default context length for {model_name}: {specs.context_length}"
                )

        # 3. 从模型名称中提取参数数量
        if not specs.parameter_count:
            param_info = self._extract_parameter_size(model_name)
            if param_info:
                specs.parameter_size_text = param_info[1]
                specs.parameter_count = param_info[0]
                logger.debug(
                    f"Extracted parameter size from name {model_name}: {specs.parameter_size_text} -> {specs.parameter_count}M"
                )

        # 4. 从模型名称中提取上下文长度
        if not specs.context_length:
            context_info = self._extract_context_length(model_name)
            if context_info:
                specs.context_text = context_info[1]
                specs.context_length = context_info[0]
                logger.debug(
                    f"Extracted context length from name {model_name}: {specs.context_text} -> {specs.context_length}"
                )

        return specs

    def _normalize_model_name(self, model_name: str) -> str:
        """标准化模型名称用于查找"""
        # 移除常见前缀
        name = model_name.lower()
        for prefix in [
            "google/",
            "openai/",
            "anthropic/",
            "meta/",
            "qwen/",
            "deepseek/",
            "moonshot/",
        ]:
            if name.startswith(prefix):
                name = name[len(prefix) :]
                break

        # 移除常见后缀
        for suffix in ["-instruct", "-chat", "-it", "-base", "-latest", "-preview"]:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break

        return name

    def _extract_parameter_size(self, model_name: str) -> Optional[tuple[int, str]]:
        """从模型名称提取参数大小"""
        name_lower = model_name.lower()

        for pattern in self.PARAMETER_PATTERNS:
            match = re.search(pattern, name_lower)
            if match:
                size_text = match.group(1)
                try:
                    if "b" in pattern:  # billions
                        param_count = int(float(size_text) * 1000)
                        return param_count, f"{size_text}b"
                    elif "m" in pattern:  # millions
                        param_count = int(float(size_text))
                        return param_count, f"{size_text}m"
                    elif "k" in pattern:  # thousands
                        param_count = int(float(size_text) / 1000)
                        return param_count, f"{size_text}k"
                except (ValueError, TypeError):
                    continue

        return None

    def _extract_context_length(self, model_name: str) -> Optional[tuple[int, str]]:
        """从模型名称提取上下文长度"""
        name_lower = model_name.lower()

        for pattern in self.CONTEXT_PATTERNS:
            match = re.search(pattern, name_lower)
            if match:
                context_text = match.group(1)
                try:
                    if "k" in pattern:
                        context_length = int(float(context_text) * 1000)
                        return context_length, f"{context_text}k"
                    elif "m" in pattern:
                        context_length = int(float(context_text) * 1000000)
                        return context_length, f"{context_text}m"
                    else:
                        context_length = int(context_text)
                        return context_length, context_text
                except (ValueError, TypeError):
                    continue

        return None

    def batch_analyze_models(
        self, models_data: dict[str, Any]
    ) -> dict[str, ModelSpecs]:
        """批量分析模型"""
        results = {}

        for model_name, model_info in models_data.items():
            specs = self.analyze_model(model_name, model_info)
            results[model_name] = specs

        return results

    def extract_tags_from_model_name(self, model_name: str) -> list[str]:
        """从模型名称中提取标签"""
        import re

        if not model_name:
            return []

        # 使用多种分隔符进行拆分
        separators = r"[:/\-_@,]"
        parts = re.split(separators, model_name.lower())

        tags = []
        for part in parts:
            part = part.strip()
            if part and len(part) > 0:
                tags.append(part)

        # 去重并保持顺序
        seen = set()
        unique_tags = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)

        return unique_tags


# 全局分析器实例
_analyzer: Optional[ModelAnalyzer] = None


def get_model_analyzer() -> ModelAnalyzer:
    """获取全局模型分析器实例"""
    global _analyzer
    if _analyzer is None:
        _analyzer = ModelAnalyzer()
    return _analyzer
