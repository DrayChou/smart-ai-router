"""
请求级缓存系统 - 优化模型选择性能
Created: 2025年1月
"""

import hashlib
import time
import json
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import asyncio
import logging

from ..config_models import Channel

logger = logging.getLogger(__name__)


@dataclass
class RequestFingerprint:
    """请求指纹，用于缓存键生成"""
    model: str
    routing_strategy: str = "balanced"
    required_capabilities: Optional[List[str]] = None
    min_context_length: Optional[int] = None
    max_cost_per_1k: Optional[float] = None
    prefer_local: bool = False
    exclude_providers: Optional[List[str]] = None
    # 新增影响路由的参数
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: bool = False
    has_functions: bool = False  # 是否有function_calling需求
    
    def to_cache_key(self) -> str:
        """生成缓存键的Hash值"""
        # 创建标准化的指纹字典
        fingerprint_dict = {
            "model": self.model.lower().strip(),
            "routing_strategy": self.routing_strategy,
            "required_capabilities": sorted(self.required_capabilities or []),
            "min_context_length": self.min_context_length,
            "max_cost_per_1k": self.max_cost_per_1k,
            "prefer_local": self.prefer_local,
            "exclude_providers": sorted(self.exclude_providers or []),
            # 新增参数
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": self.stream,
            "has_functions": self.has_functions
        }
        
        # 转换为JSON字符串（确保key排序）
        fingerprint_json = json.dumps(fingerprint_dict, sort_keys=True)
        
        # 生成SHA-256 Hash - 使用32位避免碰撞风险
        hash_object = hashlib.sha256(fingerprint_json.encode('utf-8'))
        return f"req_{hash_object.hexdigest()[:32]}"  # 使用32位减少碰撞风险


@dataclass 
class CachedModelSelection:
    """缓存的模型选择结果"""
    primary_channel: Channel
    backup_channels: List[Channel]
    selection_reason: str
    cost_estimate: float
    created_at: datetime
    expires_at: datetime
    request_count: int = 0
    last_used_at: Optional[datetime] = None
    
    def is_expired(self) -> bool:
        """检查是否已过期"""
        return datetime.now() > self.expires_at
    
    def is_valid(self) -> bool:
        """检查缓存是否有效（未过期且渠道健康）"""
        if self.is_expired():
            return False
        
        # 检查主要渠道是否仍然健康
        if not self.primary_channel.enabled:
            return False
            
        return True
    
    def mark_used(self):
        """标记为已使用"""
        self.request_count += 1
        self.last_used_at = datetime.now()


