"""
空指针安全保护工具
提供安全的对象访问和操作方法
"""

import logging
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def safe_get(obj: Any, key: str, default: Any = None) -> Any:
    """
    安全获取对象属性或字典键值

    Args:
        obj: 对象或字典
        key: 键名或属性名
        default: 默认值

    Returns:
        获取到的值或默认值
    """
    if obj is None:
        return default

    try:
        if isinstance(obj, dict):
            return obj.get(key, default)
        elif hasattr(obj, key):
            return getattr(obj, key, default)
        else:
            return default
    except (AttributeError, KeyError, TypeError):
        return default


def safe_getattr(obj: Any, attr: str, default: Any = None) -> Any:
    """
    安全获取对象属性

    Args:
        obj: 对象
        attr: 属性名
        default: 默认值

    Returns:
        属性值或默认值
    """
    if obj is None:
        return default

    try:
        return getattr(obj, attr, default)
    except (AttributeError, TypeError):
        return default


def safe_call(func: Optional[Callable], *args, default: Any = None, **kwargs) -> Any:
    """
    安全调用函数

    Args:
        func: 函数对象
        *args: 位置参数
        default: 调用失败时的默认返回值
        **kwargs: 关键字参数

    Returns:
        函数调用结果或默认值
    """
    if func is None or not callable(func):
        return default

    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.warning(f"Safe call failed for {func}: {e}")
        return default


def safe_chain(*accessors, default: Any = None) -> Any:
    """
    安全的链式访问

    Args:
        *accessors: 访问器函数列表
        default: 默认值

    Returns:
        链式访问结果或默认值

    Example:
        safe_chain(
            lambda: config_loader,
            lambda x: x.config,
            lambda x: x.auth,
            lambda x: x.enabled,
            default=False
        )
    """
    try:
        result = None
        for accessor in accessors:
            if callable(accessor):
                result = accessor(result) if result is not None else accessor()
            else:
                result = accessor

            if result is None:
                return default

        return result
    except Exception as e:
        logger.debug(f"Safe chain access failed: {e}")
        return default


def ensure_not_none(value: T, error_message: str = "Value cannot be None") -> T:
    """
    确保值不为None，否则抛出异常

    Args:
        value: 要检查的值
        error_message: 错误信息

    Returns:
        原值（如果不为None）

    Raises:
        ValueError: 如果值为None
    """
    if value is None:
        raise ValueError(error_message)
    return value


def coalesce(*values: Any) -> Any:
    """
    返回第一个非None值

    Args:
        *values: 值列表

    Returns:
        第一个非None值，如果都为None则返回None
    """
    for value in values:
        if value is not None:
            return value
    return None


def safe_len(obj: Any, default: int = 0) -> int:
    """
    安全获取对象长度

    Args:
        obj: 对象
        default: 默认长度

    Returns:
        对象长度或默认值
    """
    if obj is None:
        return default

    try:
        return len(obj)
    except (TypeError, AttributeError):
        return default


def safe_bool(obj: Any, default: bool = False) -> bool:
    """
    安全转换为布尔值

    Args:
        obj: 对象
        default: 默认值

    Returns:
        布尔值或默认值
    """
    if obj is None:
        return default

    try:
        return bool(obj)
    except Exception:
        return default


def safe_str(obj: Any, default: str = "") -> str:
    """
    安全转换为字符串

    Args:
        obj: 对象
        default: 默认值

    Returns:
        字符串或默认值
    """
    if obj is None:
        return default

    try:
        return str(obj)
    except Exception:
        return default


def safe_int(obj: Any, default: int = 0) -> int:
    """
    安全转换为整数

    Args:
        obj: 对象
        default: 默认值

    Returns:
        整数或默认值
    """
    if obj is None:
        return default

    try:
        return int(obj)
    except (ValueError, TypeError):
        return default


def safe_float(obj: Any, default: float = 0.0) -> float:
    """
    安全转换为浮点数

    Args:
        obj: 对象
        default: 默认值

    Returns:
        浮点数或默认值
    """
    if obj is None:
        return default

    try:
        return float(obj)
    except (ValueError, TypeError):
        return default


def safe_dict_access(
    d: Optional[dict], path: str, default: Any = None, separator: str = "."
) -> Any:
    """
    安全的嵌套字典访问

    Args:
        d: 字典
        path: 访问路径，如 "a.b.c"
        default: 默认值
        separator: 路径分隔符

    Returns:
        访问到的值或默认值

    Example:
        safe_dict_access({"a": {"b": {"c": 123}}}, "a.b.c")  # 返回 123
        safe_dict_access({"a": {"b": {}}}, "a.b.c", "default")  # 返回 "default"
    """
    if d is None:
        return default

    try:
        keys = path.split(separator)
        current = d

        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]

        return current
    except Exception:
        return default


class SafeProxy:
    """
    安全代理类，用于包装可能为None的对象
    """

    def __init__(self, obj: Any = None):
        self._obj = obj

    def __getattr__(self, name: str) -> "SafeProxy":
        """安全获取属性"""
        if self._obj is None:
            return SafeProxy(None)

        try:
            attr = getattr(self._obj, name)
            return SafeProxy(attr)
        except AttributeError:
            return SafeProxy(None)

    def __getitem__(self, key: Any) -> "SafeProxy":
        """安全获取项"""
        if self._obj is None:
            return SafeProxy(None)

        try:
            item = self._obj[key]
            return SafeProxy(item)
        except (KeyError, IndexError, TypeError):
            return SafeProxy(None)

    def __call__(self, *args, **kwargs) -> "SafeProxy":
        """安全调用"""
        if self._obj is None or not callable(self._obj):
            return SafeProxy(None)

        try:
            result = self._obj(*args, **kwargs)
            return SafeProxy(result)
        except Exception as e:
            logger.debug(f"SafeProxy call failed: {e}")
            return SafeProxy(None)

    def value(self, default: Any = None) -> Any:
        """获取实际值"""
        return self._obj if self._obj is not None else default

    def is_none(self) -> bool:
        """检查是否为None"""
        return self._obj is None

    def __bool__(self) -> bool:
        """布尔值转换"""
        return self._obj is not None

    def __str__(self) -> str:
        """字符串表示"""
        return str(self._obj) if self._obj is not None else "None"


def safe(obj: Any) -> SafeProxy:
    """
    创建安全代理对象

    Args:
        obj: 要包装的对象

    Returns:
        SafeProxy实例

    Example:
        config = safe(config_loader).config.auth.enabled.value(False)
    """
    return SafeProxy(obj)
