#!/usr/bin/env python3
"""
智能缓存管理器
提供基于TTL的智能缓存，支持模型发现、健康检查、API密钥验证等场景
"""

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, Union

from .async_file_ops import get_async_file_manager

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CacheEntry:
    """缓存条目"""

    def __init__(self, data: Any, ttl: float, created_at: float = None):
        self.data = data
        self.ttl = ttl  # Time to live in seconds
        self.created_at = created_at or time.time()
        self.access_count = 0
        self.last_accessed = self.created_at

    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() - self.created_at > self.ttl

    def access(self):
        """记录访问"""
        self.access_count += 1
        self.last_accessed = time.time()

    def get_age(self) -> float:
        """获取缓存项年龄（秒）"""
        return time.time() - self.created_at


class SmartCache:
    """智能缓存管理器"""

    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # 内存缓存
        self.memory_cache: dict[str, CacheEntry] = {}
        self.cache_lock = asyncio.Lock()

        # 分层缓存策略配置
        self.cache_configs = {
            # === 长期缓存层 (L1) - 数据相对稳定 ===
            "model_discovery": {
                "ttl": 3600,
                "persistent": True,
                "priority": "high",
                "max_size": 1000,
            },  # 1小时
            "api_key_validation": {
                "ttl": 1800,
                "persistent": True,
                "priority": "high",
                "max_size": 500,
            },  # 30分钟
            "model_specs": {
                "ttl": 7200,
                "persistent": True,
                "priority": "medium",
                "max_size": 2000,
            },  # 2小时
            # === 中期缓存层 (L2) - 需要定期更新 ===
            "health_check": {
                "ttl": 300,
                "persistent": True,
                "priority": "medium",
                "max_size": 200,
            },  # 5分钟
            "pricing_data": {
                "ttl": 600,
                "persistent": True,
                "priority": "medium",
                "max_size": 500,
            },  # 10分钟
            "channel_stats": {
                "ttl": 180,
                "persistent": True,
                "priority": "low",
                "max_size": 100,
            },  # 3分钟
            # === 短期缓存层 (L3) - 实时性要求高 ===
            "channel_availability": {
                "ttl": 60,
                "persistent": False,
                "priority": "high",
                "max_size": 100,
            },  # 1分钟
            "model_routing": {
                "ttl": 120,
                "persistent": False,
                "priority": "medium",
                "max_size": 500,
            },  # 2分钟
            "batch_scores": {
                "ttl": 180,
                "persistent": False,
                "priority": "medium",
                "max_size": 300,
            },  # 3分钟
            # === 临时缓存层 (L4) - 极短TTL ===
            "error_cache": {
                "ttl": 30,
                "persistent": False,
                "priority": "low",
                "max_size": 50,
            },  # 30秒
            "rate_limit": {
                "ttl": 60,
                "persistent": False,
                "priority": "high",
                "max_size": 100,
            },  # 1分钟
            "hot_queries": {
                "ttl": 300,
                "persistent": False,
                "priority": "high",
                "max_size": 200,
            },  # 5分钟（热点查询）
        }

        # 文件缓存路径
        self.persistent_cache_file = self.cache_dir / "smart_cache.json"

        # 加载持久化缓存
        self._load_persistent_cache()

        # 缓存大小管理
        self.cache_size_by_type: dict[str, int] = defaultdict(int)

        # 启动清理任务
        self._start_cleanup_task()

    def _get_cache_key(self, cache_type: str, key: str) -> str:
        """生成缓存键"""
        # 使用hash确保键的长度和格式一致
        key_hash = hashlib.sha256(f"{cache_type}:{key}".encode()).hexdigest()
        return f"{cache_type}:{key_hash}"

    def _get_cache_config(self, cache_type: str) -> dict[str, Any]:
        """获取缓存配置"""
        return self.cache_configs.get(cache_type, {"ttl": 300, "persistent": False})

    async def get(self, cache_type: str, key: str, default: Any = None) -> Any:
        """获取缓存数据"""
        cache_key = self._get_cache_key(cache_type, key)

        async with self.cache_lock:
            entry = self.memory_cache.get(cache_key)

            if entry is None:
                logger.debug(f"缓存未命中: {cache_type}:{key}")
                return default

            if entry.is_expired():
                logger.debug(
                    f"缓存已过期: {cache_type}:{key} (年龄: {entry.get_age():.1f}s)"
                )
                del self.memory_cache[cache_key]
                return default

            entry.access()
            logger.debug(
                f"缓存命中: {cache_type}:{key} (年龄: {entry.get_age():.1f}s, 访问次数: {entry.access_count})"
            )
            return entry.data

    async def set(self, cache_type: str, key: str, data: Any) -> None:
        """设置缓存数据，支持分层策略和大小限制"""
        cache_key = self._get_cache_key(cache_type, key)
        config = self._get_cache_config(cache_type)

        async with self.cache_lock:
            # 检查缓存大小限制
            await self._enforce_size_limit(cache_type, config)

            entry = CacheEntry(data, config["ttl"])
            self.memory_cache[cache_key] = entry
            self.cache_size_by_type[cache_type] += 1

            logger.debug(
                f"缓存设置: {cache_type}:{key} (TTL: {config['ttl']}s, Size: {self.cache_size_by_type[cache_type]}/{config.get('max_size', '∞')})"
            )

            # 如果需要持久化，保存到文件
            if config.get("persistent", False):
                await self._save_persistent_entry(cache_key, entry)

    async def exists(self, cache_type: str, key: str) -> bool:
        """检查缓存是否存在且未过期"""
        result = await self.get(cache_type, key)
        return result is not None

    async def delete(self, cache_type: str, key: str) -> bool:
        """删除缓存条目"""
        cache_key = self._get_cache_key(cache_type, key)

        async with self.cache_lock:
            if cache_key in self.memory_cache:
                del self.memory_cache[cache_key]
                logger.debug(f"缓存删除: {cache_type}:{key}")
                return True
            return False

    async def clear_type(self, cache_type: str) -> int:
        """清除指定类型的所有缓存"""
        prefix = f"{cache_type}:"
        deleted_count = 0

        async with self.cache_lock:
            keys_to_delete = [
                k for k in self.memory_cache.keys() if k.startswith(prefix)
            ]
            for key in keys_to_delete:
                del self.memory_cache[key]
                deleted_count += 1

        logger.info(f"清除缓存类型 {cache_type}: {deleted_count} 个条目")
        return deleted_count

    async def get_or_set(
        self,
        cache_type: str,
        key: str,
        factory: Callable[[], Union[Any, Any]],
        force_refresh: bool = False,
    ) -> Any:
        """获取缓存，如果不存在则通过factory函数生成并缓存"""
        if not force_refresh:
            cached_data = await self.get(cache_type, key)
            if cached_data is not None:
                return cached_data

        # 调用factory函数生成数据
        if asyncio.iscoroutinefunction(factory):
            data = await factory()
        else:
            data = factory()

        # 缓存数据
        await self.set(cache_type, key, data)

        logger.debug(f"缓存生成: {cache_type}:{key}")
        return data

    def _load_persistent_cache(self):
        """加载持久化缓存（同步版本，为兼容性保留）"""
        try:
            if not self.persistent_cache_file.exists():
                return

            with open(self.persistent_cache_file, encoding="utf-8") as f:
                data = json.load(f)

            time.time()
            loaded_count = 0

            for cache_key, entry_data in data.items():
                try:
                    entry = CacheEntry(
                        data=entry_data["data"],
                        ttl=entry_data["ttl"],
                        created_at=entry_data["created_at"],
                    )

                    # 检查是否过期
                    if not entry.is_expired():
                        self.memory_cache[cache_key] = entry
                        loaded_count += 1

                except (KeyError, TypeError) as e:
                    logger.warning(f"跳过无效的缓存条目 {cache_key}: {e}")
                    continue

            logger.info(f"加载持久化缓存: {loaded_count} 个有效条目")

        except Exception as e:
            logger.warning(f"加载持久化缓存失败: {e}")

    async def _load_persistent_cache_async(self):
        """异步加载持久化缓存"""
        try:
            file_manager = get_async_file_manager()

            if not await file_manager.file_exists(self.persistent_cache_file):
                return

            data = await file_manager.read_json(self.persistent_cache_file, {})

            time.time()
            loaded_count = 0

            for cache_key, entry_data in data.items():
                try:
                    entry = CacheEntry(
                        data=entry_data["data"],
                        ttl=entry_data["ttl"],
                        created_at=entry_data["created_at"],
                    )

                    # 检查是否过期
                    if not entry.is_expired():
                        self.memory_cache[cache_key] = entry
                        loaded_count += 1

                except (KeyError, TypeError) as e:
                    logger.warning(f"跳过无效的缓存条目 {cache_key}: {e}")
                    continue

            logger.info(f"异步加载持久化缓存: {loaded_count} 个有效条目")

        except Exception as e:
            logger.warning(f"异步加载持久化缓存失败: {e}")

    async def _save_persistent_entry(self, cache_key: str, entry: CacheEntry):
        """异步保存单个缓存条目到持久化文件"""
        try:
            file_manager = get_async_file_manager()

            # 读取现有数据
            persistent_data = await file_manager.read_json(
                self.persistent_cache_file, {}
            )

            # 更新数据
            persistent_data[cache_key] = {
                "data": entry.data,
                "ttl": entry.ttl,
                "created_at": entry.created_at,
            }

            # 异步写回文件
            success = await file_manager.write_json(
                self.persistent_cache_file, persistent_data, indent=2
            )

            if not success:
                logger.warning("异步保存持久化缓存失败: 文件写入返回失败")

        except Exception as e:
            logger.warning(f"异步保存持久化缓存失败: {e}")

    async def save_all_persistent_cache(self):
        """异步保存所有持久化缓存条目"""
        try:
            file_manager = get_async_file_manager()

            # 收集所有需要持久化的缓存条目
            persistent_data = {}

            async with self.cache_lock:
                for cache_key, entry in self.memory_cache.items():
                    cache_type = cache_key.split(":", 1)[0]
                    config = self._get_cache_config(cache_type)

                    if config.get("persistent", False) and not entry.is_expired():
                        persistent_data[cache_key] = {
                            "data": entry.data,
                            "ttl": entry.ttl,
                            "created_at": entry.created_at,
                        }

            # 异步保存所有数据
            if persistent_data:
                success = await file_manager.write_json(
                    self.persistent_cache_file, persistent_data, indent=2
                )

                if success:
                    logger.info(f"异步保存 {len(persistent_data)} 个持久化缓存条目")
                else:
                    logger.warning("异步保存持久化缓存失败: 文件写入返回失败")

        except Exception as e:
            logger.warning(f"异步保存所有持久化缓存失败: {e}")

    async def cleanup_expired(self) -> int:
        """清理过期的缓存条目"""
        expired_count = 0

        async with self.cache_lock:
            keys_to_delete = []
            for cache_key, entry in self.memory_cache.items():
                if entry.is_expired():
                    keys_to_delete.append(cache_key)

            for key in keys_to_delete:
                del self.memory_cache[key]
                expired_count += 1

        if expired_count > 0:
            logger.debug(f"清理过期缓存: {expired_count} 个条目")

        return expired_count

    def _start_cleanup_task(self):
        """启动定期清理任务"""

        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(60)  # 每分钟清理一次
                    await self.cleanup_expired()
                except Exception as e:
                    logger.error(f"缓存清理任务出错: {e}")

        asyncio.create_task(cleanup_loop())

    def get_stats(self) -> dict[str, Any]:
        """获取缓存统计信息"""
        stats = {
            "total_entries": len(self.memory_cache),
            "cache_types": {},
            "memory_usage_estimate": 0,
        }

        for cache_key, entry in self.memory_cache.items():
            cache_type = cache_key.split(":", 1)[0]
            if cache_type not in stats["cache_types"]:
                stats["cache_types"][cache_type] = {
                    "count": 0,
                    "total_access": 0,
                    "avg_age": 0,
                    "expired_count": 0,
                }

            type_stats = stats["cache_types"][cache_type]
            type_stats["count"] += 1
            type_stats["total_access"] += entry.access_count
            type_stats["avg_age"] += entry.get_age()

            if entry.is_expired():
                type_stats["expired_count"] += 1

            # 简单估算内存使用
            try:
                stats["memory_usage_estimate"] += len(str(entry.data))
            except:
                pass

        # 计算平均值
        for cache_type in stats["cache_types"]:
            type_stats = stats["cache_types"][cache_type]
            if type_stats["count"] > 0:
                type_stats["avg_age"] = type_stats["avg_age"] / type_stats["count"]
                type_stats["avg_access"] = (
                    type_stats["total_access"] / type_stats["count"]
                )

        return stats

    async def _enforce_size_limit(self, cache_type: str, config: dict[str, Any]):
        """强制执行缓存大小限制"""
        max_size = config.get("max_size")
        if not max_size:
            return

        current_size = self.cache_size_by_type[cache_type]
        if current_size >= max_size:
            # 需要清理，采用LRU策略
            await self._evict_lru_entries(cache_type, max_size // 4)  # 清理25%的空间

    async def _evict_lru_entries(self, cache_type: str, evict_count: int):
        """驱逐LRU缓存条目"""
        prefix = f"{cache_type}:"

        # 收集该类型的所有缓存条目
        entries_to_sort = []
        for cache_key, entry in self.memory_cache.items():
            if cache_key.startswith(prefix):
                entries_to_sort.append((cache_key, entry.last_accessed))

        # 按最后访问时间排序，最久未访问的在前
        entries_to_sort.sort(key=lambda x: x[1])

        # 驱逐最久未访问的条目
        evicted_count = 0
        for cache_key, _ in entries_to_sort[:evict_count]:
            if cache_key in self.memory_cache:
                del self.memory_cache[cache_key]
                self.cache_size_by_type[cache_type] -= 1
                evicted_count += 1

        if evicted_count > 0:
            logger.debug(f"缓存LRU清理: {cache_type} 驱逐了 {evicted_count} 个条目")

    async def preload_hot_queries(self, hot_patterns: list[str]):
        """预加载热点查询模式"""
        for pattern in hot_patterns:
            # 这里可以根据pattern预生成一些常用查询的缓存
            cache_key = f"preload_{pattern}"
            await self.set(
                "hot_queries", cache_key, {"pattern": pattern, "preloaded": True}
            )

        logger.info(f"预加载热点查询: {len(hot_patterns)} 个模式")

    def get_cache_layer_stats(self) -> dict[str, Any]:
        """获取分层缓存统计信息"""
        layer_stats = {
            "L1_long_term": {"types": [], "total_entries": 0, "total_size_mb": 0},
            "L2_medium_term": {"types": [], "total_entries": 0, "total_size_mb": 0},
            "L3_short_term": {"types": [], "total_entries": 0, "total_size_mb": 0},
            "L4_temporary": {"types": [], "total_entries": 0, "total_size_mb": 0},
        }

        # 根据TTL分层统计
        for cache_type, config in self.cache_configs.items():
            ttl = config["ttl"]
            entry_count = self.cache_size_by_type[cache_type]

            if ttl >= 1800:  # L1: >= 30分钟
                layer_stats["L1_long_term"]["types"].append(cache_type)
                layer_stats["L1_long_term"]["total_entries"] += entry_count
            elif ttl >= 300:  # L2: 5-30分钟
                layer_stats["L2_medium_term"]["types"].append(cache_type)
                layer_stats["L2_medium_term"]["total_entries"] += entry_count
            elif ttl >= 60:  # L3: 1-5分钟
                layer_stats["L3_short_term"]["types"].append(cache_type)
                layer_stats["L3_short_term"]["total_entries"] += entry_count
            else:  # L4: < 1分钟
                layer_stats["L4_temporary"]["types"].append(cache_type)
                layer_stats["L4_temporary"]["total_entries"] += entry_count

        return layer_stats


# 全局缓存实例
_global_cache: Optional[SmartCache] = None


def get_smart_cache() -> SmartCache:
    """获取全局智能缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = SmartCache()
        logger.info("初始化全局智能缓存")
    return _global_cache


async def close_global_cache():
    """关闭全局缓存（用于清理）"""
    global _global_cache
    if _global_cache is not None:
        # 执行最后的清理
        await _global_cache.cleanup_expired()
        _global_cache = None
        logger.info("全局智能缓存已关闭")


# 便捷函数
async def cache_get(cache_type: str, key: str, default: Any = None) -> Any:
    """获取缓存数据的便捷函数"""
    cache = get_smart_cache()
    return await cache.get(cache_type, key, default)


async def cache_set(cache_type: str, key: str, data: Any) -> None:
    """设置缓存数据的便捷函数"""
    cache = get_smart_cache()
    await cache.set(cache_type, key, data)


async def cache_get_or_set(
    cache_type: str, key: str, factory: Callable, force_refresh: bool = False
) -> Any:
    """获取或设置缓存的便捷函数"""
    cache = get_smart_cache()
    return await cache.get_or_set(cache_type, key, factory, force_refresh)
