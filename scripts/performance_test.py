#!/usr/bin/env python3
"""
性能测试脚本 - 验证模型筛选优化效果
测试批量评分器 vs 原始单独评分的性能差异
"""

import asyncio
import time
import json
import sys
from pathlib import Path
from typing import List

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.yaml_config import get_yaml_config_loader
from core.json_router import JSONRouter, RoutingRequest


class PerformanceTest:
    """性能测试器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.results = {}
    
    async def setup_router(self):
        """设置路由器"""
        try:
            config_loader = get_yaml_config_loader()
            self.router = JSONRouter(config_loader)
            print("OK Router initialized successfully")
        except Exception as e:
            print(f"ERROR Failed to initialize router: {e}")
            return False
        return True
    
    async def create_test_request(self, model: str) -> RoutingRequest:
        """创建测试请求"""
        request = RoutingRequest(
            model=model,
            messages=[{"role": "user", "content": "Hello"}]
        )
        request.max_tokens = 1000
        request.temperature = 0.7
        request.stream = False
        return request
    
    async def test_batch_performance(self, test_model: str = "tag:gpt", iterations: int = 5):
        """测试批量评分性能"""
        print(f"\nTESTING: Batch scoring performance for model '{test_model}'")
        
        total_times = []
        total_channels_count = 0
        
        for i in range(iterations):
            print(f"  Iteration {i+1}/{iterations}...")
            
            request = await self.create_test_request(test_model)
            
            # 记录开始时间
            start_time = time.time()
            
            # 执行路由
            try:
                results = await self.router.route_request(request)
                end_time = time.time()
                
                duration_ms = (end_time - start_time) * 1000
                total_times.append(duration_ms)
                
                if results:
                    total_channels_count = len(results)
                    print(f"    OK Found {len(results)} channels in {duration_ms:.1f}ms")
                else:
                    print(f"    WARN No channels found in {duration_ms:.1f}ms")
                    
            except Exception as e:
                print(f"    ERROR in iteration {i+1}: {e}")
                continue
        
        if total_times:
            avg_time = sum(total_times) / len(total_times)
            min_time = min(total_times)
            max_time = max(total_times)
            avg_per_channel = avg_time / max(total_channels_count, 1)
            
            print(f"\nPERFORMANCE RESULTS for '{test_model}':")
            print(f"  Average time: {avg_time:.1f}ms")
            print(f"  Min time: {min_time:.1f}ms")  
            print(f"  Max time: {max_time:.1f}ms")
            print(f"  Channels evaluated: {total_channels_count}")
            print(f"  Avg per channel: {avg_per_channel:.1f}ms")
            
            return {
                'model': test_model,
                'iterations': len(total_times),
                'avg_time_ms': avg_time,
                'min_time_ms': min_time,
                'max_time_ms': max_time,
                'channels_count': total_channels_count,
                'avg_per_channel_ms': avg_per_channel
            }
        
        return None
    
    async def compare_with_cache(self, test_model: str = "tag:free"):
        """测试缓存效果"""
        print(f"\nCACHE TEST: Testing cache performance for model '{test_model}'")
        
        request = await self.create_test_request(test_model)
        
        # 第一次请求（冷缓存）
        print("  First request (cold cache)...")
        start_time = time.time()
        results1 = await self.router.route_request(request)
        cold_time = (time.time() - start_time) * 1000
        
        # 第二次请求（热缓存）
        print("  Second request (warm cache)...")
        start_time = time.time()
        results2 = await self.router.route_request(request)
        warm_time = (time.time() - start_time) * 1000
        
        speedup = cold_time / warm_time if warm_time > 0 else 0
        
        print(f"\nCACHE PERFORMANCE:")
        print(f"  Cold cache: {cold_time:.1f}ms")
        print(f"  Warm cache: {warm_time:.1f}ms") 
        print(f"  Speedup: {speedup:.1f}x")
        
        return {
            'cold_time_ms': cold_time,
            'warm_time_ms': warm_time,
            'speedup': speedup,
            'channels_count': len(results1) if results1 else 0
        }
    
    async def run_comprehensive_test(self):
        """运行综合性能测试"""
        print("COMPREHENSIVE TEST: Starting performance test...")
        
        # 设置路由器
        if not await self.setup_router():
            return
        
        test_models = [
            "tag:gpt",
            "tag:free", 
            "tag:qwen",
            "tag:claude"
        ]
        
        all_results = {}
        
        for model in test_models:
            try:
                # 基础性能测试
                perf_result = await self.test_batch_performance(model, iterations=3)
                if perf_result:
                    all_results[f"performance_{model}"] = perf_result
                
                # 缓存测试
                cache_result = await self.compare_with_cache(model)
                if cache_result:
                    all_results[f"cache_{model}"] = cache_result
                    
                await asyncio.sleep(1)  # 避免过快请求
                
            except Exception as e:
                print(f"ERROR testing model {model}: {e}")
                continue
        
        # 保存结果
        results_file = self.project_root / "performance_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        
        print(f"\nRESULTS saved to: {results_file}")
        
        # 总结
        print("\nPERFORMANCE SUMMARY:")
        perf_results = [v for k, v in all_results.items() if k.startswith('performance_')]
        if perf_results:
            avg_per_channel = sum(r['avg_per_channel_ms'] for r in perf_results) / len(perf_results)
            print(f"  Overall avg per channel: {avg_per_channel:.1f}ms")
            
            if avg_per_channel < 20:
                print("  EXCELLENT: Performance is under 20ms per channel!")
            elif avg_per_channel < 50:
                print("  GOOD: Performance is under 50ms per channel")
            else:
                print("  NEEDS IMPROVEMENT: Performance is over 50ms per channel")
        
        cache_results = [v for k, v in all_results.items() if k.startswith('cache_')]
        if cache_results:
            avg_speedup = sum(r['speedup'] for r in cache_results if r['speedup'] > 0) / len([r for r in cache_results if r['speedup'] > 0])
            print(f"  Cache speedup: {avg_speedup:.1f}x average")
        
        return all_results
    
    async def quick_test(self, model: str = "tag:free"):
        """快速单次测试"""
        print(f"QUICK TEST: Testing model '{model}'")
        
        if not await self.setup_router():
            return
        
        request = await self.create_test_request(model)
        
        start_time = time.time()
        results = await self.router.route_request(request)
        duration = (time.time() - start_time) * 1000
        
        if results:
            per_channel = duration / len(results)
            print(f"OK Found {len(results)} channels in {duration:.1f}ms ({per_channel:.1f}ms per channel)")
            
            # 显示前3个结果
            print("\nTOP 3 CHANNELS:")
            for i, result in enumerate(results[:3], 1):
                print(f"  #{i}: {result.channel.name} (Score: {result.total_score:.3f})")
        else:
            print(f"ERROR No channels found in {duration:.1f}ms")


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Smart AI Router 性能测试")
    parser.add_argument("--quick", action="store_true", help="快速单次测试")
    parser.add_argument("--model", default="tag:free", help="测试模型名称")
    parser.add_argument("--comprehensive", action="store_true", help="综合性能测试")
    
    args = parser.parse_args()
    
    tester = PerformanceTest()
    
    if args.quick:
        await tester.quick_test(args.model)
    elif args.comprehensive:
        await tester.run_comprehensive_test()
    else:
        # 默认运行单个模型的性能测试
        await tester.setup_router()
        await tester.test_batch_performance(args.model, iterations=5)


if __name__ == "__main__":
    asyncio.run(main())