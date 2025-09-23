"""
按渠道分离的缓存管理器
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .model_analyzer import ModelSpecs, get_model_analyzer

logger = logging.getLogger(__name__)


class ChannelCacheManager:
    """按渠道分离的缓存管理器"""

    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # 创建渠道缓存子目录
        self.channels_cache_dir = self.cache_dir / "channels"
        self.channels_cache_dir.mkdir(exist_ok=True)

        self.model_analyzer = get_model_analyzer()

    def save_channel_models(self, channel_id: str, models_data: Dict[str, Any]) -> None:
        """保存单个渠道的模型发现数据"""

        channel_cache_file = self.channels_cache_dir / f"{channel_id}.json"

        # 分析所有模型的参数和上下文信息
        analyzed_models = {}
        if "models" in models_data:
            model_list = models_data["models"]
            response_data = models_data.get("response_data", {})

            for model_name in model_list:
                # 查找对应的详细信息
                model_detail = None
                if "data" in response_data:
                    for item in response_data["data"]:
                        if item.get("id") == model_name:
                            model_detail = item
                            break

                # 分析模型规格
                specs = self.model_analyzer.analyze_model(model_name, model_detail)
                analyzed_models[model_name] = {
                    "id": model_name,
                    "parameter_count": specs.parameter_count,
                    "context_length": specs.context_length,
                    "parameter_size_text": specs.parameter_size_text,
                    "context_text": specs.context_text,
                    "raw_data": model_detail or {},
                }

        # 构建完整的缓存数据
        cache_data = {
            "channel_id": channel_id,
            "basic_info": {
                "provider": models_data.get("provider"),
                "base_url": models_data.get("base_url"),
                "models_url": models_data.get("models_url"),
                "last_updated": models_data.get(
                    "last_updated", datetime.now().isoformat()
                ),
                "status": models_data.get("status"),
                "model_count": len(analyzed_models),
            },
            "models": analyzed_models,
            "raw_response": models_data.get("response_data", {}),
            "analysis_metadata": {
                "analyzed_at": datetime.now().isoformat(),
                "analyzer_version": "1.0",
                "models_with_params": sum(
                    1 for m in analyzed_models.values() if m["parameter_count"]
                ),
                "models_with_context": sum(
                    1 for m in analyzed_models.values() if m["context_length"]
                ),
            },
        }

        # 保存到文件
        try:
            with open(channel_cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)

            logger.info(
                f"✅ Saved channel cache for {channel_id}: {len(analyzed_models)} models analyzed"
            )
            logger.info(
                f"   📊 Models with parameter info: {cache_data['analysis_metadata']['models_with_params']}"
            )
            logger.info(
                f"   📏 Models with context info: {cache_data['analysis_metadata']['models_with_context']}"
            )

        except Exception as e:
            logger.error(f"❌ Failed to save channel cache for {channel_id}: {e}")

    def load_channel_models(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """加载单个渠道的模型数据"""
        channel_cache_file = self.channels_cache_dir / f"{channel_id}.json"

        if not channel_cache_file.exists():
            return None

        try:
            with open(channel_cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ Failed to load channel cache for {channel_id}: {e}")
            return None

    def get_all_channel_ids(self) -> List[str]:
        """获取所有已缓存的渠道ID"""
        channel_files = list(self.channels_cache_dir.glob("*.json"))
        return [f.stem for f in channel_files]

    def get_channel_summary(self) -> Dict[str, Any]:
        """获取所有渠道的摘要信息"""
        summary = {
            "total_channels": 0,
            "total_models": 0,
            "models_with_params": 0,
            "models_with_context": 0,
            "channels": {},
        }

        for channel_id in self.get_all_channel_ids():
            cache_data = self.load_channel_models(channel_id)
            if cache_data:
                basic_info = cache_data.get("basic_info", {})
                metadata = cache_data.get("analysis_metadata", {})

                summary["total_channels"] += 1
                summary["total_models"] += basic_info.get("model_count", 0)
                summary["models_with_params"] += metadata.get("models_with_params", 0)
                summary["models_with_context"] += metadata.get("models_with_context", 0)

                summary["channels"][channel_id] = {
                    "provider": basic_info.get("provider"),
                    "model_count": basic_info.get("model_count", 0),
                    "status": basic_info.get("status"),
                    "last_updated": basic_info.get("last_updated"),
                    "models_with_params": metadata.get("models_with_params", 0),
                    "models_with_context": metadata.get("models_with_context", 0),
                }

        return summary

    def migrate_from_old_cache(
        self, old_cache_file: str = "cache/discovered_models.json"
    ) -> None:
        """从旧的合并缓存迁移到新的分离缓存"""
        old_cache_path = Path(old_cache_file)

        if not old_cache_path.exists():
            logger.info("🔄 No old cache file found, skipping migration")
            return

        logger.info("🔄 Migrating from old cache format to channel-separated format")

        try:
            with open(old_cache_path, "r", encoding="utf-8") as f:
                old_data = json.load(f)

            migrated_count = 0
            for channel_id, channel_data in old_data.items():
                if isinstance(channel_data, dict) and "models" in channel_data:
                    self.save_channel_models(channel_id, channel_data)
                    migrated_count += 1

            logger.info(f"✅ Migration completed: {migrated_count} channels migrated")

            # 备份旧文件
            backup_path = old_cache_path.with_suffix(".json.backup")
            old_cache_path.rename(backup_path)
            logger.info(f"📦 Old cache backed up to: {backup_path}")

        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")

    def search_models_by_specs(
        self,
        min_params: Optional[int] = None,
        min_context: Optional[int] = None,
        channel_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """根据规格搜索模型"""
        results = []

        search_channels = channel_ids or self.get_all_channel_ids()

        for channel_id in search_channels:
            cache_data = self.load_channel_models(channel_id)
            if not cache_data:
                continue

            channel_info = cache_data.get("basic_info", {})
            models = cache_data.get("models", {})

            for model_name, model_info in models.items():
                # 检查参数数量条件
                if min_params is not None:
                    param_count = model_info.get("parameter_count")
                    if not param_count or param_count < min_params:
                        continue

                # 检查上下文长度条件
                if min_context is not None:
                    context_length = model_info.get("context_length")
                    if not context_length or context_length < min_context:
                        continue

                # 符合条件的模型
                results.append(
                    {
                        "channel_id": channel_id,
                        "provider": channel_info.get("provider"),
                        "model_name": model_name,
                        "parameter_count": model_info.get("parameter_count"),
                        "context_length": model_info.get("context_length"),
                        "parameter_size_text": model_info.get("parameter_size_text"),
                        "context_text": model_info.get("context_text"),
                    }
                )

        return results

    def cleanup_old_caches(self) -> None:
        """清理旧的缓存文件"""
        old_files = ["discovered_models.json.backup", "smart_cache.json"]

        for filename in old_files:
            file_path = self.cache_dir / filename
            if file_path.exists():
                try:
                    file_path.unlink()
                    logger.info(f"🗑️ Removed old cache file: {filename}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to remove {filename}: {e}")


# 全局缓存管理器实例
_cache_manager: Optional[ChannelCacheManager] = None


def get_channel_cache_manager() -> ChannelCacheManager:
    """获取全局渠道缓存管理器实例"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = ChannelCacheManager()
    return _cache_manager
