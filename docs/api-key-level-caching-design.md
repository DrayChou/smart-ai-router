# API Key级别缓存架构设计方案

## 🚨 问题分析

### 当前架构问题
```python
# 问题：按渠道缓存，忽略了API Key级别的差异
model_cache[channel_id] = {
    "models": ["gpt-3.5-turbo", "gpt-4"],
    "models_pricing": {...},
    "status": "success"
}
```

### 实际场景
- **SiliconFlow**: 免费用户 vs Pro用户有不同可用模型和定价
- **OpenRouter**: 不同等级账户有不同价格和模型访问权限
- **Gemini**: 免费API vs 付费API有不同配额和定价

## 🎯 解决方案设计

### 新架构
```python
# 解决方案：API Key级别独立缓存
model_cache[f"{channel_id}_{api_key_hash}"] = {
    "models": ["模型列表"],
    "models_pricing": {"模型定价信息"},
    "api_key_hash": "sha256前8位",
    "channel_id": "原始渠道ID", 
    "user_level": "free/pro/premium",
    "status": "success",
    "discovered_at": "2025-01-18T12:00:00Z"
}
```

### 缓存键生成策略
```python
import hashlib

def generate_cache_key(channel_id: str, api_key: str) -> str:
    """生成API Key级别的缓存键"""
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:8]
    return f"{channel_id}_{api_key_hash}"

# 示例:
# channel_id="siliconflow_1", api_key="sk-abc123..."
# cache_key="siliconflow_1_a1b2c3d4"
```

## 🔧 实现计划

### Phase 8.1: 缓存键架构重构
- [x] 设计API Key哈希机制
- [x] 修改ModelDiscoveryTask支持Key级别缓存
- [x] 更新YAMLConfigLoader的缓存接口
- [x] 保持向后兼容性

### Phase 8.2: 模型发现任务重构
- [x] 修改`_fetch_models_from_channel`方法
- [x] 实现按API Key独立发现
- [x] 添加用户级别检测逻辑
- [x] 实现缓存清理机制

### Phase 8.3: 路由逻辑更新
- [x] 更新YAMLConfigLoader缓存接口支持Key级别缓存
- [x] 修改候选渠道查找逻辑（通过新的缓存接口）
- [x] 确保定价信息准确匹配
- [x] 实现缓存回退机制

### Phase 8.4: 管理和维护
- [x] 实现缓存清理和Key管理
- [x] 添加缓存统计和监控
- [x] 实现自动缓存迁移支持
- [x] 创建缓存健康检查

**🎉 实施状态**: 核心架构已完成实现，通过全面测试验证

## 💻 核心代码实现

### 1. 缓存键工具类
```python
# core/utils/api_key_cache.py
class ApiKeyCacheManager:
    """API Key级别缓存管理器"""
    
    def __init__(self):
        self.hash_length = 8  # API Key哈希长度
    
    def generate_cache_key(self, channel_id: str, api_key: str) -> str:
        """生成缓存键"""
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:self.hash_length]
        return f"{channel_id}_{api_key_hash}"
    
    def parse_cache_key(self, cache_key: str) -> tuple[str, str]:
        """解析缓存键"""
        parts = cache_key.rsplit('_', 1)
        if len(parts) == 2:
            return parts[0], parts[1]  # channel_id, api_key_hash
        return cache_key, ""
    
    def find_cache_entries_by_channel(self, cache: dict, channel_id: str) -> list[str]:
        """查找特定渠道的所有缓存条目"""
        return [key for key in cache.keys() if key.startswith(f"{channel_id}_")]
```

### 2. 模型发现任务重构
```python
# 修改 core/scheduler/tasks/model_discovery.py
class ModelDiscoveryTask:
    def __init__(self):
        self.cache_manager = ApiKeyCacheManager()
    
    async def _fetch_models_from_channel(self, channel: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从单个渠道获取模型列表 - 支持API Key级别缓存"""
        channel_id = channel.get('id')
        api_key = channel.get('api_key')
        
        # 生成API Key级别的缓存键
        cache_key = self.cache_manager.generate_cache_key(channel_id, api_key)
        
        # 检查缓存
        if self._should_use_cache(cache_key):
            return self._get_cached_result(cache_key)
        
        # 执行API调用获取模型
        result = await self._discover_models_via_api(channel)
        
        if result:
            # 添加API Key相关信息
            result.update({
                'cache_key': cache_key,
                'channel_id': channel_id,
                'api_key_hash': cache_key.split('_')[-1],
                'user_level': self._detect_user_level(result, channel)
            })
            
            # 保存到缓存
            self._save_to_cache(cache_key, result)
        
        return result
    
    def _detect_user_level(self, api_result: dict, channel: dict) -> str:
        """检测用户等级"""
        models = api_result.get('models', [])
        
        # SiliconFlow用户等级检测
        if channel.get('provider') == 'siliconflow':
            pro_models = [m for m in models if 'Pro/' in m]
            if pro_models:
                return 'pro'
            return 'free'
        
        # OpenRouter用户等级检测
        if channel.get('provider') == 'openrouter':
            # 基于可用模型数量判断
            if len(models) > 100:
                return 'premium'
            elif len(models) > 50:
                return 'pro'
            return 'free'
        
        return 'unknown'
```

