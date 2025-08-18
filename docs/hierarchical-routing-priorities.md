# 分层路由优先级规则

Smart AI Router 使用分层优先级排序系统，而不是简单的加权平均评分。这确保了关键因素（如成本）具有绝对优先权。

## 优先级顺序

系统按以下严格的分层顺序对模型渠道进行排序：

### 1. 免费模型优先 (Free Priority)
- **最高优先级**: 免费模型绝对优先于付费模型
- **判断标准**: `free_score >= 0.9` 表示真正免费
- **检测方式**: 
  - 模型名称包含 `:free` 后缀
  - 模型级别定价信息显示 `input_cost = 0` 且 `output_cost = 0`
  - 渠道配置明确标记为免费

### 2. 本地模型优先 (Local Priority) 
- **第二优先级**: 本地模型优于远程API
- **判断标准**: `local_score >= 0.7`  
- **检测方式**:
  - LMStudio、Ollama 等本地推理服务
  - localhost、127.0.0.1 等本地地址
  - 明确配置的本地渠道

### 3. 成本优化 (Cost Optimization)
- **第三优先级**: 成本越低越好
- **评分逻辑**: `cost_score` 越高表示成本越低
- **计算方式**: 基于实际token使用量和定价信息

### 4. 上下文长度优化 (Context Length)
- **第四优先级**: 上下文长度越大越好
- **评分逻辑**: `context_score` 基于模型支持的最大上下文长度
- **业务价值**: 更长的上下文支持更复杂的对话和文档处理

### 5. 参数量优化 (Parameter Count)
- **第五优先级**: 参数量越大通常质量越好
- **评分逻辑**: `parameter_score` 基于模型参数数量
- **范围**: 从270M到670B参数的智能分析和评分

### 6. 速度优化 (Speed)
- **第六优先级**: 推理速度越快越好
- **评分逻辑**: `speed_score` 基于历史响应时间和模型特性
- **动态调整**: 基于实际延迟数据持续优化

### 7. 可靠性 (Reliability)
- **第七优先级**: 服务稳定性和可用性
- **评分逻辑**: `reliability_score` 基于历史成功率和健康状态
- **熔断机制**: 自动排除不可用的渠道

## 7位数字评分系统

系统使用精确的7位数字评分，而不是简单的元组排序，确保每个维度都有细致的区分度。

### 评分结构
```
成本|本地|上下文|参数量|速度|质量|可靠性
 9    9    7       7      6    9     9  = 9977699
```

### 评分规则
- **第1位：成本 (9=完全免费, 8=很便宜, 0=很昂贵)**
  - 免费模型固定得9分（绝对优先）
  - 付费模型根据实际成本得0-8分
- **第2位：本地 (9=本地, 0=远程)**
- **第3位：上下文长度 (9=很长, 0=很短)**
- **第4位：参数量 (9=很大, 0=很小)**
- **第5位：速度 (9=很快, 0=很慢)**
- **第6位：质量 (9=很高, 0=很低)**
- **第7位：可靠性 (9=很可靠, 0=不可靠)**

### 排序算法

```python
def sorting_key(score: RoutingScore):
    # 第1位：成本优化程度 (免费=9, 付费最高=8)
    if free_score >= 0.9:
        cost_tier = 9  # 免费模型固定为9分
    else:
        cost_tier = min(8, int(score.cost_score * 8))  # 付费模型最高8分
    
    # 其他维度评分 (0-9)
    local_tier = min(9, int(local_score * 9))
    context_tier = min(9, int(context_score * 9))
    parameter_tier = min(9, int(parameter_score * 9))
    speed_tier = min(9, int(score.speed_score * 9))
    quality_tier = min(9, int(score.quality_score * 9))
    reliability_tier = min(9, int(score.reliability_score * 9))
    
    # 组成7位数字，数字越大排序越靠前
    hierarchical_score = (
        cost_tier * 1000000 +       # 第1位：成本(免费=9,付费最高=8)
        local_tier * 100000 +       # 第2位：本地
        context_tier * 10000 +      # 第3位：上下文
        parameter_tier * 1000 +     # 第4位：参数量
        speed_tier * 100 +          # 第5位：速度
        quality_tier * 10 +         # 第6位：质量
        reliability_tier            # 第7位：可靠性
    )
    
    return -hierarchical_score  # 负数实现降序排列
```

## 综合搜索策略 (关键创新)

### 智能模型匹配
当用户请求 `"model": "qwen3-8b"` 时，系统采用**双重搜索策略**：

1. **物理模型匹配**: 查找精确名称匹配的模型
2. **自动标签化匹配**: 从模型名提取标签 `["qwen3", "8b"]`，查找所有相关模型
3. **智能合并**: 将两类结果合并去重，确保包含所有可能的选择

### 标签自动提取
```python
"qwen3-8b" → ["qwen3", "8b"]
"deepseek-r1-0528-qwen3-8b:free" → ["deepseek", "r1", "0528", "qwen3", "8b", "free"]
```

## 实际应用场景对比

