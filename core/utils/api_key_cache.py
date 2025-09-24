"""
API Key级别缓存管理器
解决渠道级别定价架构问题，支持不同API Key对应不同用户级别
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目数据结构"""

    cache_key: str
    channel_id: str
    api_key_hash: str
    user_level: str  # free/pro/premium/unknown
    models: list[str]
    models_pricing: dict[str, Any]
    status: str  # success/failed/partial
    discovered_at: datetime
    error_message: Optional[str] = None


class ApiKeyCacheManager:
    """API Key级别缓存管理器"""

    def __init__(self, hash_length: int = 8):
        """
        Args:
            hash_length: API Key哈希长度，用于生成缓存键
        """
        self.hash_length = hash_length

    def generate_cache_key(self, channel_id: str, api_key: str) -> str:
        """
        生成API Key级别的缓存键

        Args:
            channel_id: 渠道ID
            api_key: API密钥

        Returns:
            缓存键，格式: {channel_id}_{api_key_hash}

        Examples:
            >>> manager = ApiKeyCacheManager()
            >>> manager.generate_cache_key("siliconflow_1", "sk-abc123")
            'siliconflow_1_a1b2c3d4'
        """
        if not api_key:
            logger.warning(f"API key is empty for channel {channel_id}")
            return channel_id  # 回退到原始渠道ID

        api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[
            : self.hash_length
        ]
        return f"{channel_id}_{api_key_hash}"

    def parse_cache_key(self, cache_key: str) -> tuple[str, str]:
        """
        解析缓存键，提取渠道ID和API Key哈希

        Args:
            cache_key: 缓存键

        Returns:
            (channel_id, api_key_hash) 元组

        Examples:
            >>> manager = ApiKeyCacheManager()
            >>> manager.parse_cache_key("siliconflow_1_a1b2c3d4")
            ('siliconflow_1', 'a1b2c3d4')
        """
        # 使用rsplit从右侧分割，支持渠道ID中包含下划线
        parts = cache_key.rsplit("_", 1)
        if len(parts) == 2:
            return parts[0], parts[1]  # channel_id, api_key_hash
        return cache_key, ""  # 兼容旧格式

    def is_api_key_cache(self, cache_key: str) -> bool:
        """
        判断是否为API Key级别的缓存键

        Args:
            cache_key: 缓存键

        Returns:
            True表示是API Key级别缓存
        """
        _, api_key_hash = self.parse_cache_key(cache_key)
        return len(api_key_hash) == self.hash_length

    def find_cache_entries_by_channel(
        self, cache: dict[str, Any], channel_id: str
    ) -> list[str]:
        """
        查找特定渠道的所有缓存条目

        Args:
            cache: 完整的模型缓存
            channel_id: 渠道ID

        Returns:
            该渠道的所有缓存键列表
        """
        channel_keys = []
        for cache_key in cache.keys():
            parsed_channel_id, _ = self.parse_cache_key(cache_key)
            if parsed_channel_id == channel_id:
                channel_keys.append(cache_key)

        return channel_keys

    def find_cache_entry_by_channel_and_key(
        self, cache: dict[str, Any], channel_id: str, api_key: str
    ) -> Optional[str]:
        """
        查找特定渠道和API Key对应的缓存条目

        Args:
            cache: 完整的模型缓存
            channel_id: 渠道ID
            api_key: API密钥

        Returns:
            匹配的缓存键，如果没找到返回None
        """
        target_cache_key = self.generate_cache_key(channel_id, api_key)
        return target_cache_key if target_cache_key in cache else None

    def get_cache_statistics(self, cache: dict[str, Any]) -> dict[str, Any]:
        """
        获取缓存统计信息

        Args:
            cache: 完整的模型缓存

        Returns:
            统计信息字典
        """
        total_entries = len(cache)
        api_key_entries = 0
        legacy_entries = 0
        channel_groups: dict[str, int] = {}
        user_levels: dict[str, int] = {}

        for cache_key, cache_data in cache.items():
            if self.is_api_key_cache(cache_key):
                api_key_entries += 1

                # 统计渠道分组
                channel_id, _ = self.parse_cache_key(cache_key)
                channel_groups[channel_id] = channel_groups.get(channel_id, 0) + 1

                # 统计用户级别
                user_level = cache_data.get("user_level", "unknown")
                user_levels[user_level] = user_levels.get(user_level, 0) + 1

            else:
                legacy_entries += 1

        return {
            "total_entries": total_entries,
            "api_key_entries": api_key_entries,
            "legacy_entries": legacy_entries,
            "channel_groups": channel_groups,
            "user_levels": user_levels,
            "api_key_coverage": (
                round(api_key_entries / total_entries * 100, 2)
                if total_entries > 0
                else 0
            ),
        }

    def migrate_legacy_cache(
        self, old_cache: dict[str, Any], channels_map: dict[str, Any]
    ) -> dict[str, Any]:
        """
        迁移旧缓存格式到新的API Key级别格式

        Args:
            old_cache: 旧的渠道级别缓存
            channels_map: 渠道映射 {channel_id: channel_config}

        Returns:
            新格式的缓存
        """
        new_cache = {}
        migrated_count = 0
        kept_count = 0

        for cache_key, cache_data in old_cache.items():
            # 如果已经是新格式，直接保留
            if self.is_api_key_cache(cache_key):
                new_cache[cache_key] = cache_data
                kept_count += 1
                continue

            # 尝试迁移旧格式
            channel_id = cache_key
            channel_config = channels_map.get(channel_id)

            if channel_config and channel_config.get("api_key"):
                # 生成新的缓存键
                new_cache_key = self.generate_cache_key(
                    channel_id, channel_config["api_key"]
                )

                # 创建新格式的缓存数据
                new_cache[new_cache_key] = {
                    **cache_data,
                    "cache_key": new_cache_key,
                    "channel_id": channel_id,
                    "api_key_hash": new_cache_key.split("_")[-1],
                    "user_level": self._detect_user_level(cache_data, channel_config),
                    "migrated_from_legacy": True,
                    "migrated_at": datetime.now().isoformat(),
                }
                migrated_count += 1
                logger.info(f"Migrated cache: {cache_key} -> {new_cache_key}")

            else:
                # 无法迁移，保持原格式（兼容性）
                new_cache[cache_key] = cache_data
                kept_count += 1
                # [BOOST] 优化：减少重复警告，只在调试模式显示
                logger.debug(
                    f"Cannot migrate cache key {cache_key}: no channel config or API key"
                )

        logger.info(
            f"Cache migration completed: {migrated_count} migrated, {kept_count} kept as-is"
        )
        return new_cache

    def _detect_user_level(
        self, cache_data: dict[str, Any], channel_config: dict[str, Any]
    ) -> str:
        """
        检测用户等级（基于已有的缓存数据和渠道配置）

        Args:
            cache_data: 缓存数据
            channel_config: 渠道配置

        Returns:
            用户等级字符串
        """
        provider = channel_config.get("provider", "")
        models = cache_data.get("models", [])

        # SiliconFlow用户等级检测
        if provider == "siliconflow":
            pro_models = [m for m in models if "Pro/" in m or "/Pro" in m]
            if pro_models:
                return "pro"
            return "free"

        # OpenRouter用户等级检测
        if provider == "openrouter":
            model_count = len(models)
            if model_count > 100:
                return "premium"
            elif model_count > 50:
                return "pro"
            return "free"

        # 其他提供商的默认检测逻辑
        if models:
            # 基于模型数量的简单估算
            model_count = len(models)
            if model_count > 50:
                return "premium"
            elif model_count > 20:
                return "pro"
            return "free"

        return "unknown"

    def cleanup_invalid_entries(
        self, cache: dict[str, Any], channels_map: dict[str, Any]
    ) -> dict[str, Any]:
        """
        清理无效的缓存条目

        Args:
            cache: 模型缓存
            channels_map: 当前有效的渠道映射

        Returns:
            清理后的缓存
        """
        cleaned_cache = {}
        removed_count = 0

        for cache_key, cache_data in cache.items():
            channel_id, _ = self.parse_cache_key(cache_key)

            # 检查渠道是否仍然存在
            if channel_id in channels_map:
                cleaned_cache[cache_key] = cache_data
            else:
                removed_count += 1
                logger.debug(
                    f"Removed invalid cache entry: {cache_key} (channel not found)"
                )

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} invalid cache entries")

        return cleaned_cache


# 全局实例
_api_key_cache_manager: Optional[ApiKeyCacheManager] = None


def get_api_key_cache_manager() -> ApiKeyCacheManager:
    """获取全局API Key缓存管理器实例"""
    global _api_key_cache_manager
    if _api_key_cache_manager is None:
        _api_key_cache_manager = ApiKeyCacheManager()
    return _api_key_cache_manager
