# -*- coding: utf-8 -*-
"""
大小过滤器
从json_router.py中提取的大小过滤功能
"""
import logging
import re
from dataclasses import dataclass
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ChannelCandidate

logger = logging.getLogger(__name__)


@dataclass
class SizeFilter:
    """大小过滤器"""
    operator: str  # >, <, >=, <=, =
    value: float
    unit: str  # b, m, k for parameters; ki, ko, mi, mo for context
    type: str  # 'params', 'input_context', 'output_context'

    def matches(self, target_value: float) -> bool:
        """检查目标值是否匹配过滤条件"""
        if target_value is None:
            return False
            
        if self.operator == ">":
            return target_value > self.value
        elif self.operator == "<":
            return target_value < self.value
        elif self.operator == ">=":
            return target_value >= self.value
        elif self.operator == "<=":
            return target_value <= self.value
        elif self.operator == "=":
            return target_value == self.value
        return False


def parse_size_filter(tag: str) -> Optional[SizeFilter]:
    """解析大小过滤标签

    Args:
        tag: 标签字符串，如 ">20b", "<8ko", ">=10ki"

    Returns:
        SizeFilter 对象，如果解析失败则返回 None
    """
    # 参数大小过滤模式：>20b, <7b, >=1.5b
    param_pattern = r'^([><=]+)(\d+\.?\d*)([bmk])$'
    # 上下文大小过滤模式：>10ki, <8ko, >=32mi
    context_pattern = r'^([><=]+)(\d+\.?\d*)([kK]?[iI]|[mM]?[oO])$'

    # 先尝试参数大小过滤
    match = re.match(param_pattern, tag, re.IGNORECASE)
    if match:
        operator, value_str, unit = match.groups()
        try:
            value = float(value_str)
            # 转换单位到基本单位
            if unit.lower() == 'b':
                pass  # 1b = 1 billion parameters
            elif unit.lower() == 'm':
                pass  # 1m = 1 million parameters
            elif unit.lower() == 'k':
                pass  # 1k = 1 thousand parameters
            else:
                return None

            return SizeFilter(
                operator=operator,
                value=value,
                unit=unit,
                type='params'
            )
        except ValueError:
            return None

    # 再尝试上下文大小过滤
    match = re.match(context_pattern, tag, re.IGNORECASE)
    if match:
        operator, value_str, unit = match.groups()
        try:
            value = float(value_str)
            
            # 确定过滤类型
            filter_type = 'input_context'
            if unit.lower().endswith('o'):
                filter_type = 'output_context'
            elif unit.lower().endswith('i'):
                filter_type = 'input_context'
            
            return SizeFilter(
                operator=operator,
                value=value,
                unit=unit,
                type=filter_type
            )
        except ValueError:
            return None

    return None


def apply_size_filters(candidates: List['ChannelCandidate'], size_filters: List[SizeFilter]) -> List['ChannelCandidate']:
    """应用大小过滤器到候选渠道列表
    
    Args:
        candidates: 候选渠道列表
        size_filters: 大小过滤器列表
        
    Returns:
        过滤后的候选渠道列表
    """
    if not size_filters:
        return candidates

    logger.info(f"SIZE FILTERS: Applying {len(size_filters)} filters to {len(candidates)} candidates")
    
    filtered_candidates = []
    
    for candidate in candidates:
        match = True
        model_name = candidate.matched_model or candidate.channel.model_name
        
        # 获取模型规格信息
        from ..utils.model_analyzer import get_model_analyzer
        model_analyzer = get_model_analyzer()
        specs = model_analyzer.get_model_specs(model_name)
        
        # 获取模型缓存数据
        from ..yaml_config import get_yaml_config_loader
        config_loader = get_yaml_config_loader()
        model_cache = config_loader.get_model_cache_by_channel(candidate.channel.id)
        model_data = None
        if model_cache and 'models' in model_cache:
            for cached_model in model_cache['models']:
                if isinstance(cached_model, dict) and cached_model.get('id') == model_name:
                    model_data = cached_model
                    break
        
        # 应用每个过滤器
        for size_filter in size_filters:
            if size_filter.type == 'params':
                # 参数大小过滤
                if specs and specs.parameter_count:
                    # parameter_count 以百万为单位，需要转换为 billion 进行比较
                    param_count_billions = specs.parameter_count / 1000.0
                    logger.debug(f"Model {model_name}: {specs.parameter_count}M params = {param_count_billions}B")

                    if not size_filter.matches(param_count_billions):
                        logger.debug(f"SIZE FILTER: {model_name} filtered out - {param_count_billions}B params does not match {size_filter.operator}{size_filter.value}b")
                        match = False
                        break
                else:
                    logger.debug(f"SIZE FILTER: {model_name} filtered out - no parameter count available")
                    match = False
                    break

            elif size_filter.type == 'input_context':
                # 输入上下文大小过滤
                context_size = None
                if specs and specs.context_length:
                    context_size = specs.context_length
                elif model_data and model_data.get("max_input_tokens"):
                    context_size = model_data["max_input_tokens"]
                elif model_data and model_data.get("context_length"):
                    context_size = model_data["context_length"]

                if context_size:
                    # 转换为千为单位进行比较
                    context_size_k = context_size / 1000.0
                    logger.debug(f"Model {model_name}: {context_size} input tokens = {context_size_k}k")

                    if not size_filter.matches(context_size_k):
                        logger.debug(f"SIZE FILTER: {model_name} filtered out - {context_size_k}ki does not match {size_filter.operator}{size_filter.value}ki")
                        match = False
                        break
                else:
                    logger.debug(f"SIZE FILTER: {model_name} filtered out - no input context size available")
                    match = False
                    break

            elif size_filter.type == 'output_context':
                # 输出上下文大小过滤
                context_size = None
                if model_data and model_data.get("max_output_tokens"):
                    context_size = model_data["max_output_tokens"]
                elif specs and specs.context_length:
                    # 如果没有专门的输出限制，使用总上下文长度作为近似
                    context_size = specs.context_length
                elif model_data and model_data.get("context_length"):
                    context_size = model_data["context_length"]

                if context_size:
                    # 转换为千为单位进行比较
                    context_size_k = context_size / 1000.0
                    logger.debug(f"Model {model_name}: {context_size} output tokens = {context_size_k}k")

                    if not size_filter.matches(context_size_k):
                        logger.debug(f"SIZE FILTER: {model_name} filtered out - {context_size_k}ko does not match {size_filter.operator}{size_filter.value}ko")
                        match = False
                        break
                else:
                    logger.debug(f"SIZE FILTER: {model_name} filtered out - no output context size available")
                    match = False
                    break

        if match:
            filtered_candidates.append(candidate)
            logger.debug(f"SIZE FILTER: {model_name} passed all filters")

    logger.info(f"SIZE FILTERS: Filtered from {len(candidates)} to {len(filtered_candidates)} candidates")
    return filtered_candidates