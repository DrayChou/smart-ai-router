#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
成本跟踪系统使用示例
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.utils.usage_tracker import get_usage_tracker, create_usage_record
from core.utils.channel_monitor import get_channel_monitor


async def example_record_usage():
    """示例：记录使用情况"""
    print("📝 成本跟踪系统示例")
    print("=" * 50)
    
    tracker = get_usage_tracker()
    
    # 示例1: 记录一个成功的请求
    print("\n1️⃣ 记录成功请求示例:")
    usage_record = create_usage_record(
        model="gpt-4o-mini",
        channel_id="ch_openai_001",
        channel_name="OpenAI Official",
        provider="openai",
        input_tokens=150,
        output_tokens=300,
        input_cost=0.000075,  # $0.075/1M tokens * 150 tokens
        output_cost=0.0003,   # $0.30/1M tokens * 300 tokens
        request_type="chat",
        status="success",
        response_time_ms=1250,
        tags=["gpt", "4o", "mini", "chat"]
    )
    
    await tracker.record_usage_async(usage_record)
    print(f"✅ 记录成功请求: {usage_record.model} - ${usage_record.total_cost:.6f}")
    
    # 示例2: 记录一个免费模型的请求
    print("\n2️⃣ 记录免费模型请求示例:")
    free_record = create_usage_record(
        model="qwen2.5-7b-instruct",
        channel_id="ch_siliconflow_001",
        channel_name="SiliconFlow Free",
        provider="siliconflow",
        input_tokens=200,
        output_tokens=150,
        input_cost=0.0,
        output_cost=0.0,
        request_type="chat",
        status="success",
        response_time_ms=850,
        tags=["qwen", "free", "7b", "instruct"]
    )
    
    await tracker.record_usage_async(free_record)
    print(f"✅ 记录免费请求: {free_record.model} - ${free_record.total_cost:.6f}")
    
    # 示例3: 记录一个失败的请求
    print("\n3️⃣ 记录失败请求示例:")
    error_record = create_usage_record(
        model="claude-3-haiku",
        channel_id="ch_anthropic_001",
        channel_name="Anthropic Official",
        provider="anthropic",
        input_tokens=100,
        output_tokens=0,
        input_cost=0.0,
        output_cost=0.0,
        request_type="chat",
        status="error",
        error_message="API key quota exceeded",
        response_time_ms=500,
        tags=["claude", "3", "haiku", "error"]
    )
    
    await tracker.record_usage_async(error_record)
    print(f"❌ 记录失败请求: {error_record.model} - {error_record.error_message}")


def example_view_statistics():
    """示例：查看统计信息"""
    print("\n📊 统计信息查看示例")
    print("=" * 50)
    
    tracker = get_usage_tracker()
    
    # 今日统计
    daily_stats = tracker.get_daily_stats()
    print(f"\n📅 今日统计:")
    print(f"  请求总数: {daily_stats['total_requests']}")
    print(f"  成功请求: {daily_stats['successful_requests']}")
    print(f"  失败请求: {daily_stats['failed_requests']}")
    print(f"  总成本: ${daily_stats['total_cost']:.6f}")
    print(f"  总Tokens: {daily_stats['total_tokens']:,}")
    
    if daily_stats['total_requests'] > 0:
        print(f"  平均每请求成本: ${daily_stats['avg_cost_per_request']:.6f}")
        print(f"  平均每1K Tokens成本: ${daily_stats['avg_cost_per_1k_tokens']:.6f}")
    
    # 模型使用统计
    if daily_stats['models']:
        print(f"\n🤖 模型使用统计:")
        for model, stats in daily_stats['models'].items():
            print(f"  {model}: {stats['requests']} 请求, ${stats['cost']:.6f}, {stats['tokens']} tokens")
    
    # 渠道使用统计
    if daily_stats['channels']:
        print(f"\n📡 渠道使用统计:")
        for channel, stats in daily_stats['channels'].items():
            print(f"  {channel}: {stats['requests']} 请求, ${stats['cost']:.6f}")
    
    # 提供商统计
    if daily_stats['providers']:
        print(f"\n🏢 提供商统计:")
        for provider, stats in daily_stats['providers'].items():
            print(f"  {provider}: {stats['requests']} 请求, ${stats['cost']:.6f}")


