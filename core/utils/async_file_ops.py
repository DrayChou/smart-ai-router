#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异步文件操作工具 - 使用aiofiles优化IO性能
"""

import asyncio
import json
import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import aiofiles
import aiofiles.os
import yaml

logger = logging.getLogger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    """自定义JSON编码器，支持datetime对象序列化"""

    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif hasattr(obj, "__dict__"):
            # 处理包含datetime的自定义对象
            return obj.__dict__
        return super().default(obj)


class AsyncFileManager:
    """异步文件管理器"""

    def __init__(self):
        self._file_locks = {}  # 文件锁，防止并发写入冲突

    def _get_file_lock(self, file_path: Union[str, Path]) -> asyncio.Lock:
        """获取文件锁"""
        file_key = str(file_path)
        if file_key not in self._file_locks:
            self._file_locks[file_key] = asyncio.Lock()
        return self._file_locks[file_key]

    async def read_json(self, file_path: Union[str, Path], default: Any = None) -> Any:
        """异步读取JSON文件"""
        try:
            path = Path(file_path)
            if not await aiofiles.os.path.exists(path):
                logger.debug(f"JSON文件不存在: {path}")
                return default

            start_time = time.time()
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()

            if not content.strip():
                logger.debug(f"JSON文件为空: {path}")
                return default

            data = json.loads(content)
            read_time = (time.time() - start_time) * 1000
            logger.debug(
                f"📖 ASYNC READ: {path.name} ({len(content)} bytes, {read_time:.1f}ms)"
            )

            return data

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败 {file_path}: {e}")
            return default
        except Exception as e:
            logger.error(f"异步读取JSON失败 {file_path}: {e}")
            return default

    async def write_json(
        self,
        file_path: Union[str, Path],
        data: Any,
        ensure_dir: bool = True,
        indent: int = 2,
    ) -> bool:
        """异步写入JSON文件"""
        try:
            path = Path(file_path)

            # 确保目录存在
            if ensure_dir:
                await aiofiles.os.makedirs(path.parent, exist_ok=True)

            # 使用文件锁防止并发写入
            async with self._get_file_lock(path):
                start_time = time.time()

                # 序列化数据，使用自定义编码器支持datetime
                json_content = json.dumps(
                    data, indent=indent, ensure_ascii=False, cls=DateTimeEncoder
                )

                # 异步写入
                async with aiofiles.open(path, "w", encoding="utf-8") as f:
                    await f.write(json_content)

                write_time = (time.time() - start_time) * 1000
                logger.debug(
                    f"💾 ASYNC WRITE: {path.name} ({len(json_content)} bytes, {write_time:.1f}ms)"
                )

            return True

        except Exception as e:
            logger.error(f"异步写入JSON失败 {file_path}: {e}")
            return False

    async def read_yaml(self, file_path: Union[str, Path], default: Any = None) -> Any:
        """异步读取YAML文件"""
        try:
            path = Path(file_path)
            if not await aiofiles.os.path.exists(path):
                logger.debug(f"YAML文件不存在: {path}")
                return default

            start_time = time.time()
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()

            if not content.strip():
                logger.debug(f"YAML文件为空: {path}")
                return default

            data = yaml.safe_load(content)
            read_time = (time.time() - start_time) * 1000
            logger.debug(
                f"📖 ASYNC READ: {path.name} YAML ({len(content)} bytes, {read_time:.1f}ms)"
            )

            return data

        except yaml.YAMLError as e:
            logger.error(f"YAML解析失败 {file_path}: {e}")
            return default
        except Exception as e:
            logger.error(f"异步读取YAML失败 {file_path}: {e}")
            return default

    async def write_yaml(
        self, file_path: Union[str, Path], data: Any, ensure_dir: bool = True
    ) -> bool:
        """异步写入YAML文件"""
        try:
            path = Path(file_path)

            # 确保目录存在
            if ensure_dir:
                await aiofiles.os.makedirs(path.parent, exist_ok=True)

            # 使用文件锁防止并发写入
            async with self._get_file_lock(path):
                start_time = time.time()

                # 序列化数据
                yaml_content = yaml.dump(
                    data, default_flow_style=False, allow_unicode=True, indent=2
                )

                # 异步写入
                async with aiofiles.open(path, "w", encoding="utf-8") as f:
                    await f.write(yaml_content)

                write_time = (time.time() - start_time) * 1000
                logger.debug(
                    f"💾 ASYNC WRITE: {path.name} YAML ({len(yaml_content)} bytes, {write_time:.1f}ms)"
                )

            return True

        except Exception as e:
            logger.error(f"异步写入YAML失败 {file_path}: {e}")
            return False

    async def read_text(
        self, file_path: Union[str, Path], encoding: str = "utf-8"
    ) -> Optional[str]:
        """异步读取文本文件"""
        try:
            path = Path(file_path)
            if not await aiofiles.os.path.exists(path):
                logger.debug(f"文本文件不存在: {path}")
                return None

            start_time = time.time()
            async with aiofiles.open(path, "r", encoding=encoding) as f:
                content = await f.read()

            read_time = (time.time() - start_time) * 1000
            logger.debug(
                f"📖 ASYNC READ: {path.name} ({len(content)} chars, {read_time:.1f}ms)"
            )

            return content

        except Exception as e:
            logger.error(f"异步读取文本失败 {file_path}: {e}")
            return None

    async def write_text(
        self,
        file_path: Union[str, Path],
        content: str,
        encoding: str = "utf-8",
        ensure_dir: bool = True,
    ) -> bool:
        """异步写入文本文件"""
        try:
            path = Path(file_path)

            # 确保目录存在
            if ensure_dir:
                await aiofiles.os.makedirs(path.parent, exist_ok=True)

            # 使用文件锁防止并发写入
            async with self._get_file_lock(path):
                start_time = time.time()

                # 异步写入
                async with aiofiles.open(path, "w", encoding=encoding) as f:
                    await f.write(content)

                write_time = (time.time() - start_time) * 1000
                logger.debug(
                    f"💾 ASYNC WRITE: {path.name} ({len(content)} chars, {write_time:.1f}ms)"
                )

            return True

        except Exception as e:
            logger.error(f"异步写入文本失败 {file_path}: {e}")
            return False

    async def append_text(
        self,
        file_path: Union[str, Path],
        content: str,
        encoding: str = "utf-8",
        ensure_dir: bool = True,
    ) -> bool:
        """异步追加文本到文件"""
        try:
            path = Path(file_path)

            # 确保目录存在
            if ensure_dir:
                await aiofiles.os.makedirs(path.parent, exist_ok=True)

            # 使用文件锁防止并发写入
            async with self._get_file_lock(path):
                start_time = time.time()

                # 异步追加
                async with aiofiles.open(path, "a", encoding=encoding) as f:
                    await f.write(content)

                write_time = (time.time() - start_time) * 1000
                logger.debug(
                    f"➕ ASYNC APPEND: {path.name} (+{len(content)} chars, {write_time:.1f}ms)"
                )

            return True

        except Exception as e:
            logger.error(f"异步追加文本失败 {file_path}: {e}")
            return False

    async def file_exists(self, file_path: Union[str, Path]) -> bool:
        """异步检查文件是否存在"""
        try:
            return await aiofiles.os.path.exists(Path(file_path))
        except Exception:
            return False

    async def get_file_size(self, file_path: Union[str, Path]) -> Optional[int]:
        """异步获取文件大小"""
        try:
            path = Path(file_path)
            if await aiofiles.os.path.exists(path):
                stat = await aiofiles.os.stat(path)
                return stat.st_size
            return None
        except Exception as e:
            logger.error(f"获取文件大小失败 {file_path}: {e}")
            return None

    async def remove_file(self, file_path: Union[str, Path]) -> bool:
        """异步删除文件"""
        try:
            path = Path(file_path)
            if await aiofiles.os.path.exists(path):
                await aiofiles.os.remove(path)
                logger.debug(f"🗑️ ASYNC DELETE: {path.name}")
                return True
            return False
        except Exception as e:
            logger.error(f"异步删除文件失败 {file_path}: {e}")
            return False

    async def backup_file(
        self, file_path: Union[str, Path], backup_suffix: str = ".backup"
    ) -> Optional[Path]:
        """异步备份文件"""
        try:
            path = Path(file_path)
            if not await aiofiles.os.path.exists(path):
                return None

            backup_path = path.with_suffix(path.suffix + backup_suffix)

            # 读取原文件
            content = await self.read_text(path)
            if content is None:
                return None

            # 写入备份
            success = await self.write_text(backup_path, content)
            if success:
                logger.debug(f"💾 ASYNC BACKUP: {path.name} -> {backup_path.name}")
                return backup_path

            return None

        except Exception as e:
            logger.error(f"异步备份文件失败 {file_path}: {e}")
            return None

    async def batch_read_json(
        self, file_paths: List[Union[str, Path]], default: Any = None
    ) -> Dict[str, Any]:
        """批量异步读取JSON文件"""

        async def read_single(path):
            return str(path), await self.read_json(path, default)

        results = await asyncio.gather(*[read_single(path) for path in file_paths])
        return dict(results)

    async def batch_write_json(
        self, file_data: Dict[Union[str, Path], Any], **kwargs
    ) -> Dict[str, bool]:
        """批量异步写入JSON文件"""

        async def write_single(path, data):
            return str(path), await self.write_json(path, data, **kwargs)

        results = await asyncio.gather(
            *[write_single(path, data) for path, data in file_data.items()]
        )
        return dict(results)


# 全局异步文件管理器实例
_async_file_manager: Optional[AsyncFileManager] = None


def get_async_file_manager() -> AsyncFileManager:
    """获取全局异步文件管理器"""
    global _async_file_manager
    if _async_file_manager is None:
        _async_file_manager = AsyncFileManager()
    return _async_file_manager


# 便捷函数
async def async_read_json(file_path: Union[str, Path], default: Any = None) -> Any:
    """便捷的异步JSON读取函数"""
    return await get_async_file_manager().read_json(file_path, default)


async def async_write_json(file_path: Union[str, Path], data: Any, **kwargs) -> bool:
    """便捷的异步JSON写入函数"""
    return await get_async_file_manager().write_json(file_path, data, **kwargs)


async def async_read_yaml(file_path: Union[str, Path], default: Any = None) -> Any:
    """便捷的异步YAML读取函数"""
    return await get_async_file_manager().read_yaml(file_path, default)


async def async_write_yaml(file_path: Union[str, Path], data: Any, **kwargs) -> bool:
    """便捷的异步YAML写入函数"""
    return await get_async_file_manager().write_yaml(file_path, data, **kwargs)


async def async_read_text(
    file_path: Union[str, Path], encoding: str = "utf-8"
) -> Optional[str]:
    """便捷的异步文本读取函数"""
    return await get_async_file_manager().read_text(file_path, encoding)


async def async_write_text(file_path: Union[str, Path], content: str, **kwargs) -> bool:
    """便捷的异步文本写入函数"""
    return await get_async_file_manager().write_text(file_path, content, **kwargs)
