#!/usr/bin/env python3
"""
Smart AI Router 统一API测试脚本
测试ChatGPT、Anthropic、Gemini三种协议的：
- 普通文本对话
- 多模态（图片）
- Tools调用
"""

import base64
import json
import time
from typing import Any, Dict, List

import requests


class UnifiedAPITester:
    """统一API测试器"""

    def __init__(self, base_url: str = "http://localhost:7602"):
        self.base_url = base_url
        self.results = {"chatgpt": {}, "anthropic": {}, "gemini": {}}

    def test_chatgpt_text(self):
        """测试ChatGPT文本对话（非流式）"""
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": "Bearer test-key",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tag:qwen,free",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 50,
                    "stream": False,
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                self.results["chatgpt"]["text"] = {
                    "status": "success",
                    "response_id": data.get("id"),
                    "model": data.get("model"),
                    "content": data["choices"][0]["message"]["content"][:50] + "...",
                }
                return True
            else:
                self.results["chatgpt"]["text"] = {
                    "status": "failed",
                    "error": f"HTTP {response.status_code}",
                }
                return False

        except Exception as e:
            self.results["chatgpt"]["text"] = {"status": "error", "error": str(e)}
            return False

    def test_chatgpt_vision(self):
        """测试ChatGPT多模态"""
        # 创建一个简单的测试图片
        image_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI/hQCKXwAAAABJRU5ErkJggg=="
        )

        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": "Bearer test-key",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tag:qwen,vl,free",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "What do you see?"},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64.b64encode(image_data).decode()}"
                                    },
                                },
                            ],
                        }
                    ],
                    "max_tokens": 50,
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                self.results["chatgpt"]["vision"] = {
                    "status": "success",
                    "response_id": data.get("id"),
                    "content": data["choices"][0]["message"]["content"][:50] + "...",
                }
                return True
            else:
                self.results["chatgpt"]["vision"] = {
                    "status": "failed",
                    "error": f"HTTP {response.status_code}",
                }
                return False

        except Exception as e:
            self.results["chatgpt"]["vision"] = {"status": "error", "error": str(e)}
            return False

    def test_chatgpt_streaming(self):
        """测试ChatGPT流式响应"""
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": "Bearer test-key",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tag:qwen,free",
                    "messages": [
                        {"role": "user", "content": "Count from 1 to 5 slowly"}
                    ],
                    "max_tokens": 100,
                    "stream": True,
                },
                timeout=30,
                stream=True,
            )

            if response.status_code == 200:
                chunks = []
                for line in response.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: ") and line != "data: [DONE]":
                            try:
                                chunk_data = json.loads(line[6:])
                                if chunk_data.get("choices"):
                                    content = chunk_data["choices"][0]["delta"].get(
                                        "content", ""
                                    )
                                    if content:
                                        chunks.append(content)
                            except:
                                continue

                self.results["chatgpt"]["streaming"] = {
                    "status": "success",
                    "chunks_received": len(chunks),
                    "total_content": "".join(chunks)[:50] + "...",
                }
                return True
            else:
                self.results["chatgpt"]["streaming"] = {
                    "status": "failed",
                    "error": f"HTTP {response.status_code}",
                }
                return False

        except Exception as e:
            self.results["chatgpt"]["streaming"] = {"status": "error", "error": str(e)}
            return False

    def test_chatgpt_tools(self):
        """测试ChatGPT Tools"""
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": "Bearer test-key",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tag:qwen3,4b,free",
                    "messages": [
                        {"role": "user", "content": "What's the weather in Beijing?"}
                    ],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "description": "Get weather for a location",
                                "parameters": {
                                    "type": "object",
                                    "properties": {"location": {"type": "string"}},
                                    "required": ["location"],
                                },
                            },
                        }
                    ],
                    "tool_choice": "auto",
                    "max_tokens": 100,
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                message = data["choices"][0]["message"]
                tool_calls = message.get("tool_calls", [])

                self.results["chatgpt"]["tools"] = {
                    "status": "success",
                    "response_id": data.get("id"),
                    "content": message.get("content", "")[:50] + "...",
                    "tool_calls": len(tool_calls),
                    "tool_names": [tc["function"]["name"] for tc in tool_calls],
                }
                return True
            else:
                self.results["chatgpt"]["tools"] = {
                    "status": "failed",
                    "error": f"HTTP {response.status_code}",
                }
                return False

        except Exception as e:
            self.results["chatgpt"]["tools"] = {"status": "error", "error": str(e)}
            return False

    def test_anthropic_text(self):
        """测试Anthropic文本对话"""
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": "test-key",
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tag:qwen,free",
                    "max_tokens": 50,
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                self.results["anthropic"]["text"] = {
                    "status": "success",
                    "message_id": data.get("id"),
                    "model": data.get("model"),
                    "content": data["content"][0]["text"][:50] + "...",
                }
                return True
            else:
                self.results["anthropic"]["text"] = {
                    "status": "failed",
                    "error": f"HTTP {response.status_code}",
                }
                return False

        except Exception as e:
            self.results["anthropic"]["text"] = {"status": "error", "error": str(e)}
            return False

    def test_anthropic_vision(self):
        """测试Anthropic多模态"""
        image_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI/hQCKXwAAAABJRU5ErkJggg=="
        )

        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": "test-key",
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tag:qwen,vl,free",
                    "max_tokens": 50,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "What do you see?"},
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": base64.b64encode(image_data).decode(),
                                    },
                                },
                            ],
                        }
                    ],
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                self.results["anthropic"]["vision"] = {
                    "status": "success",
                    "message_id": data.get("id"),
                    "content": data["content"][0]["text"][:50] + "...",
                }
                return True
            else:
                self.results["anthropic"]["vision"] = {
                    "status": "failed",
                    "error": f"HTTP {response.status_code}",
                }
                return False

        except Exception as e:
            self.results["anthropic"]["vision"] = {"status": "error", "error": str(e)}
            return False

    def test_anthropic_streaming(self):
        """测试Anthropic流式响应"""
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": "test-key",
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tag:qwen,free",
                    "max_tokens": 100,
                    "messages": [
                        {"role": "user", "content": "Count from 1 to 5 slowly"}
                    ],
                    "stream": True,
                },
                timeout=30,
                stream=True,
            )

            if response.status_code == 200:
                chunks = []
                for line in response.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            try:
                                chunk_data = json.loads(line[6:])
                                if chunk_data.get("type") == "content_block_delta":
                                    content = chunk_data.get("delta", {}).get(
                                        "text", ""
                                    )
                                    if content:
                                        chunks.append(content)
                            except:
                                continue

                self.results["anthropic"]["streaming"] = {
                    "status": "success",
                    "chunks_received": len(chunks),
                    "total_content": "".join(chunks)[:50] + "...",
                }
                return True
            else:
                self.results["anthropic"]["streaming"] = {
                    "status": "failed",
                    "error": f"HTTP {response.status_code}",
                }
                return False

        except Exception as e:
            self.results["anthropic"]["streaming"] = {
                "status": "error",
                "error": str(e),
            }
            return False

    def test_anthropic_tools(self):
        """测试Anthropic Tools"""
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": "test-key",
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tag:qwen3,4b,free",
                    "max_tokens": 100,
                    "messages": [
                        {"role": "user", "content": "What's the weather in Beijing?"}
                    ],
                    "tools": [
                        {
                            "name": "get_weather",
                            "description": "Get weather for a location",
                            "input_schema": {
                                "type": "object",
                                "properties": {"location": {"type": "string"}},
                                "required": ["location"],
                            },
                        }
                    ],
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                content = data["content"][0]["text"]

                self.results["anthropic"]["tools"] = {
                    "status": "success",
                    "message_id": data.get("id"),
                    "content": content[:50] + "...",
                    "has_tool_use": "tool_use" in content.lower(),
                }
                return True
            else:
                self.results["anthropic"]["tools"] = {
                    "status": "failed",
                    "error": f"HTTP {response.status_code}",
                }
                return False

        except Exception as e:
            self.results["anthropic"]["tools"] = {"status": "error", "error": str(e)}
            return False

    def test_gemini_text(self):
        """测试Gemini文本对话"""
        try:
            response = requests.post(
                f"{self.base_url}/v1beta/models/tag:qwen,free:generateContent",
                headers={
                    "x-goog-api-key": "test-key",
                    "Content-Type": "application/json",
                },
                json={
                    "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
                    "generationConfig": {"maxOutputTokens": 50},
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    candidate = candidates[0]
                    content = candidate["content"]["parts"][0]["text"]

                    self.results["gemini"]["text"] = {
                        "status": "success",
                        "model_version": data.get("model_version"),
                        "content": content[:50] + "...",
                    }
                    return True

            self.results["gemini"]["text"] = {
                "status": "failed",
                "error": f"HTTP {response.status_code}",
            }
            return False

        except Exception as e:
            self.results["gemini"]["text"] = {"status": "error", "error": str(e)}
            return False

    def test_gemini_vision(self):
        """测试Gemini多模态"""
        image_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI/hQCKXwAAAABJRU5ErkJggg=="
        )

        try:
            response = requests.post(
                f"{self.base_url}/v1beta/models/tag:qwen,vl,free:generateContent",
                headers={
                    "x-goog-api-key": "test-key",
                    "Content-Type": "application/json",
                },
                json={
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {"text": "What do you see?"},
                                {
                                    "inline_data": {
                                        "mime_type": "image/png",
                                        "data": base64.b64encode(image_data).decode(),
                                    }
                                },
                            ],
                        }
                    ],
                    "generationConfig": {"maxOutputTokens": 50},
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    candidate = candidates[0]
                    content = candidate["content"]["parts"][0]["text"]

                    self.results["gemini"]["vision"] = {
                        "status": "success",
                        "model_version": data.get("model_version"),
                        "content": content[:50] + "...",
                    }
                    return True

            self.results["gemini"]["vision"] = {
                "status": "failed",
                "error": f"HTTP {response.status_code}",
            }
            return False

        except Exception as e:
            self.results["gemini"]["vision"] = {"status": "error", "error": str(e)}
            return False

    def test_gemini_streaming(self):
        """测试Gemini流式响应"""
        try:
            response = requests.post(
                f"{self.base_url}/v1beta/models/tag:qwen,free:streamGenerateContent",
                headers={
                    "x-goog-api-key": "test-key",
                    "Content-Type": "application/json",
                },
                json={
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": "Count from 1 to 5 slowly"}],
                        }
                    ],
                    "generationConfig": {"maxOutputTokens": 100},
                },
                timeout=30,
                stream=True,
            )

            if response.status_code == 200:
                chunks = []
                for line in response.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            try:
                                chunk_data = json.loads(line[6:])
                                if chunk_data.get("candidates"):
                                    candidate = chunk_data["candidates"][0]
                                    content = (
                                        candidate.get("content", {})
                                        .get("parts", [{}])[0]
                                        .get("text", "")
                                    )
                                    if content:
                                        chunks.append(content)
                            except:
                                continue

                self.results["gemini"]["streaming"] = {
                    "status": "success",
                    "chunks_received": len(chunks),
                    "total_content": "".join(chunks)[:50] + "...",
                }
                return True
            else:
                self.results["gemini"]["streaming"] = {
                    "status": "failed",
                    "error": f"HTTP {response.status_code}",
                }
                return False

        except Exception as e:
            self.results["gemini"]["streaming"] = {"status": "error", "error": str(e)}
            return False

    def test_gemini_tools(self):
        """测试Gemini Tools"""
        try:
            response = requests.post(
                f"{self.base_url}/v1beta/models/tag:qwen3,4b,free:generateContent",
                headers={
                    "x-goog-api-key": "test-key",
                    "Content-Type": "application/json",
                },
                json={
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": "What's the weather in Beijing?"}],
                        }
                    ],
                    "tools": [
                        {
                            "function_declarations": [
                                {
                                    "name": "get_weather",
                                    "description": "Get weather for a location",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {"location": {"type": "string"}},
                                        "required": ["location"],
                                    },
                                }
                            ]
                        }
                    ],
                    "generationConfig": {"maxOutputTokens": 100},
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    candidate = candidates[0]
                    content = candidate["content"]["parts"][0]["text"]
                    finish_reason = candidate.get("finishReason", "")

                    self.results["gemini"]["tools"] = {
                        "status": "success",
                        "model_version": data.get("model_version"),
                        "content": content[:50] + "...",
                        "finish_reason": finish_reason,
                        "tool_called": finish_reason in ["tool_calls", "stop"],
                    }
                    return True

            self.results["gemini"]["tools"] = {
                "status": "failed",
                "error": f"HTTP {response.status_code}",
            }
            return False

        except Exception as e:
            self.results["gemini"]["tools"] = {"status": "error", "error": str(e)}
            return False

    def run_all_tests(self):
        """运行所有测试"""
        print("Smart AI Router 统一API测试")
        print("=" * 60)

        # 运行所有测试
        start_time = time.time()

        tests = [
            ("ChatGPT文本", self.test_chatgpt_text),
            ("ChatGPT流式", self.test_chatgpt_streaming),
            ("ChatGPT多模态", self.test_chatgpt_vision),
            ("ChatGPT Tools", self.test_chatgpt_tools),
            ("Anthropic文本", self.test_anthropic_text),
            ("Anthropic流式", self.test_anthropic_streaming),
            ("Anthropic多模态", self.test_anthropic_vision),
            ("Anthropic Tools", self.test_anthropic_tools),
            ("Gemini文本", self.test_gemini_text),
            ("Gemini流式", self.test_gemini_streaming),
            ("Gemini多模态", self.test_gemini_vision),
            ("Gemini Tools", self.test_gemini_tools),
        ]

        for test_name, test_func in tests:
            print(f"测试 {test_name}...")
            try:
                test_func()
            except Exception as e:
                print(f"  错误: {e}")

        elapsed = time.time() - start_time
        print(f"\n测试完成，耗时: {elapsed:.2f}秒")

        # 生成报告
        self.generate_report()

    def generate_report(self):
        """生成测试报告"""
        print("\n" + "=" * 60)
        print("测试结果报告")
        print("=" * 60)

        # 统计结果
        total_tests = 0
        passed_tests = 0

        # ChatGPT结果
        print("\n[ChatGPT API]")
        for test_name, result in self.results["chatgpt"].items():
            total_tests += 1
            status = result.get("status", "unknown")
            if status == "success":
                passed_tests += 1
                print(f"  {test_name}: [成功]")
            else:
                print(f"  {test_name}: [失败] ({result.get('error', 'Unknown error')})")

        # Anthropic结果
        print("\n[Anthropic API]")
        for test_name, result in self.results["anthropic"].items():
            total_tests += 1
            status = result.get("status", "unknown")
            if status == "success":
                passed_tests += 1
                print(f"  {test_name}: [成功]")
            else:
                print(f"  {test_name}: [失败] ({result.get('error', 'Unknown error')})")

        # Gemini结果
        print("\n[Gemini API]")
        for test_name, result in self.results["gemini"].items():
            total_tests += 1
            status = result.get("status", "unknown")
            if status == "success":
                passed_tests += 1
                print(f"  {test_name}: [成功]")
            else:
                print(f"  {test_name}: [失败] ({result.get('error', 'Unknown error')})")

        # 总结
        print(
            f"\n总结: {passed_tests}/{total_tests} 测试通过 ({passed_tests/total_tests*100:.1f}%)"
        )

        if passed_tests >= total_tests * 0.8:
            print("[成功] Smart AI Router 多API兼容性测试通过！")
        else:
            print("[警告] 部分测试失败，需要进一步检查")

        # 保存详细结果
        with open("api_test_results.json", "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        print(f"\n详细结果已保存到: api_test_results.json")


def main():
    """主函数"""
    import sys

    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:7602"

    tester = UnifiedAPITester(base_url)
    tester.run_all_tests()


if __name__ == "__main__":
    main()
