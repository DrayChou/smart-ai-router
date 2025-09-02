# 架构迁移计划

## 🎯 **目标**

从当前过度复杂的多层架构迁移到基于 KISS 原则的统一模型管理架构。

## 📊 **当前问题分析**

### 旧架构问题

- **5 层调用链路**: JSONRouter → capability_mapper → legacy_adapter → unified_registry
- **1800+行冗余代码**: 职责重叠的 5 个模块
- **性能浪费**: 多层调用、重复数据转换
- **维护困难**: 相同逻辑分散在多处

### 新架构优势

- **2-3 层清晰链路**: JSONRouter → ModelService → Data Sources
- **650 行精简代码**: 职责单一的 3 个模块
- **性能优化**: 直接调用、缓存机制
- **维护简单**: 统一数据源、统一接口

## 📋 **迁移策略**

### Phase 1: 并行部署 (风险最小)

1. **保留旧架构** - 现有代码完全不动
2. **部署新架构** - 新模块独立部署
3. **渐进测试** - 在测试环境验证新架构

**实施步骤**:

```bash
# 1. 新模块已创建完成
core/services/model_service.py      ✓ 完成
core/models/model_info.py           ✓ 完成
core/utils/openrouter_loader.py     ✓ 完成
core/utils/local_detector.py        ✓ 完成

# 2. 测试新架构
python scripts/test_new_architecture.py  ✓ 通过

# 3. 在现有模块中添加切换开关
# 通过环境变量控制使用新旧架构
USE_NEW_ARCHITECTURE=true python main.py
```

### Phase 2: 逐步替换 (渐进式)

1. **JSONRouter 集成** - 优先使用新服务，旧服务作为回退
2. **缓存管理器升级** - 使用新的 ModelService
3. **其他模块更新** - 逐个替换调用点

**实施代码**:

```python
# core/json_router.py 修改示例
class JSONRouter:
    def __init__(self):
        # 新架构优先
        if os.getenv('USE_NEW_ARCHITECTURE', 'false').lower() == 'true':
            from core.services import get_model_service
            self.model_service = get_model_service()
            self.use_new_arch = True
        else:
            # 旧架构回退
            self.unified_registry = get_unified_model_registry()
            self.model_analyzer = get_model_analyzer()
            self.capability_mapper = get_capability_mapper()
            self.use_new_arch = False

    def get_model_capabilities(self, model: str, provider: str):
        if self.use_new_arch:
            return self.model_service.get_capabilities(model, provider).to_legacy_dict()
        else:
            return self.capability_mapper.predict_capabilities(model, provider)
```

### Phase 3: 完全切换 (激进式)

**当新架构稳定运行 1-2 周后**:

1. **删除冗余模块**:

```bash
rm core/utils/legacy_adapters.py           # 360行无价值代码
rm core/utils/capability_mapper.py         # 并入ModelService
rm core/utils/model_analyzer.py            # 并入ModelService
# 精简 core/utils/local_model_capabilities.py  # 只保留检测逻辑
```

2. **更新所有导入**:

```python
# 替换所有地方的导入
# 旧: from core.utils.capability_mapper import get_capability_mapper
# 新: from core.services import get_model_service
```

3. **统一接口调用**:

```python
# 旧: capabilities = capability_mapper.predict_capabilities(model, provider)
# 新: capabilities = model_service.get_capabilities(model, provider).to_legacy_dict()
```

## ⚠️ **风险评估**

### 高风险操作

- **删除现有模块**: 可能影响未知的依赖关系
- **批量接口替换**: 可能引入兼容性问题

### 降低风险的措施

1. **充分测试**: 新架构在生产环境运行 1-2 周
2. **分步实施**: 一个模块一个模块地替换
3. **回退机制**: 保留旧代码直到确认新架构稳定
4. **监控告警**: 密切监控错误率和性能指标

## 📈 **迁移时间线**

### Week 1: 验证阶段

- [x] 新架构设计完成
- [x] 核心模块实现完成
- [x] 单元测试通过
- [ ] 集成测试验证
- [ ] 性能基准测试

### Week 2: 集成阶段

- [ ] JSONRouter 集成新架构
- [ ] 缓存管理器升级
- [ ] 环境变量切换机制
- [ ] A/B 测试对比

### Week 3-4: 生产验证

- [ ] 生产环境并行运行
- [ ] 监控性能和稳定性
- [ ] 修复发现的问题
- [ ] 用户体验验证

### Week 5: 完全切换 (可选)

- [ ] 删除冗余旧模块
- [ ] 统一接口调用
- [ ] 代码清理和文档更新
- [ ] 最终性能验证

## 🎯 **预期效果**

### 代码质量提升

- **代码减少 64%**: 1800 行 → 650 行
- **调用层数减少 60%**: 5 层 → 2 层
- **模块数量减少 40%**: 5 个 → 3 个

### 性能提升

- **查询延迟减少**: 消除多层调用开销
- **内存占用减少**: 消除重复对象创建
- **缓存效率提升**: 统一缓存策略

### 维护成本降低

- **统一数据源**: 只需维护 OpenRouter + 覆盖配置
- **统一接口**: 所有模型操作通过一个服务
- **清晰职责**: 每个模块职责单一明确

## ✅ **验证标准**

### 功能验证

- [ ] 所有现有 API 保持兼容
- [ ] 模型查询结果一致
- [ ] 能力检测结果准确
- [ ] 标签查询功能正常

### 性能验证

- [ ] 响应时间不增加
- [ ] 内存占用不增加
- [ ] 并发处理能力维持
- [ ] 缓存命中率正常

### 稳定性验证

- [ ] 7x24 小时无故障运行
- [ ] 错误率不增加
- [ ] 回退机制工作正常
- [ ] 监控告警正常

---

## 🚀 **立即可执行的行动**

1. **测试新架构**: `python scripts/test_new_architecture.py`
2. **启用新架构**: `USE_NEW_ARCHITECTURE=true python main.py`
3. **监控运行状态**: 观察日志和性能指标
4. **收集反馈**: 记录任何异常或问题

**新架构已准备就绪，可以开始渐进式迁移！**
