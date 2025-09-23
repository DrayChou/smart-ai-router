"""
线程安全的单例管理器
用于替换项目中的全局变量模式
"""

import threading
from functools import wraps
from typing import Any, Callable, Dict, Optional, Type, TypeVar

T = TypeVar("T")


class ThreadSafeSingleton:
    """线程安全的单例基类"""

    _instances: Dict[Type, Any] = {}
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                # 双重检查锁定
                if cls not in cls._instances:
                    instance = super().__new__(cls)
                    cls._instances[cls] = instance
        return cls._instances[cls]

    @classmethod
    def get_instance(cls: Type[T]) -> T:
        """获取单例实例"""
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = cls()
        return cls._instances[cls]

    @classmethod
    def clear_instance(cls):
        """清除单例实例（主要用于测试）"""
        with cls._lock:
            if cls in cls._instances:
                del cls._instances[cls]


class SingletonFactory:
    """单例工厂，管理所有单例实例"""

    _instances: Dict[str, Any] = {}
    _factories: Dict[str, Callable] = {}
    _lock = threading.RLock()

    @classmethod
    def register(cls, name: str, factory: Callable[[], T]) -> None:
        """注册单例工厂函数"""
        with cls._lock:
            cls._factories[name] = factory

    @classmethod
    def get(cls, name: str) -> Any:
        """获取单例实例"""
        if name not in cls._instances:
            with cls._lock:
                # 双重检查锁定
                if name not in cls._instances:
                    if name not in cls._factories:
                        raise ValueError(f"No factory registered for '{name}'")
                    cls._instances[name] = cls._factories[name]()
        return cls._instances[name]

    @classmethod
    def clear(cls, name: Optional[str] = None) -> None:
        """清除单例实例"""
        with cls._lock:
            if name is None:
                cls._instances.clear()
            elif name in cls._instances:
                del cls._instances[name]

    @classmethod
    def is_initialized(cls, name: str) -> bool:
        """检查单例是否已初始化"""
        return name in cls._instances


def singleton_factory(name: str):
    """装饰器：将函数注册为单例工厂"""

    def decorator(func: Callable[[], T]) -> Callable[[], T]:
        SingletonFactory.register(name, func)

        @wraps(func)
        def wrapper() -> T:
            return SingletonFactory.get(name)

        return wrapper

    return decorator


class LazyInit:
    """延迟初始化包装器"""

    def __init__(self, factory: Callable[[], T]):
        self._factory = factory
        self._instance: Optional[T] = None
        self._lock = threading.RLock()

    def get(self) -> T:
        """获取实例（延迟初始化）"""
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self._instance = self._factory()
        return self._instance

    def clear(self) -> None:
        """清除实例"""
        with self._lock:
            self._instance = None

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._instance is not None


class ThreadSafeContainer:
    """线程安全的容器，用于替代全局变量"""

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def set(self, key: str, value: Any) -> None:
        """设置值"""
        with self._lock:
            self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """获取值"""
        with self._lock:
            return self._data.get(key, default)

    def get_or_create(self, key: str, factory: Callable[[], Any]) -> Any:
        """获取值，如果不存在则创建"""
        if key not in self._data:
            with self._lock:
                if key not in self._data:
                    self._data[key] = factory()
        return self._data[key]

    def delete(self, key: str) -> bool:
        """删除值"""
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def clear(self) -> None:
        """清除所有值"""
        with self._lock:
            self._data.clear()

    def keys(self):
        """获取所有键"""
        with self._lock:
            return list(self._data.keys())


# 全局容器实例
_global_container = ThreadSafeContainer()


def get_global_container() -> ThreadSafeContainer:
    """获取全局容器"""
    return _global_container


# 便捷函数
def set_global(key: str, value: Any) -> None:
    """设置全局值"""
    _global_container.set(key, value)


def get_global(key: str, default: Any = None) -> Any:
    """获取全局值"""
    return _global_container.get(key, default)


def get_or_create_global(key: str, factory: Callable[[], Any]) -> Any:
    """获取全局值，如果不存在则创建"""
    return _global_container.get_or_create(key, factory)
