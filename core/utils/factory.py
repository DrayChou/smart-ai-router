# -*- coding: utf-8 -*-
"""
统一工厂函数
减少重复的单例模式代码
"""
import threading
from typing import Callable, Optional, Type, TypeVar

T = TypeVar("T")


class SingletonFactory:
    """线程安全的单例工厂"""

    def __init__(self):
        self._instances = {}
        self._locks = {}
        self._main_lock = threading.Lock()

    def get_instance(
        self, cls: Type[T], factory_func: Optional[Callable[[], T]] = None
    ) -> T:
        """获取单例实例（线程安全）"""
        cls_name = cls.__name__

        # 检查是否已有实例
        if cls_name in self._instances:
            return self._instances[cls_name]

        # 获取或创建类专用锁
        if cls_name not in self._locks:
            with self._main_lock:
                if cls_name not in self._locks:
                    self._locks[cls_name] = threading.Lock()

        # 双重检查锁定模式
        with self._locks[cls_name]:
            if cls_name not in self._instances:
                if factory_func:
                    instance = factory_func()
                else:
                    instance = cls()
                self._instances[cls_name] = instance

            return self._instances[cls_name]

    def clear_instance(self, cls: Type[T]) -> None:
        """清除指定类的实例"""
        cls_name = cls.__name__
        if cls_name in self._instances:
            with self._locks.get(cls_name, threading.Lock()):
                self._instances.pop(cls_name, None)

    def clear_all(self) -> None:
        """清除所有实例"""
        with self._main_lock:
            self._instances.clear()
            self._locks.clear()


# 全局工厂实例
_global_factory = SingletonFactory()


def get_singleton(cls: Type[T], factory_func: Optional[Callable[[], T]] = None) -> T:
    """获取单例实例的便捷函数"""
    return _global_factory.get_instance(cls, factory_func)


def clear_singleton(cls: Type[T]) -> None:
    """清除单例实例的便捷函数"""
    _global_factory.clear_instance(cls)


def clear_all_singletons() -> None:
    """清除所有单例实例"""
    _global_factory.clear_all()
