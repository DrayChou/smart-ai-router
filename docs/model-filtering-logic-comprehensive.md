# Smart AI Router 大模型筛选逻辑详解

## 概述

Smart AI Router 采用三阶段筛选策略，确保为客户选择最优大模型：
1. **候选发现阶段**: 发现所有可能的模型选择
2. **需求筛选阶段**: 过滤不符合客户需求的模型
3. **智能排序阶段**: 按优先级排序，选择最优模型

## 阶段1: 候选模型发现

### A. 标签路由 (tag: 前缀)

**支持的标签格式**:
```bash
tag:free                    # 单标签查询
tag:qwen3,free             # 多标签 AND 逻辑
tag:qwen3,free,!local      # 包含正标签，排除负标签
tag:!embedding             # 纯排除查询
tag:gpt,!paid              # 包含gpt，排除付费
```

**标签匹配逻辑**:
1. **渠道级标签**: 检查 `channel.tags` 配置
2. **模型级标签**: 从模型名称自动提取标签
3. **合并匹配**: 渠道标签 + 模型标签的合并匹配
4. **严格验证**: 对 `free` 标签进行严格的定价验证

### B. 综合搜索 (普通模型名)

这是我们的**关键创新**，解决"精确匹配导致成本浪费"问题。

**双重搜索策略**:
```python
# 用户请求: "qwen3-8b"

1. 物理模型匹配:
   - 查找精确名称为 "qwen3-8b" 的模型
   - 结果: AliBailian/qwen3-8b (付费)
   
2. 自动标签化匹配:
   - 提取标签: ["qwen3", "8b"] 
   - 查找包含这些标签的所有模型
   - 结果: deepseek/deepseek-r1-0528-qwen3-8b:free (免费)
   
3. 智能合并去重:
   - 合并两类结果: 31个候选
   - 去除 channel+model 重复组合
   - 确保覆盖全面，避免遗漏
```

**标签自动提取规则**:
- **分隔符**: `:`, `/`, `@`, `-`, `_`, `,`
- **示例**:
  ```python
  "qwen3-8b" → ["qwen3", "8b"]
  "deepseek/deepseek-r1-0528-qwen3-8b:free" → ["deepseek", "r1", "0528", "qwen3", "8b", "free"]
  "openai/gpt-4o-mini" → ["openai", "gpt", "4o", "mini"]
  ```
- **过滤规则**: 移除空字符串、单字符、纯数字

## 阶段2: 客户需求筛选

### A. 基础可用性筛选

**必须满足的基础条件**:
```python
✅ channel.enabled == True        # 渠道启用状态
✅ channel.api_key 存在           # API密钥有效
✅ health_score >= 0.3           # 健康状态良好
```

### B. 模型能力筛选

**自动排除不适合的模型**:

#### B1. Embedding模型过滤
```python
# 检测关键词
embedding_keywords = ['embedding', 'embed', 'text-embedding', 'bge-', 'gte-', 'e5-']

# 被过滤的示例
❌ "bge-large-en-v1.5"
❌ "text-embedding-ada-002"  
❌ "e5-large-v2"
```

#### B2. 纯视觉模型过滤
```python
# 检测关键词
vision_only_keywords = ['vision-only', 'image-only', 'ocr-only']

# 被过滤的示例
❌ "claude-3-vision-only"
❌ "gpt-4-image-only"
```

#### B3. 对话任务适配检查
```python
def _is_suitable_for_chat(model_name):
    """确保模型适合chat对话任务"""
    if embedding模型 or 纯视觉模型:
        return False
    return True
```

### C. 规格要求筛选

**支持的配置化筛选**:
```yaml
model_filters:
  min_context_length: 2048      # 最小上下文长度
  min_parameter_count: 1000     # 最小参数数量(M)
  exclude_embedding_models: true
  exclude_vision_only_models: true
```

**筛选逻辑**:
```python
✅ 上下文长度检查: context_length >= min_context_length
✅ 参数数量检查: parameter_count >= min_parameter_count
✅ 自定义规格要求: 支持扩展配置
```

### D. 免费模型严格验证

**多层免费验证机制**:
```python
# 第1层: 模型名称检查
if ":free" in model_name.lower():
    potential_free = True

# 第2层: 定价信息验证  
if pricing.input_cost == 0 and pricing.output_cost == 0:
    confirmed_free = True

# 第3层: 渠道级别标记
if "free" in channel.tags:
    channel_free = True

# 综合评分: free_score >= 0.9 才认为真正免费
if free_score >= 0.9:
    logger.info("✅ FREE MODEL VALIDATED")
else:
    logger.warning("❌ FREE TAG REJECTED - not truly free")
```

## 阶段3: 智能评分排序

### A. 7位数字评分系统

