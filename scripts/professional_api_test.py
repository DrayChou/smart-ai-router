#!/usr/bin/env python3
"""
Smart AI Router 专业统一API测试脚本
基于参考脚本优化的完整测试方案

测试覆盖：
- 基础接口测试 (Health, Models)
- OpenAI兼容接口 (文本/流式/多模态/Tools)
- Anthropic兼容接口 (文本/流式/多模态/Tools)
- Gemini兼容接口 (文本/流式/多模态/Tools)
"""

import base64
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


class ProfessionalAPITester:
    """专业API测试器"""

    def __init__(
        self, base_url: str = "http://localhost:7602", api_key: str = "test-key"
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.results = {
            "basic": {},
            "openai": {},
            "anthropic": {},
            "gemini": {},
            "summary": {},
        }

        # 测试数据 - 使用验证过的可用标签
        self.base64_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI/hQCKXwAAAABJRU5ErkJggg=="
        self.model_chat = "tag:qwen,free"
        self.model_vision = "yi-vision-v2"  # 尝试使用yi渠道的vision模型
        self.model_tools = "tag:qwen3,4b,free"
        self.model_gemini = "tag:gemini,flash"  # 使用验证过的gemini标签

    def print_header(self, title: str):
        """打印标题"""
        print("\n" + "=" * 80)
        print(f"  {title}")
        print("=" * 80)
        print()

    def make_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        data: Optional[Dict] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """统一请求方法"""
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            elif method.upper() == "POST":
                if stream:
                    response = requests.post(
                        url, headers=headers, json=data, timeout=30, stream=True
                    )
                else:
                    response = requests.post(
                        url, headers=headers, json=data, timeout=30
                    )
            else:
                return {"status": "error", "error": f"Unsupported method: {method}"}

            result = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "url": url,
            }

            if stream:
                # 处理流式响应
                chunks = []
                for line in response.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        chunks.append(line)
                result["chunks"] = chunks
                result["chunks_count"] = len(chunks)
            else:
                # 处理普通响应
                try:
                    result["data"] = response.json()
                except:
                    result["text"] = response.text

            return result

        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ===== 基础接口测试 =====

    def test_basic_root(self):
        """测试根路径"""
        self.print_header("1.1: 测试根路径 (GET /)")
        result = self.make_request("GET", f"{self.base_url}/", {})

        if result.get("status_code") == 200:
            self.results["basic"]["root"] = {
                "status": "success",
                "response": result.get("data", {}),
            }
            print("[成功] 根路径测试成功")
        else:
            self.results["basic"]["root"] = {
                "status": "failed",
                "error": result.get("error", "Unknown error"),
            }
            print("[失败] 根路径测试失败")

        return result.get("status_code") == 200

    def test_basic_health(self):
        """测试健康检查"""
        self.print_header("1.2: 测试健康检查 (GET /health)")
        result = self.make_request("GET", f"{self.base_url}/health", {})

        if result.get("status_code") == 200:
            self.results["basic"]["health"] = {
                "status": "success",
                "response": result.get("data", {}),
            }
            print("[成功] 健康检查测试成功")
        else:
            self.results["basic"]["health"] = {
                "status": "failed",
                "error": result.get("error", "Unknown error"),
            }
            print("[失败] 健康检查测试失败")

        return result.get("status_code") == 200

    def test_basic_models(self):
        """测试模型列表"""
        self.print_header("1.3: 测试模型列表 (GET /v1/models)")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        result = self.make_request("GET", f"{self.base_url}/v1/models", headers)

        if result.get("status_code") == 200:
            data = result.get("data", {})
            model_count = len(data.get("data", []))
            self.results["basic"]["models"] = {
                "status": "success",
                "model_count": model_count,
            }
            print(f"[成功] 模型列表测试成功，发现 {model_count} 个模型")
        else:
            self.results["basic"]["models"] = {
                "status": "failed",
                "error": result.get("error", "Unknown error"),
            }
            print("[失败] 模型列表测试失败")

        return result.get("status_code") == 200

    # ===== OpenAI兼容接口测试 =====

    def test_openai_text(self):
        """OpenAI - 纯文本聊天 (非流式)"""
        self.print_header("2.1: OpenAI - 纯文本聊天 (非流式)")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": self.model_chat,
            "messages": [
                {"role": "user", "content": "你好，请用中文简单介绍一下自己。"}
            ],
            "max_tokens": 50,
        }

        result = self.make_request(
            "POST", f"{self.base_url}/v1/chat/completions", headers, data
        )

        if result.get("status_code") == 200:
            response_data = result.get("data", {})
            content = (
                response_data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            self.results["openai"]["text"] = {
                "status": "success",
                "content": content[:50] + "...",
            }
            print(f"[成功] OpenAI文本聊天成功: {content[:50]}...")
        else:
            self.results["openai"]["text"] = {
                "status": "failed",
                "error": result.get("error", "Unknown error"),
            }
            print("[失败] OpenAI文本聊天失败")

        return result.get("status_code") == 200

    def test_openai_streaming(self):
        """OpenAI - 纯文本聊天 (流式)"""
        self.print_header("2.2: OpenAI - 纯文本聊天 (流式)")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": self.model_chat,
            "messages": [
                {"role": "user", "content": "你好，请用中文写一首关于春天的小诗。"}
            ],
            "max_tokens": 100,
            "stream": True,
        }

        result = self.make_request(
            "POST", f"{self.base_url}/v1/chat/completions", headers, data, stream=True
        )

        if result.get("status_code") == 200:
            chunks = result.get("chunks", [])
            content_chunks = [
                chunk
                for chunk in chunks
                if chunk.startswith("data: ") and "content" in chunk
            ]
            self.results["openai"]["streaming"] = {
                "status": "success",
                "chunks": len(content_chunks),
            }
            print(f"[成功] OpenAI流式聊天成功，接收 {len(content_chunks)} 个内容块")
        else:
            self.results["openai"]["streaming"] = {
                "status": "failed",
                "error": result.get("error", "Unknown error"),
            }
            print("[失败] OpenAI流式聊天失败")

        return result.get("status_code") == 200

    def test_openai_vision(self):
        """OpenAI - 多模态 (图片) 聊天"""
        self.print_header("2.3: OpenAI - 多模态 (图片) 聊天")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": self.model_vision,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "这张图片里有什么内容？"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{self.base64_image}"
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 50,
        }

        result = self.make_request(
            "POST", f"{self.base_url}/v1/chat/completions", headers, data
        )

        if result.get("status_code") == 200:
            response_data = result.get("data", {})
            content = (
                response_data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            self.results["openai"]["vision"] = {
                "status": "success",
                "content": content[:50] + "...",
            }
            print(f"[成功] OpenAI多模态聊天成功: {content[:50]}...")
        else:
            error_msg = result.get("error", "Unknown error")
            status_code = result.get("status_code", 0)
            response_text = result.get("response_text", "")

            print(f"[调试] OpenAI Vision错误详情:")
            print(f"  状态码: {status_code}")
            print(f"  错误信息: {error_msg}")
            print(f"  响应内容: {response_text[:200]}...")
            print(f"  使用模型: {self.model_vision}")

            if "No available channels" in error_msg or "vision" in error_msg.lower():
                self.results["openai"]["vision"] = {
                    "status": "failed",
                    "error": "Vision capability not available in current channels",
                }
                print("[跳过] OpenAI多模态聊天 - 渠道不支持vision功能")
            else:
                self.results["openai"]["vision"] = {
                    "status": "failed",
                    "error": f"{status_code}: {error_msg}",
                }
                print("[失败] OpenAI多模态聊天失败")

        return result.get("status_code") == 200

    def test_openai_tools(self):
        """OpenAI - 工具调用 (Tools)"""
        self.print_header("2.4: OpenAI - 工具调用 (Tools)")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": self.model_tools,
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
                                "location": {
                                    "type": "string",
                                    "description": "城市名, e.g. Beijing",
                                }
                            },
                            "required": ["location"],
                        },
                    },
                }
            ],
        }

        result = self.make_request(
            "POST", f"{self.base_url}/v1/chat/completions", headers, data
        )

        if result.get("status_code") == 200:
            response_data = result.get("data", {})
            message = response_data.get("choices", [{}])[0].get("message", {})
            tool_calls = message.get("tool_calls", [])
            self.results["openai"]["tools"] = {
                "status": "success",
                "tool_calls": len(tool_calls),
            }
            print(f"[成功] OpenAI工具调用成功，检测到 {len(tool_calls)} 个工具调用")
        else:
            self.results["openai"]["tools"] = {
                "status": "failed",
                "error": result.get("error", "Unknown error"),
            }
            print("[失败] OpenAI工具调用失败")

        return result.get("status_code") == 200

    # ===== Anthropic兼容接口测试 =====

    def test_anthropic_text(self):
        """Anthropic - 纯文本聊天 (非流式)"""
        self.print_header("3.1: Anthropic - 纯文本聊天 (非流式)")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        data = {
            "model": self.model_chat,
            "messages": [
                {"role": "user", "content": "Hello, what is the capital of France?"}
            ],
            "max_tokens": 50,
        }

        result = self.make_request(
            "POST", f"{self.base_url}/v1/messages", headers, data
        )

        if result.get("status_code") == 200:
            response_data = result.get("data", {})
            content = response_data.get("content", [{}])[0].get("text", "")
            self.results["anthropic"]["text"] = {
                "status": "success",
                "content": content[:50] + "...",
            }
            print(f"[成功] Anthropic文本聊天成功: {content[:50]}...")
        else:
            self.results["anthropic"]["text"] = {
                "status": "failed",
                "error": result.get("error", "Unknown error"),
            }
            print("[失败] Anthropic文本聊天失败")

        return result.get("status_code") == 200

    def test_anthropic_streaming(self):
        """Anthropic - 纯文本聊天 (流式)"""
        self.print_header("3.2: Anthropic - 纯文本聊天 (流式)")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        data = {
            "model": self.model_chat,
            "messages": [
                {
                    "role": "user",
                    "content": "Write a short story about a robot who discovers music.",
                }
            ],
            "max_tokens": 150,
            "stream": True,
        }

        result = self.make_request(
            "POST", f"{self.base_url}/v1/messages", headers, data, stream=True
        )

        if result.get("status_code") == 200:
            chunks = result.get("chunks", [])
            content_chunks = [
                chunk for chunk in chunks if "content_block_delta" in chunk
            ]
            self.results["anthropic"]["streaming"] = {
                "status": "success",
                "chunks": len(content_chunks),
            }
            print(f"[成功] Anthropic流式聊天成功，接收 {len(content_chunks)} 个内容块")
        else:
            self.results["anthropic"]["streaming"] = {
                "status": "failed",
                "error": result.get("error", "Unknown error"),
            }
            print("[失败] Anthropic流式聊天失败")

        return result.get("status_code") == 200

    def test_anthropic_vision(self):
        """Anthropic - 多模态 (图片) 聊天"""
        self.print_header("3.3: Anthropic - 多模态 (图片) 聊天")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        data = {
            "model": self.model_vision,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image?"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": self.base64_image,
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 50,
        }

        result = self.make_request(
            "POST", f"{self.base_url}/v1/messages", headers, data
        )

        if result.get("status_code") == 200:
            response_data = result.get("data", {})
            content = response_data.get("content", [{}])[0].get("text", "")
            self.results["anthropic"]["vision"] = {
                "status": "success",
                "content": content[:50] + "...",
            }
            print(f"[成功] Anthropic多模态聊天成功: {content[:50]}...")
        else:
            error_msg = result.get("error", "Unknown error")
            if "No available channels" in error_msg or "vision" in error_msg.lower():
                self.results["anthropic"]["vision"] = {
                    "status": "failed",
                    "error": "Vision capability not available in current channels",
                }
                print("[跳过] Anthropic多模态聊天 - 渠道不支持vision功能")
            else:
                self.results["anthropic"]["vision"] = {
                    "status": "failed",
                    "error": error_msg,
                }
                print("[失败] Anthropic多模态聊天失败")

        return result.get("status_code") == 200

    def test_anthropic_tools(self):
        """Anthropic - 工具调用 (Tools)"""
        self.print_header("3.4: Anthropic - 工具调用 (Tools)")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        data = {
            "model": self.model_tools,
            "messages": [{"role": "user", "content": "What is the weather in Tokyo?"}],
            "tools": [
                {
                    "name": "get_weather",
                    "description": "Get the current weather for a specific location.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city to get the weather for.",
                            }
                        },
                        "required": ["location"],
                    },
                }
            ],
        }

        result = self.make_request(
            "POST", f"{self.base_url}/v1/messages", headers, data
        )

        if result.get("status_code") == 200:
            response_data = result.get("data", {})
            content = response_data.get("content", [{}])[0].get("text", "")
            has_tool_use = "tool_use" in content.lower()
            self.results["anthropic"]["tools"] = {
                "status": "success",
                "has_tool_use": has_tool_use,
            }
            print(f"[成功] Anthropic工具调用成功，工具使用检测: {has_tool_use}")
        else:
            error_msg = result.get("error", "Unknown error")
            status_code = result.get("status_code", 0)
            response_text = result.get("response_text", "")

            print(f"[调试] Anthropic Tools错误详情:")
            print(f"  状态码: {status_code}")
            print(f"  错误信息: {error_msg}")
            print(f"  响应内容: {response_text[:200]}...")
            print(f"  使用模型: {self.model_tools}")

            self.results["anthropic"]["tools"] = {
                "status": "failed",
                "error": f"{status_code}: {error_msg}",
            }
            print("[失败] Anthropic工具调用失败")

        return result.get("status_code") == 200

    # ===== Gemini兼容接口测试 =====

    def test_gemini_text(self):
        """Gemini - 纯文本聊天 (非流式)"""
        self.print_header("4.1: Gemini - 纯文本聊天 (非流式)")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "contents": [
                {"role": "user", "parts": [{"text": "你好，请解释一下什么是黑洞。"}]}
            ]
        }

        result = self.make_request(
            "POST",
            f"{self.base_url}/v1beta/models/{self.model_gemini}:generateContent",
            headers,
            data,
        )

        if result.get("status_code") == 200:
            response_data = result.get("data", {})
            candidates = response_data.get("candidates", [])
            if candidates:
                content = (
                    candidates[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
                self.results["gemini"]["text"] = {
                    "status": "success",
                    "content": content[:50] + "...",
                }
                print(f"[成功] Gemini文本聊天成功: {content[:50]}...")
            else:
                self.results["gemini"]["text"] = {
                    "status": "failed",
                    "error": "No candidates in response",
                }
                print("[失败] Gemini文本聊天失败: 无候选结果")
        else:
            self.results["gemini"]["text"] = {
                "status": "failed",
                "error": result.get("error", "Unknown error"),
            }
            print("[失败] Gemini文本聊天失败")

        return result.get("status_code") == 200

    def test_gemini_streaming(self):
        """Gemini - 纯文本聊天 (流式)"""
        self.print_header("4.2: Gemini - 纯文本聊天 (流式)")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "请写一个关于太空探险的简短故事开头。"}],
                }
            ]
        }

        result = self.make_request(
            "POST",
            f"{self.base_url}/v1beta/models/{self.model_gemini}:streamGenerateContent",
            headers,
            data,
            stream=True,
        )

        if result.get("status_code") == 200:
            chunks = result.get("chunks", [])
            content_chunks = [chunk for chunk in chunks if "candidates" in chunk]
            self.results["gemini"]["streaming"] = {
                "status": "success",
                "chunks": len(content_chunks),
            }
            print(f"[成功] Gemini流式聊天成功，接收 {len(content_chunks)} 个内容块")
        else:
            self.results["gemini"]["streaming"] = {
                "status": "failed",
                "error": result.get("error", "Unknown error"),
            }
            print("[失败] Gemini流式聊天失败")

        return result.get("status_code") == 200

    def test_gemini_vision(self):
        """Gemini - 多模态 (图片) 聊天"""
        self.print_header("4.3: Gemini - 多模态 (图片) 聊天")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "contents": [
                {
                    "parts": [
                        {"text": "Describe this image."},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": self.base64_image,
                            }
                        },
                    ]
                }
            ]
        }

        result = self.make_request(
            "POST",
            f"{self.base_url}/v1beta/models/{self.model_gemini}:generateContent",
            headers,
            data,
        )

        if result.get("status_code") == 200:
            response_data = result.get("data", {})
            candidates = response_data.get("candidates", [])
            if candidates:
                content = (
                    candidates[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
                self.results["gemini"]["vision"] = {
                    "status": "success",
                    "content": content[:50] + "...",
                }
                print(f"[成功] Gemini多模态聊天成功: {content[:50]}...")
            else:
                self.results["gemini"]["vision"] = {
                    "status": "failed",
                    "error": "No candidates in response",
                }
                print("[失败] Gemini多模态聊天失败: 无候选结果")
        else:
            error_msg = result.get("error", "Unknown error")
            status_code = result.get("status_code", 0)
            response_text = result.get("response_text", "")

            print(f"[调试] Gemini Vision错误详情:")
            print(f"  状态码: {status_code}")
            print(f"  错误信息: {error_msg}")
            print(f"  响应内容: {response_text[:200]}...")
            print(f"  使用模型: {self.model_gemini}")
            print(f"  请求URL: /v1beta/models/{self.model_gemini}:generateContent")

            if "No available channels" in error_msg or "vision" in error_msg.lower():
                self.results["gemini"]["vision"] = {
                    "status": "failed",
                    "error": "Vision capability not available in current channels",
                }
                print("[跳过] Gemini多模态聊天 - 渠道不支持vision功能")
            else:
                self.results["gemini"]["vision"] = {
                    "status": "failed",
                    "error": f"{status_code}: {error_msg}",
                }
                print("[失败] Gemini多模态聊天失败")

        return result.get("status_code") == 200

    def test_gemini_tools(self):
        """Gemini - 工具调用 (Tools)"""
        self.print_header("4.4: Gemini - 工具调用 (Tools)")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "我应该给我的朋友发什么短信祝他生日快乐？"}],
                }
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
                                    "recipient_name": {
                                        "type": "STRING",
                                        "description": "收信人的名字",
                                    }
                                },
                            },
                        }
                    ]
                }
            ],
        }

        result = self.make_request(
            "POST",
            f"{self.base_url}/v1beta/models/{self.model_tools}:generateContent",
            headers,
            data,
        )

        if result.get("status_code") == 200:
            response_data = result.get("data", {})
            candidates = response_data.get("candidates", [])
            if candidates:
                finish_reason = candidates[0].get("finishReason", "")
                tool_called = finish_reason in ["tool_calls", "stop"]
                self.results["gemini"]["tools"] = {
                    "status": "success",
                    "tool_called": tool_called,
                    "finish_reason": finish_reason,
                }
                print(
                    f"[成功] Gemini工具调用成功，工具调用检测: {tool_called} (原因: {finish_reason})"
                )
            else:
                self.results["gemini"]["tools"] = {
                    "status": "failed",
                    "error": "No candidates in response",
                }
                print("[失败] Gemini工具调用失败: 无候选结果")
        else:
            self.results["gemini"]["tools"] = {
                "status": "failed",
                "error": result.get("error", "Unknown error"),
            }
            print("[失败] Gemini工具调用失败")

        return result.get("status_code") == 200

    def run_all_tests(self):
        """运行所有测试"""
        print("Smart AI Router 专业统一API测试")
        print("=" * 80)
        print(f"测试服务器: {self.base_url}")
        print(f"API密钥: {self.api_key}")
        print("=" * 80)

        # 运行所有测试
        start_time = time.time()

        # 基础接口测试
        basic_tests = [
            ("根路径", self.test_basic_root),
            ("健康检查", self.test_basic_health),
            ("模型列表", self.test_basic_models),
        ]

        for test_name, test_func in basic_tests:
            try:
                test_func()
            except Exception as e:
                print(f"[失败] {test_name}测试异常: {e}")

        # OpenAI兼容接口测试
        openai_tests = [
            ("文本聊天", self.test_openai_text),
            ("流式聊天", self.test_openai_streaming),
            ("多模态聊天", self.test_openai_vision),
            ("工具调用", self.test_openai_tools),
        ]

        for test_name, test_func in openai_tests:
            try:
                test_func()
            except Exception as e:
                print(f"[失败] OpenAI {test_name}测试异常: {e}")

        # Anthropic兼容接口测试
        anthropic_tests = [
            ("文本聊天", self.test_anthropic_text),
            ("流式聊天", self.test_anthropic_streaming),
            ("多模态聊天", self.test_anthropic_vision),
            ("工具调用", self.test_anthropic_tools),
        ]

        for test_name, test_func in anthropic_tests:
            try:
                test_func()
            except Exception as e:
                print(f"[失败] Anthropic {test_name}测试异常: {e}")

        # Gemini兼容接口测试
        gemini_tests = [
            ("文本聊天", self.test_gemini_text),
            ("流式聊天", self.test_gemini_streaming),
            ("多模态聊天", self.test_gemini_vision),
            ("工具调用", self.test_gemini_tools),
        ]

        for test_name, test_func in gemini_tests:
            try:
                test_func()
            except Exception as e:
                print(f"[失败] Gemini {test_name}测试异常: {e}")

        elapsed = time.time() - start_time
        print(f"\n测试完成，耗时: {elapsed:.2f}秒")

        # 生成专业报告
        self.generate_professional_report()

    def generate_professional_report(self):
        """生成专业测试报告"""
        print("\n" + "=" * 80)
        print("专业测试结果报告")
        print("=" * 80)

        # 统计结果
        total_tests = 0
        passed_tests = 0

        # 基础接口结果
        print("\n[基础接口测试]")
        for test_name, result in self.results["basic"].items():
            total_tests += 1
            status = result.get("status", "unknown")
            if status == "success":
                passed_tests += 1
                print(f"  {test_name}: [成功]")
            else:
                print(f"  {test_name}: [失败] ({result.get('error', 'Unknown error')})")

        # OpenAI结果
        print("\n[OpenAI兼容接口]")
        for test_name, result in self.results["openai"].items():
            total_tests += 1
            status = result.get("status", "unknown")
            if status == "success":
                passed_tests += 1
                print(f"  {test_name}: [成功]")
            else:
                print(f"  {test_name}: [失败] ({result.get('error', 'Unknown error')})")

        # Anthropic结果
        print("\n[Anthropic兼容接口]")
        for test_name, result in self.results["anthropic"].items():
            total_tests += 1
            status = result.get("status", "unknown")
            if status == "success":
                passed_tests += 1
                print(f"  {test_name}: [成功]")
            else:
                print(f"  {test_name}: [失败] ({result.get('error', 'Unknown error')})")

        # Gemini结果
        print("\n[Gemini兼容接口]")
        for test_name, result in self.results["gemini"].items():
            total_tests += 1
            status = result.get("status", "unknown")
            if status == "success":
                passed_tests += 1
                print(f"  {test_name}: [成功]")
            else:
                print(f"  {test_name}: [失败] ({result.get('error', 'Unknown error')})")

        # 总结
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        print(f"\n总结: {passed_tests}/{total_tests} 测试通过 ({success_rate:.1f}%)")

        if success_rate >= 90:
            print("[优秀] Smart AI Router 多API兼容性测试优秀通过！")
            grade = "A"
        elif success_rate >= 80:
            print("[良好] Smart AI Router 多API兼容性测试良好通过！")
            grade = "B"
        elif success_rate >= 70:
            print("[及格] Smart AI Router 多API兼容性测试及格通过！")
            grade = "C"
        else:
            print("[不及格] Smart AI Router 多API兼容性测试不及格，需要改进！")
            grade = "D"

        # 保存详细结果
        self.results["summary"] = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "success_rate": success_rate,
            "grade": grade,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        with open("professional_api_test_results.json", "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        print(f"\n详细结果已保存到: professional_api_test_results.json")


def main():
    """主函数"""
    import sys

    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:7602"
    api_key = sys.argv[2] if len(sys.argv) > 2 else "test-key"

    tester = ProfessionalAPITester(base_url, api_key)
    tester.run_all_tests()


if __name__ == "__main__":
    main()