### 3. 配置加载器适配
```python
# 修改 core/yaml_config.py
class YAMLConfigLoader:
    def __init__(self):
        self.cache_manager = ApiKeyCacheManager()
        # 保持原有的model_cache接口不变
        self.model_cache: Dict[str, Dict] = {}
    
    def get_model_cache_by_channel_and_key(self, channel_id: str, api_key: str) -> Optional[Dict]:
        """获取特定API Key的模型缓存"""
        cache_key = self.cache_manager.generate_cache_key(channel_id, api_key)
        return self.model_cache.get(cache_key)
    
    def get_model_cache_by_channel(self, channel_id: str) -> Dict[str, Dict]:
        """获取渠道下所有API Key的缓存（兼容性方法）"""
        channel_caches = {}
        for cache_key in self.cache_manager.find_cache_entries_by_channel(self.model_cache, channel_id):
            channel_caches[cache_key] = self.model_cache[cache_key]
        
        # 如果只有一个API Key，返回其缓存（向后兼容）
        if len(channel_caches) == 1:
            return list(channel_caches.values())[0]
        
        return channel_caches
```

### 4. 路由器适配
```python
# 修改 core/json_router.py
class JSONRouter:
    def _get_candidate_channels(self, request: RoutingRequest) -> List[ChannelCandidate]:
        """获取候选渠道 - 支持API Key级别缓存"""
        model_cache = self.config_loader.get_model_cache()
        candidates = []
        
        for channel in all_enabled_channels:
            # 获取该渠道对应API Key的缓存
            channel_cache = self.config_loader.get_model_cache_by_channel_and_key(
                channel.id, channel.api_key
            )
            
            if channel_cache and request.model in channel_cache.get("models", []):
                candidates.append(ChannelCandidate(
                    channel=channel,
                    matched_model=request.model
                ))
        
        return candidates
```

## 🔄 兼容性策略

### 向后兼容
- 单API Key渠道：行为保持不变
- 多API Key渠道：自动使用新架构
- 缓存文件：自动迁移到新格式

### 迁移策略
```python
def migrate_legacy_cache(self, old_cache: Dict[str, Dict]) -> Dict[str, Dict]:
    """迁移旧缓存格式到新格式"""
    new_cache = {}
    
    for channel_id, cache_data in old_cache.items():
        # 查找对应的渠道配置
        channel = self.channels_map.get(channel_id)
        if channel and channel.api_key:
            # 生成新的缓存键
            new_key = self.cache_manager.generate_cache_key(channel_id, channel.api_key)
            new_cache[new_key] = {
                **cache_data,
                'cache_key': new_key,
                'channel_id': channel_id,
                'migrated_from_legacy': True
            }
        else:
            # 保持原有键名（兼容性）
            new_cache[channel_id] = cache_data
    
    return new_cache
```

## 📊 影响评估

### 性能影响
- **存储空间**: 增加20-30%（多API Key渠道）
- **查询速度**: 基本无影响（哈希查找）
- **缓存命中率**: 提高准确性，避免错误匹配

### 复杂度影响
- **代码复杂度**: 中等增加，但架构更清晰
- **维护难度**: 降低（问题定位更精确）
- **测试复杂度**: 增加，需要多Key测试场景

## 🎯 预期收益

### 解决的问题
- ✅ **定价准确性**: 不同用户等级的定价完全隔离
- ✅ **模型可用性**: 免费/付费用户访问正确的模型列表
- ✅ **成本控制**: 成本计算基于真实的用户定价
- ✅ **系统稳定性**: 避免权限错误和访问拒绝

### 技术优势
- 🏗️ **架构清晰**: 每个API Key独立管理
- 🔍 **问题定位**: 快速识别特定Key的问题
- 🔄 **扩展性**: 支持更多复杂的用户等级策略
- 🛡️ **数据隔离**: 不同用户的数据完全分离

这个设计解决了当前架构的根本问题，为Smart AI Router提供了企业级的多用户支持能力。