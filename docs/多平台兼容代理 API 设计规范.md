### **多平台兼容代理 API 设计规范**

#### **1. 概述**

本代理服务的核心目标是提供一个统一的入口，将后端的本地大模型（如 LM Studio 托管的模型）能力，通过模拟三家主流厂商的 API 接口暴露给客户端。客户端无需修改代码，只需将请求地址指向本代理服务，即可无缝切换和使用。

**核心设计哲学**：为每个目标平台实现一个独立的、高度仿真的 API Endpoint。这样做可以最大化兼容性，避免因试图统一接口而导致各平台高级功能（如 `tools`）的实现细节丢失。

#### **2. 通用设计原则**

  * **基础 URL (Base URL)**: `https://your-proxy-domain.com`
  * **认证 (Authentication)**: 所有接口均通过 HTTP Header 进行认证。
      * `Authorization: Bearer <YOUR_CUSTOM_API_KEY>`
  * **错误处理 (Error Handling)**: 发生错误时，返回统一格式的 JSON 响应体，并附带相应的 HTTP 状态码（如 400, 401, 500）。
    ```json
    {
      "error": {
        "message": "Error message explaining what went wrong.",
        "type": "invalid_request_error",
        "param": "model",
        "code": "model_not_found"
      }
    }
    ```

-----

#### **3. 核心 API 接口定义**

以下是您需要实现的三个核心接口，分别对应三家厂商。

##### **3.1 OpenAI 兼容接口 (基础核心)**

这是最重要的一组接口，也是代理服务内部处理的基准。

**Endpoint 1: `POST /v1/chat/completions`**

  * **功能**: 处理聊天、函数调用和图片理解请求。
  * **请求体 (Request Body)**:
    ```json
    {
      "model": "gpt-4-turbo", // 客户端指定的模型名，由代理映射到本地模型
      "messages": [
        {
          "role": "system",
          "content": "You are a helpful assistant."
        },
        {
          "role": "user",
          "content": [ // 支持多模态内容数组
            {
              "type": "text",
              "text": "这张图片里有什么？"
            },
            {
              "type": "image_url",
              "image_url": {
                // 支持URL或Base64
                "url": "data:image/jpeg;base64,{BASE64_ENCODED_IMAGE}"
              }
            }
          ]
        },
        { // 用于函数调用后返回结果
           "role": "tool",
           "tool_call_id": "call_abc123",
           "content": "{\"temperature\": 25, \"unit\": \"celsius\"}" // 函数执行结果 (JSON字符串)
        }
      ],
      "tools": [ // 定义可用的函数
        {
          "type": "function",
          "function": {
            "name": "get_current_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
              "type": "object",
              "properties": {
                "location": {
                  "type": "string",
                  "description": "The city and state, e.g. San Francisco, CA"
                },
                "unit": { "type": "string", "enum": ["celsius", "fahrenheit"] }
              },
              "required": ["location"]
            }
          }
        }
      ],
      "tool_choice": "auto", // 或 {"type": "function", "function": {"name": "get_current_weather"}}
      "stream": false, // 是否流式返回
      "max_tokens": 1024,
      "temperature": 0.7
    }
    ```
  * **响应体 (Response Body)**:
      * **非流式 (Standard):**
        ```json
        {
          "id": "chatcmpl-...",
          "object": "chat.completion",
          "created": 1677652288,
          "model": "...",
          "choices": [{
            "index": 0,
            "message": {
              "role": "assistant",
              "content": null, // 如果是调用工具，content为null
              "tool_calls": [ // 模型决定调用工具
                {
                  "id": "call_abc123",
                  "type": "function",
                  "function": {
                    "name": "get_current_weather",
                    "arguments": "{\"location\": \"Boston, MA\"}"
                  }
                }
              ]
            },
            "finish_reason": "tool_calls" // 或 "stop"
          }]
        }
        ```
      * **流式 (Streaming - SSE):** 响应体是一系列 `data: {...}` 事件，最终以 `data: [DONE]` 结束。每个数据块的结构与 OpenAI 的 `chat.completion.chunk` 对象保持一致。

**Endpoint 2: `GET /v1/models`**

  * **功能**: 供客户端获取可用的模型列表。
  * **响应体 (Response Body)**:
    ```json
    {
      "object": "list",
      "data": [
        {
          "id": "gpt-4-turbo", // 提供给客户端的兼容模型名
          "object": "model",
          "owned_by": "your-organization"
        },
        {
          "id": "llama3-8b-instruct", // 也可以是本地真实模型名
          "object": "model",
          "owned_by": "your-organization"
        }
      ]
    }
    ```

-----

##### **3.2 Anthropic (Claude) 兼容接口**

