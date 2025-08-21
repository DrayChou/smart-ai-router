#!/usr/bin/env python3
"""
查询预加载器 - 预加载热点查询以提升API响应速度
基于KISS原则设计，优先使用函数而非复杂类结构
"""

import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Callable
from collections import defaultdict
from dataclasses import dataclass

from .smart_cache import get_smart_cache, cache_set, cache_get

logger = logging.getLogger(__name__)

@dataclass
class HotQuery:
    """热点查询模式"""
    pattern: str
    frequency: int
    last_accessed: float
    avg_response_time: float

# 热点查询统计 - 使用简单的全局字典而非类
_query_stats: Dict[str, HotQuery] = {}
_preload_tasks: Dict[str, asyncio.Task] = {}

def record_query_access(query_pattern: str, response_time_ms: float):
    """记录查询访问，用于热点检测"""
    current_time = time.time()
    
    if query_pattern in _query_stats:
        stats = _query_stats[query_pattern]
        stats.frequency += 1
        stats.last_accessed = current_time
        # 计算平均响应时间
        stats.avg_response_time = (stats.avg_response_time + response_time_ms) / 2
    else:
        _query_stats[query_pattern] = HotQuery(
            pattern=query_pattern,
            frequency=1,
            last_accessed=current_time,
            avg_response_time=response_time_ms
        )

def get_hot_queries(min_frequency: int = 3, max_age_hours: float = 24) -> List[HotQuery]:
    """获取热点查询列表"""
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    hot_queries = []
    for query in _query_stats.values():
        # 过滤：频率足够高且最近被访问过
        if (query.frequency >= min_frequency and 
            current_time - query.last_accessed < max_age_seconds):
            hot_queries.append(query)
    
    # 按频率降序排序
    return sorted(hot_queries, key=lambda q: q.frequency, reverse=True)

async def preload_query_result(query_pattern: str, preload_func: Callable) -> bool:
    """预加载单个查询结果"""
    try:
        cache = get_smart_cache()
        cache_key = f"preload_{query_pattern}"
        
        # 检查是否已经预加载
        existing = await cache.get("hot_queries", cache_key)
        if existing:
            logger.debug(f"Query already preloaded: {query_pattern}")
            return True
        
        # 执行预加载函数
        start_time = time.time()
        if asyncio.iscoroutinefunction(preload_func):
            result = await preload_func()
        else:
            result = preload_func()
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # 缓存预加载结果
        await cache.set("hot_queries", cache_key, {
            "result": result,
            "preloaded_at": time.time(),
            "preload_time_ms": elapsed_ms,
            "pattern": query_pattern
        })
        
        logger.info(f"🔥 PRELOADED: {query_pattern} in {elapsed_ms:.1f}ms")
        return True
        
    except Exception as e:
        logger.error(f"Failed to preload query {query_pattern}: {e}")
        return False

async def batch_preload_hot_queries(router_instance, max_concurrent: int = 3):
    """批量预加载热点查询"""
    hot_queries = get_hot_queries(min_frequency=5)  # 至少访问5次才预加载
    
    if not hot_queries:
        logger.info("No hot queries to preload")
        return
    
    logger.info(f"🔥 PRELOADING: {len(hot_queries)} hot queries")
    
    # 定义常见查询模式的预加载函数
    preload_functions = {
        "tag:gpt": lambda: _preload_tag_query(router_instance, ["gpt"]),
        "tag:claude": lambda: _preload_tag_query(router_instance, ["claude"]),
        "tag:free": lambda: _preload_tag_query(router_instance, ["free"]),
        "tag:local": lambda: _preload_tag_query(router_instance, ["local"]),
        "tag:fast": lambda: _preload_tag_query(router_instance, ["fast"]),
        "tag:cheap": lambda: _preload_tag_query(router_instance, ["cheap"]),
    }
    
    # 创建预加载任务
    tasks = []
    for query in hot_queries[:max_concurrent]:  # 限制并发数
        pattern = query.pattern
        if pattern in preload_functions:
            preload_func = preload_functions[pattern]
            task = asyncio.create_task(preload_query_result(pattern, preload_func))
            tasks.append((pattern, task))
    
    # 等待所有预加载任务完成
    results = []
    for pattern, task in tasks:
        try:
            success = await task
            results.append((pattern, success))
        except Exception as e:
            logger.error(f"Preload task failed for {pattern}: {e}")
            results.append((pattern, False))
    
    # 统计结果
    successful = sum(1 for _, success in results if success)
    logger.info(f"🔥 PRELOAD COMPLETE: {successful}/{len(results)} queries preloaded successfully")

async def _preload_tag_query(router_instance, tags: List[str]):
    """预加载标签查询（辅助函数）"""
    from ..json_router import RoutingRequest
    
    # 创建模拟请求
    request = RoutingRequest(
        model=f"tag:{','.join(tags)}",
        messages=[{"role": "user", "content": "test"}],
        temperature=0.7
    )
    
    # 执行路由查询（这会填充缓存）
    candidates = await router_instance.route_request(request)
    return {"candidates_count": len(candidates), "tags": tags}

def get_preload_stats() -> Dict[str, Any]:
    """获取预加载统计信息"""
    hot_queries = get_hot_queries()
    
    return {
        "total_tracked_queries": len(_query_stats),
        "hot_queries_count": len(hot_queries),
        "active_preload_tasks": len(_preload_tasks),
        "top_queries": [
            {
                "pattern": q.pattern,
                "frequency": q.frequency,
                "avg_response_time_ms": q.avg_response_time
            }
            for q in hot_queries[:10]
        ]
    }

def cleanup_old_queries(max_age_days: int = 7):
    """清理过期的查询统计"""
    current_time = time.time()
    max_age_seconds = max_age_days * 24 * 3600
    
    expired_patterns = []
    for pattern, query in _query_stats.items():
        if current_time - query.last_accessed > max_age_seconds:
            expired_patterns.append(pattern)
    
    for pattern in expired_patterns:
        del _query_stats[pattern]
    
    if expired_patterns:
        logger.info(f"🧹 CLEANUP: Removed {len(expired_patterns)} expired query patterns")

# 启动预加载任务的便捷函数
async def start_preload_scheduler(router_instance, interval_minutes: int = 30):
    """启动预加载调度器"""
    while True:
        try:
            await batch_preload_hot_queries(router_instance)
            cleanup_old_queries()
            await asyncio.sleep(interval_minutes * 60)
        except Exception as e:
            logger.error(f"Preload scheduler error: {e}")
            await asyncio.sleep(300)  # 出错时等待5分钟

# 简单的装饰器函数用于自动记录查询
def track_query_performance(query_pattern: str):
    """装饰器：自动跟踪查询性能"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed_ms = (time.time() - start_time) * 1000
                record_query_access(query_pattern, elapsed_ms)
                return result
            except Exception as e:
                elapsed_ms = (time.time() - start_time) * 1000
                record_query_access(query_pattern, elapsed_ms)
                raise
        return wrapper
    return decorator