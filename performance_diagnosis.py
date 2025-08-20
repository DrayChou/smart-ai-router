#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能诊断工具 - 分析Smart AI Router的性能瓶颈
"""

import asyncio
import time
import sys
from pathlib import Path
# import psutil  # 可选依赖
import logging

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

# 设置日志级别为WARNING以减少输出噪音
logging.getLogger().setLevel(logging.WARNING)

async def measure_startup_time():
    """测量启动时间"""
    print("=== 启动时间分析 ===")
    
    # 1. 导入核心模块
    start = time.time()
    from core.yaml_config import get_yaml_config_loader
    import_time = time.time() - start
    print(f"导入配置模块: {import_time*1000:.1f}ms")
    
    # 2. 初始化配置加载器
    start = time.time()
    config_loader = get_yaml_config_loader()
    config_init_time = time.time() - start
    print(f"配置加载器初始化: {config_init_time*1000:.1f}ms")
    
    # 3. 加载配置
    start = time.time()
    config = config_loader.config
    config_load_time = time.time() - start
    print(f"配置文件加载: {config_load_time*1000:.1f}ms")
    
    # 4. 初始化路由器
    start = time.time()
    from core.json_router import JSONRouter
    router = JSONRouter()
    router_init_time = time.time() - start
    print(f"路由器初始化: {router_init_time*1000:.1f}ms")
    
    total_startup = import_time + config_init_time + config_load_time + router_init_time
    print(f"总启动时间: {total_startup*1000:.1f}ms")
    
    return router

async def measure_routing_performance(router):
    """测量路由性能"""
    print("\n=== 路由性能分析 ===")
    
    from core.json_router import RoutingRequest
    
    # 简单请求
    simple_request = RoutingRequest(
        model="tag:test",
        messages=[{"role": "user", "content": "Hello"}],
        data={"model": "tag:test", "messages": [{"role": "user", "content": "Hello"}]}
    )
    
    # 第一次路由（冷启动）
    start = time.time()
    candidates1 = await router.route_request(simple_request)
    first_route_time = time.time() - start
    print(f"首次路由请求: {first_route_time*1000:.1f}ms (找到 {len(candidates1)} 个候选)")
    
    # 第二次路由（缓存命中）
    start = time.time()
    candidates2 = await router.route_request(simple_request)
    second_route_time = time.time() - start
    print(f"第二次路由请求: {second_route_time*1000:.1f}ms (找到 {len(candidates2)} 个候选)")
    
    # 复杂请求（带vision）
    vision_request = RoutingRequest(
        model="tag:vision",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What's in this image?"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,test"}}
                ]
            }
        ],
        data={
            "model": "tag:vision",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's in this image?"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,test"}}
                    ]
                }
            ]
        }
    )
    
    start = time.time()
    vision_candidates = await router.route_request(vision_request)
    vision_route_time = time.time() - start
    print(f"视觉请求路由: {vision_route_time*1000:.1f}ms (找到 {len(vision_candidates)} 个候选)")

async def measure_capability_detection():
    """测量能力检测性能"""
    print("\n=== 能力检测性能分析 ===")
    
    from core.utils.capability_mapper import get_capability_mapper
    from core.utils.local_model_capabilities import get_capability_detector
    
    # 能力映射器性能
    start = time.time()
    mapper = get_capability_mapper()
    mapper_init_time = time.time() - start
    print(f"能力映射器初始化: {mapper_init_time*1000:.1f}ms")
    
    # 批量能力预测
    start = time.time()
    test_models = [("gpt-4o", "openai"), ("llama2", "ollama")] * 50
    for model, provider in test_models:
        capabilities = mapper.predict_capabilities(model, provider)
    batch_predict_time = time.time() - start
    print(f"100次能力预测: {batch_predict_time*1000:.1f}ms")
    
    # 请求分析
    test_request = {
        "model": "test",
        "messages": [{"role": "user", "content": "Hello"}]
    }
    
    start = time.time()
    for _ in range(100):
        requirements = mapper.get_capability_requirements(test_request)
    analyze_time = time.time() - start
    print(f"100次请求分析: {analyze_time*1000:.1f}ms")

async def measure_cache_performance():
    """测量缓存性能"""
    print("\n=== 缓存性能分析 ===")
    
    from core.utils.api_key_cache import get_api_key_cache_manager
    
    start = time.time()
    cache_manager = get_api_key_cache_manager()
    cache_init_time = time.time() - start
    print(f"缓存管理器初始化: {cache_init_time*1000:.1f}ms")
    
    # 缓存键生成性能
    start = time.time()
    for i in range(1000):
        cache_key = cache_manager.generate_cache_key(f"channel_{i}", f"sk-key-{i}")
    keygen_time = time.time() - start
    print(f"1000次缓存键生成: {keygen_time*1000:.1f}ms")

def measure_system_resources():
    """测量系统资源使用"""
    print("\n=== 系统资源分析 ===")
    
    try:
        import psutil
        process = psutil.Process()
        print(f"内存使用: {process.memory_info().rss / 1024 / 1024:.1f}MB")
        print(f"CPU使用: {process.cpu_percent()}%")
        print(f"线程数: {process.num_threads()}")
    except ImportError:
        print("psutil未安装，跳过系统资源监控")

async def measure_real_request_simulation():
    """模拟真实请求的完整流程"""
    print("\n=== 真实请求模拟 ===")
    
    try:
        # 模拟HTTP请求处理
        from core.handlers.chat_handler import ChatCompletionHandler
        
        start = time.time()
        handler = ChatCompletionHandler()
        handler_init_time = time.time() - start
        print(f"处理器初始化: {handler_init_time*1000:.1f}ms")
        
        # 创建模拟请求 - 使用字典而不是Pydantic模型
        request_data = {
            "model": "tag:gpt",
            "messages": [{"role": "user", "content": "Hello, how are you?"}]
        }
        
        start = time.time()
        try:
            # 只测试路由部分，不做实际API调用
            from core.json_router import RoutingRequest
            routing_request = RoutingRequest(
                model=request_data["model"],
                messages=request_data["messages"],
                data=request_data
            )
            router = handler.router
            candidates = await router.route_request(routing_request)
            print(f"路由到 {len(candidates)} 个候选渠道")
        except Exception as e:
            print(f"路由测试失败: {e}")
        
        full_process_time = time.time() - start
        print(f"完整路由处理: {full_process_time*1000:.1f}ms")
        
    except Exception as e:
        print(f"真实请求模拟跳过: {e}")

async def main():
    """主诊断函数"""
    print("Smart AI Router 性能诊断工具")
    print("=" * 50)
    
    overall_start = time.time()
    
    # 测量各个组件
    router = await measure_startup_time()
    await measure_routing_performance(router)
    await measure_capability_detection()
    await measure_cache_performance()
    measure_system_resources()
    await measure_real_request_simulation()
    
    overall_time = time.time() - overall_start
    print(f"\n总诊断时间: {overall_time:.2f}秒")
    
    # 分析结果
    print("\n=== 性能分析结论 ===")
    print("如果发现以下问题:")
    print("1. 启动时间 > 100ms: 配置文件或模块导入问题")
    print("2. 首次路由 > 1000ms: 模型发现或缓存问题") 
    print("3. 后续路由 > 100ms: 路由算法效率问题")
    print("4. 内存使用 > 500MB: 内存泄漏或缓存过大")
    print("5. 能力检测 > 50ms: 检测逻辑需要优化")

if __name__ == "__main__":
    asyncio.run(main())