def example_channel_monitoring():
    """示例：渠道监控"""
    print("\n🚨 渠道监控示例")
    print("=" * 50)
    
    monitor = get_channel_monitor()
    
    # 模拟配额用完
    print("\n1️⃣ 模拟配额用完告警:")
    monitor.record_quota_exhausted(
        "ch_openai_001",
        "OpenAI Official",
        {"remaining_requests": 0, "reset_time": "2025-08-25T00:00:00Z"}
    )
    
    # 模拟余额不足
    print("\n2️⃣ 模拟余额不足告警:")
    monitor.record_low_balance(
        "ch_anthropic_002", 
        "Anthropic Backup",
        2.50
    )
    
    # 模拟API密钥无效
    print("\n3️⃣ 模拟API密钥无效告警:")
    monitor.record_api_key_invalid(
        "ch_groq_001",
        "Groq Fast",
        {"error_code": "invalid_api_key", "last_valid": "2025-08-20"}
    )
    
    # 查看最近告警
    print("\n📋 查看最近24小时告警:")
    recent_alerts = monitor.get_recent_alerts(24)
    for alert in recent_alerts:
        print(f"  🚨 {alert.timestamp}: {alert.message}")


async def example_api_usage():
    """示例：模拟API使用场景"""
    print("\n🔄 模拟API使用场景")
    print("=" * 50)
    
    tracker = get_usage_tracker()
    
    scenarios = [
        # 场景1: 文档摘要 (中等长度输入，短输出)
        {
            "name": "文档摘要",
            "model": "gpt-4o-mini",
            "channel_id": "ch_openai_001",
            "channel_name": "OpenAI Official",
            "provider": "openai",
            "input_tokens": 2000,
            "output_tokens": 200,
            "input_cost": 0.0015,  # $0.15/1M * 2000
            "output_cost": 0.0012,  # $0.60/1M * 200
            "tags": ["document", "summary", "gpt"]
        },
        # 场景2: 代码生成 (短输入，长输出)
        {
            "name": "代码生成", 
            "model": "claude-3-haiku",
            "channel_id": "ch_anthropic_001",
            "channel_name": "Anthropic Official",
            "provider": "anthropic",
            "input_tokens": 300,
            "output_tokens": 800,
            "input_cost": 0.000075,  # $0.25/1M * 300
            "output_cost": 0.001,     # $1.25/1M * 800
            "tags": ["code", "generation", "claude"]
        },
        # 场景3: 免费模型对话
        {
            "name": "免费对话",
            "model": "qwen2.5-14b-instruct",
            "channel_id": "ch_siliconflow_002", 
            "channel_name": "SiliconFlow Pro",
            "provider": "siliconflow",
            "input_tokens": 500,
            "output_tokens": 600,
            "input_cost": 0.0,
            "output_cost": 0.0,
            "tags": ["free", "chat", "qwen", "14b"]
        },
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{i}️⃣ {scenario['name']}:")
        
        record = create_usage_record(
            model=scenario['model'],
            channel_id=scenario['channel_id'],
            channel_name=scenario['channel_name'],
            provider=scenario['provider'],
            input_tokens=scenario['input_tokens'],
            output_tokens=scenario['output_tokens'],
            input_cost=scenario['input_cost'],
            output_cost=scenario['output_cost'],
            request_type="chat",
            status="success",
            response_time_ms=1000 + i * 200,
            tags=scenario['tags']
        )
        
        await tracker.record_usage_async(record)
        total_cost = scenario['input_cost'] + scenario['output_cost']
        print(f"  💰 成本: ${total_cost:.6f} ({scenario['input_tokens']+scenario['output_tokens']} tokens)")
        
        # 短暂延迟模拟真实使用
        await asyncio.sleep(0.1)
    
    print(f"\n✅ 完成 {len(scenarios)} 个使用场景的记录")


async def main():
    """主函数"""
    print("🚀 Smart AI Router - 成本跟踪系统示例")
    print("=" * 60)
    
    # 1. 记录使用示例
    await example_record_usage()
    
    # 2. 模拟API使用场景
    await example_api_usage()
    
    # 3. 查看统计信息
    example_view_statistics()
    
    # 4. 渠道监控示例
    example_channel_monitoring()
    
    print("\n🎉 所有示例运行完成!")
    print("\n💡 提示:")
    print("  - 使用记录保存在 logs/usage_YYYYMMDD.jsonl")
    print("  - 告警记录保存在 logs/channel_alerts.jsonl")
    print("  - 运行 python scripts/archive_usage_logs.py --report 查看详细统计")
    print("  - API接口: GET /v1/stats/daily, /v1/stats/weekly, /v1/stats/monthly")


if __name__ == "__main__":
    asyncio.run(main())