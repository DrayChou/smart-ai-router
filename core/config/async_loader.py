#!/usr/bin/env python3
"""
异步配置加载器 - Phase 1 Python 性能优化
专注解决配置加载的 2-4 秒延迟问题
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional, Union

import aiofiles
import yaml
from pydantic import ValidationError

from ..config_models import Config
from ..utils.async_file_ops import get_async_file_manager

logger = logging.getLogger(__name__)


class AsyncConfigLoadingMonitor:
    """配置加载进度监控器"""

    def __init__(self):
        self._progress = {}
        self._start_time = None
        self._total_tasks = 0

    async def track_config_loading(self, loader_tasks: list[asyncio.Task]) -> list[Any]:
        """实时跟踪配置加载进度"""
        self._start_time = time.time()
        self._total_tasks = len(loader_tasks)

        logger.info(f"开始并行加载 {self._total_tasks} 个配置任务")

        completed_results = []
        for i, task in enumerate(asyncio.as_completed(loader_tasks)):
            try:
                result = await task
                completed_results.append(result)

                progress = (i + 1) / self._total_tasks * 100
                elapsed = time.time() - self._start_time

                logger.info(f"配置加载进度: {progress:.1f}% ({elapsed:.2f}s)")

            except Exception as e:
                logger.error(f"配置任务失败: {e}")
                completed_results.append(None)

        elapsed = time.time() - self._start_time
        logger.info(f"配置加载完成，总耗时: {elapsed:.2f}s")

        return completed_results


class AsyncConfigFailoverManager:
    """配置加载容错管理器"""

    def __init__(self, timeout_seconds: int = 10):
        self._fallback_configs = {}
        self._timeout_seconds = timeout_seconds

    async def load_with_timeout_and_fallback(
        self, primary_loader_coro, fallback_config: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """带超时和回退的配置加载"""
        try:
            # 主要加载路径，带超时
            config = await asyncio.wait_for(
                primary_loader_coro, timeout=self._timeout_seconds
            )
            logger.info("配置主要加载路径成功")
            return config

        except asyncio.TimeoutError:
            logger.warning(f"配置加载超时 ({self._timeout_seconds}s)，使用回退配置")
            return self._get_fallback_config(fallback_config)

        except Exception as e:
            logger.error(f"配置加载失败: {e}，使用回退配置")
            return self._get_fallback_config(fallback_config)

    def _get_fallback_config(
        self, fallback_config: Optional[dict[str, Any]]
    ) -> dict[str, Any]:
        """获取回退配置"""
        if fallback_config:
            return fallback_config

        # 返回最小可用配置
        return {
            "providers": [],
            "channels": [],
            "auth": {"enabled": False},
            "routing": {"default_strategy": "cost_first", "timeout_seconds": 30},
        }


class AsyncYAMLConfigLoader:
    """
    异步 YAML 配置加载器

    核心优化点:
    1. 并行加载多个配置文件
    2. 异步文件 I/O 操作
    3. 线程池并行验证
    4. 智能容错和回退机制
    """

    def __init__(self):
        self._config_cache = {}
        self._validation_pool = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="config-validation"
        )
        self._file_manager = get_async_file_manager()
        self._monitor = AsyncConfigLoadingMonitor()
        self._failover = AsyncConfigFailoverManager()

    async def async_load_config(self, config_path: Union[str, Path]) -> Config:
        """异步并行加载所有配置文件"""
        start_time = time.time()

        try:
            # 识别所有需要加载的配置文件
            config_files = self._identify_config_files(config_path)

            # 创建并行加载任务
            config_tasks = [
                asyncio.create_task(
                    self._load_yaml_async(file_path, file_type),
                    name=f"load-{file_type}",
                )
                for file_path, file_type in config_files
            ]

            # 使用监控器跟踪加载进度
            config_results = await self._monitor.track_config_loading(config_tasks)

            # 合并配置结果
            merged_config = await self._merge_configs(config_results, config_files)

            # 并行验证配置
            validated_config = await self._validate_config_async(merged_config)

            elapsed = time.time() - start_time
            logger.info(f"异步配置加载完成，总耗时: {elapsed:.2f}s")

            return validated_config

        except Exception as e:
            logger.error(f"异步配置加载失败: {e}")
            # 尝试同步回退加载
            return await self._fallback_sync_load(config_path)

    def _identify_config_files(
        self, primary_config_path: Union[str, Path]
    ) -> list[tuple]:
        """识别需要加载的配置文件"""
        config_files = []

        # 主要配置文件
        config_files.append((primary_config_path, "primary"))

        # 检查其他相关配置文件
        config_dir = Path(primary_config_path).parent

        additional_configs = [
            ("providers.yaml", "providers"),
            ("pricing_config.yaml", "pricing"),
            ("routing_config.yaml", "routing"),
        ]

        for filename, file_type in additional_configs:
            file_path = config_dir / filename
            if file_path.exists():
                config_files.append((file_path, file_type))

        logger.debug(f"识别到 {len(config_files)} 个配置文件需要加载")
        return config_files

    async def _load_yaml_async(
        self, file_path: Union[str, Path], file_type: str
    ) -> dict[str, Any]:
        """异步 YAML 文件加载"""
        try:
            start_time = time.time()

            # 检查缓存
            file_key = f"{file_path}_{file_type}"
            if file_key in self._config_cache:
                logger.debug(f"配置缓存命中: {file_type}")
                return self._config_cache[file_key]

            # 异步读取文件内容
            async with aiofiles.open(file_path, encoding="utf-8") as f:
                content = await f.read()

            # 使用线程池进行 YAML 解析 (CPU 密集型)
            loop = asyncio.get_event_loop()
            parsed_data = await loop.run_in_executor(
                self._validation_pool, yaml.safe_load, content
            )

            # 缓存结果
            self._config_cache[file_key] = parsed_data

            elapsed = time.time() - start_time
            logger.debug(f"配置文件 {file_type} 加载完成: {elapsed:.3f}s")

            return {"type": file_type, "data": parsed_data, "path": str(file_path)}

        except FileNotFoundError:
            logger.warning(f"配置文件不存在: {file_path}")
            return {"type": file_type, "data": {}, "path": str(file_path)}

        except Exception as e:
            logger.error(f"配置文件 {file_type} 加载失败 ({file_path}): {e}")
            return {
                "type": file_type,
                "data": {},
                "path": str(file_path),
                "error": str(e),
            }

    async def _merge_configs(
        self, config_results: list[dict[str, Any]], config_files: list[tuple]
    ) -> dict[str, Any]:
        """合并配置结果"""
        merged_config = {
            "providers": {},  # 修复：providers 应该是字典，不是列表
            "channels": [],
            "auth": {"enabled": False},
            "routing": {},
        }

        for result in config_results:
            if result and isinstance(result, dict) and "data" in result:
                config_type = result.get("type", "unknown")
                config_data = result.get("data", {})

                if config_type == "primary":
                    # 主要配置文件，更新所有字段
                    merged_config.update(config_data)
                elif config_type == "providers" and config_data:
                    # 确保 providers 是字典格式
                    providers_data = config_data.get("providers", {})
                    if isinstance(providers_data, dict):
                        merged_config["providers"] = providers_data
                    else:
                        logger.warning(
                            f"providers 配置格式不正确，期望字典但得到: {type(providers_data)}"
                        )
                elif config_type == "pricing" and config_data:
                    merged_config.setdefault("pricing", {}).update(config_data)
                elif config_type == "routing" and config_data:
                    merged_config.setdefault("routing", {}).update(config_data)

        logger.debug(f"配置合并完成: {len(merged_config)} 个顶级配置项")
        return merged_config

    async def _validate_config_async(self, config_data: dict[str, Any]) -> Config:
        """异步验证配置"""
        try:
            # 使用线程池进行 Pydantic 验证 (CPU 密集型)
            loop = asyncio.get_event_loop()
            validated_config = await loop.run_in_executor(
                self._validation_pool, self._validate_with_pydantic, config_data
            )

            logger.debug("配置验证成功")
            return validated_config

        except ValidationError as e:
            logger.error(f"配置验证失败: {e}")
            raise
        except Exception as e:
            logger.error(f"配置验证过程出错: {e}")
            raise

    def _validate_with_pydantic(self, config_data: dict[str, Any]) -> Config:
        """使用 Pydantic 验证配置"""
        return Config.parse_obj(config_data)

    async def _fallback_sync_load(self, config_path: Union[str, Path]) -> Config:
        """同步回退加载"""
        logger.warning("使用同步回退加载配置")

        try:
            with open(config_path, encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            return Config.parse_obj(config_data)

        except Exception as e:
            logger.error(f"同步回退加载也失败: {e}")
            # 返回最小可用配置
            minimal_config = {
                "providers": [],
                "channels": [],
                "auth": {"enabled": False},
            }
            return Config.parse_obj(minimal_config)

    def cleanup(self):
        """清理资源"""
        if self._validation_pool:
            self._validation_pool.shutdown(wait=True)
            logger.debug("配置验证线程池已关闭")


class AsyncConfigPerformanceProfiler:
    """配置加载性能分析器"""

    def __init__(self):
        self._metrics = {
            "total_load_time": [],
            "file_load_times": {},
            "validation_time": [],
            "merge_time": [],
            "cache_hit_rate": 0.0,
        }

    async def profile_config_loading(
        self, loader: AsyncYAMLConfigLoader, config_path: Union[str, Path]
    ):
        """性能分析包装器"""
        start_time = time.time()

        try:
            config = await loader.async_load_config(config_path)

            total_time = time.time() - start_time
            self._metrics["total_load_time"].append(total_time)

            logger.info(f"配置加载性能: {total_time:.3f}s")
            return config

        except Exception as e:
            logger.error(f"性能分析期间配置加载失败: {e}")
            raise

    def get_performance_stats(self) -> dict[str, Any]:
        """获取性能统计"""
        if not self._metrics["total_load_time"]:
            return {"message": "无性能数据"}

        return {
            "average_load_time": sum(self._metrics["total_load_time"])
            / len(self._metrics["total_load_time"]),
            "min_load_time": min(self._metrics["total_load_time"]),
            "max_load_time": max(self._metrics["total_load_time"]),
            "total_loads": len(self._metrics["total_load_time"]),
            "cache_hit_rate": self._metrics["cache_hit_rate"],
        }


# 全局实例和工厂函数
_async_config_loader = None
_performance_profiler = None


def get_async_config_loader() -> AsyncYAMLConfigLoader:
    """获取全局异步配置加载器实例"""
    global _async_config_loader
    if _async_config_loader is None:
        _async_config_loader = AsyncYAMLConfigLoader()
    return _async_config_loader


def get_config_performance_profiler() -> AsyncConfigPerformanceProfiler:
    """获取配置性能分析器"""
    global _performance_profiler
    if _performance_profiler is None:
        _performance_profiler = AsyncConfigPerformanceProfiler()
    return _performance_profiler


async def load_config_async(config_path: Union[str, Path]) -> Config:
    """
    便捷的异步配置加载函数

    这是主要的公共 API，替代同步的配置加载
    """
    loader = get_async_config_loader()
    profiler = get_config_performance_profiler()

    return await profiler.profile_config_loading(loader, config_path)
