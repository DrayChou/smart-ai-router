# 渠道级别定价问题分析

## 问题描述

用户提出的重要架构问题：不同API Key对应不同用户级别，可能有不同的价格和模型访问权限。

## 当前架构的风险

### 现状
```python
# 当前缓存结构
model_cache = {
    "siliconflow_01": {
        "models": ["Qwen/Qwen2.5-7B", "GLM-4-9b-chat"],
        "models_data": {
            "Qwen/Qwen2.5-7B": {
                "raw_data": {
                    "pricing": {"prompt": "0", "completion": "0"}  # 免费用户价格
                }
            }
        }
    }
}
```

### 问题场景
1. **SiliconFlow渠道用免费API Key发现模型** → 缓存免费定价
2. **同一渠道的付费API Key来请求** → 错误地使用了免费定价
3. **结果**：付费用户按免费价格计费，或免费用户尝试访问付费模型失败

## 影响的提供商

- **SiliconFlow**: 免费用户 vs Pro用户有不同定价和模型
- **OpenRouter**: 不同积分等级有不同价格和模型权限  
- **Gemini**: 免费层 vs 付费层有不同配额和定价
- **Anthropic**: 不同用户等级有不同价格和速率限制

## 解决方案

### 方案1: API Key级别缓存（推荐）
```python
# 新的缓存结构
model_cache = {
    # 每个API Key独立缓存
    "siliconflow_01_hash1234": {  # channel_id + "_" + api_key_hash
        "api_key_hash": "hash1234",
        "user_tier": "free",
        "models": ["Qwen/Qwen2.5-7B"],  # 免费用户可访问的模型
        "models_data": {
            "Qwen/Qwen2.5-7B": {"pricing": {"prompt": "0", "completion": "0"}}
        }
    },
    "siliconflow_01_hash5678": {  # 同一渠道，不同API Key
        "api_key_hash": "hash5678", 
        "user_tier": "pro",
        "models": ["Qwen/Qwen2.5-7B", "Pro/GLM-4-plus"],  # Pro用户更多模型
        "models_data": {
            "Qwen/Qwen2.5-7B": {"pricing": {"prompt": "0.35", "completion": "0.35"}},
            "Pro/GLM-4-plus": {"pricing": {"prompt": "2.8", "completion": "2.8"}}
        }
    }
}
```

### 方案2: 分层缓存（复杂但精确）
```python
# 渠道级别 + API Key级别的两层缓存
channel_cache = {
    "siliconflow_01": {
        "api_keys": {
            "hash1234": {...},  # 免费用户数据
            "hash5678": {...}   # Pro用户数据
        }
    }
}
```

## 实现计划

### 立即修复
1. ✅ **识别问题范围**：确认当前代码确实存在此问题
2. ✅ **评估影响**：SiliconFlow、OpenRouter等多Key渠道都受影响
3. ⏳ **向用户确认**：是否需要立即修复还是可以在后续版本处理

### 修复方案（如果需要）
1. **模型发现任务**：为每个API Key独立发现和缓存模型
2. **路由逻辑**：查找模型时使用当前请求的API Key对应的缓存
3. **成本计算**：使用API Key对应的定价信息计算成本
4. **缓存清理**：定期清理不再使用的API Key缓存

## 兼容性考虑

- **单Key渠道**：保持现有行为，无影响
- **多Key渠道**：每个Key独立缓存，精确定价
- **配置迁移**：现有配置无需修改

## 性能影响

- **存储增加**：每个API Key独立缓存，存储量增加
- **发现时间**：需要为每个API Key发现模型（可异步）
- **查询性能**：几乎无影响（哈希查找）

## 总结

这是一个重要的架构问题，确实需要解决以确保定价准确性。建议：
1. 短期：添加警告日志，提醒用户注意此问题
2. 长期：实现API Key级别的独立缓存机制