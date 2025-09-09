"""
路由异常定义
"""


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