# 豆包(Doubao)定价系统详细文档

## 📋 概述

豆包定价系统是 Smart AI Router 中最完善的厂商定价集成之一，支持火山方舟平台的 17 个核心 AI 模型，包含完整的架构信息、阶梯定价、多模态能力等详细数据。

### 🎯 核心特性

- **17 个核心模型**: 覆盖深度思考、大语言、视觉理解等全系列
- **完整架构信息**: modality、input/output 模态、tokenizer 详细标识
- **阶梯定价支持**: 保留 CNY 原始定价，支持复杂定价条件
- **2 层定价系统**: 统一格式优先，阶梯定价智能回退
- **多模态能力**: 精确识别 thinking、vision、GUI、visual_positioning 等

## 📊 支持的模型列表

### 🧠 深度思考模型 (Thinking Models)

#### Seed 1.6 系列 (最新推荐)

```json
doubao-seed-1-6-vision-250815     - 豆包 Seed 1.6 Vision
doubao-seed-1-6-250615            - 豆包 Seed 1.6
doubao-seed-1-6-flash-250715      - 豆包 Seed 1.6 Flash
doubao-seed-1-6-thinking-250715   - 豆包 Seed 1.6 Thinking
```

**能力特征**:

- ✅ 深度思考 (thinking) - 32k 思维链 tokens
- ✅ 多模态理解 (vision + video)
- ✅ 工具调用 (function_calling)
- ✅ 结构化输出 (structured_output)
- ✅ GUI 任务处理 (部分模型)

#### 第三方深度思考模型

```json
deepseek-v3-1-250821              - DeepSeek V3.1
deepseek-r1-250528                - DeepSeek R1
```

### 💬 大语言模型 (Large Language Models)

#### 豆包 1.5 系列

```json
doubao-1-5-pro-32k-character-250715  - 豆包 1.5 Pro 32K Character (角色扮演增强)
doubao-1-5-pro-256k-250115           - 豆包 1.5 Pro 256K (长上下文)
doubao-1-5-lite-32k-250115           - 豆包 1.5 Lite 32K (轻量高效)
```

#### 轻量专业版

```json
doubao-pro-32k-241215                - 豆包 Pro 32K
doubao-lite-32k-240828               - 豆包 Lite 32K
doubao-lite-128k-240828              - 豆包 Lite 128K
```

#### 第三方大语言模型

```json
kimi-k2-250711                       - Kimi K2 (月之暗面)
deepseek-v3-250324                   - DeepSeek V3
```

### 👁️ 视觉理解模型 (Vision Models)

```json
doubao-1-5-vision-pro-250328         - 豆包 1.5 Vision Pro (专业版)
doubao-1-5-vision-lite-250315        - 豆包 1.5 Vision Lite (轻量版)
doubao-1-5-ui-tars-250428            - 豆包 1.5 UI Tars (GUI专用)
```

**视觉能力**:

- 📷 图片理解 (image understanding)
- 🎬 视频理解 (video understanding, 部分模型)
- 🎯 视觉定位 (visual_positioning)
- 🖥️ GUI 任务处理 (gui operations)

## 🏗️ 架构信息详解

每个模型都包含完整的架构信息：

### Modality 定义

```json
"architecture": {
  "modality": "text+vision+video->text",      // 输入输出模态组合
  "input_modalities": ["text", "image", "video"], // 支持的输入类型
  "output_modalities": ["text"],              // 支持的输出类型
  "tokenizer": "doubao",                      // 使用的分词器
  "instruct_type": "chat"                     // 指令类型
}
```

### 常见 Modality 类型

- `"text->text"` - 纯文本模型
- `"text+vision->text"` - 图文理解模型
- `"text+vision+video->text"` - 多模态理解模型

### Tokenizer 类型

- `"doubao"` - 豆包自研分词器
- `"deepseek"` - DeepSeek 分词器
- `"kimi"` - Kimi 分词器

## 💰 定价结构详解

### 统一定价格式 (USD per token)

