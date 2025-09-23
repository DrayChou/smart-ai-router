#!/usr/bin/env python3
"""
API Key级别缓存管理器
解决同一渠道不同API Key可能有不同定价和可用模型的问题
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .model_analyzer import ModelSpecs, get_model_analyzer

logger = logging.getLogger(__name__)


class ApiKeyCacheManager:
    """API Key级别的缓存管理器"""

    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # 创建API Key级别缓存子目录
        self.api_keys_cache_dir = self.cache_dir / "api_keys"
        self.api_keys_cache_dir.mkdir(exist_ok=True)

        # 创建映射文件目录
        self.mappings_dir = self.cache_dir / "mappings"
        self.mappings_dir.mkdir(exist_ok=True)

        self.model_analyzer = get_model_analyzer()

        # 内存缓存，避免频繁文件读取
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl: Dict[str, datetime] = {}
        self._ttl_duration = timedelta(hours=1)  # 1小时TTL

    def _get_api_key_hash(self, api_key: str) -> str:
        """生成API Key的安全哈希值"""
        if not api_key or api_key == "dummy":
            return "default"

        # 使用SHA256生成不可逆哈希
        hash_obj = hashlib.sha256(api_key.encode("utf-8"))
        return hash_obj.hexdigest()[:16]  # 取前16字符作为文件名

    def _get_cache_key(self, channel_id: str, api_key: str) -> str:
        """生成缓存键"""
        api_key_hash = self._get_api_key_hash(api_key)
        return f"{channel_id}_{api_key_hash}"

    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查内存缓存是否有效"""
        if cache_key not in self._cache_ttl:
            return False
        return datetime.now() < self._cache_ttl[cache_key]

    def save_api_key_models(
        self,
        channel_id: str,
        api_key: str,
        models_data: Dict[str, Any],
        provider: str = None,
    ) -> None:
        """保存特定API Key的模型发现数据"""

        cache_key = self._get_cache_key(channel_id, api_key)
        api_key_hash = self._get_api_key_hash(api_key)

        # 构建缓存文件路径
        cache_file = self.api_keys_cache_dir / f"{cache_key}.json"

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
                    "pricing": (
                        self._extract_pricing_info(model_detail)
                        if model_detail
                        else None
                    ),
                }

        # 构建完整的缓存数据
        cache_data = {
            "channel_id": channel_id,
            "api_key_hash": api_key_hash,
            "provider": provider or models_data.get("provider"),
            "basic_info": {
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
                "analyzer_version": "2.0",  # 升级版本号
                "api_key_level": True,  # 标记为API Key级别缓存
                "models_with_params": sum(
                    1 for m in analyzed_models.values() if m["parameter_count"]
                ),
                "models_with_context": sum(
                    1 for m in analyzed_models.values() if m["context_length"]
                ),
                "models_with_pricing": sum(
                    1 for m in analyzed_models.values() if m.get("pricing")
                ),
            },
        }

        # 保存到文件
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)

            # 更新内存缓存
            self._memory_cache[cache_key] = cache_data
            self._cache_ttl[cache_key] = datetime.now() + self._ttl_duration

            # 更新映射文件
            self._update_mapping(channel_id, api_key_hash, cache_key)

            logger.info(
                f"✅ Saved API key level cache for {channel_id} (key: {api_key_hash[:8]}...): {len(analyzed_models)} models"
            )
            logger.info(
                f"   📊 Models with parameter info: {cache_data['analysis_metadata']['models_with_params']}"
            )
            logger.info(
                f"   💰 Models with pricing info: {cache_data['analysis_metadata']['models_with_pricing']}"
            )

        except Exception as e:
            logger.error(f"❌ Failed to save API key cache for {channel_id}: {e}")

    def _extract_pricing_info(
        self, model_detail: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """从模型详情中提取定价信息"""
        if not model_detail:
            return None

        pricing = {}

        # 常见的定价字段
        for price_field in ["pricing", "cost", "price", "rates"]:
            if price_field in model_detail:
                pricing[price_field] = model_detail[price_field]

        # 检查是否有输入/输出定价
        for field in model_detail:
            if any(
                keyword in field.lower()
                for keyword in ["input", "prompt", "completion", "output"]
            ):
                if any(
                    price_keyword in field.lower()
                    for price_keyword in ["price", "cost", "rate"]
                ):
                    pricing[field] = model_detail[field]

        # 检查免费标记
        if "free" in str(model_detail).lower():
            pricing["is_free"] = True

        return pricing if pricing else None

    def _update_mapping(self, channel_id: str, api_key_hash: str, cache_key: str):
        """更新渠道到API Key的映射"""
        mapping_file = self.mappings_dir / f"{channel_id}_mapping.json"

        # 读取现有映射
        mapping = {}
        if mapping_file.exists():
            try:
                with open(mapping_file, "r", encoding="utf-8") as f:
                    mapping = json.load(f)
            except Exception as e:
                logger.warning(f"无法读取映射文件 {mapping_file}: {e}")

        # 更新映射
        mapping[api_key_hash] = {
            "cache_key": cache_key,
            "updated_at": datetime.now().isoformat(),
        }

        # 保存映射
        try:
            with open(mapping_file, "w", encoding="utf-8") as f:
                json.dump(mapping, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"无法保存映射文件 {mapping_file}: {e}")

    def load_api_key_models(
        self, channel_id: str, api_key: str
    ) -> Optional[Dict[str, Any]]:
        """加载特定API Key的模型数据"""
        cache_key = self._get_cache_key(channel_id, api_key)

        # 检查内存缓存
        if self._is_cache_valid(cache_key):
            return self._memory_cache.get(cache_key)

        # 从文件加载
        cache_file = self.api_keys_cache_dir / f"{cache_key}.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            # 更新内存缓存
            self._memory_cache[cache_key] = cache_data
            self._cache_ttl[cache_key] = datetime.now() + self._ttl_duration

            return cache_data

        except Exception as e:
            logger.error(f"❌ Failed to load API key cache for {channel_id}: {e}")
            return None

    def get_channel_api_keys(self, channel_id: str) -> List[str]:
        """获取渠道下的所有API Key哈希"""
        mapping_file = self.mappings_dir / f"{channel_id}_mapping.json"

        if not mapping_file.exists():
            return []

        try:
            with open(mapping_file, "r", encoding="utf-8") as f:
                mapping = json.load(f)
            return list(mapping.keys())
        except Exception as e:
            logger.error(f"无法读取渠道映射 {channel_id}: {e}")
            return []

    def load_channel_models_fallback(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """回退到任意可用的API Key数据（用于兼容性）"""
        api_keys = self.get_channel_api_keys(channel_id)

        if not api_keys:
            return None

        # 尝试加载第一个可用的API Key数据
        for api_key_hash in api_keys:
            cache_key = f"{channel_id}_{api_key_hash}"
            cache_file = self.api_keys_cache_dir / f"{cache_key}.json"

            if cache_file.exists():
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"无法加载缓存 {cache_key}: {e}")
                    continue

        return None

    def clear_api_key_cache(self, channel_id: str, api_key: str) -> bool:
        """清除特定API Key的缓存"""
        cache_key = self._get_cache_key(channel_id, api_key)

        # 清除内存缓存
        self._memory_cache.pop(cache_key, None)
        self._cache_ttl.pop(cache_key, None)

        # 删除文件缓存
        cache_file = self.api_keys_cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                cache_file.unlink()
                logger.info(f"✅ Cleared API key cache for {channel_id}")
                return True
            except Exception as e:
                logger.error(f"❌ Failed to clear API key cache: {e}")
                return False

        return True

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_files = len(list(self.api_keys_cache_dir.glob("*.json")))
        memory_entries = len(self._memory_cache)
        valid_memory_entries = sum(
            1 for key in self._memory_cache if self._is_cache_valid(key)
        )

        return {
            "total_cache_files": total_files,
            "memory_entries": memory_entries,
            "valid_memory_entries": valid_memory_entries,
            "cache_hit_rate": valid_memory_entries / max(1, memory_entries),
            "ttl_duration_hours": self._ttl_duration.total_seconds() / 3600,
        }


# 全局实例
_api_key_cache_manager = None


def get_api_key_cache_manager() -> ApiKeyCacheManager:
    """获取API Key缓存管理器实例"""
    global _api_key_cache_manager
    if _api_key_cache_manager is None:
        _api_key_cache_manager = ApiKeyCacheManager()
    return _api_key_cache_manager
