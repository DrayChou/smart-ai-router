# API 接口文档

## 概述

Smart AI Router 提供 OpenAI 兼容的 API 接口，同时包含管理接口用于动态配置。

## 聊天接口

### POST /v1/chat/completions

OpenAI 兼容的聊天完成接口。

**请求参数:**
```json
{
  "model": "auto:free",  // 模型组名称
  "messages": [
    {
      "role": "user",
      "content": "Hello!"
    }
  ],
  "stream": false,
  "temperature": 0.7,
  "max_tokens": 1000
}
```

**响应格式:**
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "auto:free",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 9,
    "completion_tokens": 12,
    "total_tokens": 21
  }
}
```

## 模型列表接口

### GET /v1/models

获取可用的模型组列表。

**响应格式:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "auto:free",
      "object": "model",
      "created": 1677610602,
      "owned_by": "smart-ai-router"
    },
    {
      "id": "auto:fast",
      "object": "model", 
      "created": 1677610602,
      "owned_by": "smart-ai-router"
    }
  ]
}
```

## 健康检查接口

### GET /health

系统健康状态检查。

**响应格式:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-01-01T00:00:00Z",
  "database": "connected",
  "active_channels": 15,
  "active_providers": 6
}
```

## 管理接口

### GET /management/channels

获取所有渠道列表。

### POST /management/channels

创建新渠道。

### GET /management/model-groups

获取所有模型组。

### POST /management/model-groups

创建新模型组。

### GET /management/api-keys

获取API密钥列表。

### POST /management/api-keys

创建新API密钥。

## 认证

所有API请求需要在Header中包含认证信息：

```
Authorization: Bearer your-api-key
```

## 错误处理

API遵循标准HTTP状态码：

- `200` - 成功
- `400` - 请求参数错误
- `401` - 认证失败
- `429` - 请求频率限制
- `500` - 服务器内部错误

错误响应格式：
```json
{
  "error": {
    "message": "Invalid request",
    "type": "invalid_request_error",
    "code": "invalid_model"
  }
}
```