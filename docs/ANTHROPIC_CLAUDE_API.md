# Anthropic Claude API 接口文档

## 概述

Anthropic Claude API 是一个用于与Claude系列AI模型进行交互的RESTful API。本文档基于Smart AI Router中的实现，详细描述了API的接口规范、请求格式和响应结构。

## 基本信息

- **Base URL**: `https://api.anthropic.com`
- **API版本**: `2023-06-01`
- **认证方式**: `x-api-key` header
- **主要端点**: `/v1/messages`

## 认证

### 请求头要求

```http
POST /v1/messages HTTP/1.1
Host: api.anthropic.com
x-api-key: YOUR_API_KEY
anthropic-version: 2023-06-01
Content-Type: application/json
```

### 认证参数

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `x-api-key` | string | 是 | Anthropic API密钥 |
| `anthropic-version` | string | 是 | API版本，固定为`2023-06-01` |
| `content-type` | string | 是 | 请求内容类型，固定为`application/json` |

## 主要端点

### 1. Messages API - 创建消息

**端点**: `POST /v1/messages`

**描述**: 创建一个新的对话消息并获取Claude的响应

#### 请求格式

```json
{
  "model": "claude-3-5-sonnet-20241022",
  "max_tokens": 4096,
  "temperature": 0.7,
  "messages": [
    {
      "role": "user", 
      "content": "Hello, Claude!"
    }
  ],
  "system": "You are a helpful assistant.",
  "stream": false,
  "tools": [...]
}
```

#### 请求参数

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `model` | string | 是 | 模型ID |
| `max_tokens` | integer | 是 | 最大生成token数 |
| `messages` | array | 是 | 消息数组 |
| `temperature` | float | 否 | 温度参数，控制随机性 (0.0-1.0) |
| `system` | string | 否 | 系统提示词 |
| `stream` | boolean | 否 | 是否使用流式响应 |
| `tools` | array | 否 | 工具定义数组 |

#### 消息格式

每条消息的格式：

```json
{
  "role": "user|assistant",
  "content": "消息内容"
}
```

**角色说明**:
- `user`: 用户消息
- `assistant`: 助手回复

**注意**: Anthropic不支持`system`角色，系统消息需要通过单独的`system`字段传递。

#### 响应格式

**非流式响应**:
```json
{
  "id": "msg_123456789",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Hello! I'm Claude, an AI assistant created by Anthropic."
    }
  ],
  "model": "claude-3-5-sonnet-20241022",
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 15,
    "output_tokens": 20
  }
}
```

**流式响应**:
```
data: {"type": "message_start", "message": {"id": "msg_123", "type": "message", "role": "assistant", "content": [], "model": "claude-3-5-sonnet-20241022", "stop_reason": null, "usage": {"input_tokens": 15, "output_tokens": 0}}}

data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}}

data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 5}}

data: {"type": "message_stop"}
```

#### 响应字段说明

| 字段 | 类型 | 描述 |
|------|------|------|
| `id` | string | 消息ID |
| `type` | string | 响应类型 |
| `role` | string | 响应角色 |
| `content` | array | 内容块数组 |
| `model` | string | 使用的模型 |
| `stop_reason` | string | 停止原因 |
| `usage` | object | Token使用统计 |

### 2. 模型列表

**注意**: Anthropic不提供获取模型列表的API端点，需要手动定义支持的模型。

## 支持的模型

### Claude 3.5 系列

| 模型ID | 名称 | 上下文长度 | 输入成本 | 输出成本 | 能力 |
|--------|------|------------|----------|----------|------|
| `claude-3-5-sonnet-20241022` | Claude 3.5 Sonnet | 200K | $0.003/1K | $0.015/1K | 文本、视觉、函数调用、代码生成 |
| `claude-3-5-haiku-20241022` | Claude 3.5 Haiku | 200K | $0.001/1K | $0.005/1K | 文本、函数调用 |

### Claude 3 系列

| 模型ID | 名称 | 上下文长度 | 输入成本 | 输出成本 | 能力 |
|--------|------|------------|----------|----------|------|
| `claude-3-opus-20240229` | Claude 3 Opus | 200K | $0.015/1K | $0.075/1K | 文本、视觉、函数调用、代码生成 |

## 功能特性

### 1. 流式响应

支持实时流式响应，通过设置`stream: true`启用。

**流式事件类型**:
- `message_start`: 消息开始
- `content_block_delta`: 内容增量
- `message_delta`: 消息增量
- `message_stop`: 消息结束

### 2. 工具调用

支持函数调用功能，需要定义工具描述。

**工具格式**:
```json
{
  "name": "function_name",
  "description": "Function description",
  "input_schema": {
    "type": "object",
    "properties": {...},
    "required": [...]
  }
}
```

### 3. 多模态支持

部分模型支持图像输入，内容格式：

```json
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "请描述这张图片"
    },
    {
      "type": "image",
      "source": {
        "type": "base64",
        "media_type": "image/jpeg",
        "data": "base64_encoded_image_data"
      }
    }
  ]
}
```

## 错误处理

### 错误响应格式

```json
{
  "type": "error",
  "error": {
    "type": "invalid_request_error",
    "message": "错误描述"
  }
}
```

### 常见错误类型

| 错误类型 | HTTP状态码 | 描述 |
|----------|------------|------|
| `invalid_request_error` | 400 | 请求格式错误 |
| `authentication_error` | 401 | 认证失败 |
| `permission_error` | 403 | 权限不足 |
| `not_found_error` | 404 | 资源不存在 |
| `rate_limit_error` | 429 | 请求频率限制 |
| `api_error` | 5xx | 服务器内部错误 |

## 速率限制

- **请求限制**: 根据API密钥类型有所不同
- **Token限制**: 每分钟处理的token数量限制
- **并发限制**: 同时进行的请求数量限制

## 使用示例

### 基本对话

```python
import httpx

async def chat_with_claude():
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": "YOUR_API_KEY",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": "Hello, Claude!"
            }
        ]
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        return response.json()
```

### 流式对话

```python
import httpx
import json

async def stream_chat_with_claude():
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": "YOUR_API_KEY",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 4096,
        "stream": True,
        "messages": [
            {
                "role": "user",
                "content": "Tell me a story"
            }
        ]
    }
    
    async with httpx.AsyncClient() as client:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data.get("type") == "content_block_delta":
                        print(data.get("delta", {}).get("text", ""), end="")
```

## 最佳实践

1. **设置合适的max_tokens**: Anthropic要求必须设置此参数
2. **处理系统消息**: 使用`system`字段而不是`messages`中的system角色
3. **错误重试**: 实现适当的重试逻辑处理网络问题
4. **流式响应**: 对于长文本生成使用流式响应提升用户体验
5. **成本控制**: 监控token使用量，控制成本

## 与OpenAI API的对比

| 特性 | Anthropic Claude | OpenAI GPT |
|------|------------------|------------|
| 认证方式 | `x-api-key` | `Authorization: Bearer` |
| 系统消息 | 单独字段 | 消息数组中的system角色 |
| 流式格式 | Server-Sent Events | Server-Sent Events |
| 工具调用 | 自定义格式 | Function calling |
| 必需参数 | `max_tokens` | 可选 |

## 参考链接

- [Anthropic官方文档](https://docs.anthropic.com/claude/reference)
- [Claude模型介绍](https://www.anthropic.com/claude/models)
- [API最佳实践](https://docs.anthropic.com/claude/docs/api-best-practices)

---

*本文档基于Smart AI Router项目中的Anthropic适配器实现，包含了完整的API接口规范和使用指南。*