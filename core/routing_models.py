"""
路由相关数据模型和异常定义
遵循KISS原则：简单的数据类和异常，无复杂业务逻辑
"""
from dataclasses import dataclass
from typing import Any, Optional, List, Dict


class TagNotFoundError(Exception):
    """标签未找到错误"""
    def __init__(self, tags: list[str], message: str = None):
        self.tags = tags
        if message is None:
            if len(tags) == 1:
                message = f"没有找到匹配标签 '{tags[0]}' 的模型"
            else:
                message = f"没有找到同时匹配标签 {tags} 的模型"
        super().__init__(message)


class ParameterComparisonError(Exception):
    """参数量比较错误"""
    def __init__(self, query: str, message: str = None):
        self.query = query
        if message is None:
            message = f"没有找到满足参数量比较 '{query}' 的模型"
        super().__init__(message)


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
            
        if self.operator == '>':
            return target_value > self.value
        elif self.operator == '<':
            return target_value < self.value
        elif self.operator == '>=':
            return target_value >= self.value
        elif self.operator == '<=':
            return target_value <= self.value
        elif self.operator == '=':
            return abs(target_value - self.value) < 0.001
        return False


@dataclass 
class RoutingScore:
    """路由评分结果"""
    channel_id: str
    total_score: float
    scores: Dict[str, float]
    estimated_cost: Optional[float] = None
    estimated_tokens: Optional[int] = None
    matched_model: Optional[str] = None
    
    
@dataclass
class ChannelCandidate:
    """渠道候选者"""
    channel_id: str
    model_name: str
    
    
@dataclass 
class RoutingRequest:
    """路由请求"""
    model: str
    messages: List[Dict[str, Any]]
    strategy: Optional[str] = None
    # 其他请求参数根据需要添加