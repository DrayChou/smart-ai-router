"""
路由异常定义 - 重定向到统一异常系统
"""

# 导入统一异常系统
from ..exceptions import TagNotFoundError, ParameterComparisonError

# 保持向后兼容
__all__ = ["TagNotFoundError", "ParameterComparisonError"]