**评分结构**:
```
成本|本地|上下文|参数量|速度|质量|可靠性
 9    9    7       7      6    9     9  = 9977699
```

**各维度评分规则**:

| 位置 | 维度 | 评分规则 | 权重 |
|------|------|----------|------|
| 1 | 成本 | **免费=9，付费≤8** (绝对优先) | 最高 |
| 2 | 本地 | localhost/LMStudio=9，远程=0-8 | 高 |
| 3 | 上下文 | 基于context_length规格 | 中 |
| 4 | 参数量 | 智能提取270m-670b参数 | 中 |
| 5 | 速度 | 基于历史延迟数据 | 中低 |
| 6 | 质量 | 基于模型表现和规格 | 中低 |
| 7 | 可靠性 | 基于健康监控 | 最低 |

### B. 分层优先级保证

**核心优势**:
- **免费绝对优先**: 第1位=9确保免费模型永远排在付费模型前面
- **精确区分**: 每个维度0-9分，避免浮点精度问题
- **可观测性**: 每个7位数字都有明确含义

**排序示例**:
```
免费+本地: 9977699 (9,977,699) - 最高优先级
免费+远程: 9077699 (9,077,699) - 次优先级  
付费+本地: 8977699 (8,977,699) - 第三优先级
付费+远程: 8077699 (8,077,699) - 最低优先级
```

## 完整筛选流程实例

### 示例: 用户请求 "qwen3-8b"

#### 阶段1: 候选发现
```
🔍 物理匹配: 找到3个精确匹配
   - AliBailian/qwen3-8b (付费)
   - katonai.dev/qwen3-8b (付费)  
   - tu-zi.com/qwen3-8b (付费)

🏷️ 标签匹配: 从 ["qwen3", "8b"] 找到28个模型
   - openrouter/deepseek-r1-0528-qwen3-8b:free (免费)
   - lmstudio/qwen3-8b-local (本地免费)
   - siliconflow/Qwen3-8B:free (免费)
   - ...更多免费和付费选项

🔄 智能合并: 31个候选 (去重后)
```

#### 阶段2: 客户需求筛选
```
✅ 基础筛选: 31个 → 31个 (全部通过)
✅ 能力筛选: 31个 → 28个 (过滤3个embedding模型)  
✅ 规格筛选: 28个 → 25个 (过滤3个上下文不足)
✅ 健康筛选: 25个 → 23个 (过滤2个不健康渠道)
```

#### 阶段3: 智能排序
```
🏆 #1: lmstudio_local [FREE/LOCAL] Score: 9977769
🏆 #2: openrouter.free [FREE/REMOTE] Score: 9087779  
🏆 #3: siliconflow.free [FREE/REMOTE] Score: 9087779
🏆 #4: AliBailian [PAID/REMOTE] Score: 4077769

最终选择: lmstudio_local (免费+本地，最优选择)
```

## 筛选逻辑优势

### 1. 客户需求完美匹配
- ✅ **能力保证**: 自动过滤不合适的模型类型
- ✅ **规格满足**: 支持上下文、参数数量等要求
- ✅ **可用性验证**: 确保渠道健康和API有效

### 2. 成本优化最大化  
- ✅ **免费优先**: 严格验证的免费模型绝对优先
- ✅ **智能发现**: 用户不知道的免费替代品自动发现
- ✅ **成本透明**: 实际花费明确显示

### 3. 用户体验最佳
- ✅ **无缝使用**: 无需修改请求格式
- ✅ **智能扩展**: 自动标签化大幅提高匹配率
- ✅ **故障转移**: 多候选支持平滑切换

### 4. 技术架构先进
- ✅ **双重搜索**: 物理+标签，覆盖全面
- ✅ **精确评分**: 7位数字避免浮点问题
- ✅ **配置驱动**: 支持动态调整筛选规则

## 待优化建议

### 1. 能力筛选增强
```python
# 当前: TODO注释
# 建议: 实现基于请求的能力需求筛选
if request.required_capabilities:
    if not all(cap in channel.capabilities for cap in request.required_capabilities):
        continue
```

### 2. 用户偏好支持
```python
# 建议: 支持请求级别的筛选偏好
{
  "model": "qwen3-8b",
  "preferences": {
    "prefer_local": true,
    "max_latency_ms": 5000,
    "min_context_length": 8192
  }
}
```

### 3. 动态筛选规则
```yaml
# 建议: 更丰富的配置化筛选
model_filters:
  exclude_model_types: ["embedding", "vision-only", "audio-only"]
  performance_requirements:
    max_latency_ms: 10000
    min_success_rate: 0.95
  business_rules:
    prefer_providers: ["openai", "anthropic"]  
    avoid_providers: ["unstable_provider"]
```

这套筛选逻辑确保了Smart AI Router能够完美满足客户需求，同时实现成本优化的最大化。