```json
"pricing": {
  "prompt": 0.00000112,        // 输入价格 USD/token
  "completion": 0.00001120,    // 输出价格 USD/token
  "request": 0.0,              // 请求固定费用
  "image": 0.0                 // 图像处理费用
}
```

### 阶梯定价扩展信息

```json
"doubao_extensions": {
  "tiered_pricing": {
    "currency": "CNY",
    "unit": "per_million_tokens",
    "doubao-seed-1-6-vision-250815": {
      "max_input_tokens": 229376,
      "thinking_tokens": 32768,
      "online_inference": {
        "tier_1": {"input_range": "[0, 32k]", "input_price": 0.80, "output_price": 8.00},
        "tier_2": {"input_range": "(32k, 128k]", "input_price": 1.20, "output_price": 16.00},
        "tier_3": {"input_range": "(128k, 256k]", "input_price": 2.40, "output_price": 24.00}
      }
    }
  }
}
```

### 复杂定价条件示例

```json
"doubao-seed-1-6-250615": {
  "online_inference": {
    "tier_1_short": {
      "condition": "input[0,32k] && output[0,0.2k]",
      "input_price": 0.80,
      "output_price": 2.00
    },
    "tier_1_long": {
      "condition": "input[0,32k] && output(0.2k,+∞)",
      "input_price": 0.80,
      "output_price": 8.00
    }
  }
}
```

## 🎛️ 技术参数详解

### Top Provider 信息

```json
"top_provider": {
  "context_length": 262144,        // 上下文长度
  "max_completion_tokens": 32768,  // 最大输出tokens
  "is_moderated": true            // 是否内容审核
}
```

### 运营参数

```json
"doubao_extensions": {
  "common_features": {
    "free_quota": 500000,                    // 免费配额 (tokens)
    "rate_limits_default": {
      "rpm": 30000,                         // 每分钟请求数
      "tpm": 5000000                        // 每分钟tokens数
    }
  }
}
```

## 🔄 2 层定价系统工作原理

### 查询优先级

1. **第 1 层**: 渠道专属定价查询

   ```python
   # 查找文件优先级
   doubao_price.json       # Legacy格式 (优先级最高)
   doubao_pricing.json     # 通用定价格式
   doubao_unified.json     # 统一格式 (推荐)
   doubao.json            # 简化格式
   ```

2. **第 2 层**: 回退策略
   - 豆包特殊回退: 阶梯定价计算器
   - 通用回退: OpenRouter 基准定价

### 代码实现逻辑

```python
# core/utils/static_pricing.py
def get_model_pricing(self, provider_name, model_name):
    # 第1层：渠道专属定价
    result = self._query_channel_pricing(provider_name, model_name)
    if result:
        return result

    # 第2层：豆包特殊回退
    if "doubao" in provider_name.lower():
        result = self._query_doubao_pricing(model_name)
        if result:
            result.pricing_info += " (阶梯定价回退)"
            return result

    # 通用回退
    return self._query_base_pricing(model_name)
```

## 🧪 使用示例

### 基础查询

```python
from core.utils.static_pricing import get_static_pricing_loader

loader = get_static_pricing_loader()
result = loader.get_model_pricing('doubao', 'doubao-seed-1-6-vision-250815')

print(f"模型: {result.model_id}")
print(f"输入价格: ${result.input_price}/K tokens")
print(f"输出价格: ${result.output_price}/K tokens")
print(f"定价来源: {result.pricing_info}")
```

### 统一格式文件验证

```python
from core.pricing.unified_format import UnifiedPricingFile
from pathlib import Path

file_path = Path('config/pricing/doubao_unified.json')
unified_data = UnifiedPricingFile.load_from_file(file_path)

print(f"加载了 {len(unified_data.models)} 个模型")

# 检查架构信息
vision_model = unified_data.models.get('doubao-seed-1-6-vision-250815')
if vision_model and vision_model.architecture:
    print(f"模态: {vision_model.architecture.modality}")
    print(f"输入类型: {vision_model.architecture.input_modalities}")
```

## 📈 成本对比分析

### 深度思考模型成本 (100 万 tokens)

