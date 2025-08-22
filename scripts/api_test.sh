#!/bin/bash

# ==============================================================================
# API 代理服务综合测试脚本
#
# 功能:
# 1. 测试基础 Health Check 和 Models 接口。
# 2. 测试 OpenAI 兼容接口 (文本/图片/工具/流式)。
# 3. 测试 Anthropic (Claude) 兼容接口 (文本/图片/工具/流式)。
# 4. 测试 Google (Gemini) 兼容接口 (文本/图片/工具/流式)。
# 5. 提供对 Admin 接口的基本测试命令。
#
# 使用:
# 1. 修改下面的 BASE_URL 和 API_KEY。
# 2. 在终端运行: ./test_router.sh
# ==============================================================================

# --- 配置变量 ---
# 请修改为您的代理服务地址
BASE_URL="http://127.0.0.1:8000"
# 请修改为您的 API 密钥
API_KEY="your-secret-api-key"

# --- 模型名称 (根据您在 LM Studio 加载的模型进行修改) ---
# 用于 OpenAI 和 Anthropic 的模型名称
MODEL_CHAT="gpt-4"
# 用于 Gemini 的模型名称 (通常需要 'models/' 前缀)
MODEL_GEMINI="gemini-pro"

# --- 辅助数据 ---
# 一个 1x1 红色像素点的 Base64 编码，用于多模态测试
BASE64_IMAGE="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/wcAAwAB/epv2AAAAABJRU5ErkJggg=="

# --- 辅助函数 ---
# 打印标题
print_header() {
    echo ""
    echo "=============================================================================="
    echo "  $1"
    echo "=============================================================================="
    echo ""
}

# 检查 jq 是否安装
if ! command -v jq &> /dev/null
then
    echo "错误: 本脚本需要 'jq'。请先安装它。"
    exit 1
fi

# ==============================================================================
# 1. 基础接口测试
# ==============================================================================

print_header "1.1: 测试根路径 (GET /)"
curl -s -X GET "$BASE_URL/" | jq .
echo "------------------------------------------------------------------------------"

print_header "1.2: 测试健康检查 (GET /health)"
curl -s -X GET "$BASE_URL/health" | jq .
echo "------------------------------------------------------------------------------"

print_header "1.3: 测试模型列表 (GET /v1/models)"
curl -s -X GET "$BASE_URL/v1/models" \
  -H "Authorization: Bearer $API_KEY" | jq .
echo "------------------------------------------------------------------------------"


# ==============================================================================
# 2. OpenAI 兼容接口测试 (/v1/chat/completions)
# ==============================================================================

print_header "2.1: OpenAI - 纯文本聊天 (非流式)"
curl -s -X POST "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'"$MODEL_CHAT"'",
    "messages": [{"role": "user", "content": "你好，请用中文简单介绍一下自己。"}],
    "max_tokens": 50
  }' | jq .
echo "------------------------------------------------------------------------------"

print_header "2.2: OpenAI - 纯文本聊天 (流式)"
echo "注意: 流式输出将直接打印在下方，不会格式化。"
curl -N -X POST "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'"$MODEL_CHAT"'",
    "messages": [{"role": "user", "content": "你好，请用中文写一首关于春天的小诗。"}],
    "max_tokens": 100,
    "stream": true
  }'
echo ""
echo "------------------------------------------------------------------------------"

print_header "2.3: OpenAI - 多模态 (图片) 聊天 (非流式)"
curl -s -X POST "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'"$MODEL_CHAT"'",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "这张图片里有什么内容？"},
          {"type": "image_url", "image_url": {"url": "data:image/png;base64,'"$BASE64_IMAGE"'"}}
        ]
      }
    ],
    "max_tokens": 50
  }' | jq .
echo "------------------------------------------------------------------------------"

print_header "2.4: OpenAI - 工具调用 (Tools) (非流式)"
curl -s -X POST "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'"$MODEL_CHAT"'",
    "messages": [{"role": "user", "content": "查询一下北京今天的天气怎么样？"}],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_current_weather",
          "description": "获取一个地点的当前天气",
          "parameters": {
            "type": "object",
            "properties": {
              "location": {"type": "string", "description": "城市名, e.g. Beijing"}
            },
            "required": ["location"]
          }
        }
      }
    ]
  }' | jq .
echo "------------------------------------------------------------------------------"


# ==============================================================================
# 3. Anthropic (Claude) 兼容接口测试 (/v1/messages)
# ==============================================================================

print_header "3.1: Claude - 纯文本聊天 (非流式)"
# 注意: Claude API 需要特定的 Header，但我们的代理应该只使用统一的 Bearer Token
curl -s -X POST "$BASE_URL/v1/messages" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'"$MODEL_CHAT"'",
    "messages": [{"role": "user", "content": "Hello, what is the capital of France?"}],
    "max_tokens": 50
  }' | jq .
