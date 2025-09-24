"""
Provider适配器注册中心
管理所有可用的Provider适配器
"""

from typing import Any, Optional

from core.utils.logger import get_logger

from .adapters.anthropic import AnthropicAdapter
from .adapters.groq import GroqAdapter
from .adapters.openai import OpenAIAdapter
from .adapters.openrouter import OpenRouterAdapter
from .base import BaseAdapter

logger = get_logger(__name__)


class ProviderRegistry:
    """Provider适配器注册中心"""

    def __init__(self):
        self._adapters: dict[str, type[BaseAdapter]] = {}
        self._instances: dict[str, BaseAdapter] = {}
        self._register_builtin_adapters()

    def _register_builtin_adapters(self):
        """注册内置适配器"""
        self.register("OpenAIAdapter", OpenAIAdapter)
        self.register("AnthropicAdapter", AnthropicAdapter)
        self.register("GroqAdapter", GroqAdapter)
        self.register("OpenRouterAdapter", OpenRouterAdapter)

        logger.info(f"注册了{len(self._adapters)}个内置适配器")

    def register(self, adapter_class_name: str, adapter_class: type[BaseAdapter]):
        """
        注册适配器类

        Args:
            adapter_class_name: 适配器类名
            adapter_class: 适配器类
        """
        if not issubclass(adapter_class, BaseAdapter):
            raise ValueError(f"适配器类必须继承BaseAdapter: {adapter_class}")

        self._adapters[adapter_class_name] = adapter_class
        logger.info(f"注册适配器: {adapter_class_name}")

    def get_adapter_class(self, adapter_class_name: str) -> Optional[type[BaseAdapter]]:
        """
        获取适配器类

        Args:
            adapter_class_name: 适配器类名

        Returns:
            适配器类或None
        """
        return self._adapters.get(adapter_class_name)

    def create_adapter(
        self, provider_name: str, adapter_class_name: str, config: dict[str, Any]
    ) -> BaseAdapter:
        """
        创建适配器实例

        Args:
            provider_name: Provider名称
            adapter_class_name: 适配器类名
            config: 配置

        Returns:
            适配器实例
        """
        adapter_class = self.get_adapter_class(adapter_class_name)
        if not adapter_class:
            raise ValueError(f"未找到适配器类: {adapter_class_name}")

        # 创建实例
        instance = adapter_class(provider_name, config)

        # 缓存实例（如果需要）
        instance_key = f"{provider_name}:{adapter_class_name}"
        self._instances[instance_key] = instance

        logger.info(f"创建适配器实例: {provider_name} ({adapter_class_name})")
        return instance

    def get_adapter_instance(
        self, provider_name: str, adapter_class_name: str
    ) -> Optional[BaseAdapter]:
        """
        获取已创建的适配器实例

        Args:
            provider_name: Provider名称
            adapter_class_name: 适配器类名

        Returns:
            适配器实例或None
        """
        instance_key = f"{provider_name}:{adapter_class_name}"
        return self._instances.get(instance_key)

    def list_adapters(self) -> dict[str, type[BaseAdapter]]:
        """
        列出所有已注册的适配器

        Returns:
            适配器字典
        """
        return self._adapters.copy()

    def list_instances(self) -> dict[str, BaseAdapter]:
        """
        列出所有已创建的适配器实例

        Returns:
            实例字典
        """
        return self._instances.copy()

    async def cleanup(self):
        """清理所有适配器实例"""
        for instance in self._instances.values():
            try:
                await instance.close()
            except Exception as e:
                logger.warning(f"清理适配器实例失败: {e}")

        self._instances.clear()
        logger.info("适配器实例清理完成")


# 全局注册中心实例
provider_registry = ProviderRegistry()


def get_provider_registry() -> ProviderRegistry:
    """获取全局Provider注册中心"""
    return provider_registry


def register_adapter(adapter_class_name: str, adapter_class: type[BaseAdapter]) -> None:
    """
    注册适配器的便捷函数

    Args:
        adapter_class_name: 适配器类名
        adapter_class: 适配器类
    """
    provider_registry.register(adapter_class_name, adapter_class)


def create_adapter_from_config(
    provider_name: str, provider_config: dict[str, Any]
) -> BaseAdapter:
    """
    从配置创建适配器实例

    Args:
        provider_name: Provider名称
        provider_config: Provider配置

    Returns:
        适配器实例
    """
    adapter_class_name = provider_config.get("adapter_class")
    if not adapter_class_name:
        raise ValueError(f"Provider配置缺少adapter_class: {provider_name}")

    return provider_registry.create_adapter(
        provider_name, adapter_class_name, provider_config
    )
