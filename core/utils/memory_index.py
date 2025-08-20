"""
内存索引系统 - 消除文件I/O性能瓶颈
构建高性能的标签→模型映射索引
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple, Optional
import threading

logger = logging.getLogger(__name__)

@dataclass
class ModelInfo:
    """模型信息"""
    channel_id: str
    model_name: str
    provider: str
    tags: Set[str]
    pricing: Optional[Dict] = None
    capabilities: Optional[Dict] = None
    specs: Optional[Dict] = None  # 模型规格信息（参数量、上下文长度等）
    # 健康状态缓存
    health_score: Optional[float] = None
    health_cached_at: Optional[float] = None  # Unix时间戳

@dataclass 
class IndexStats:
    """索引统计信息"""
    total_models: int
    total_channels: int
    total_tags: int
    build_time_ms: float
    memory_usage_mb: float

class MemoryModelIndex:
    """内存模型索引 - 高性能标签查询"""
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # 核心索引结构
        self._tag_to_models: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)  # tag -> {(channel_id, model_name)}
        self._channel_to_models: Dict[str, Set[str]] = defaultdict(set)  # channel_id -> {model_names}
        self._model_info: Dict[Tuple[str, str], ModelInfo] = {}  # (channel_id, model_name) -> ModelInfo
        
        # 性能统计
        self._stats = IndexStats(0, 0, 0, 0.0, 0.0)
        self._last_build_time = 0.0
        
        logger.info("🚀 MemoryModelIndex initialized - ready for high-performance tag queries")
    
    def build_index_from_cache(self, model_cache: Dict[str, Dict]) -> IndexStats:
        """
        从模型缓存构建内存索引
        
        Args:
            model_cache: 原始模型缓存数据
            
        Returns:
            索引构建统计信息
        """
        start_time = time.time()
        
        with self._lock:
            # 清空现有索引
            self._tag_to_models.clear()
            self._channel_to_models.clear()
            self._model_info.clear()
            
            logger.info(f"🔨 INDEX BUILD: Processing {len(model_cache)} cache entries...")
            
            total_models = 0
            processed_channels = set()
            
            for cache_key, cache_data in model_cache.items():
                if not isinstance(cache_data, dict):
                    continue
                
                # 提取渠道ID（处理API Key级别的缓存键）
                channel_id = self._extract_channel_id(cache_key)
                if not channel_id:
                    continue
                    
                processed_channels.add(channel_id)
                
                # 处理模型列表
                models = cache_data.get("models", [])
                models_data = cache_data.get("models_data", {})  # 模型详细规格数据
                provider = cache_data.get("provider", "unknown")
                
                for model_name in models:
                    if not isinstance(model_name, str):
                        continue
                    
                    # 生成标签
                    tags = self._generate_model_tags(model_name, provider)
                    
                    # 获取模型详细规格
                    model_specs = models_data.get(model_name, {}) if models_data else {}
                    
                    # 创建模型信息
                    model_key = (channel_id, model_name)
                    model_info = ModelInfo(
                        channel_id=channel_id,
                        model_name=model_name,
                        provider=provider,
                        tags=tags,
                        pricing=cache_data.get("models_pricing", {}).get(model_name),
                        capabilities=self._extract_capabilities(cache_data, model_name)
                    )
                    
                    # 添加模型规格到ModelInfo（扩展用于健康检查优化）
                    if model_specs:
                        model_info.specs = model_specs
                    
                    # 更新索引
                    self._model_info[model_key] = model_info
                    self._channel_to_models[channel_id].add(model_name)
                    
                    # 更新标签索引
                    for tag in tags:
                        self._tag_to_models[tag].add(model_key)
                    
                    total_models += 1
            
            # 构建统计信息
            build_time_ms = (time.time() - start_time) * 1000
            self._stats = IndexStats(
                total_models=total_models,
                total_channels=len(processed_channels),
                total_tags=len(self._tag_to_models),
                build_time_ms=build_time_ms,
                memory_usage_mb=self._estimate_memory_usage()
            )
            
            self._last_build_time = time.time()
            
            # 保存缓存哈希值以避免重复重建
            try:
                import hashlib
                # 🚀 优化：只对前50个缓存键计算哈希，与检查逻辑保持一致
                sorted_keys = sorted(model_cache.keys())[:50]
                self._cache_hash = hashlib.md5(str(sorted_keys).encode()).hexdigest()
            except:
                self._cache_hash = None
            
            logger.info(f"✅ INDEX BUILT: {total_models} models, {len(processed_channels)} channels, "
                       f"{len(self._tag_to_models)} tags in {build_time_ms:.1f}ms")
            
            return self._stats
    
    def find_models_by_tags(self, include_tags: List[str], exclude_tags: List[str] = None) -> List[Tuple[str, str]]:
        """
        根据标签查找模型（超高速）
        
        Args:
            include_tags: 必须包含的标签
            exclude_tags: 必须排除的标签
            
        Returns:
            匹配的模型列表 [(channel_id, model_name), ...]
        """
        if not include_tags:
            return []
        
        with self._lock:
            # 开始从最小的标签集合进行交集运算
            tag_sets = [self._tag_to_models.get(tag, set()) for tag in include_tags]
            if not all(tag_sets):
                return []  # 如果任何标签都没有匹配，直接返回空
            
            # 找到最小的集合作为起点（性能优化）
            result_set = min(tag_sets, key=len)
            
            # 计算交集
            for tag_set in tag_sets:
                if tag_set is not result_set:  # 避免自己和自己求交集
                    result_set = result_set.intersection(tag_set)
                    if not result_set:  # 如果交集为空，提前退出
                        break
            
            # 排除不需要的标签
            if exclude_tags and result_set:
                exclude_set = set()
                for tag in exclude_tags:
                    exclude_set.update(self._tag_to_models.get(tag, set()))
                result_set = result_set - exclude_set
            
            return list(result_set)
    
    def get_model_info(self, channel_id: str, model_name: str) -> Optional[ModelInfo]:
        """获取模型详细信息"""
        with self._lock:
            return self._model_info.get((channel_id, model_name))
    
    def get_model_specs(self, channel_id: str, model_name: str) -> Optional[Dict]:
        """获取模型规格（优化版，替代文件I/O）"""
        with self._lock:
            model_info = self._model_info.get((channel_id, model_name))
            return model_info.specs if model_info else None
    
    def get_channel_models(self, channel_id: str) -> Set[str]:
        """获取渠道下的所有模型"""
        with self._lock:
            return self._channel_to_models.get(channel_id, set()).copy()
    
    def get_health_score(self, channel_id: str, cache_ttl: float = 60.0) -> Optional[float]:
        """获取健康评分（带缓存TTL检查）"""
        current_time = time.time()
        
        with self._lock:
            # 查找该渠道下的任意模型来获取健康状态
            models = self._channel_to_models.get(channel_id, set())
            if not models:
                return None
            
            # 使用第一个模型的健康状态（渠道级别）
            first_model = next(iter(models))
            model_info = self._model_info.get((channel_id, first_model))
            
            if (model_info and 
                model_info.health_score is not None and 
                model_info.health_cached_at is not None and
                (current_time - model_info.health_cached_at) < cache_ttl):
                return model_info.health_score
            
            return None
    
    def set_health_score(self, channel_id: str, health_score: float):
        """设置健康评分（更新所有该渠道下的模型）"""
        current_time = time.time()
        
        with self._lock:
            models = self._channel_to_models.get(channel_id, set())
            for model_name in models:
                model_info = self._model_info.get((channel_id, model_name))
                if model_info:
                    model_info.health_score = health_score
                    model_info.health_cached_at = current_time
    
    def get_tag_stats(self) -> Dict[str, int]:
        """获取标签统计信息"""
        with self._lock:
            return {tag: len(models) for tag, models in self._tag_to_models.items()}
    
    def get_stats(self) -> IndexStats:
        """获取索引统计信息"""
        with self._lock:
            return self._stats
    
    def is_stale(self, cache_update_time: float) -> bool:
        """检查索引是否过期"""
        return cache_update_time > self._last_build_time
    
    def needs_rebuild(self, model_cache: Dict[str, Dict]) -> bool:
        """检查是否需要重建索引"""
        # 🚀 修复：只有在索引为空时才强制重建
        if self._stats.total_models == 0:
            logger.debug("INDEX REBUILD: Index is empty, needs rebuild")
            return True
        
        # 🚀 修复：更智能的缓存大小检查
        current_cache_size = len(model_cache)
        cached_channels = self._stats.total_channels
        
        # 🚀 容忍缓存迁移造成的大小变化（从legacy格式到API Key格式）
        if current_cache_size < cached_channels:
            # 如果缓存减少超过30%，可能是迁移导致的清理，需要重建
            reduction_ratio = current_cache_size / cached_channels
            if reduction_ratio < 0.7:  # 减少超过30%
                logger.debug(f"INDEX REBUILD: Cache size reduced significantly ({current_cache_size} vs {cached_channels})")
                return True
        elif current_cache_size > cached_channels:
            # 🚀 缓存增加了，仅当增加超过50%时才重建（更宽松）
            growth_ratio = current_cache_size / cached_channels
            if growth_ratio > 1.5:  # 增长超过50%才重建
                logger.debug(f"INDEX REBUILD: Cache size increased significantly ({current_cache_size} vs {cached_channels})")
                return True
        
        # 🚀 更稳定的哈希检查：基于模型总数而非缓存键结构
        try:
            total_models_in_cache = sum(len(cache_data.get('models', [])) for cache_data in model_cache.values() if isinstance(cache_data, dict))
            if abs(total_models_in_cache - self._stats.total_models) > self._stats.total_models * 0.1:  # 模型数量变化超过10%
                logger.debug(f"INDEX REBUILD: Model count changed significantly ({total_models_in_cache} vs {self._stats.total_models})")
                return True
        except Exception as e:
            logger.debug(f"INDEX REBUILD: Error checking model count: {e}")
            pass
        
        logger.debug(f"INDEX REBUILD: No rebuild needed (cache: {current_cache_size}, indexed: {cached_channels})")
        return False  # 默认不重建
    
    def _extract_channel_id(self, cache_key: str) -> Optional[str]:
        """从缓存键提取渠道ID"""
        if not cache_key:
            return None
            
        # 处理API Key级别的缓存键格式: "channel_id_apikeyash"
        if '_' in cache_key:
            parts = cache_key.split('_')
            if len(parts) >= 2:
                # 检查最后一部分是否为hash格式（8位十六进制）
                potential_hash = parts[-1]
                if len(potential_hash) == 8 and all(c in '0123456789abcdef' for c in potential_hash.lower()):
                    return '_'.join(parts[:-1])
        
        # 直接返回作为渠道ID
        return cache_key
    
    def _generate_model_tags(self, model_name: str, provider: str) -> Set[str]:
        """为模型生成标签集合"""
        tags = set()
        
        if not model_name:
            return tags
        
        model_lower = model_name.lower()
        
        # 添加提供商标签
        if provider:
            tags.add(provider.lower())
        
        # 使用多种分隔符分割模型名称生成标签
        separators = [':', '/', '@', '-', '_', ',', '.', ' ']
        tokens = [model_lower]
        
        for sep in separators:
            new_tokens = []
            for token in tokens:
                new_tokens.extend(token.split(sep))
            tokens = [t.strip() for t in new_tokens if t.strip()]
        
        # 添加所有有效的token作为标签
        for token in tokens:
            if len(token) >= 2:  # 过滤太短的标签
                tags.add(token)
        
        # 特殊标签识别
        if any(free_indicator in model_lower for free_indicator in ['free', 'gratis', '免费']):
            tags.add('free')
        
        if any(vision_indicator in model_lower for vision_indicator in ['vision', 'visual', 'image', 'multimodal']):
            tags.add('vision')
            
        if any(code_indicator in model_lower for code_indicator in ['code', 'coder', 'coding', 'program']):
            tags.add('code')
        
        return tags
    
    def _extract_capabilities(self, cache_data: Dict, model_name: str) -> Optional[Dict]:
        """提取模型能力信息"""
        capabilities_data = cache_data.get("models_capabilities", {})
        return capabilities_data.get(model_name) if capabilities_data else None
    
    def _estimate_memory_usage(self) -> float:
        """估算内存使用量（MB）"""
        import sys
        
        total_size = 0
        total_size += sys.getsizeof(self._tag_to_models)
        total_size += sys.getsizeof(self._channel_to_models)
        total_size += sys.getsizeof(self._model_info)
        
        # 估算内部数据结构的大小
        for tag_set in self._tag_to_models.values():
            total_size += sys.getsizeof(tag_set)
        
        for model_set in self._channel_to_models.values():
            total_size += sys.getsizeof(model_set)
            
        return total_size / 1024 / 1024


# 全局索引实例
_memory_index: Optional[MemoryModelIndex] = None

def get_memory_index() -> MemoryModelIndex:
    """获取全局内存索引实例"""
    global _memory_index
    if _memory_index is None:
        _memory_index = MemoryModelIndex()
    return _memory_index

def rebuild_index_if_needed(model_cache: Dict[str, Dict], force_rebuild: bool = False) -> IndexStats:
    """按需重建索引"""
    index = get_memory_index()
    
    # 检查是否需要重建（这里可以基于缓存更新时间等条件）
    if force_rebuild:
        return index.build_index_from_cache(model_cache)
    
    return index.get_stats()