echo "------------------------------------------------------------------------------"

print_header "3.2: Claude - 纯文本聊天 (流式)"
echo "注意: 流式输出将直接打印在下方，不会格式化。"
curl -N -X POST "$BASE_URL/v1/messages" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'"$MODEL_CHAT"'",
    "messages": [{"role": "user", "content": "Write a short story about a robot who discovers music."}],
    "max_tokens": 150,
    "stream": true
  }'
echo ""
echo "------------------------------------------------------------------------------"

print_header "3.3: Claude - 多模态 (图片) 聊天 (非流式)"
curl -s -X POST "$BASE_URL/v1/messages" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'"$MODEL_CHAT"'",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "What is in this image?"},
          {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "'"$BASE64_IMAGE"'"}}
        ]
      }
    ],
    "max_tokens": 50
  }' | jq .
echo "------------------------------------------------------------------------------"

print_header "3.4: Claude - 工具调用 (Tools) (非流式)"
curl -s -X POST "$BASE_URL/v1/messages" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'"$MODEL_CHAT"'",
    "messages": [{"role": "user", "content": "What is the weather in Tokyo?"}],
    "tools": [
      {
        "name": "get_weather",
        "description": "Get the current weather for a specific location.",
        "input_schema": {
          "type": "object",
          "properties": {
            "location": {"type": "string", "description": "The city to get the weather for."}
          },
          "required": ["location"]
        }
      }
    ]
  }' | jq .
echo "------------------------------------------------------------------------------"


# ==============================================================================
# 4. Google (Gemini) 兼容接口测试
# ==============================================================================

print_header "4.1: Gemini - 纯文本聊天 (非流式)"
curl -s -X POST "$BASE_URL/v1/models/$MODEL_GEMINI:generateContent" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      {"role": "user", "parts": [{"text": "你好，请解释一下什么是黑洞。"}]}
    ]
  }' | jq .
echo "------------------------------------------------------------------------------"

print_header "4.2: Gemini - 纯文本聊天 (流式)"
echo "注意: 流式输出将直接打印在下方，不会格式化。"
curl -N -X POST "$BASE_URL/v1/models/$MODEL_GEMINI:streamGenerateContent" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      {"role": "user", "parts": [{"text": "请写一个关于太空探险的简短故事开头。"}]}
    ]
  }'
echo ""
echo "------------------------------------------------------------------------------"

print_header "4.3: Gemini - 多模态 (图片) 聊天 (非流式)"
curl -s -X POST "$BASE_URL/v1/models/$MODEL_GEMINI:generateContent" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{
      "parts": [
        {"text": "Describe this image."},
        {"inline_data": {"mime_type":"image/png", "data": "'"$BASE64_IMAGE"'"}}
      ]
    }]
  }' | jq .
echo "------------------------------------------------------------------------------"

print_header "4.4: Gemini - 工具调用 (Tools) (非流式)"
curl -s -X POST "$BASE_URL/v1/models/$MODEL_GEMINI:generateContent" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      {"role": "user", "parts": [{"text": "我应该给我的朋友发什么短信祝他生日快乐？"}]}
    ],
    "tools": [
      {
        "functionDeclarations": [
          {
            "name": "generate_birthday_wish",
            "description": "生成一条生日祝福短信",
            "parameters": {
              "type": "OBJECT",
              "properties": {
                "recipient_name": { "type": "STRING", "description": "收信人的名字" }
              }
            }
          }
        ]
      }
    ]
  }' | jq .
echo "------------------------------------------------------------------------------"


# ==============================================================================
# 5. Admin 接口测试 (可选)
# ==============================================================================

print_header "5. Admin 接口 (请根据需要取消注释并运行)"
# echo "5.1: 获取配置状态 (GET /v1/admin/config/status)"
# curl -s -X GET "$BASE_URL/v1/admin/config/status" -H "Authorization: Bearer $API_KEY" | jq .
#
# echo "5.2: 重新加载配置 (POST /v1/admin/config/reload)"
# curl -s -X POST "$BASE_URL/v1/admin/config/reload" -H "Authorization: Bearer $API_KEY" | jq .
#
# echo "5.3: 搜索日志 (GET /v1/admin/logs/search)"
# curl -s -X GET "$BASE_URL/v1/admin/logs/search?query=error" -H "Authorization: Bearer $API_KEY" | jq .
#
# echo "5.4: 获取成本优化信息 (GET /v1/admin/cost/optimize)"
# curl -s -X GET "$BASE_URL/v1/admin/cost/optimize" -H "Authorization: Bearer $API_KEY" | jq .

echo ""
print_header "所有测试已完成！"
