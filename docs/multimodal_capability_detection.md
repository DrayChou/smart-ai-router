# 多模态能力检测机制

## 概述

Smart AI Router 使用 OpenRouter 的模型数据库作为**通用参考源**，为所有提供商（OpenRouter、OpenAI、Anthropic、Groq 等）的模型提供准确的能力检测。

## 核心设计理念

### OpenRouter 作为能力数据源

OpenRouter 维护着最全面和最新的 AI 模型数据库，包括：

- 模型的完整架构信息
- 支持的输入/输出模态
- 参数支持列表
- 上下文长度等规格信息

我们将其作为**单一真实来源**，避免在代码中硬编码模型能力。

## 能力检测流程

### 1. 主要检测方法：OpenRouter 数据库查询

```python
def get_model_capabilities_from_openrouter(model_name: str) -> tuple[list[str], int]:
    """
    使用OpenRouter数据库作为通用模型能力参考
    所有渠道（OpenRouter、OpenAI、Anthropic等）的模型能力都参考OpenRouter的模型列表
    """
```

#### 检测步骤：

1. **直接匹配**：首先在 OpenRouter 数据中查找完全匹配的模型名称
2. **模糊匹配**：如果直接匹配失败，尝试跨提供商匹配（例如 `gpt-4o-mini` 匹配 `openai/gpt-4o-mini`）
3. **降级处理**：如果 OpenRouter 数据不可用，返回基础的文本能力

### 2. 能力提取规则

#### Vision（多模态）能力

从 OpenRouter 数据的 `architecture.input_modalities` 字段检测：

```python
architecture = raw_data.get('architecture', {})
input_modalities = architecture.get('input_modalities', [])

if "image" in input_modalities:
    capabilities.append("vision")
```

**示例数据结构**：

```json
{
  "meta-llama/llama-3.2-90b-vision-instruct": {
    "raw_data": {
      "architecture": {
        "modality": "text+image->text",
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"]
      }
    }
  }
}
```

#### Function Calling 能力

从 `supported_parameters` 字段检测：

```python
supported_params = raw_data.get('supported_parameters', [])

if any(param in supported_params for param in ["tools", "tool_choice"]):
    capabilities.append("function_calling")
```

#### JSON Mode 能力

```python
if any(param in supported_params for param in ["response_format", "structured_outputs"]):
    capabilities.append("json_mode")
```

#### 上下文长度

直接从 OpenRouter 数据获取：

```python
context_length = raw_data.get('context_length', 0)
```

## 优势和好处

### 1. 统一性

- **所有提供商统一**：无论是 OpenRouter、OpenAI 还是其他提供商的模型，都使用相同的能力检测逻辑
- **避免重复维护**：不需要为每个提供商单独维护能力映射

### 2. 准确性

- **数据来源权威**：OpenRouter 的数据库经过专业维护，准确性高
- **实时更新**：随着 OpenRouter 数据的更新，能力检测自动保持最新

### 3. 可维护性

- **无硬编码**：代码中不包含特定模型的能力硬编码
- **自动扩展**：新模型上线后自动获得正确的能力标签

### 4. 智能匹配

- **跨提供商匹配**：能够识别相同模型在不同提供商下的变体名称
- **容错处理**：支持名称变体（如 `-instruct`、`-chat`、`:free` 等后缀）

## 数据流程

```
用户查询模型 (gpt-4o-mini)
          ↓
在 OpenRouter 数据库中查找
          ↓
找到: openai/gpt-4o-mini
          ↓
解析 architecture.input_modalities: ["text", "image"]
          ↓
返回能力: ["text", "vision"]
          ↓
在 Web 界面显示: 💬 文本 🖼️ 图像
```

## 模型匹配逻辑

### 精确匹配

```python
if model_name in models_data:
    # 直接使用 OpenRouter 数据
```

### 模糊匹配

```python
def _models_match(model_name_1: str, model_name_2: str) -> bool:
    # 移除provider前缀
    clean_1 = model_name_1.split('/')[-1].lower()
    clean_2 = model_name_2.split('/')[-1].lower()

    # 移除常见变体后缀
    variants = ['-instruct', '-chat', '-v1', '-v2', '-v3', '-latest', ':free', ':beta']

    for variant in variants:
        clean_1 = clean_1.replace(variant, '')
        clean_2 = clean_2.replace(variant, '')

    return clean_1 == clean_2
```

## 使用场景

### 1. Web 界面搜索

当用户在 Web 界面搜索模型时，系统会：

1. 获取匹配的渠道列表
2. 为每个模型调用 `get_model_capabilities_from_openrouter()`
3. 在搜索结果中显示能力标签

### 2. 自动模型过滤

当用户发送包含图片的请求时，系统会：

1. 检测到请求中包含视觉内容
2. 自动过滤掉不支持 vision 能力的模型
3. 只路由到支持多模态的模型

### 3. 能力验证

在路由决策时，系统会：

1. 检查目标模型是否支持所需能力
2. 如果不支持，自动跳过该渠道
3. 选择下一个合适的渠道

## 错误处理

### 缓存文件不存在

```python
# 如果OpenRouter数据不可用，只提供基础文本能力
logger.debug(f"⚠️ 未找到 {model_name} 的OpenRouter数据，使用默认能力")
return ["text"], 0
```

### 数据解析错误

```python
except Exception as e:
    logger.warning(f"读取OpenRouter数据失败: {e}")
    return ["text"], 0
```

## 最佳实践

### 1. 信任 OpenRouter 数据

- 优先使用 OpenRouter 提供的能力信息
- 避免基于模型名称的推测

### 2. 定期更新缓存

- 通过定时任务更新 OpenRouter 模型数据
- 保持能力检测的时效性

### 3. 日志记录

- 记录能力检测的详细过程
- 便于调试和优化

## 配置文件

### OpenRouter 缓存位置

```
cache/channels/openrouter.free.json
```

### 数据结构示例

```json
{
  "models": {
    "meta-llama/llama-3.2-90b-vision-instruct": {
      "raw_data": {
        "architecture": {
          "modality": "text+image->text",
          "input_modalities": ["text", "image"],
          "output_modalities": ["text"]
        },
        "supported_parameters": ["tools", "tool_choice"],
        "context_length": 128000
      }
    }
  }
}
```

## 总结

通过使用 OpenRouter 作为模型能力的统一数据源，Smart AI Router 实现了：

- **准确的多模态检测**：基于权威数据，避免猜测
- **自动化维护**：新模型自动获得正确能力标签
- **统一的能力标准**：所有提供商使用相同的检测逻辑
- **智能的匹配算法**：支持跨提供商和名称变体

这种设计确保了系统的可靠性和可维护性，为用户提供准确的模型能力信息和智能的路由决策。
