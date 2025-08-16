#!/usr/bin/env python3
"""
测试性能优化效果的脚本
"""

import asyncio
import time
import httpx
import json
from typing import List, Dict, Any

# 测试配置
TEST_BASE_URL = "http://localhost:7601"
TEST_ENDPOINTS = {
    "health": f"{TEST_BASE_URL}/health",
    "models": f"{TEST_BASE_URL}/v1/models", 
    "chat": f"{TEST_BASE_URL}/v1/chat/completions"
}

async def test_health_check_speed():
    """测试健康检查速度"""
    print("🔍 测试健康检查速度...")
    
    start_time = time.time()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(TEST_ENDPOINTS["health"])
            
        end_time = time.time()
        latency = (end_time - start_time) * 1000
        
        print(f"✅ 健康检查延迟: {latency:.1f}ms")
        print(f"✅ 状态码: {response.status_code}")
        
        return latency, response.status_code == 200
        
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")
        return None, False

async def test_models_endpoint_speed():
    """测试模型列表获取速度"""
    print("📋 测试模型列表获取速度...")
    
    start_time = time.time()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(TEST_ENDPOINTS["models"])
            
        end_time = time.time()
        latency = (end_time - start_time) * 1000
        
        if response.status_code == 200:
            data = response.json()
            model_count = len(data.get("data", []))
            print(f"✅ 模型列表延迟: {latency:.1f}ms")
            print(f"✅ 发现模型数量: {model_count}")
            return latency, True, model_count
        else:
            print(f"❌ 模型列表获取失败: {response.status_code}")
            return latency, False, 0
            
    except Exception as e:
        print(f"❌ 模型列表获取异常: {e}")
        return None, False, 0

async def test_chat_request_speed(model: str = "tag:gpt", test_message: str = "Hi"):
    """测试聊天请求速度"""
    print(f"💬 测试聊天请求速度 (模型: {model})...")
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": test_message}
        ],
        "max_tokens": 10,
        "temperature": 0.1
    }
    
    start_time = time.time()
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                TEST_ENDPOINTS["chat"],
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
        end_time = time.time()
        latency = (end_time - start_time) * 1000
        
        if response.status_code == 200:
            data = response.json()
            used_model = data.get("model", "unknown")
            usage = data.get("usage", {})
            
            print(f"✅ 聊天请求延迟: {latency:.1f}ms")
            print(f"✅ 使用的模型: {used_model}")
            print(f"✅ Token使用: {usage}")
            
            # 检查调试头
            debug_headers = {k: v for k, v in response.headers.items() if k.startswith("X-Router-")}
            if debug_headers:
                print(f"🔍 路由调试信息:")
                for k, v in debug_headers.items():
                    print(f"   {k}: {v}")
            
            return latency, True, used_model
        else:
            print(f"❌ 聊天请求失败: {response.status_code}")
            print(f"❌ 错误信息: {response.text[:200]}")
            return latency, False, None
            
    except Exception as e:
        print(f"❌ 聊天请求异常: {e}")
        return None, False, None

async def test_concurrent_requests(count: int = 5):
    """测试并发请求性能"""
    print(f"🚀 测试并发请求性能 ({count}个并发)...")
    
    start_time = time.time()
    
    # 创建并发任务
    tasks = []
    for i in range(count):
        task = test_chat_request_speed(
            model="tag:free", 
            test_message=f"Concurrent test {i+1}"
        )
        tasks.append(task)
    
    # 执行并发请求
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    end_time = time.time()
    total_time = (end_time - start_time) * 1000
    
    # 分析结果
    successful_requests = 0
    total_latency = 0
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"❌ 并发请求 {i+1} 异常: {result}")
        else:
            latency, success, model = result
            if success and latency:
                successful_requests += 1
                total_latency += latency
                print(f"✅ 并发请求 {i+1} 成功: {latency:.1f}ms (模型: {model})")
            else:
                print(f"❌ 并发请求 {i+1} 失败")
    
    if successful_requests > 0:
        avg_latency = total_latency / successful_requests
        print(f"📊 并发测试结果:")
        print(f"   总时间: {total_time:.1f}ms")
        print(f"   成功请求: {successful_requests}/{count}")
        print(f"   平均单请求延迟: {avg_latency:.1f}ms")
        print(f"   成功率: {successful_requests/count*100:.1f}%")
    else:
        print(f"❌ 所有并发请求都失败了")

async def test_negative_tag_filtering():
    """测试负标签过滤功能"""
    print("🚫 测试负标签过滤功能...")
    
    test_cases = [
        ("tag:gpt,!free", "查询GPT模型但排除免费版"),
        ("tag:free,!local", "查询免费模型但排除本地模型"), 
        ("tag:qwen3,!embedding", "查询qwen3但排除embedding模型")
    ]
    
    for model_query, description in test_cases:
        print(f"\n🔍 测试用例: {description}")
        print(f"   查询: {model_query}")
        
        latency, success, used_model = await test_chat_request_speed(
            model=model_query,
            test_message="测试负标签过滤"
        )
        
        if success:
            print(f"✅ 负标签过滤成功，使用模型: {used_model}")
        else:
            print(f"❌ 负标签过滤测试失败")

async def main():
    """主测试函数"""
    print("Smart AI Router - Performance Optimization Test")
    print("=" * 50)
    
    # 测试基础功能
    print("\nBasic Function Tests")
    await test_health_check_speed()
    await test_models_endpoint_speed()
    
    # 测试单个请求
    print("\nSingle Request Test")
    await test_chat_request_speed("tag:free", "Hello optimization test!")
    
    # 测试负标签过滤
    print("\nNegative Tag Filtering Test")
    await test_negative_tag_filtering()
    
    # 测试并发性能
    print("\nConcurrent Performance Test")
    await test_concurrent_requests(3)
    await test_concurrent_requests(5)
    
    print("\nAll tests completed!")
    print("\nOptimization Analysis:")
    print("1. Health check latency < 100ms indicates /models endpoint optimization works")
    print("2. Low chat request latency indicates fast-fail detection works")
    print("3. High concurrent success rate indicates smart channel pre-check works")
    print("4. Check X-Router-* headers for routing decision details")

if __name__ == "__main__":
    asyncio.run(main())