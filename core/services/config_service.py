"""
配置服务 - 统一的配置管理
遵循KISS原则：单一配置源，优先级明确
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

logger = logging.getLogger(__name__)


class ConfigService:
    """统一配置服务 - 替代多种配置管理方式"""

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or "config/config.yaml"
        self.config_path = Path(self.config_file)
        self._config_cache: Optional[Dict[str, Any]] = None

        logger.info(f"配置服务初始化完成，配置文件: {self.config_path}")

    def get_config(self, key: str = None, default: Any = None) -> Any:
        """获取配置值 - 支持点号分隔的嵌套键"""
        config = self._load_config()

        if key is None:
            return config

        # 支持嵌套键查找 (如: "providers.openai.enabled")
        keys = key.split(".")
        value = config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def get_providers(self) -> Dict[str, Any]:
        """获取所有提供商配置"""
        return self.get_config("providers", {})

    def get_provider_config(self, provider_name: str) -> Dict[str, Any]:
        """获取指定提供商配置"""
        providers = self.get_providers()
        return providers.get(provider_name, {})

    def get_channels(self, provider_name: str = None) -> List[Dict[str, Any]]:
        """获取渠道配置"""
        if provider_name:
            provider_config = self.get_provider_config(provider_name)
            return provider_config.get("channels", [])

        # 获取所有渠道
        all_channels = []
        providers = self.get_providers()

        for provider, config in providers.items():
            channels = config.get("channels", [])
            for channel in channels:
                channel["provider"] = provider
                all_channels.append(channel)

        return all_channels

    def get_routing_strategies(self) -> Dict[str, Any]:
        """获取路由策略配置"""
        return self.get_config("routing_strategies", {})

    def is_provider_enabled(self, provider_name: str) -> bool:
        """检查提供商是否启用"""
        provider_config = self.get_provider_config(provider_name)
        return provider_config.get("enabled", False)

    def get_system_config(self) -> Dict[str, Any]:
        """获取系统配置"""
        return self.get_config("system", {})

    def get_database_url(self) -> str:
        """获取数据库URL - 优先使用环境变量"""
        # 环境变量优先
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            return db_url

        # 配置文件次之
        return self.get_config("system.database_url", "sqlite:///smart-ai-router.db")

    def get_log_level(self) -> str:
        """获取日志级别"""
        # 环境变量优先
        log_level = os.getenv("LOG_LEVEL")
        if log_level:
            return log_level.upper()

        return self.get_config("system.log_level", "INFO").upper()

    def reload_config(self) -> None:
        """重新加载配置"""
        self._config_cache = None
        logger.info("配置已重新加载")

    def validate_config(self) -> List[str]:
        """验证配置有效性，返回错误列表"""
        errors = []

        try:
            config = self._load_config()

            # 检查必要的顶级配置
            required_sections = ["providers", "system"]
            for section in required_sections:
                if section not in config:
                    errors.append(f"缺少必要的配置节: {section}")

            # 检查提供商配置
            providers = config.get("providers", {})
            if not providers:
                errors.append("未配置任何提供商")

            for provider_name, provider_config in providers.items():
                if not isinstance(provider_config, dict):
                    errors.append(f"提供商 {provider_name} 配置格式错误")
                    continue

                # 检查渠道配置
                channels = provider_config.get("channels", [])
                if provider_config.get("enabled", False) and not channels:
                    errors.append(f"启用的提供商 {provider_name} 没有配置渠道")

        except Exception as e:
            errors.append(f"配置文件加载失败: {e}")

        return errors

    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要信息"""
        try:
            config = self._load_config()
            providers = config.get("providers", {})

            summary = {
                "config_file": str(self.config_path),
                "config_exists": self.config_path.exists(),
                "providers_count": len(providers),
                "enabled_providers": [
                    name for name, cfg in providers.items() if cfg.get("enabled", False)
                ],
                "total_channels": sum(
                    len(cfg.get("channels", [])) for cfg in providers.values()
                ),
                "log_level": self.get_log_level(),
                "database_url_source": "ENV" if os.getenv("DATABASE_URL") else "CONFIG",
            }

            return summary

        except Exception as e:
            return {"config_file": str(self.config_path), "error": str(e)}

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if self._config_cache is not None:
            return self._config_cache

        try:
            if not self.config_path.exists():
                logger.warning(f"配置文件不存在: {self.config_path}")
                self._config_cache = {}
                return self._config_cache

            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

            self._config_cache = config
            logger.debug("配置文件加载完成")
            return config

        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            self._config_cache = {}
            return self._config_cache


# 全局配置服务实例
_global_config_service: Optional[ConfigService] = None


def get_config_service(config_file: Optional[str] = None) -> ConfigService:
    """获取全局配置服务实例"""
    global _global_config_service
    if _global_config_service is None:
        _global_config_service = ConfigService(config_file)
    return _global_config_service
