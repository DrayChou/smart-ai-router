"""
大小过滤器和相关功能
"""
import re
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ChannelCandidate


@dataclass
class SizeFilter:
    """大小过滤器"""
    operator: str  # >, <, >=, <=, =
    value: float
    unit: str  # b, m, k for parameters; ki, ko, mi, mo for context
    type: str  # 'params', 'input_context', 'output_context'

    def matches(self, target_value: float) -> bool:
        """检查目标值是否匹配过滤条件"""
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
            
            # 确定上下文类型
            context_type = 'input_context'
            if unit.lower().endswith('o'):
                context_type = 'output_context'
            elif unit.lower().endswith('i'):
                context_type = 'input_context'
            else:
                # 默认处理为输入上下文
                context_type = 'input_context'

            return SizeFilter(
                operator=operator,
                value=value,
                unit=unit,
                type=context_type
            )
        except ValueError:
            return None

    return None


def apply_size_filters(candidates: list['ChannelCandidate'], size_filters: list[SizeFilter]) -> list['ChannelCandidate']:
    """应用大小过滤器到候选渠道列表
    
    Args:
        candidates: 候选渠道列表
        size_filters: 大小过滤器列表
        
    Returns:
        过滤后的候选渠道列表
    """
    if not size_filters:
        return candidates
    
    from core.utils.model_analyzer import get_model_analyzer
    analyzer = get_model_analyzer()
    
    filtered_candidates = []
    
    for candidate in candidates:
        # 获取模型分析信息
        model_analysis = analyzer.get_model_analysis(candidate.channel.id, candidate.model_name)
        
        if not model_analysis:
            # 如果没有分析信息，跳过这个候选者
            continue
        
        # 检查是否所有过滤器都匹配
        matches_all_filters = True
        
        for filter_obj in size_filters:
            if filter_obj.type == 'params':
                # 检查参数大小
                param_count = model_analysis.get('parameter_count', 0)
                if param_count == 0:
                    matches_all_filters = False
                    break
                
                # 根据单位转换参数数量
                if filter_obj.unit.lower() == 'b':
                    target_value = param_count / 1e9  # 转换为十亿
                elif filter_obj.unit.lower() == 'm':
                    target_value = param_count / 1e6  # 转换为百万
                elif filter_obj.unit.lower() == 'k':
                    target_value = param_count / 1e3  # 转换为千
                else:
                    matches_all_filters = False
                    break
                
                if not filter_obj.matches(target_value):
                    matches_all_filters = False
                    break
                    
            elif filter_obj.type in ['input_context', 'output_context']:
                # 检查上下文大小
                context_key = 'max_input_context' if filter_obj.type == 'input_context' else 'max_output_context'
                context_size = model_analysis.get(context_key, 0)
                
                if context_size == 0:
                    matches_all_filters = False
                    break
                
                # 根据单位转换上下文大小
                unit_lower = filter_obj.unit.lower()
                if unit_lower in ['ki', 'i']:
                    target_value = context_size / 1000  # 转换为K tokens
                elif unit_lower in ['ko', 'o']:
                    target_value = context_size / 1000  # 转换为K tokens
                elif unit_lower in ['mi']:
                    target_value = context_size / 1e6  # 转换为M tokens
                elif unit_lower in ['mo']:
                    target_value = context_size / 1e6  # 转换为M tokens
                else:
                    matches_all_filters = False
                    break
                
                if not filter_obj.matches(target_value):
                    matches_all_filters = False
                    break
        
        if matches_all_filters:
            filtered_candidates.append(candidate)
    
    return filtered_candidates