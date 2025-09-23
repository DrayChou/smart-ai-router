# 安全文件删除计划

## ❌ **绝对不能删除的文件** (风险极高)

### 核心系统文件

- `core/json_router.py` - 被 15+文件依赖，系统核心
- `core/utils/memory_index.py` - 性能关键组件
- `main.py` - 系统入口
- `api/*.py` - API 接口层

### 缓存和性能文件

- `core/utils/channel_cache_manager.py` - 被模型发现依赖
- `core/utils/api_key_cache_manager.py` - 被定价系统依赖
- `core/scheduler/tasks/model_discovery.py` - 模型发现核心

**删除后果**: 导致系统完全无法启动或核心功能失效

## ⚠️ **需要谨慎处理的文件** (中等风险)

### 1. `core/utils/legacy_adapters.py` - 可删除但需预处理

**当前依赖**:

- `core/json_router.py` (导入 legacy 适配器)
- `core/utils/capability_mapper.py` (调用适配器)
- `core/utils/local_model_capabilities.py` (调用适配器)

**删除步骤**:

```bash
# 1. 首先更新依赖文件，移除legacy_adapters导入
# 2. 然后删除文件
rm core/utils/legacy_adapters.py
```

### 2. 精简现有模块 (保留文件，删除内容)

#### `core/utils/capability_mapper.py` - 保留外壳

```python
# 将内容替换为直接调用新服务
from core.services import get_model_service

def get_capability_mapper():
    return CapabilityMapperWrapper()

class CapabilityMapperWrapper:
    def __init__(self):
        self.model_service = get_model_service()

    def predict_capabilities(self, model_name: str, provider: str):
        return self.model_service.get_capabilities(model_name, provider).to_legacy_dict()

    # 其他方法类似处理...
```

#### `core/utils/model_analyzer.py` - 保留外壳

```python
# 将内容替换为直接调用新服务
from core.services import get_model_service

def get_model_analyzer():
    return ModelAnalyzerWrapper()

class ModelAnalyzerWrapper:
    def __init__(self):
        self.model_service = get_model_service()

    def analyze_model(self, model_name: str, model_data=None):
        specs = self.model_service.get_specs(model_name)
        # 转换为旧格式...
        return ModelSpecs(...)
```

## ✅ **推荐的渐进删除策略**

### Phase 1: 准备阶段 (安全)

1. **不删除任何文件**
2. **创建包装器类**替换实现
3. **保持所有现有导入和接口不变**

### Phase 2: 内容替换 (中等风险)

1. **替换模块内部实现**为新服务调用
2. **保留所有公共接口**不变
3. **一个模块一个模块地替换**

### Phase 3: 适配器清理 (低风险)

1. **删除 legacy_adapters.py**
2. **更新相关导入**
3. **验证功能正常**

### Phase 4: 最终清理 (可选)

1. **合并相似模块**
2. **删除空实现文件** (在确认无依赖后)

## 📊 **删除效果预估**

### 立即可删除 (Phase 3 完成后)

- `core/utils/legacy_adapters.py` - 360 行

### 内容精简 (Phase 2 完成后)

- `core/utils/capability_mapper.py`: 300 行 → 50 行
- `core/utils/model_analyzer.py`: 300 行 → 50 行
- `core/utils/local_model_capabilities.py`: 400 行 → 150 行

### 总削减效果

- **直接删除**: 360 行
- **内容精简**: 800 行 → 250 行 (削减 550 行)
- **总计减少**: 910 行 (**约 50%的冗余代码**)

## ⚡ **立即可执行的安全操作**

### 第一步: 包装器替换 (完全安全)

```python
# 修改 core/utils/capability_mapper.py
# 不删除文件，只替换实现为调用新服务

# 旧实现: 300行复杂逻辑
# 新实现: 20行包装器调用
```

### 第二步: 验证兼容性

```bash
# 运行所有测试确保功能不变
python scripts/test_new_architecture.py
python -m pytest tests/ # 如果有测试套件
```

### 第三步: 删除适配器 (确认安全后)

```bash
rm core/utils/legacy_adapters.py
```

## 🚨 **关键风险警告**

### 不要做的事情

❌ **不要批量删除多个文件**
❌ **不要一次性删除超过 1 个模块**  
❌ **不要在没有备份的情况下删除**
❌ **不要忽略编译检查和测试**

### 必须做的事情

✅ **每次只处理 1 个文件**
✅ **每步都要测试验证**
✅ **保持 git 提交记录**
✅ **有问题立即回退**

---

## 🎯 **结论**

**不是所有多余文件都需要删除**。正确的策略是：

1. **保留文件结构** - 避免破坏依赖关系
2. **替换内部实现** - 用新服务替换旧逻辑
3. **渐进式清理** - 一步步安全推进
4. **重点删除** - 只删除真正无用的适配器

**预期效果**: 在不破坏系统的前提下，削减 50%冗余代码，实现架构目标。