**Endpoint: `POST /v1/messages`**

  * **功能**: 模拟 Claude 3 的 Messages API，支持系统提示、多轮对话、函数调用和图片输入。
  * **请求体 (Request Body)**:
    ```json
    {
      "model": "claude-3-opus-20240229", // 客户端指定的模型名
      "system": "You are a helpful assistant that translates English to French.", // 系统提示
      "messages": [
        {
          "role": "user",
          "content": [ // 支持多模态内容数组
            {
              "type": "text",
              "text": "What is in this image?"
            },
            {
              "type": "image",
              "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "{BASE64_ENCODED_IMAGE}"
              }
            }
          ]
        },
        { // 用于函数调用后返回结果
          "role": "user",
          "content": [
            {
              "type": "tool_result",
              "tool_use_id": "toolu_abc123",
              "content": "{\"temperature\": 25}"
            }
          ]
        }
      ],
      "tools": [ // 定义可用的函数
        {
          "name": "get_weather",
          "description": "Get the current weather for a specific location.",
          "input_schema": {
            "type": "object",
            "properties": {
              "location": {
                "type": "string",
                "description": "The city to get the weather for."
              }
            },
            "required": ["location"]
          }
        }
      ],
      "max_tokens": 1024,
      "stream": false
    }
    ```
  * **响应体 (Response Body)**:
      * 需要严格模仿 Claude 的响应结构。当模型决定调用工具时，`stop_reason` 为 `tool_use`，并在 `content` 数组中包含 `tool_use` 块。
        ```json
        {
          "id": "msg_...",
          "type": "message",
          "role": "assistant",
          "content": [
            {
              "type": "text",
              "text": "Okay, I will get the weather for you."
            },
            {
              "type": "tool_use",
              "id": "toolu_abc123",
              "name": "get_weather",
              "input": { "location": "San Francisco" }
            }
          ],
          "stop_reason": "tool_use"
        }
        ```

-----

##### **3.3 Google (Gemini) 兼容接口**

**Endpoint: `POST /v1beta/models/{model}:generateContent`**

  * **功能**: 模拟 Gemini API，支持多轮对话、函数调用和图片输入。`{model}` 部分是 URL 的一部分。
  * **请求体 (Request Body)**:
    ```json
    {
      "contents": [
        {
          "role": "user",
          "parts": [ // parts数组用于支持多模态
            { "text": "What is in this picture?" },
            {
              "inline_data": {
                "mime_type": "image/jpeg",
                "data": "{BASE64_ENCODED_IMAGE}"
              }
            }
          ]
        },
        { // Gemini将模型的回复也放在contents中
          "role": "model",
          "parts": [/* ... previous model parts ... */]
        },
        { // 用于函数调用后返回结果
          "role": "user", // 在Gemini中，这个role是'function'或新版'tool'
          "parts": [
            {
              "functionResponse": {
                "name": "get_weather",
                "response": {
                  "content": "The weather is sunny."
                }
              }
            }
          ]
        }
      ],
      "tools": [ // 定义可用的函数
        {
          "functionDeclarations": [
            {
              "name": "get_weather",
              "description": "Get the weather in a location",
              "parameters": {
                "type": "OBJECT",
                "properties": {
                  "location": { "type": "STRING" }
                },
                "required": ["location"]
              }
            }
          ]
        }
      ],
      "generationConfig": {
        "maxOutputTokens": 1024,
        "temperature": 0.7
      }
    }
    ```
  * **响应体 (Response Body)**:
      * 需要严格模仿 Gemini 的响应结构。当模型决定调用函数时，响应中会包含 `functionCall`。
        ```json
        {
          "candidates": [
            {
              "content": {
                "role": "model",
                "parts": [
                  {
                    "functionCall": {
                      "name": "get_weather",
                      "args": {
                        "location": "Paris"
                      }
                    }
                  }
                ]
              },
              "finishReason": "TOOL_CODE"
            }
          ]
        }
        ```

-----

#### **4. 接口功能支持矩阵**

| 功能 Feature | OpenAI 接口 (`/v1/chat/completions`) | Claude 接口 (`/v1/messages`) | Gemini 接口 (`/v1beta/...:generateContent`) |
| :--- | :--- | :--- | :--- |
| **标准文本聊天** | **支持** | **支持** | **支持** |
| **流式响应** | **支持** | **支持** | **支持** |
| **函数调用/Tools** | **支持** (通过 `tools` 和 `tool_calls`) | **支持** (通过 `tools` 和 `tool_use`) | **支持** (通过 `tools` 和 `functionCall`) |
| **图片输入 (多模态)** | **支持** (通过 `content` 数组和 `image_url`) | **支持** (通过 `content` 数组和 `image` source) | **支持** (通过 `parts` 数组和 `inline_data`) |

#### **5. 总结**

要构建一个功能完备且兼容性强的代理服务，您需要：

1.  **实现 OpenAI 的 `/v1/chat/completions` 和 `/v1/models` 接口作为基础。** 这是覆盖率最广的方案。
2.  **为 Claude 和 Gemini 分别实现其官方的 `messages` 和 `generateContent` 接口。**
3.  在每个接口的实现中，**精确地模拟** 对应厂商对于 `tools` 和多模态（图片）数据的**请求和响应结构**。

通过实现上述接口规范，您的代理服务将能作为一个强大的“中间件”，让各类遵循这三家主流 API 的客户端应用，都能无缝地利用您在本地 LM Studio 中部署的大模型能力。