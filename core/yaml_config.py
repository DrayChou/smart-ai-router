"""
基于YAML的配置加载器 - Pydantic版本
"""

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from .auth import generate_secure_token as generate_random_token
from .config.async_loader import load_config_async
from .config_models import Channel, Config, Provider
from .utils.api_key_cache import get_api_key_cache_manager
from .utils.async_file_ops import get_async_file_manager

logger = logging.getLogger(__name__)


@dataclass
class RuntimeState:
    """运行时状态"""

    channel_stats: dict[str, Any] = field(default_factory=dict)
    request_history: list[dict[str, Any]] = field(default_factory=list)
    health_scores: dict[str, float] = field(default_factory=dict)
    cost_tracking: dict[str, Any] = field(default_factory=dict)


class YAMLConfigLoader:
    """基于Pydantic的YAML配置加载器"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_path("router_config.yaml")

        # 运行时状态
        self.runtime_state: RuntimeState = RuntimeState()

        # 模型缓存
        self.model_cache: dict[str, dict] = {}

        # API Key缓存管理器
        self.api_key_cache_manager = get_api_key_cache_manager()

        # 迁移状态标志，防止重复迁移
        self._migration_completed = False
        self._migration_in_progress = False

        # 加载并解析配置
        self.config: Config = self._load_and_validate_config()

        # 创建渠道映射
        self.channels_map = {ch.id: ch for ch in self.config.channels}

        # 加载模型缓存
        self._load_model_cache_from_disk()

        logger.info(
            f"Config loaded: {len(self.config.providers)} providers, {len(self.config.channels)} channels"
        )

    @classmethod
    async def create_async(
        cls, config_path: Optional[str] = None
    ) -> "YAMLConfigLoader":
        """
        异步创建配置加载器实例

        这是 Phase 1 优化的核心方法，使用异步配置加载器
        替代同步的 __init__ 方法以减少 2-4 秒的启动延迟
        """
        start_time = asyncio.get_event_loop().time()

        # 创建实例但跳过同步初始化
        instance = cls.__new__(cls)

        # 设置基本属性
        instance.config_path = config_path or instance._get_default_path(
            "router_config.yaml"
        )
        instance.runtime_state = RuntimeState()
        instance.model_cache = {}
        instance.api_key_cache_manager = get_api_key_cache_manager()
        instance._migration_completed = False
        instance._migration_in_progress = False

        try:
            # [BOOST] 使用异步配置加载器替代同步加载
            logger.info("开始异步配置加载...")
            instance.config = await load_config_async(instance.config_path)

            # 创建渠道映射
            instance.channels_map = {ch.id: ch for ch in instance.config.channels}

            # [BOOST] 异步加载模型缓存（如果有的话）
            await instance._load_model_cache_async()

            elapsed = asyncio.get_event_loop().time() - start_time
            logger.info(
                f"异步配置加载完成: {len(instance.config.providers)} providers, "
                f"{len(instance.config.channels)} channels, 耗时: {elapsed:.2f}s"
            )

            return instance

        except Exception as e:
            logger.error(f"异步配置加载失败，回退到同步模式: {e}")
            # 如果异步加载失败，回退到同步加载
            return cls(config_path)

    async def _load_model_cache_async(self) -> None:
        """异步加载模型缓存"""
        try:
            cache_file = (
                Path(__file__).parent.parent / "cache" / "discovered_models.json"
            )
            if not cache_file.exists():
                logger.debug("模型缓存文件不存在，跳过加载")
                return

            # 使用异步文件管理器
            file_manager = get_async_file_manager()
            raw_cache = await file_manager.read_json(cache_file, {})

            if raw_cache:
                # 检查是否需要迁移缓存格式
                if (
                    self._needs_cache_migration(raw_cache)
                    and not self._migration_completed
                    and not self._migration_in_progress
                ):
                    logger.info("检测到传统缓存格式，使用现有缓存并安排后台迁移")
                    self.model_cache = raw_cache  # 临时使用原始缓存

                    # 标记迁移正在进行
                    self._migration_in_progress = True

                    # [BOOST] 启动后台迁移任务（不阻塞启动）
                    asyncio.create_task(self._async_cache_migration(raw_cache))
                else:
                    self.model_cache = raw_cache

                logger.debug(f"异步加载模型缓存成功: {len(self.model_cache)} 条记录")
            else:
                logger.debug("模型缓存为空")

        except Exception as e:
            logger.error(f"异步加载模型缓存失败: {e}")
            # 不抛出异常，允许系统继续运行

    async def _async_cache_migration(self, raw_cache: dict[str, dict]) -> None:
        """异步缓存迁移任务"""
        try:
            logger.info("开始后台缓存迁移...")

            # 在线程池中执行迁移逻辑
            loop = asyncio.get_event_loop()
            migrated_cache = await loop.run_in_executor(
                None, self._perform_cache_migration, raw_cache
            )

            # 更新缓存
            self.model_cache = migrated_cache
            self._migration_completed = True
            self._migration_in_progress = False

            # 异步保存迁移后的缓存
            cache_file = (
                Path(__file__).parent.parent / "cache" / "discovered_models.json"
            )
            file_manager = get_async_file_manager()
            await file_manager.write_json(cache_file, migrated_cache)

            logger.info("后台缓存迁移完成")

        except Exception as e:
            logger.error(f"后台缓存迁移失败: {e}")
            self._migration_in_progress = False

    def _perform_cache_migration(self, raw_cache: dict[str, dict]) -> dict[str, dict]:
        """执行缓存迁移逻辑（CPU密集型，在线程池中运行）"""
        # 这里放置原有的缓存迁移逻辑
        migrated_cache = {}

        for provider_id, provider_data in raw_cache.items():
            if isinstance(provider_data, dict) and "models" in provider_data:
                # 新格式，直接使用
                migrated_cache[provider_id] = provider_data
            else:
                # 旧格式，需要迁移
                migrated_cache[provider_id] = {
                    "models": provider_data if isinstance(provider_data, list) else [],
                    "last_discovery": datetime.now().isoformat(),
                    "total_models": (
                        len(provider_data) if isinstance(provider_data, list) else 0
                    ),
                }

        return migrated_cache

    def _get_default_path(self, filename: str) -> str:
        """获取配置文件的默认路径"""
        project_root = Path(__file__).parent.parent
        config_file = project_root / "config" / filename
        if config_file.exists():
            return str(config_file)

        # 尝试其他常见配置文件
        alternatives = ["test_config.yaml", "router_config.yaml.template"]
        for alt in alternatives:
            alt_file = project_root / "config" / alt
            if alt_file.exists():
                logger.warning(f"Using fallback config: {alt}")
                return str(alt_file)

        raise FileNotFoundError(
            f"Configuration file {filename} not found in 'config' directory."
        )

    def _load_and_validate_config(self) -> Config:
        """加载并验证配置文件（同步版本，为兼容性保留）"""
        try:
            with open(self.config_path, encoding="utf-8") as f:
                raw_data = yaml.safe_load(f) or {}

            # 检查Token配置并自动生成
            config_modified = self._ensure_auth_token(raw_data)

            # 使用Pydantic进行验证和解析
            config = Config.parse_obj(raw_data)

            # 如果配置被修改，保存回文件
            if config_modified:
                self._save_config_to_file(raw_data)

            return config

        except Exception as e:
            logger.error(f"Failed to load config from {self.config_path}: {e}")
            raise

    async def _load_and_validate_config_async(self) -> Config:
        """异步加载并验证配置文件"""
        try:
            file_manager = get_async_file_manager()
            raw_data = await file_manager.read_yaml(self.config_path, {})

            # 检查Token配置并自动生成
            config_modified = self._ensure_auth_token(raw_data)

            # 使用Pydantic进行验证和解析
            config = Config.parse_obj(raw_data)

            # 如果配置被修改，异步保存回文件
            if config_modified:
                await self._save_config_to_file_async(raw_data)

            return config

        except Exception as e:
            logger.error(f"Failed to load config from {self.config_path}: {e}")
            raise

    def _ensure_auth_token(self, config_data: dict[str, Any]) -> bool:
        """
        确保认证配置中有Token，如果启用认证但没有Token则自动生成

        Returns:
            bool: 如果配置被修改则返回True
        """
        auth_config = config_data.get("auth", {})

        # 如果认证启用但没有api_token，自动生成
        if auth_config.get("enabled", False) and not auth_config.get("api_token"):
            new_token = generate_random_token()
            auth_config["api_token"] = new_token
            config_data["auth"] = auth_config

            logger.info(f"Auto-generated API token for authentication: {new_token}")
            logger.warning(
                "Please save this token! You will need it to access the API."
            )

            return True

        return False

    def _save_config_to_file(self, config_data: dict[str, Any]) -> None:
        """
        保存配置数据到文件（同步版本，为兼容性保留）
        """
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    config_data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    indent=2,
                )
            logger.info(f"Configuration updated and saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save config to {self.config_path}: {e}")
            raise

    async def _save_config_to_file_async(self, config_data: dict[str, Any]) -> None:
        """
        异步保存配置数据到文件
        """
        try:
            file_manager = get_async_file_manager()
            success = await file_manager.write_yaml(self.config_path, config_data)

            if success:
                logger.info(f"Configuration updated and saved to {self.config_path}")
            else:
                raise Exception("Failed to write config file")
        except Exception as e:
            logger.error(f"Failed to save config to {self.config_path}: {e}")
            raise

    def _schedule_cache_migration(self, raw_cache: dict[str, Any]) -> None:
        """Schedule cache migration regardless of event loop availability."""

        async def _runner() -> None:
            await self._migrate_cache_background(raw_cache)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.info(
                "No event loop available for background migration, spawning worker thread"
            )

            def _thread_target() -> None:
                try:
                    asyncio.run(_runner())
                except Exception as exc:
                    logger.error(
                        "BACKGROUND MIGRATION: Threaded migration failed: %s", exc
                    )
                    self._migration_in_progress = False

            threading.Thread(
                target=_thread_target, name="cache-migration", daemon=True
            ).start()
        else:
            loop.create_task(_runner())

    def _load_model_cache_from_disk(self) -> None:
        """从磁盘加载模型发现任务的缓存（同步版本，为兼容性保留）"""
        try:
            # 直接从缓存文件加载
            cache_file = (
                Path(__file__).parent.parent / "cache" / "discovered_models.json"
            )
            if cache_file.exists():
                with open(cache_file, encoding="utf-8") as f:
                    raw_cache = json.load(f)

                    # 检查是否需要迁移缓存格式
                    if (
                        self._needs_cache_migration(raw_cache)
                        and not self._migration_completed
                        and not self._migration_in_progress
                    ):
                        logger.info(
                            "CACHE MIGRATION: Detected legacy cache format, using as-is and scheduling background migration"
                        )
                        # [BOOST] 优化：先使用现有缓存，避免阻塞启动
                        self.model_cache = raw_cache  # 临时使用原始缓存

                        # 标记迁移正在进行
                        self._migration_in_progress = True

                        # [BOOST] 启动后台迁移任务（不阻塞启动）
                        self._schedule_cache_migration(raw_cache)
                    else:
                        self.model_cache = raw_cache
                        if not self._needs_cache_migration(raw_cache):
                            self._migration_completed = True

                        # 清理无效条目（仅对已迁移的缓存执行）
                        self.model_cache = (
                            self.api_key_cache_manager.cleanup_invalid_entries(
                                self.model_cache, self._get_channels_for_migration()
                            )
                        )

                    # 输出缓存统计信息
                    stats = self.api_key_cache_manager.get_cache_statistics(
                        self.model_cache
                    )
                    logger.info(
                        f"Loaded model cache: {stats['total_entries']} entries, "
                        f"{stats['api_key_entries']} API key-level, {stats['legacy_entries']} legacy, "
                        f"{stats['api_key_coverage']}% coverage"
                    )

                    # [BOOST] 立即构建内存索引（启动时预加载）
                    self._build_memory_index()
            else:
                logger.warning("Model cache file not found")
                self.model_cache = {}
        except Exception as e:
            # 作为后备方案，尝试从任务模块加载
            try:
                from .scheduler.tasks.model_discovery import get_model_discovery_task

                task = get_model_discovery_task()
                raw_cache = task.cached_models
                if raw_cache:
                    # 应用相同的迁移逻辑
                    if self._needs_cache_migration(raw_cache):
                        logger.info(
                            "Migrating task cache from legacy format to API key-level format"
                        )
                        self.model_cache = (
                            self.api_key_cache_manager.migrate_legacy_cache(
                                raw_cache, self._get_channels_for_migration()
                            )
                        )
                    else:
                        self.model_cache = raw_cache
                    logger.info(
                        f"Loaded model cache from task for {len(self.model_cache)} entries"
                    )
                else:
                    self.model_cache = {}
            except Exception as e2:
                logger.warning(
                    f"Failed to load model cache from both sources: {e}, {e2}"
                )
                self.model_cache = {}

    def get_channels_by_model(self, model_name: str) -> list[Channel]:
        """根据模型名称获取渠道"""
        return [ch for ch in self.get_enabled_channels() if ch.model_name == model_name]

    def get_channels_by_tag(self, tag: str) -> list[Channel]:
        """根据标签获取渠道"""
        return [ch for ch in self.get_enabled_channels() if tag in ch.tags]

    def _build_memory_index(self) -> None:
        """构建内存索引（启动时预加载）"""
        try:
            if not self.model_cache:
                logger.warning("MEMORY INDEX: No model cache to index")
                return

            from core.utils.memory_index import get_memory_index

            memory_index = get_memory_index()

            # 获取渠道配置用于标签继承
            channel_configs = []
            try:
                from core.scheduler.tasks.model_discovery import get_merged_config

                merged_config = get_merged_config()
                channel_configs = merged_config.get("channels", [])
                logger.debug(
                    f"MEMORY INDEX: Loaded {len(channel_configs)} channel configs for tag mapping"
                )
            except Exception as e:
                logger.warning(f"MEMORY INDEX: Failed to load channel configs: {e}")

            stats = memory_index.build_index_from_cache(
                self.model_cache, channel_configs
            )

            logger.info(
                f"MEMORY INDEX READY: {stats.total_models} models, {stats.total_tags} tags, "
                f"{stats.memory_usage_mb:.1f}MB memory in {stats.build_time_ms:.1f}ms"
            )

        except Exception as e:
            logger.error(f"MEMORY INDEX BUILD FAILED: {e}")
            # 不影响系统启动，继续运行

    def _needs_cache_migration(self, cache: dict[str, Any]) -> bool:
        """检查缓存是否需要迁移到API Key级别格式"""
        if not cache:
            return False

        # 检查是否存在旧格式的缓存键
        for cache_key in cache.keys():
            if not self.api_key_cache_manager.is_api_key_cache(cache_key):
                return True
        return False

    def _get_channels_for_migration(self) -> dict[str, Any]:
        """获取用于缓存迁移的渠道映射"""
        channels_map = {}
        for channel in self.config.channels:
            channels_map[channel.id] = {
                "id": channel.id,
                "provider": getattr(
                    channel, "provider_name", getattr(channel, "provider", "unknown")
                ),
                "api_key": getattr(channel, "api_key", ""),
                "enabled": channel.enabled,
            }
        return channels_map

    def _save_migrated_cache(self) -> None:
        """保存迁移后的缓存（同步版本，为兼容性保留）"""
        try:
            cache_file = (
                Path(__file__).parent.parent / "cache" / "discovered_models.json"
            )
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(self.model_cache, f, indent=2, ensure_ascii=False)
            logger.info("Migrated cache saved successfully")
        except Exception as e:
            logger.error(f"Failed to save migrated cache: {e}")

    async def _save_migrated_cache_async(self) -> None:
        """异步保存迁移后的缓存"""
        try:
            cache_file = (
                Path(__file__).parent.parent / "cache" / "discovered_models.json"
            )
            file_manager = get_async_file_manager()
            success = await file_manager.write_json(
                cache_file, self.model_cache, indent=2
            )

            if success:
                logger.info("Migrated cache saved successfully")
            else:
                raise Exception("Failed to write cache file")
        except Exception as e:
            logger.error(f"Failed to save migrated cache async: {e}")

    async def _migrate_cache_background(self, raw_cache: dict[str, Any]) -> None:
        """后台迁移缓存格式（不阻塞主线程）"""
        try:
            logger.info("BACKGROUND MIGRATION: Starting cache migration in background")

            # 执行迁移
            migrated_cache = self.api_key_cache_manager.migrate_legacy_cache(
                raw_cache, self._get_channels_for_migration()
            )

            # 清理无效条目
            cleaned_cache = self.api_key_cache_manager.cleanup_invalid_entries(
                migrated_cache, self._get_channels_for_migration()
            )

            # [BOOST] 先保存已清理的缓存到磁盘，但不立即更新内存缓存
            self.model_cache = cleaned_cache  # 临时设置以便保存
            await self._save_migrated_cache_async()

            # [BOOST] 标记迁移完成状态
            self._migration_completed = True
            self._migration_in_progress = False

            # [BOOST] 重建内存索引以使用新缓存（一次性操作）
            self._build_memory_index()

            logger.info("BACKGROUND MIGRATION: Cache migration completed successfully")

        except Exception as e:
            logger.error(
                f"BACKGROUND MIGRATION: Failed to migrate cache in background: {e}"
            )
            # [BOOST] 迁移失败时重置状态，允许重试
            self._migration_in_progress = False

    async def _load_model_cache_from_disk_async(self) -> None:
        """异步从磁盘加载模型发现任务的缓存"""
        try:
            file_manager = get_async_file_manager()
            cache_file = (
                Path(__file__).parent.parent / "cache" / "discovered_models.json"
            )

            if await file_manager.file_exists(cache_file):
                raw_cache = await file_manager.read_json(cache_file, {})

                # 检查是否需要迁移缓存格式
                if self._needs_cache_migration(raw_cache):
                    logger.info(
                        "Migrating cache from legacy format to API key-level format"
                    )
                    self.model_cache = self.api_key_cache_manager.migrate_legacy_cache(
                        raw_cache, self._get_channels_for_migration()
                    )
                    # 异步保存迁移后的缓存
                    await self._save_migrated_cache_async()
                else:
                    self.model_cache = raw_cache

                # 清理无效条目
                self.model_cache = self.api_key_cache_manager.cleanup_invalid_entries(
                    self.model_cache, self._get_channels_for_migration()
                )

                # 输出缓存统计信息
                stats = self.api_key_cache_manager.get_cache_statistics(
                    self.model_cache
                )
                logger.info(
                    f"Loaded model cache: {stats['total_entries']} entries, "
                    f"{stats['api_key_entries']} API key-level, {stats['legacy_entries']} legacy, "
                    f"{stats['api_key_coverage']}% coverage"
                )

                # [BOOST] 立即构建内存索引（启动时预加载）
                self._build_memory_index()
            else:
                logger.warning("Model cache file not found")
                self.model_cache = {}
        except Exception as e:
            # 作为后备方案，尝试从任务模块加载
            try:
                from .scheduler.tasks.model_discovery import get_model_discovery_task

                task = get_model_discovery_task()
                raw_cache = task.cached_models
                if raw_cache:
                    # 应用相同的迁移逻辑
                    if self._needs_cache_migration(raw_cache):
                        logger.info(
                            "Migrating task cache from legacy format to API key-level format"
                        )
                        self.model_cache = (
                            self.api_key_cache_manager.migrate_legacy_cache(
                                raw_cache, self._get_channels_for_migration()
                            )
                        )
                    else:
                        self.model_cache = raw_cache
                    logger.info(
                        f"Loaded model cache from task for {len(self.model_cache)} entries"
                    )
                else:
                    self.model_cache = {}
            except Exception as e2:
                logger.warning(
                    f"Failed to load model cache from both sources: {e}, {e2}"
                )
                self.model_cache = {}

    def get_model_cache(self) -> dict[str, dict]:
        """获取模型缓存（兼容性方法）"""
        return self.model_cache

    def get_model_cache_by_channel_and_key(
        self, channel_id: str, api_key: str
    ) -> Optional[dict]:
        """获取特定API Key的模型缓存"""
        cache_key = self.api_key_cache_manager.generate_cache_key(channel_id, api_key)
        return self.model_cache.get(cache_key)

    def get_model_cache_by_channel(self, channel_id: str) -> dict[str, Any]:
        """获取渠道下所有API Key的缓存（兼容性方法）"""
        # 查找该渠道的所有缓存条目
        channel_cache_keys = self.api_key_cache_manager.find_cache_entries_by_channel(
            self.model_cache, channel_id
        )

        if not channel_cache_keys:
            # 尝试查找旧格式缓存
            legacy_cache = self.model_cache.get(channel_id)
            if legacy_cache:
                return legacy_cache
            return {}

        # 如果只有一个API Key，返回其缓存（向后兼容）
        if len(channel_cache_keys) == 1:
            return self.model_cache[channel_cache_keys[0]]

        # 多个API Key的情况，返回合并结果
        merged_models = []
        latest_status = "unknown"
        latest_update = None

        for cache_key in channel_cache_keys:
            cache_data = self.model_cache[cache_key]
            models = cache_data.get("models", [])
            merged_models.extend(models)

            # 使用最新的状态和更新时间
            if cache_data.get("last_updated", "") > (latest_update or ""):
                latest_update = cache_data.get("last_updated")
                latest_status = cache_data.get("status", "unknown")

        # 去重并排序
        unique_models = sorted(set(merged_models))

        return {
            "channel_id": channel_id,
            "models": unique_models,
            "model_count": len(unique_models),
            "status": latest_status,
            "last_updated": latest_update,
            "merged_from_keys": len(channel_cache_keys),
            "note": f"Merged from {len(channel_cache_keys)} API keys",
        }

    def get_enabled_channels(self) -> list[Channel]:
        """获取所有启用的渠道"""
        return [ch for ch in self.config.channels if ch.enabled]

    def get_channel_by_id(self, channel_id: str) -> Optional[Channel]:
        """根据ID获取渠道"""
        for channel in self.config.channels:
            if channel.id == channel_id:
                return channel
        return None

    def update_model_cache(self, new_cache: dict[str, dict]) -> None:
        """更新模型缓存（支持API Key级别缓存）"""
        # 检查是否需要迁移新的缓存数据
        if self._needs_cache_migration(new_cache):
            logger.info("Migrating new cache data to API key-level format")
            migrated_cache = self.api_key_cache_manager.migrate_legacy_cache(
                new_cache, self._get_channels_for_migration()
            )
            self.model_cache.update(migrated_cache)
        else:
            self.model_cache.update(new_cache)

        # 输出更新统计信息
        stats = self.api_key_cache_manager.get_cache_statistics(self.model_cache)
        logger.info(
            f"Updated model cache: {stats['total_entries']} entries, "
            f"{stats['api_key_coverage']}% API key-level coverage"
        )

    def update_model_cache_for_channel_and_key(
        self, channel_id: str, api_key: str, cache_data: dict[str, Any]
    ):
        """更新特定渠道和API Key的模型缓存"""
        cache_key = self.api_key_cache_manager.generate_cache_key(channel_id, api_key)

        # 添加API Key相关元数据
        enhanced_cache_data = {
            **cache_data,
            "cache_key": cache_key,
            "channel_id": channel_id,
            "api_key_hash": cache_key.split("_")[-1] if "_" in cache_key else "",
            "updated_at": datetime.now().isoformat(),
        }

        self.model_cache[cache_key] = enhanced_cache_data
        logger.info(
            f"Updated cache for channel '{channel_id}' with API key hash '{enhanced_cache_data['api_key_hash'][:8]}...'"
        )

    def invalidate_cache_for_channel(
        self, channel_id: str, api_key: Optional[str] = None
    ):
        """使特定渠道的缓存失效"""
        if api_key:
            # 清除特定API Key的缓存
            cache_key = self.api_key_cache_manager.generate_cache_key(
                channel_id, api_key
            )
            if cache_key in self.model_cache:
                del self.model_cache[cache_key]
                logger.info(
                    f"Invalidated cache for channel '{channel_id}' with specific API key"
                )
        else:
            # 清除该渠道所有API Key的缓存
            channel_cache_keys = (
                self.api_key_cache_manager.find_cache_entries_by_channel(
                    self.model_cache, channel_id
                )
            )
            for cache_key in channel_cache_keys:
                if cache_key in self.model_cache:
                    del self.model_cache[cache_key]

            # 同时清除可能存在的旧格式缓存
            if channel_id in self.model_cache:
                del self.model_cache[channel_id]

            logger.info(
                f"Invalidated {len(channel_cache_keys)} cache entries for channel '{channel_id}'"
            )

    def update_channel_health(
        self, channel_id: str, success: bool, latency: Optional[float] = None
    ):
        """更新渠道健康状态"""
        current_health = self.runtime_state.health_scores.get(channel_id, 1.0)

        if success:
            new_health = min(1.0, current_health * 1.01 + 0.01)
        else:
            new_health = max(0.0, current_health * 0.9 - 0.1)

        self.runtime_state.health_scores[channel_id] = new_health

        # 更新统计信息
        if channel_id not in self.runtime_state.channel_stats:
            self.runtime_state.channel_stats[channel_id] = {
                "request_count": 0,
                "success_count": 0,
                "total_latency": 0.0,
                "avg_latency_ms": 0.0,
            }

        stats = self.runtime_state.channel_stats[channel_id]
        stats["request_count"] = stats.get("request_count", 0) + 1

        if success:
            stats["success_count"] = stats.get("success_count", 0) + 1
            if latency is not None:
                stats["total_latency"] = stats.get("total_latency", 0.0) + latency
                stats["avg_latency_ms"] = (stats["total_latency"] * 1000) / stats[
                    "success_count"
                ]

        if new_health < 0.3:
            logger.warning(
                f"Channel {channel_id} health score is low: {new_health:.3f}"
            )

    def get_server_config(self) -> dict[str, Any]:
        """获取服务器配置"""
        return {
            "host": self.config.server.host,
            "port": self.config.server.port,
            "debug": self.config.server.debug,
            "cors_origins": self.config.server.cors_origins,
        }

    def get_routing_config(self) -> dict[str, Any]:
        """获取路由配置"""
        return {
            "default_strategy": self.config.routing.default_strategy,
            "enable_fallback": self.config.routing.enable_fallback,
            "max_retry_attempts": self.config.routing.max_retry_attempts,
        }

    def get_tasks_config(self) -> dict[str, Any]:
        """获取任务配置"""
        return {
            "model_discovery": {
                "enabled": self.config.tasks.model_discovery.enabled,
                "interval_hours": self.config.tasks.model_discovery.interval_hours,
                "run_on_startup": self.config.tasks.model_discovery.run_on_startup,
            },
            # [DELETE] Removed pricing_discovery - was generating unused cache files
            "health_check": {
                "enabled": self.config.tasks.health_check.enabled,
                "interval_minutes": self.config.tasks.health_check.interval_minutes,
                "run_on_startup": self.config.tasks.health_check.run_on_startup,
            },
            "api_key_validation": {
                "enabled": self.config.tasks.api_key_validation.enabled,
                "interval_hours": self.config.tasks.api_key_validation.interval_hours,
                "run_on_startup": self.config.tasks.api_key_validation.run_on_startup,
            },
        }

    def get_system_config(self) -> dict[str, Any]:
        """获取系统配置"""
        return {
            "name": self.config.system.name,
            "version": self.config.system.version,
            "storage_mode": self.config.system.storage_mode,
        }

    def get_provider(self, provider_name: str) -> Optional[Provider]:
        """根据名称获取Provider配置"""
        provider = self.config.providers.get(provider_name)
        if provider:
            return provider

        # 如果找不到provider，返回一个默认的OpenAI兼容配置
        logger.warning(
            f"Provider '{provider_name}' not found, using default OpenAI-compatible config"
        )
        return Provider(
            name=provider_name,
            display_name=provider_name.title(),
            adapter_class="OpenAIAdapter",
            base_url="https://api.openai.com",
            auth_type="bearer",
            rate_limit=60,
            capabilities=["text", "function_calling"],
        )

    # --- Simple mutation helpers for YAML-first workflow ---
    def set_channel_enabled(self, channel_id: str, enabled: bool) -> bool:
        """Enable/disable a channel and persist to YAML, then reload config.

        This edits the YAML file directly to keep truth in one place, then
        refreshes the in-memory Pydantic config and maps.
        """
        try:

            import yaml as _yaml

            with open(self.config_path, encoding="utf-8") as f:
                raw = _yaml.safe_load(f) or {}

            changed = False
            for ch in raw.get("channels", []):
                if ch.get("id") == channel_id:
                    ch["enabled"] = bool(enabled)
                    changed = True
                    break

            if not changed:
                logger.warning(
                    f"Channel '{channel_id}' not found in YAML; no changes applied"
                )
                return False

            # Save back and reload Pydantic config
            self._save_config_to_file(raw)
            self.config = self._load_and_validate_config()
            self.channels_map = {ch.id: ch for ch in self.config.channels}
            logger.info(
                f"Configuration updated: channel '{channel_id}' enabled={enabled}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update channel enabled flag: {e}")
            return False

    def set_channel_priority(self, channel_id: str, priority: int) -> bool:
        """Set channel priority and persist to YAML, then reload config."""
        try:
            import yaml as _yaml

            with open(self.config_path, encoding="utf-8") as f:
                raw = _yaml.safe_load(f) or {}

            changed = False
            for ch in raw.get("channels", []):
                if ch.get("id") == channel_id:
                    ch["priority"] = int(priority)
                    changed = True
                    break

            if not changed:
                logger.warning(
                    f"Channel '{channel_id}' not found in YAML; no changes applied"
                )
                return False

            self._save_config_to_file(raw)
            self.config = self._load_and_validate_config()
            self.channels_map = {ch.id: ch for ch in self.config.channels}
            logger.info(
                f"Configuration updated: channel '{channel_id}' priority={priority}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update channel priority: {e}")
            return False

    @property
    def config_data(self) -> dict[str, Any]:
        """为兼容性提供config_data属性"""
        return {
            "system": self.get_system_config(),
            "server": self.get_server_config(),
            "providers": {k: v.dict() for k, v in self.config.providers.items()},
            "channels": [ch.dict() for ch in self.config.channels],
            "routing": self.get_routing_config(),
            "tasks": self.get_tasks_config(),
        }


# 全局配置加载器实例
_yaml_config_loader: Optional[YAMLConfigLoader] = None


def get_yaml_config_loader() -> YAMLConfigLoader:
    """获取全局YAML配置加载器实例"""
    global _yaml_config_loader
    if _yaml_config_loader is None:
        _yaml_config_loader = YAMLConfigLoader()
    return _yaml_config_loader