| 模型                | 输入成本 | 输出成本 | 总成本     | 特殊能力   |
| ------------------- | -------- | -------- | ---------- | ---------- |
| **Seed 1.6 Vision** | $1.12    | $11.20   | **$12.32** | 多模态+GUI |
| **Seed 1.6 Flash**  | $0.21    | $2.10    | **$2.31**  | 高速思考   |
| **DeepSeek V3.1**   | $5.60    | $16.80   | **$22.40** | 第三方推理 |
| **DeepSeek R1**     | $5.60    | $22.40   | **$28.00** | 推理专用   |

### 视觉模型成本对比

| 模型            | 输入成本 | 输出成本 | 总成本     | 应用场景     |
| --------------- | -------- | -------- | ---------- | ------------ |
| **Vision Lite** | $2.10    | $6.30    | **$8.40**  | 轻量图像理解 |
| **Vision Pro**  | $4.20    | $12.60   | **$16.80** | 专业视觉分析 |
| **UI Tars**     | $4.90    | $16.80   | **$21.70** | GUI 自动化   |

## ⚙️ 配置文件结构

### doubao_unified.json 结构

```json
{
  "provider": "doubao",
  "source": "volcanic_engine_official",
  "currency": "USD",
  "unit": "per_token",
  "format_version": "2.0",
  "last_updated": "2025-01-12T12:00:00Z",
  "description": "豆包(Doubao)大模型完整定价配置",

  "models": {
    "model_id": {
      "id": "模型标识",
      "name": "显示名称",
      "context_length": 262144,
      "architecture": {
        /* 架构信息 */
      },
      "capabilities": ["能力列表"],
      "category": "模型分类",
      "pricing": {
        /* USD定价 */
      },
      "top_provider": {
        /* 技术参数 */
      }
    }
  },

  "doubao_extensions": {
    "description": "豆包扩展信息",
    "common_features": {
      /* 通用特性 */
    },
    "tiered_pricing": {
      /* 阶梯定价 */
    }
  }
}
```

## 🚀 集成建议

### 新厂商集成模板

基于豆包定价系统的成功经验，其他厂商可以参考以下模板：

1. **创建 unified 格式文件**: `{provider}_unified.json`
2. **完善架构信息**: modality、capabilities、tokenizer
3. **添加扩展信息**: 厂商特有的定价策略和技术参数
4. **2 层系统集成**: 修改`static_pricing.py`添加特殊回退逻辑

### 最佳实践

- ✅ 使用统一格式作为主要定价来源
- ✅ 保留厂商原始定价信息用于审计
- ✅ 扩展信息与标准格式分离
- ✅ 完整的架构和能力标识
- ✅ 定期更新汇率转换

## 🔧 故障排除

### 常见问题

#### 1. 模型加载失败

```bash
# 检查文件是否存在
ls -la config/pricing/doubao_unified.json

# 验证JSON格式
python -c "
from core.pricing.unified_format import UnifiedPricingFile
UnifiedPricingFile.load_from_file('config/pricing/doubao_unified.json')
print('JSON格式正确')
"
```

#### 2. 定价查询返回 None

```python
# 调试定价查询
loader = get_static_pricing_loader()
result = loader.get_model_pricing('doubao', 'model-name', debug=True)
```

#### 3. 汇率过期问题

```python
# 检查当前汇率设置
# doubao_unified.json中的定价基于 CNY->USD = 0.14
# 建议定期更新此汇率
```

## 📋 维护清单

### 定期维护任务

- [ ] **月度**: 检查火山方舟官方定价更新
- [ ] **季度**: 更新 CNY->USD 汇率转换
- [ ] **半年**: 审核模型架构信息准确性
- [ ] **年度**: 评估新模型集成需求

### 监控指标

- 定价查询成功率
- 缓存命中率
- 汇率偏差程度
- 模型覆盖完整度

---

**💡 提示**: 豆包定价系统已完全集成到 Smart AI Router 的 2 层定价架构中，为成本优化和智能路由提供准确的定价基础！
