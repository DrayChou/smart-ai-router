#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token预估和模型优化功能演示
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.utils.token_estimator import get_token_estimator, get_model_optimizer, TaskComplexity
from core.utils.api_key_cache_manager import get_api_key_cache_manager
from core.yaml_config import get_yaml_config_loader

def demo_token_estimation():
    """演示Token预估功能"""
    print("🧠 Token预估功能演示")
    print("=" * 50)
    
    estimator = get_token_estimator()
    
    # 测试不同复杂度的任务
    test_cases = [
        {
            "name": "简单对话",
            "messages": [
                {"role": "user", "content": "你好，今天天气怎么样？"}
            ]
        },
        {
            "name": "文档总结",
            "messages": [
                {"role": "user", "content": "请帮我总结以下文档的主要内容：这是一份关于人工智能发展历程的长篇文档，包含了从图灵测试到现代大语言模型的完整发展历程..."}
            ]
        },
        {
            "name": "代码生成",
            "messages": [
                {"role": "user", "content": "请帮我写一个Python函数，实现二叉搜索树的插入、删除和查找操作，要求代码要有详细注释并且包含单元测试。"}
            ]
        },
        {
            "name": "专家级分析",
            "messages": [
                {"role": "user", "content": "请从技术架构、市场前景、商业模式、竞争分析等多个维度，深入分析ChatGPT对整个AI行业的影响，并提出未来5年的发展预测。要求分析深入、逻辑清晰、数据支撑。"}
            ]
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n{i}. {case['name']}")
        print("-" * 30)
        
        # 执行Token预估
        estimate = estimator.estimate_tokens(case['messages'])
        
        print(f"📊 输入Tokens: {estimate.input_tokens}")
        print(f"📊 预估输出Tokens: {estimate.estimated_output_tokens}")
        print(f"📊 总计Tokens: {estimate.total_tokens}")
        print(f"📊 任务复杂度: {estimate.task_complexity.value.upper()}")
        print(f"📊 预估置信度: {estimate.confidence:.1%}")
        
        # 根据复杂度给出建议
        complexity_advice = {
            TaskComplexity.SIMPLE: "建议使用轻量级模型，如GPT-3.5或小参数量模型",
            TaskComplexity.MODERATE: "建议使用中等规模模型，平衡质量和成本",
            TaskComplexity.COMPLEX: "建议使用高性能模型，如GPT-4或大参数量模型",
            TaskComplexity.EXPERT: "强烈建议使用顶级模型，确保输出质量"
        }
        print(f"💡 使用建议: {complexity_advice[estimate.task_complexity]}")

def demo_model_optimization():
    """演示模型优化功能"""
    print("\n\n🎯 模型优化功能演示")
    print("=" * 50)
    
    optimizer = get_model_optimizer()
    estimator = get_token_estimator()
    
    # 模拟一个中等复杂度的任务
    messages = [
        {"role": "user", "content": "请帮我写一篇关于Python装饰器的技术博客，包含基本概念、使用场景和代码示例。"}
    ]
    
    token_estimate = estimator.estimate_tokens(messages)
    print(f"📊 Token预估: {token_estimate.total_tokens} tokens ({token_estimate.task_complexity.value})")
    
    # 模拟可用渠道
    mock_channels = [
        {
            'id': 'ch_gpt4o_mini',
            'model_name': 'gpt-4o-mini',
            'provider': 'openai',
            'input_price': 0.15,  # $0.15/1M tokens
            'output_price': 0.60,  # $0.60/1M tokens
        },
        {
            'id': 'ch_gpt4',
            'model_name': 'gpt-4',
            'provider': 'openai',
            'input_price': 30.0,  # $30/1M tokens
            'output_price': 60.0,  # $60/1M tokens
        },
        {
            'id': 'ch_claude_haiku',
            'model_name': 'claude-3-haiku',
            'provider': 'anthropic',
            'input_price': 0.25,  # $0.25/1M tokens
            'output_price': 1.25,  # $1.25/1M tokens
        },
        {
            'id': 'ch_llama_free',
            'model_name': 'llama-3.1-8b',
            'provider': 'groq',
            'input_price': 0.0,   # 免费
            'output_price': 0.0,  # 免费
        },
        {
            'id': 'ch_qwen_free',
            'model_name': 'qwen2.5-7b',
            'provider': 'siliconflow',
            'input_price': 0.0,   # 免费
            'output_price': 0.0,  # 免费
        }
    ]
    
    # 测试不同优化策略
    strategies = ['cost_first', 'quality_first', 'speed_first', 'balanced']
    
    for strategy in strategies:
        print(f"\n📈 {strategy.upper()} 策略推荐:")
        print("-" * 25)
        
        recommendations = optimizer.recommend_models(
            token_estimate, mock_channels, strategy
        )
        
        for i, rec in enumerate(recommendations[:3], 1):
            cost_str = f"${rec.estimated_cost:.6f}" if rec.estimated_cost > 0 else "免费"
            print(f"  {i}. {rec.model_name}")
            print(f"     💰 预估成本: {cost_str}")
            print(f"     ⏱️  预估时间: {rec.estimated_time:.1f}秒")
            print(f"     ⭐ 质量评分: {rec.quality_score:.2f}")
            print(f"     📝 推荐理由: {rec.reason}")
            print()

def demo_api_key_cache():
    """演示API Key级别缓存功能"""
    print("\n\n🔑 API Key级别缓存演示")
    print("=" * 50)
    
    cache_manager = get_api_key_cache_manager()
    
    # 模拟不同API Key的模型发现数据
    test_data = [
        {
            'channel_id': 'ch_openrouter_001',
            'api_key': 'demo-free-user-key-123',
            'provider': 'openrouter',
            'models_data': {
                'models': [
                    'mistralai/mistral-7b-instruct:free',
                    'meta-llama/llama-3-8b-instruct:free',
                    'google/gemma-7b-it:free'
                ],
                'response_data': {'data': []}
            }
        },
        {
            'channel_id': 'ch_openrouter_001', 
            'api_key': 'demo-pro-user-key-456',
            'provider': 'openrouter',
            'models_data': {
                'models': [
                    'mistralai/mistral-7b-instruct:free',
                    'meta-llama/llama-3-8b-instruct:free', 
                    'google/gemma-7b-it:free',
                    'openai/gpt-4o-mini',
                    'anthropic/claude-3-haiku',
                    'openai/gpt-4o'
                ],
                'response_data': {'data': []}
            }
        }
    ]
    
    # 保存不同API Key的缓存
    for data in test_data:
        cache_manager.save_api_key_models(
            data['channel_id'],
            data['api_key'],
            data['models_data'],
            data['provider']
        )
    
    print("✅ 已保存API Key级别缓存数据")
    
    # 验证缓存数据
    print("\n🔍 验证缓存数据:")
    for data in test_data:
        cached_data = cache_manager.load_api_key_models(
            data['channel_id'],
            data['api_key']
        )
        
        if cached_data:
            user_type = "免费用户" if len(cached_data['models']) <= 3 else "付费用户"
            api_key_preview = data['api_key'][:8] + "..."
            print(f"  📋 {api_key_preview} ({user_type}): {len(cached_data['models'])} 个模型")
            print(f"     可用模型: {list(cached_data['models'].keys())[:3]}...")
        else:
            print(f"  ❌ API Key {data['api_key'][:8]}... 缓存加载失败")
    
    # 显示缓存统计
    stats = cache_manager.get_cache_stats()
    print(f"\n📊 缓存统计:")
    print(f"  总缓存文件: {stats['total_cache_files']}")
    print(f"  内存条目: {stats['memory_entries']}")
    print(f"  有效内存条目: {stats['valid_memory_entries']}")
    print(f"  缓存命中率: {stats['cache_hit_rate']:.1%}")

async def demo_integration():
    """演示集成使用场景"""
    print("\n\n🚀 集成使用场景演示")
    print("=" * 50)
    
    try:
        # 尝试加载配置
        config_loader = get_yaml_config_loader()
        channels = config_loader.get_enabled_channels()
        
        print(f"📊 系统状态:")
        print(f"  可用渠道: {len(channels)}")
        
        # 模拟一个实际的API请求优化过程
        print(f"\n💡 智能路由建议:")
        print(f"  1. 对于简单对话，推荐使用免费模型（如Groq Llama3-8B）")
        print(f"  2. 对于文档分析，推荐使用性价比模型（如GPT-4O-Mini）")
        print(f"  3. 对于代码生成，推荐使用专业模型（如Claude-3-Haiku）")
        print(f"  4. 对于复杂分析，推荐使用顶级模型（如GPT-4）")
        
    except Exception as e:
        print(f"⚠️  配置加载失败: {e}")
        print("这是正常的，因为演示环境可能没有完整配置")

def main():
    """主函数"""
    print("🚀 Smart AI Router - Token预估和API Key级别缓存演示")
    print("=" * 60)
    
    try:
        # 1. Token预估演示
        demo_token_estimation()
        
        # 2. 模型优化演示
        demo_model_optimization()
        
        # 3. API Key缓存演示
        demo_api_key_cache()
        
        # 4. 集成演示
        asyncio.run(demo_integration())
        
        print("\n\n🎉 演示完成!")
        print("\n💡 使用提示:")
        print("  • Token预估可以帮助选择合适的模型和max_tokens设置")
        print("  • 模型优化可以根据任务类型推荐最佳模型")
        print("  • API Key级别缓存解决了不同用户级别的定价差异问题")
        print("  • 新的API端点: /v1/token/estimate, /v1/token/pricing 等")
        
    except KeyboardInterrupt:
        print("\n👋 演示被用户中断")
    except Exception as e:
        print(f"\n❌ 演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()