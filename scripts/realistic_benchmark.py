#!/usr/bin/env python3
"""
实际场景性能基准测试
模拟真实用户使用场景的性能测试
"""

import asyncio
import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.json_router import JSONRouter, RoutingRequest
from core.yaml_config import get_yaml_config_loader


class RealisticBenchmark:
    """实际场景基准测试"""

    def __init__(self):
        self.router = None

    async def setup(self):
        """初始化路由器"""
        try:
            config_loader = get_yaml_config_loader()
            self.router = JSONRouter(config_loader)
            print("Router initialized successfully")
            return True
        except Exception as e:
            print(f"Failed to initialize router: {e}")
            return False

    async def create_request(self, model: str):
        """创建测试请求"""
        return RoutingRequest(
            model=model, messages=[{"role": "user", "content": "Hello, how are you?"}]
        )

    async def benchmark_common_scenarios(self):
        """测试常见使用场景"""
        print("\n=== REALISTIC BENCHMARK TEST ===")

        # 常见的查询场景
        test_cases = [
            # 精确标签查询（最常见）
            ("tag:gpt", "GPT models"),
            ("tag:claude", "Claude models"),
            ("tag:free", "Free models"),
            ("tag:qwen", "Qwen models"),
            # 特定功能查询
            ("tag:vision", "Vision models"),
            ("tag:function", "Function calling models"),
            # 价格敏感查询
            ("tag:cheap", "Budget models"),
            ("tag:premium", "Premium models"),
        ]

        results = {}

        for model_query, description in test_cases:
            print(f"\nTesting: {description} ('{model_query}')")

            # 测试冷缓存性能（第一次查询）
            start_time = time.time()
            try:
                request = await self.create_request(model_query)
                channels = await self.router.route_request(request)
                cold_time = (time.time() - start_time) * 1000

                if channels:
                    print(
                        f"  Cold cache: {cold_time:.1f}ms -> {len(channels)} channels"
                    )
                else:
                    print(f"  Cold cache: {cold_time:.1f}ms -> No channels found")

                # 测试热缓存性能（重复查询）
                start_time = time.time()
                channels = await self.router.route_request(request)
                hot_time = (time.time() - start_time) * 1000

                print(f"  Hot cache:  {hot_time:.1f}ms -> {len(channels)} channels")

                results[model_query] = {
                    "description": description,
                    "cold_time_ms": cold_time,
                    "hot_time_ms": hot_time,
                    "channels_found": len(channels) if channels else 0,
                    "speedup": cold_time / hot_time if hot_time > 0 else 0,
                }

            except Exception as e:
                print(f"  ERROR: {e}")
                results[model_query] = {"error": str(e)}

        # 性能总结
        print(f"\n=== PERFORMANCE SUMMARY ===")

        successful_tests = [r for r in results.values() if "error" not in r]
        if successful_tests:
            avg_cold = sum(r["cold_time_ms"] for r in successful_tests) / len(
                successful_tests
            )
            avg_hot = sum(r["hot_time_ms"] for r in successful_tests) / len(
                successful_tests
            )
            avg_speedup = sum(
                r["speedup"] for r in successful_tests if r["speedup"] > 0
            ) / len([r for r in successful_tests if r["speedup"] > 0])

            print(f"Average cold cache time: {avg_cold:.1f}ms")
            print(f"Average hot cache time:  {avg_hot:.1f}ms")
            print(f"Average cache speedup:   {avg_speedup:.1f}x")

            # 性能评级
            if avg_hot < 1.0:
                print("PERFORMANCE RATING: EXCELLENT (sub-millisecond)")
            elif avg_hot < 10.0:
                print("PERFORMANCE RATING: VERY GOOD (< 10ms)")
            elif avg_hot < 50.0:
                print("PERFORMANCE RATING: GOOD (< 50ms)")
            else:
                print("PERFORMANCE RATING: NEEDS IMPROVEMENT (> 50ms)")

        return results

    async def stress_test_concurrent_queries(self):
        """压力测试：并发查询"""
        print(f"\n=== CONCURRENT STRESS TEST ===")

        # 模拟多个并发用户查询
        concurrent_queries = [
            "tag:gpt",
            "tag:claude",
            "tag:free",
            "tag:qwen",
            "tag:vision",
        ] * 4  # 20个并发查询

        start_time = time.time()

        # 创建并发任务
        tasks = []
        for i, model in enumerate(concurrent_queries):
            request = await self.create_request(model)
            task = self.router.route_request(request)
            tasks.append(task)

        # 并发执行
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            total_time = (time.time() - start_time) * 1000

            successful = [r for r in results if not isinstance(r, Exception)]
            errors = [r for r in results if isinstance(r, Exception)]

            print(f"Concurrent queries: {len(concurrent_queries)}")
            print(f"Total time: {total_time:.1f}ms")
            print(f"Average per query: {total_time/len(concurrent_queries):.1f}ms")
            print(f"Successful: {len(successful)}")
            print(f"Errors: {len(errors)}")

            if successful:
                total_channels = sum(len(r) for r in successful if r)
                print(f"Total channels found: {total_channels}")

        except Exception as e:
            print(f"Concurrent test failed: {e}")

    async def run_full_benchmark(self):
        """运行完整基准测试"""
        if not await self.setup():
            return

        # 场景测试
        await self.benchmark_common_scenarios()

        # 并发测试
        await self.stress_test_concurrent_queries()

        print(f"\n=== BENCHMARK COMPLETE ===")


async def main():
    benchmark = RealisticBenchmark()
    await benchmark.run_full_benchmark()


if __name__ == "__main__":
    asyncio.run(main())