class RequestModelCache:
    """请求级模型选择缓存管理器"""
    
    def __init__(self, 
                 default_ttl_seconds: int = 60,
                 max_cache_entries: int = 1000,
                 cleanup_interval_seconds: int = 300):
        """
        Args:
            default_ttl_seconds: 默认缓存TTL（秒）
            max_cache_entries: 最大缓存条目数
            cleanup_interval_seconds: 清理间隔（秒）
        """
        self.default_ttl = default_ttl_seconds
        self.max_entries = max_cache_entries
        self.cleanup_interval = cleanup_interval_seconds
        
        # 缓存存储: {cache_key: CachedModelSelection}
        self._cache: Dict[str, CachedModelSelection] = {}
        
        # 统计信息
        self._stats = {
            "hits": 0,
            "misses": 0,
            "invalidations": 0,
            "cleanup_runs": 0
        }
        
        # 异步锁保护并发访问
        self._lock = asyncio.Lock()
        
        # 最后清理时间（同步清理机制）
        self._last_cleanup = datetime.now()
    
    def _maybe_cleanup(self):
        """按需清理过期缓存（同步机制，避免异步任务复杂性）"""
        now = datetime.now()
        if (now - self._last_cleanup).total_seconds() > self.cleanup_interval:
            self._cleanup_expired_sync()
            self._last_cleanup = now
    
    async def get_cached_selection(self, fingerprint: RequestFingerprint) -> Optional[CachedModelSelection]:
        """获取缓存的模型选择结果"""
        cache_key = fingerprint.to_cache_key()
        
        async with self._lock:
            # 按需清理
            self._maybe_cleanup()
            
            if cache_key not in self._cache:
                self._stats["misses"] += 1
                logger.debug(f"🚫 CACHE MISS: {cache_key} (model: {fingerprint.model})")
                return None
            
            cached_result = self._cache[cache_key]
            
            # 检查缓存有效性
            if not cached_result.is_valid():
                # 缓存失效，删除并返回None
                del self._cache[cache_key]
                self._stats["invalidations"] += 1
                logger.info(f"❌ CACHE INVALIDATED: {cache_key} (expired or unhealthy)")
                return None
            
            # 缓存命中
            cached_result.mark_used()
            self._stats["hits"] += 1
            
            age_seconds = (datetime.now() - cached_result.created_at).total_seconds()
            logger.debug(f"✅ CACHE HIT: {cache_key} "
                       f"(model: {fingerprint.model}, age: {age_seconds:.1f}s, uses: {cached_result.request_count})")
            
            return cached_result
    
    async def cache_selection(self, 
                             fingerprint: RequestFingerprint,
                             primary_channel: Channel,
                             backup_channels: List[Channel],
                             selection_reason: str,
                             cost_estimate: float,
                             ttl_seconds: Optional[int] = None) -> str:
        """缓存模型选择结果"""
        
        cache_key = fingerprint.to_cache_key()
        ttl = ttl_seconds or self.default_ttl
        
        async with self._lock:
            # 检查缓存大小限制
            if len(self._cache) >= self.max_entries:
                self._evict_lru_sync()
            
            now = datetime.now()
            expires_at = now + timedelta(seconds=ttl)
            
            cached_selection = CachedModelSelection(
                primary_channel=primary_channel,
                backup_channels=backup_channels[:5],  # 限制备选数量
                selection_reason=selection_reason,
                cost_estimate=cost_estimate,
                created_at=now,
                expires_at=expires_at
            )
            
            self._cache[cache_key] = cached_selection
            
            logger.debug(f"💾 CACHED: {cache_key} -> {primary_channel.name} "
                       f"(ttl: {ttl}s, backups: {len(backup_channels)}, cost: ${cost_estimate:.4f})")
            
            return cache_key
    
    def invalidate_channel(self, channel_id: str):
        """使特定渠道相关的缓存失效"""
        invalidated_keys = []
        
        for cache_key, cached_result in list(self._cache.items()):
            if (cached_result.primary_channel.id == channel_id or
                any(backup.id == channel_id for backup in cached_result.backup_channels)):
                del self._cache[cache_key]
                invalidated_keys.append(cache_key)
        
        if invalidated_keys:
            self._stats["invalidations"] += len(invalidated_keys)
            logger.info(f"🗑️  INVALIDATED {len(invalidated_keys)} cache entries for channel: {channel_id}")
    
    def invalidate_model(self, model_name: str):
        """使特定模型相关的缓存失效（基于cache_key前缀匹配）"""
        # 注意：由于cache_key是Hash，无法直接按模型名匹配
        # 这里采用保守策略：清空所有缓存
        cleared_count = len(self._cache)
        self._cache.clear()
        self._stats["invalidations"] += cleared_count
        logger.warning(f"🗑️  CLEARED ALL CACHE due to model update: {model_name} ({cleared_count} entries)")
    
    def _cleanup_expired_sync(self):
        """清理过期缓存（内部同步方法）"""
        expired_keys = []
        now = datetime.now()
        
        for cache_key, cached_result in list(self._cache.items()):
            if cached_result.is_expired():
                expired_keys.append(cache_key)
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            self._stats["cleanup_runs"] += 1
            self._stats["invalidations"] += len(expired_keys)
            logger.debug(f"🧹 CLEANUP: Removed {len(expired_keys)} expired cache entries")
    
    def _evict_lru_sync(self):
        """LRU淘汰策略（内部同步方法）"""
        if not self._cache:
            return
        
        # 找到最久未使用的条目（优化为单行）
        lru_key = min(self._cache.keys(), 
                     key=lambda k: self._cache[k].last_used_at or self._cache[k].created_at)
        
        if lru_key:
            del self._cache[lru_key]
            logger.debug(f"🗑️  LRU EVICTED: {lru_key}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "cache_entries": len(self._cache),
            "max_entries": self.max_entries,
            "hit_rate_percent": round(hit_rate, 2),
            "total_hits": self._stats["hits"],
            "total_misses": self._stats["misses"],
            "total_invalidations": self._stats["invalidations"],
            "cleanup_runs": self._stats["cleanup_runs"],
            "default_ttl_seconds": self.default_ttl
        }
    
    def clear_all(self):
        """清空所有缓存"""
        cleared_count = len(self._cache)
        self._cache.clear()
        logger.info(f"🗑️  CLEARED ALL CACHE: {cleared_count} entries removed")
    
    def __del__(self):
        """清理资源"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()


# 全局缓存实例
_global_cache: Optional[RequestModelCache] = None


def get_request_cache() -> RequestModelCache:
    """获取全局请求缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = RequestModelCache(
            default_ttl_seconds=60,      # 1分钟默认TTL
            max_cache_entries=1000,      # 最大1000个缓存条目  
            cleanup_interval_seconds=300 # 5分钟清理一次
        )
    return _global_cache