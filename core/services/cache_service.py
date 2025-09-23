"""
缓存服务 - 统一的缓存管理
遵循KISS原则和统一命名规范：使用Service后缀
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CacheService:
    """统一缓存服务 - 整合原有的各种缓存管理器"""

    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # 内存缓存
        self._memory_cache: Dict[str, Any] = {}

        logger.info(f"缓存服务初始化完成，缓存目录: {self.cache_dir}")

    async def get(self, key: str, namespace: str = "default") -> Optional[Any]:
        """获取缓存数据"""
        cache_key = f"{namespace}:{key}"

        # 先查内存缓存
        if cache_key in self._memory_cache:
            logger.debug(f"内存缓存命中: {cache_key}")
            return self._memory_cache[cache_key]

        # 查文件缓存
        file_cache = await self._get_file_cache(namespace, key)
        if file_cache is not None:
            # 回写到内存缓存
            self._memory_cache[cache_key] = file_cache
            logger.debug(f"文件缓存命中: {cache_key}")
            return file_cache

        logger.debug(f"缓存未命中: {cache_key}")
        return None

    async def set(
        self,
        key: str,
        value: Any,
        namespace: str = "default",
        ttl: Optional[int] = None,
    ) -> None:
        """设置缓存数据"""
        cache_key = f"{namespace}:{key}"

        # 写入内存缓存
        self._memory_cache[cache_key] = value

        # 异步写入文件缓存
        await self._set_file_cache(namespace, key, value)

        logger.debug(f"缓存已设置: {cache_key}")

    async def delete(self, key: str, namespace: str = "default") -> None:
        """删除缓存数据"""
        cache_key = f"{namespace}:{key}"

        # 从内存缓存删除
        self._memory_cache.pop(cache_key, None)

        # 从文件缓存删除
        await self._delete_file_cache(namespace, key)

        logger.debug(f"缓存已删除: {cache_key}")

    async def clear_namespace(self, namespace: str) -> None:
        """清空指定命名空间的缓存"""
        # 清理内存缓存
        keys_to_delete = [
            k for k in self._memory_cache.keys() if k.startswith(f"{namespace}:")
        ]
        for key in keys_to_delete:
            del self._memory_cache[key]

        # 清理文件缓存
        namespace_dir = self.cache_dir / namespace
        if namespace_dir.exists():
            import shutil

            shutil.rmtree(namespace_dir)

        logger.info(f"已清空命名空间缓存: {namespace}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "memory_cache_size": len(self._memory_cache),
            "cache_dir": str(self.cache_dir),
            "namespaces": self._get_namespaces(),
        }

    async def _get_file_cache(self, namespace: str, key: str) -> Optional[Any]:
        """从文件获取缓存"""
        try:
            cache_file = self.cache_dir / namespace / f"{key}.json"
            if not cache_file.exists():
                return None

            import json

            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("value")
        except Exception as e:
            logger.warning(f"读取文件缓存失败: {e}")
            return None

    async def _set_file_cache(self, namespace: str, key: str, value: Any) -> None:
        """设置文件缓存"""
        try:
            namespace_dir = self.cache_dir / namespace
            namespace_dir.mkdir(exist_ok=True)

            cache_file = namespace_dir / f"{key}.json"

            import json
            from datetime import datetime

            cache_data = {
                "value": value,
                "timestamp": datetime.now().isoformat(),
                "namespace": namespace,
                "key": key,
            }

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.warning(f"写入文件缓存失败: {e}")

    async def _delete_file_cache(self, namespace: str, key: str) -> None:
        """删除文件缓存"""
        try:
            cache_file = self.cache_dir / namespace / f"{key}.json"
            if cache_file.exists():
                cache_file.unlink()
        except Exception as e:
            logger.warning(f"删除文件缓存失败: {e}")

    def _get_namespaces(self) -> List[str]:
        """获取所有命名空间"""
        namespaces = set()

        # 从内存缓存获取
        for key in self._memory_cache.keys():
            if ":" in key:
                namespaces.add(key.split(":", 1)[0])

        # 从文件系统获取
        if self.cache_dir.exists():
            for item in self.cache_dir.iterdir():
                if item.is_dir():
                    namespaces.add(item.name)

        return sorted(list(namespaces))


# 全局缓存服务实例
_global_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """获取全局缓存服务实例"""
    global _global_cache_service
    if _global_cache_service is None:
        _global_cache_service = CacheService()
    return _global_cache_service
