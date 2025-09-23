"""
参数量比较查询处理器
支持 qwen3->8b、qwen3-<72b 等语法进行模型参数量比较筛选
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ParameterComparison:
    """参数量比较信息"""

    model_prefix: str  # 模型前缀，如 "qwen3"
    operator: str  # 比较操作符，如 ">" 或 "<"
    target_params: float  # 目标参数量(以十亿计)，如 8.0
    raw_query: str  # 原始查询字符串


class ParameterComparator:
    """参数量比较处理器"""

    def __init__(self):
        # 支持的比较操作符模式
        self.comparison_patterns = [
            r"^(.+?)->(\d+(?:\.\d+)?[bBmMkK]?)$",  # qwen3->8b (大于)
            r"^(.+?)-<(\d+(?:\.\d+)?[bBmMkK]?)$",  # qwen3-<72b (小于)
            r"^(.+?)->=(\d+(?:\.\d+)?[bBmMkK]?)$",  # qwen3->=8b (大于等于)
            r"^(.+?)-<=(\d+(?:\.\d+)?[bBmMkK]?)$",  # qwen3-<=30b (小于等于)
        ]

        # 操作符映射
        self.operator_mapping = {
            "->": ">",  # 大于
            "-<": "<",  # 小于
            "->=": ">=",  # 大于等于
            "-<=": "<=",  # 小于等于
        }

    def is_parameter_comparison(self, query: str) -> bool:
        """检查查询是否是参数量比较格式"""
        for pattern in self.comparison_patterns:
            if re.match(pattern, query, re.IGNORECASE):
                return True
        return False

    def parse_comparison(self, query: str) -> Optional[ParameterComparison]:
        """解析参数量比较查询"""
        try:
            for pattern in self.comparison_patterns:
                match = re.match(pattern, query, re.IGNORECASE)
                if match:
                    model_prefix = match.group(1).strip()
                    param_str = match.group(2).strip()

                    # 确定操作符
                    if "->" in query:
                        operator = ">"
                    elif "-<" in query:
                        operator = "<"
                    elif "->=" in query:
                        operator = ">="
                    elif "-<=" in query:
                        operator = "<="
                    else:
                        continue

                    # 解析参数量
                    target_params = self._parse_parameter_size(param_str)
                    if target_params is None:
                        continue

                    logger.info(
                        f"🔍 PARAMETER COMPARISON: Parsed '{query}' -> prefix='{model_prefix}', operator='{operator}', target={target_params}B"
                    )

                    return ParameterComparison(
                        model_prefix=model_prefix,
                        operator=operator,
                        target_params=target_params,
                        raw_query=query,
                    )

            logger.warning(
                f"❌ PARSE FAILED: Could not parse parameter comparison '{query}'"
            )
            return None

        except Exception as e:
            logger.error(
                f"❌ PARSE ERROR: Failed to parse parameter comparison '{query}': {e}"
            )
            return None

    def _parse_parameter_size(self, param_str: str) -> Optional[float]:
        """解析参数量字符串为标准数值（以十亿为单位）

        支持的格式：
        - 270m -> 0.27B
        - 8b -> 8.0B
        - 120b -> 120.0B
        - 1.7b -> 1.7B
        - 2k -> 0.000002B
        """
        try:
            # 移除空格并转换为小写
            param_str = param_str.strip().lower()

            # 提取数字部分和单位
            match = re.match(r"^(\d+(?:\.\d+)?)([bkmgt]?)$", param_str)
            if not match:
                logger.warning(
                    f"❌ PARAM FORMAT: Invalid parameter format '{param_str}'"
                )
                return None

            value = float(match.group(1))
            unit = match.group(2)

            # 单位转换 - 统一转换为十亿参数(B)
            if unit in ["", "b"]:  # 默认或明确的十亿(B)
                converted = value
            elif unit == "m":  # 百万(M) -> 除以1000转换为B
                converted = value / 1000.0
            elif unit == "k":  # 千(K) -> 除以1,000,000转换为B
                converted = value / 1000000.0
            elif unit == "t":  # 万亿(T) -> 乘以1000转换为B
                converted = value * 1000.0
            elif unit == "g":  # 十亿(G) - 同B
                converted = value
            else:
                logger.warning(f"❌ UNIT ERROR: Unknown unit '{unit}' in '{param_str}'")
                return None

            logger.debug(f"🔢 CONVERSION: '{param_str}' -> {converted:.6f}B")
            return converted

        except Exception as e:
            logger.error(
                f"❌ CONVERSION ERROR: Failed to parse parameter size '{param_str}': {e}"
            )
            return None

    def extract_model_parameters(self, model_name: str) -> Optional[float]:
        """从模型名称中提取参数量信息

        支持识别各种参数量格式：
        - 270m -> 0.27B
        - 8b -> 8.0B
        - 120b -> 120.0B
        - 1.7b -> 1.7B
        - gemma-3-270m-it -> 0.27B
        - qwen3-4b-2507 -> 4.0B
        """
        try:
            # 常见的参数量表示模式 - 按优先级排序
            patterns = [
                # 直接数字+单位模式（高优先级）
                r"(\d+(?:\.\d+)?)[bB]",  # 8B, 70B, 1.5B
                r"(\d+(?:\.\d+)?)[mM]",  # 270M, 405M
                r"(\d+(?:\.\d+)?)[kK]",  # 7K (罕见)
                r"(\d+(?:\.\d+)?)[tT]",  # 1T (未来可能)
                # 分隔符包围的格式
                r"-(\d+(?:\.\d+)?)[bB]-",  # -8B-, -70B-
                r"_(\d+(?:\.\d+)?)[bB]_",  # _8B_, _70B_
                r"-(\d+(?:\.\d+)?)[mM]-",  # -270M-
                r"_(\d+(?:\.\d+)?)[mM]_",  # _270M_
                # 边界格式
                r"(\d+(?:\.\d+)?)[bB](?:-|_)",  # 8B-, 70B_
                r"(?:-|_)(\d+(?:\.\d+)?)[bB]",  # -8B, _70B
                r"(\d+(?:\.\d+)?)[mM](?:-|_)",  # 270M-, 405M_
                r"(?:-|_)(\d+(?:\.\d+)?)[mM]",  # -270M, _405M
                # 纯数字（假设为B，低优先级）
                r"-(\d+)-",  # -8-, -70-
                r"_(\d+)_",  # _8_, _70_
            ]

            model_lower = model_name.lower()

            for pattern in patterns:
                matches = re.findall(pattern, model_lower)
                if matches:
                    for match in matches:
                        try:
                            # 获取数值
                            if isinstance(match, tuple):
                                value_str = match[0]
                            else:
                                value_str = match

                            value = float(value_str)

                            # 根据模式确定单位并转换
                            if "m" in pattern.lower():
                                # 百万参数 -> 转换为B
                                params = value / 1000.0
                                logger.debug(f"🔢 M->B: {value}M -> {params:.6f}B")
                            elif "k" in pattern.lower():
                                # 千参数 -> 转换为B
                                params = value / 1000000.0
                                logger.debug(f"🔢 K->B: {value}K -> {params:.6f}B")
                            elif "t" in pattern.lower():
                                # 万亿参数 -> 转换为B
                                params = value * 1000.0
                                logger.debug(f"🔢 T->B: {value}T -> {params:.6f}B")
                            else:
                                # 默认十亿参数
                                params = value
                                logger.debug(f"🔢 B->B: {value}B -> {params:.6f}B")

                            # 验证合理性（模型参数量通常在0.001B到10000B之间）
                            if 0.001 <= params <= 10000:
                                logger.debug(
                                    f"🔍 PARAM EXTRACT: '{model_name}' -> {params:.6f}B parameters"
                                )
                                return params

                        except ValueError:
                            continue

            # 特殊模型名称映射
            special_mappings = {
                "gpt-3.5": 20.0,
                "gpt-4": 1760.0,  # 估计值
                "claude-3-haiku": 20.0,
                "claude-3-sonnet": 70.0,
                "claude-3-opus": 175.0,
                "gemini-pro": 70.0,
                "gemini-ultra": 540.0,
            }

            model_lower = model_name.lower()
            for special_name, params in special_mappings.items():
                if special_name in model_lower:
                    logger.debug(
                        f"🔍 SPECIAL MAPPING: '{model_name}' -> {params}B parameters (mapped)"
                    )
                    return params

            # 如果无法提取，记录但不报错
            logger.debug(
                f"🔍 NO PARAMS: Could not extract parameters from '{model_name}'"
            )
            return None

        except Exception as e:
            logger.debug(
                f"🔍 EXTRACT ERROR: Failed to extract parameters from '{model_name}': {e}"
            )
            return None

    def filter_models_by_comparison(
        self, comparison: ParameterComparison, models_cache: dict[str, Any]
    ) -> list[tuple[str, str, float]]:
        """根据参数量比较筛选模型

        Returns:
            list[tuple[channel_id, model_name, params]]: 匹配的渠道ID、模型名和参数量
        """
        try:
            matching_models = []
            total_checked = 0
            prefix_matched = 0
            param_extracted = 0
            comparison_matched = 0

            logger.info(
                f"🔍 COMPARISON FILTER: Starting search for '{comparison.raw_query}'"
            )
            logger.info(
                f"🔍 TARGET: {comparison.model_prefix} models {comparison.operator} {comparison.target_params}B"
            )

            # 遍历所有缓存的渠道
            for channel_id, cache_data in models_cache.items():
                if not isinstance(cache_data, dict) or "models" not in cache_data:
                    continue

                models = cache_data.get("models", [])
                total_checked += len(models)

                for model_name in models:
                    # 1. 检查模型前缀匹配
                    if not self._model_matches_prefix(
                        model_name, comparison.model_prefix
                    ):
                        continue

                    prefix_matched += 1

                    # 2. 提取模型参数量
                    model_params = self.extract_model_parameters(model_name)
                    if model_params is None:
                        continue

                    param_extracted += 1

                    # 3. 执行参数量比较
                    if self._compare_parameters(
                        model_params, comparison.operator, comparison.target_params
                    ):
                        comparison_matched += 1
                        matching_models.append((channel_id, model_name, model_params))
                        logger.debug(
                            f"✅ MATCH: {model_name} ({model_params}B) in {channel_id}"
                        )

            # 按参数量排序（大的在前）
            matching_models.sort(key=lambda x: x[2], reverse=True)

            logger.info(
                f"🔍 FILTER STATS: checked={total_checked}, prefix_matched={prefix_matched}, "
                f"param_extracted={param_extracted}, final_matched={comparison_matched}"
            )
            logger.info(
                f"✅ COMPARISON RESULT: Found {len(matching_models)} models matching '{comparison.raw_query}'"
            )

            return matching_models

        except Exception as e:
            logger.error(f"❌ FILTER ERROR: Failed to filter models by comparison: {e}")
            return []

    def _model_matches_prefix(self, model_name: str, prefix: str) -> bool:
        """检查模型名是否匹配前缀"""
        try:
            model_lower = model_name.lower()
            prefix_lower = prefix.lower()

            # 直接前缀匹配
            if model_lower.startswith(prefix_lower):
                return True

            # 考虑分隔符的情况
            separators = ["/", "-", "_", ":"]
            for sep in separators:
                if prefix_lower + sep in model_lower:
                    return True
                if sep + prefix_lower in model_lower:
                    return True

            # 考虑部分匹配（更宽松）
            if prefix_lower in model_lower:
                # 检查是否是独立词汇（避免误匹配）
                words = re.split(r"[/-_:.\s]", model_lower)
                prefix_words = re.split(r"[/-_:.\s]", prefix_lower)

                for prefix_word in prefix_words:
                    if any(prefix_word in word for word in words):
                        return True

            return False

        except Exception as e:
            logger.debug(
                f"🔍 PREFIX ERROR: Failed to check prefix match for '{model_name}' vs '{prefix}': {e}"
            )
            return False

    def _compare_parameters(
        self, model_params: float, operator: str, target_params: float
    ) -> bool:
        """执行参数量比较"""
        try:
            if operator == ">":
                return model_params > target_params
            elif operator == "<":
                return model_params < target_params
            elif operator == ">=":
                return model_params >= target_params
            elif operator == "<=":
                return model_params <= target_params
            else:
                logger.warning(f"❌ UNKNOWN OPERATOR: '{operator}'")
                return False

        except Exception as e:
            logger.error(
                f"❌ COMPARISON ERROR: Failed to compare {model_params} {operator} {target_params}: {e}"
            )
            return False


# 全局实例
_parameter_comparator = None


def get_parameter_comparator() -> ParameterComparator:
    """获取全局参数量比较器实例"""
    global _parameter_comparator
    if _parameter_comparator is None:
        _parameter_comparator = ParameterComparator()
    return _parameter_comparator
