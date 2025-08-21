# 本次会话需求与功能核对清单

## 主要需求总结

### 1. API.tu-zi.com 货币汇率系统 (✅ 已实现)
**需求**: 实现特殊汇率 "充值0.7人民币获得1美元"
**实现位置**: 
- `core/config_models.py` - 添加 `currency_exchange` 字段
- `core/utils/token_counter.py` - 增强 `calculate_cost` 方法支持货币转换
- `config/router_config.yaml` line 1071 - 配置 tu-zi.com 渠道

**技术细节**:
```yaml
currency_exchange:
  from: USD
  to: CNY
  rate: 0.7
  description: 充值0.7人民币获得1美元
```

**节省成本**: 90.3% (0.7 CNY vs 正常 7.2 CNY 汇率)

### 2. SiliconFlow 定价解析优化 (✅ 已实现)
**需求**: 修复HTML解析，从6个模型提升到实际数十个模型
**实现位置**: `core/scheduler/tasks/siliconflow_pricing.py`

**技术改进**:
- 从正则表达式改为BeautifulSoup HTML表格解析
- 添加详细调试日志和HTML内容保存到 `cache/siliconflow_debug/`
- 解析准确度：从300+垃圾条目降到61个精确模型

### 3. 渠道ID标准化 (✅ 已实现)  
**需求**: 将oneapi_前缀ID改为基于name的ID
**影响**: 36个渠道ID被批量替换 (如: oneapi_27 → tu-zi.com)

### 4. /models API 增强 (⚠️ 部分丢失)
**原始需求**: 添加搜索、过滤、排序和分页功能，包含渠道商ID+名称信息

**应有功能**:
- ✅ 渠道信息显示 (id, name, provider等)
- ⚠️ 搜索功能 (search参数)
- ⚠️ 提供商过滤 (provider参数) 
- ⚠️ 能力过滤 (capabilities参数)
- ⚠️ 标签过滤 (tags参数)
- ⚠️ 排序功能 (sort_by, sort_order参数)
- ⚠️ 分页功能 (limit, offset参数)

**当前状态**: 基础渠道信息显示正常，但搜索/排序/分页功能在main.py替换过程中可能丢失

### 5. main.py 精简化 (✅ 已实现)
**需求**: 从复杂版本精简为8个核心端点的MINIMAL模式
**实现**: 成功替换，保留核心功能，移除过多端点

## 当前问题排查

### 🚨 高优先级问题

#### 1. 标签路由返回404
**错误日志**: `WARNING:core.json_router:🔍 TAG MATCHING: Model cache is empty, cannot perform tag routing`
**表现**: `tag:free,qwen3` 查询返回404
**分析**: 模型缓存在启动时显示9967个模型，但路由时却为空

#### 2. /models 搜索排序功能缺失
**表现**: URL参数 `?search=qwen&limit=2` 不生效
**原因**: main.py替换过程中功能代码可能未正确迁移

### 📋 待验证功能

1. **货币汇率计算**: tu-zi.com渠道成本计算是否正确
2. **SiliconFlow定价**: 是否正确解析到61个模型
3. **渠道ID一致性**: 配置文件中是否都使用name-based ID
4. **API兼容性**: 是否保持100%向后兼容

## 恢复计划

1. **优先**: 修复标签路由的模型缓存问题
2. **次要**: 完整恢复/models端点的搜索排序功能  
3. **验证**: 逐项核对上述所有功能是否正常工作
4. **测试**: 使用实际API调用验证功能

## 备份信息

- `.lh/main.py.json` - 包含历史版本的备份数据
- 多个文档文件被删除，但核心功能代码应该保留
- `cache/discovered_models.json` - 模型缓存文件存在且有内容

## 下一步行动

1. 修复 `get_model_cache()` 返回空值的问题
2. 恢复完整的/models端点搜索排序功能
3. 测试所有标签路由功能 (`tag:free`, `tag:gpt`, etc.)
4. 验证tu-zi.com货币转换是否正常工作