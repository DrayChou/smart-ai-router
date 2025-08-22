#!/usr/bin/env python3
"""
Anthropic Claude API 使用示例
演示如何在Smart AI Router中使用Anthropic Claude API
"""

import asyncio
import json
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.providers.adapters.anthropic import AnthropicAdapter
from core.providers.base import ChatRequest
from core.yaml_config import YAMLConfigLoader


async def basic_chat_example():
    """基本对话示例"""
    print("=== 基本对话示例 ===")
    
    # 创建适配器
    config_loader = YAMLConfigLoader()
    anthropic_config = config_loader.config.providers['anthropic']
    adapter = AnthropicAdapter("anthropic", anthropic_config.__dict__)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("请设置 ANTHROPIC_API_KEY 环境变量")
        return
    
    # 创建请求
    request = ChatRequest(
        model="claude-3-5-haiku-20241022",
        messages=[
            {"role": "user", "content": "你好，请简单介绍一下Claude 3.5"}
        ],
        max_tokens=150,
        temperature=0.7
    )
    
    # 发送请求
    response = await adapter.chat_completions(request, api_key)
    
    print(f"模型: {response.model}")
    print(f"回复: {response.content}")
    print(f"使用token: {response.usage}")
    print()


async def streaming_chat_example():
    """流式对话示例"""
    print("=== 流式对话示例 ===")
    
    # 创建适配器
    config_loader = YAMLConfigLoader()
    anthropic_config = config_loader.config.providers['anthropic']
    adapter = AnthropicAdapter("anthropic", anthropic_config.__dict__)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("请设置 ANTHROPIC_API_KEY 环境变量")
        return
    
    # 创建流式请求
    request = ChatRequest(
        model="claude-3-5-haiku-20241022",
        messages=[
            {"role": "user", "content": "请写一首关于AI的短诗"}
        ],
        max_tokens=100,
        temperature=0.8,
        stream=True
    )
    
    print("流式回复: ", end="")
    async for chunk in adapter.chat_completions_stream(request, api_key):
        print(chunk, end="", flush=True)
    print("\n")


async def system_prompt_example():
    """系统提示示例"""
    print("=== 系统提示示例 ===")
    
    # 创建适配器
    config_loader = YAMLConfigLoader()
    anthropic_config = config_loader.config.providers['anthropic']
    adapter = AnthropicAdapter("anthropic", anthropic_config.__dict__)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("请设置 ANTHROPIC_API_KEY 环境变量")
        return
    
    # 创建带系统提示的请求
    request = ChatRequest(
        model="claude-3-5-haiku-20241022",
        messages=[
            {"role": "user", "content": "什么是深度学习？"}
        ],
        system="你是一个专业的AI教育助手，请用简单易懂的语言解释复杂概念。",
        max_tokens=200,
        temperature=0.5
    )
    
    # 发送请求
    response = await adapter.chat_completions(request, api_key)
    
    print(f"系统提示: 你是一个专业的AI教育助手")
    print(f"用户问题: 什么是深度学习？")
    print(f"Claude回复: {response.content}")
    print()


async def tool_calling_example():
    """工具调用示例（如果需要）"""
    print("=== 工具调用示例 ===")
    
    # 创建适配器
    config_loader = YAMLConfigLoader()
    anthropic_config = config_loader.config.providers['anthropic']
    adapter = AnthropicAdapter("anthropic", anthropic_config.__dict__)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("请设置 ANTHROPIC_API_KEY 环境变量")
        return
    
    # 定义工具
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取指定城市的天气信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名称"
                        }
                    },
                    "required": ["city"]
                }
            }
        }
    ]
    
    # 创建带工具的请求
    request = ChatRequest(
        model="claude-3-5-sonnet-20241022",
        messages=[
            {"role": "user", "content": "北京今天的天气怎么样？"}
        ],
        tools=tools,
        max_tokens=100,
        temperature=0.7
    )
    
    # 发送请求
    response = await adapter.chat_completions(request, api_key)
    
    print(f"用户问题: 北京今天的天气怎么样？")
    print(f"Claude回复: {response.content}")
    
    if response.tools_called:
        print(f"工具调用: {json.dumps(response.tools_called, indent=2, ensure_ascii=False)}")
    print()


async def model_info_example():
    """模型信息示例"""
    print("=== 模型信息示例 ===")
    
    # 创建适配器
    config_loader = YAMLConfigLoader()
    anthropic_config = config_loader.config.providers['anthropic']
    adapter = AnthropicAdapter("anthropic", anthropic_config.__dict__)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("请设置 ANTHROPIC_API_KEY 环境变量")
        return
    
    # 获取模型列表
    models = await adapter.list_models(api_key)
    
    print("可用的Claude模型:")
    for model in models:
        print(f"- {model.id}")
        print(f"  名称: {model.name}")
        print(f"  上下文长度: {model.context_length}")
        print(f"  能力: {', '.join(model.capabilities)}")
        print(f"  输入成本: ${model.input_cost_per_1k}/1K tokens")
        print(f"  输出成本: ${model.output_cost_per_1k}/1K tokens")
        print(f"  速度评分: {model.speed_score}")
        print(f"  质量评分: {model.quality_score}")
        print()


async def main():
    """主函数"""
    print("Anthropic Claude API 使用示例")
    print("=" * 50)
    
    # 检查API密钥
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️  请设置 ANTHROPIC_API_KEY 环境变量")
        print("   export ANTHROPIC_API_KEY=your_api_key_here")
        return
    
    try:
        # 运行示例
        await model_info_example()
        await basic_chat_example()
        await streaming_chat_example()
        await system_prompt_example()
        await tool_calling_example()
        
        print("✅ 所有示例运行完成")
        
    except Exception as e:
        print(f"❌ 运行示例时出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())