### 场景1: 请求 "qwen3-8b" (直接模型名)

**之前行为** (仅物理匹配):
```
候选: 3个付费模型
🏆   #1: 'AliBailian' [PAID/REMOTE] Score: 4077769
🏆   #2: 'katonai.dev' [PAID/REMOTE] Score: 4077769  
🏆   #3: 'tu-zi.com' [PAID/REMOTE] Score: 4077769
结果: 选择付费模型，cost > $0
```

**现在行为** (综合搜索):
```
候选: 31个模型 (物理3个 + 标签28个)
🏆   #1: 'lmstudio_local' [FREE/LOCAL] Score: 9977769
🏆   #2: 'openrouter.free' [FREE/REMOTE] Score: 9087779
🏆   #3: 'siliconflow.free' [FREE/REMOTE] Score: 9087779
🏆   #4: 'AliBailian' [PAID/REMOTE] Score: 4077769
结果: 选择免费模型，cost = $0.00
```

### 场景2: 请求 "tag:free" (标签查询)
```
候选: 所有免费模型
🏆   #1: 'lmstudio_local' [FREE/LOCAL] Score: 9977769
🏆   #2: 'openrouter.free' [FREE/REMOTE] Score: 9087779
排序: 本地免费 > 远程免费 > 其他维度
结果: 优先本地免费模型
```

### 场景3: 请求 "tag:qwen3,free" (多标签)
```
候选: 同时包含 qwen3 AND free 标签的模型
🏆   #1: 'lmstudio/qwen3-8b' [FREE/LOCAL] Score: 9977769  
🏆   #2: 'openrouter/qwen3-8b:free' [FREE/REMOTE] Score: 9087779
结果: 免费的qwen3模型，按本地优先排序
```

### 场景4: 故障转移场景
- **本地服务离线**: 自动切换到最优远程免费服务
- **免费额度用完**: 切换到最便宜的付费模型 
- **API限流**: 故障转移到备用渠道
- **保持连续性**: 用户无感知的平滑切换

## 配置和调优

### 阈值调整
- `free_score >= 0.9`: 免费模型识别阈值
- `local_score >= 0.7`: 本地模型识别阈值
- 可根据实际需求调整这些阈值

### 日志监控
系统会输出详细的7位数字评分日志：
```
🏆 HIERARCHICAL SORTING: 7-digit scoring system (Cost|Local|Context|Param|Speed|Quality|Reliability)
🏆   #1: 'lmstudio_local' [FREE/LOCAL] Score: 9977769 (Total: 9,977,769)
🏆   #2: 'lmstudio_local' [FREE/LOCAL] Score: 9956759 (Total: 9,956,759)
🏆   #3: 'siliconflow_free' [FREE/REMOTE] Score: 9077689 (Total: 9,077,689)
```

每个数字位的含义：
- **位数1 (9)**: 免费模型
- **位数2 (9/0)**: 本地(9)/远程(0)
- **位数3-7**: 上下文、参数量、速度、质量、可靠性评分

## 核心优势

### 1. 智能成本优化
- **免费绝对优先**: 7位数字评分确保免费模型永远排在付费模型前面
- **自动发现免费替代**: 即使用户不知道免费版本存在，系统也会自动找到
- **成本透明**: 响应中显示实际花费，便于成本跟踪

### 2. 用户体验最佳
- **无需学习成本**: 用户发送 `"model": "qwen3-8b"` 就能自动获得最优选择
- **智能匹配扩展**: 自动标签化大幅提高匹配成功率
- **平滑故障转移**: 多候选排序支持无感知的服务切换

### 3. 技术架构先进
- **双重搜索策略**: 物理匹配 + 标签匹配，覆盖所有可能的选择
- **7位数字评分**: 精确的分层优先级，避免浮点数精度问题
- **智能去重合并**: 避免重复候选和循环调用

### 4. 运维友好
- **详细可观测性**: 每步都有清晰日志，便于调试和优化
- **配置驱动**: 动态调整阈值和策略，无需重启服务
- **多层回退机制**: 物理→标签→配置→错误，确保高可用性

### 5. 商业价值
- **成本节省最大化**: 自动选择免费资源，显著降低AI API成本
- **服务质量保障**: 在免费的基础上选择最佳质量和性能
- **用户留存提升**: 降低使用门槛，提高用户满意度

## 技术创新点

### 双重搜索策略
这是Smart AI Router的关键创新，解决了传统路由器"精确匹配优先导致成本浪费"的问题：

**传统路由器**:
```
用户请求: gpt-4
找到: gpt-4 ($0.03/1K tokens)
结果: 直接使用付费版本
```

**Smart AI Router**:
```
用户请求: gpt-4  
物理匹配: gpt-4 ($0.03/1K tokens)
标签匹配: gpt-4:free (免费), gpt-4-turbo:free (免费)
智能合并: 31个候选 (包含免费和付费)
7位评分: 免费模型排在最前
结果: 选择免费版本，节省100%成本
```

这种设计确保了Smart AI Router能够在保持用户便利性的同时，实现成本优化的最大化。