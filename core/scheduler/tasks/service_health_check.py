#!/usr/bin/env python3
"""
服务健康检查任务 - 定时检查每个服务商的可用性和延迟
自动选择最便宜的小模型进行测试，记录延迟和可用性信息
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import httpx
import logging
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class HealthCheckResult:
    """健康检查结果"""
    channel_id: str
    provider: str
    model_name: str
    test_model: str
    success: bool
    latency_ms: Optional[float]
    error_message: Optional[str]
    response_time: float
    timestamp: datetime
    status_code: Optional[int] = None
    tokens_per_second: Optional[float] = None

@dataclass
class ProviderHealth:
    """Provider健康状态"""
    provider: str
    total_channels: int
    healthy_channels: int
    avg_latency_ms: float
    fastest_channel: Optional[str]
    cheapest_healthy_channel: Optional[str]
    last_check: datetime
    success_rate: float

class ServiceHealthChecker:
    """服务健康检查器"""
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # 缓存文件路径
        self.health_cache_file = self.cache_dir / "service_health.json"
        self.health_history_file = self.cache_dir / "health_history.json"
        self.latency_cache_file = self.cache_dir / "latency_stats.json"
        
        # 健康检查数据
        self.health_results: Dict[str, HealthCheckResult] = {}
        self.provider_health: Dict[str, ProviderHealth] = {}
        self.health_history: List[Dict] = []
        
        # 加载现有数据
        self._load_cache()
        
        # HTTP客户端配置
        self.http_timeout = httpx.Timeout(30.0, connect=10.0)
        
    def _load_cache(self):
        """加载缓存的健康检查数据"""
        try:
            if self.health_cache_file.exists():
                with open(self.health_cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.health_results = {
                        k: HealthCheckResult(**v) for k, v in data.get('health_results', {}).items()
                    }
                    self.provider_health = {
                        k: ProviderHealth(**v) for k, v in data.get('provider_health', {}).items()
                    }
                logger.info(f"已加载健康检查缓存: {len(self.health_results)} 个渠道")
                
            if self.health_history_file.exists():
                with open(self.health_history_file, 'r', encoding='utf-8') as f:
                    self.health_history = json.load(f)
                    # 只保留最近24小时的历史记录
                    cutoff = datetime.now() - timedelta(hours=24)
                    self.health_history = [
                        h for h in self.health_history 
                        if datetime.fromisoformat(h['timestamp']) > cutoff
                    ]
                logger.info(f"已加载健康检查历史: {len(self.health_history)} 条记录")
                
        except Exception as e:
            logger.warning(f"加载健康检查缓存失败: {e}")
    
    def _save_cache(self):
        """保存健康检查数据到缓存"""
        try:
            # 保存当前状态
            cache_data = {
                'health_results': {
                    k: asdict(v) for k, v in self.health_results.items()
                },
                'provider_health': {
                    k: asdict(v) for k, v in self.provider_health.items()
                },
                'last_update': datetime.now().isoformat()
            }
            
            with open(self.health_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2, default=str)
            
            # 保存历史记录
            with open(self.health_history_file, 'w', encoding='utf-8') as f:
                json.dump(self.health_history, f, ensure_ascii=False, indent=2, default=str)
                
            logger.info("健康检查数据已保存到缓存")
            
        except Exception as e:
            logger.error(f"保存健康检查缓存失败: {e}")
    
    def _select_test_model(self, channel: Dict[str, Any], available_models: List[str]) -> Optional[str]:
        """为渠道选择最适合的测试模型"""
        if not available_models:
            return None
            
        # 优先级策略：
        # 1. 寻找便宜的小模型 (含4b, 8b, 12b关键词)
        # 2. 寻找免费模型（包含free标签）
        # 3. 选择第一个可用的模型
        
        small_models = []
        free_models = []
        
        for model in available_models:
            # 处理字符串格式的模型名
            model_id = model.lower() if isinstance(model, str) else str(model).lower()
            
            # 检查是否是小模型
            if any(keyword in model_id for keyword in ['4b', '8b', '12b', 'mini', 'small', 'lite']):
                small_models.append(model)
            
            # 检查是否是免费模型（包含free标签或已知免费模型）
            if ('free' in model_id or 
                'gpt-3.5-turbo' in model_id or 
                'claude-3-haiku' in model_id or
                any(keyword in model_id for keyword in ['gemini-pro', 'llama-3', 'mixtral'])):
                free_models.append(model)
        
        # 优先选择小模型
        if small_models:
            return small_models[0]
        
        # 其次选择免费模型
        if free_models:
            return free_models[0]
        
        # 兜底：选择第一个可用模型
        return available_models[0] if available_models else None
    
    async def _test_channel_health(self, channel: Dict[str, Any], test_model: str) -> HealthCheckResult:
        """测试单个渠道的健康状态"""
        channel_id = channel.get('id', 'unknown')
        provider = channel.get('provider', 'unknown')
        api_key = channel.get('api_key', '')
        base_url = channel.get('base_url', '')
        
        start_time = time.time()
        
        # 构建测试请求
        test_payload = {
            "model": test_model,
            "messages": [
                {"role": "user", "content": "Hi"}
            ],
            "max_tokens": 10,
            "temperature": 0.1
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SmartAIRouter/1.0"
        }
        
        # 设置认证头
        if api_key:
            if provider.lower() in ['openai', 'groq', 'openrouter']:
                headers["Authorization"] = f"Bearer {api_key}"
            elif provider.lower() in ['anthropic']:
                headers["x-api-key"] = api_key
            else:
                headers["Authorization"] = f"Bearer {api_key}"
        
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                # 构建URL
                if base_url.endswith('/'):
                    url = f"{base_url}v1/chat/completions"
                else:
                    url = f"{base_url}/v1/chat/completions"
                
                response = await client.post(url, json=test_payload, headers=headers)
                
                end_time = time.time()
                latency_ms = (end_time - start_time) * 1000
                
                if response.status_code == 200:
                    # 解析响应计算tokens/second
                    try:
                        response_data = response.json()
                        usage = response_data.get('usage', {})
                        total_tokens = usage.get('total_tokens', 0)
                        tokens_per_second = total_tokens / (latency_ms / 1000) if latency_ms > 0 else 0
                    except:
                        tokens_per_second = None
                    
                    return HealthCheckResult(
                        channel_id=channel_id,
                        provider=provider,
                        model_name=channel.get('model_name', 'unknown'),
                        test_model=test_model,
                        success=True,
                        latency_ms=latency_ms,
                        error_message=None,
                        response_time=end_time - start_time,
                        timestamp=datetime.now(),
                        status_code=response.status_code,
                        tokens_per_second=tokens_per_second
                    )
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    return HealthCheckResult(
                        channel_id=channel_id,
                        provider=provider,
                        model_name=channel.get('model_name', 'unknown'),
                        test_model=test_model,
                        success=False,
                        latency_ms=latency_ms,
                        error_message=error_msg,
                        response_time=end_time - start_time,
                        timestamp=datetime.now(),
                        status_code=response.status_code
                    )
                    
        except Exception as e:
            end_time = time.time()
            error_msg = f"连接错误: {str(e)}"
            return HealthCheckResult(
                channel_id=channel_id,
                provider=provider,
                model_name=channel.get('model_name', 'unknown'),
                test_model=test_model,
                success=False,
                latency_ms=None,
                error_message=error_msg,
                response_time=end_time - start_time,
                timestamp=datetime.now()
            )
    
    async def check_all_channels(self, channels: List[Dict[str, Any]], 
                               discovered_models: Dict[str, List[Dict]] = None) -> Dict[str, HealthCheckResult]:
        """检查所有渠道的健康状态"""
        if not channels:
            logger.warning("没有可检查的渠道")
            return {}
        
        logger.info(f"开始健康检查，共 {len(channels)} 个渠道")
        
        # 并发检查所有渠道
        tasks = []
        for channel in channels:
            # 跳过没有API密钥的渠道
            if not channel.get('api_key') or len(channel.get('api_key', '').strip()) < 10:
                continue
                
            # 为每个渠道选择测试模型
            channel_id = channel.get('id', 'unknown')
            available_models = discovered_models.get(channel_id, []) if discovered_models else []
            
            # 如果没有发现的模型，使用渠道配置的模型
            if not available_models and channel.get('model_name'):
                test_model = channel['model_name']
            else:
                test_model = self._select_test_model(channel, available_models)
            
            if not test_model:
                logger.warning(f"渠道 {channel_id} 没有可测试的模型")
                continue
            
            task = self._test_channel_health(channel, test_model)
            tasks.append(task)
        
        # 执行并发检查，限制并发数
        semaphore = asyncio.Semaphore(10)  # 最多10个并发请求
        
        async def limited_check(task):
            async with semaphore:
                return await task
        
        results = await asyncio.gather(*[limited_check(task) for task in tasks], return_exceptions=True)
        
        # 处理结果
        health_results = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"健康检查出错: {result}")
                continue
            if isinstance(result, HealthCheckResult):
                health_results[result.channel_id] = result
                # 添加到历史记录
                self.health_history.append(asdict(result))
        
        self.health_results.update(health_results)
        
        # 计算Provider级别的健康统计
        self._calculate_provider_health()
        
        # 保存缓存
        self._save_cache()
        
        # 打印统计信息
        self._log_health_summary()
        
        return health_results
    
    def _calculate_provider_health(self):
        """计算Provider级别的健康统计"""
        provider_stats = {}
        
        for result in self.health_results.values():
            provider = result.provider
            if provider not in provider_stats:
                provider_stats[provider] = {
                    'total': 0,
                    'healthy': 0,
                    'latencies': [],
                    'fastest_channel': None,
                    'cheapest_healthy': None,
                    'min_latency': float('inf')
                }
            
            stats = provider_stats[provider]
            stats['total'] += 1
            
            if result.success:
                stats['healthy'] += 1
                if result.latency_ms is not None:
                    stats['latencies'].append(result.latency_ms)
                    if result.latency_ms < stats['min_latency']:
                        stats['min_latency'] = result.latency_ms
                        stats['fastest_channel'] = result.channel_id
        
        # 构建ProviderHealth对象
        for provider, stats in provider_stats.items():
            avg_latency = sum(stats['latencies']) / len(stats['latencies']) if stats['latencies'] else 0
            success_rate = stats['healthy'] / stats['total'] if stats['total'] > 0 else 0
            
            self.provider_health[provider] = ProviderHealth(
                provider=provider,
                total_channels=stats['total'],
                healthy_channels=stats['healthy'],
                avg_latency_ms=avg_latency,
                fastest_channel=stats['fastest_channel'],
                cheapest_healthy_channel=stats['fastest_channel'],  # 简化：暂时用最快的代替
                last_check=datetime.now(),
                success_rate=success_rate
            )
    
    def _log_health_summary(self):
        """打印健康检查摘要"""
        total_channels = len(self.health_results)
        healthy_channels = sum(1 for r in self.health_results.values() if r.success)
        
        logger.info(f"=== 健康检查完成 ===")
        logger.info(f"总渠道数: {total_channels}")
        logger.info(f"健康渠道: {healthy_channels}")
        logger.info(f"成功率: {healthy_channels/total_channels*100:.1f}%")
        
        for provider, health in self.provider_health.items():
            logger.info(f"Provider {provider}: {health.healthy_channels}/{health.total_channels} "
                       f"({health.success_rate*100:.1f}%), 平均延迟: {health.avg_latency_ms:.1f}ms")
    
    def get_channel_health(self, channel_id: str) -> Optional[HealthCheckResult]:
        """获取指定渠道的健康状态"""
        return self.health_results.get(channel_id)
    
    def get_provider_health(self, provider: str) -> Optional[ProviderHealth]:
        """获取指定Provider的健康状态"""
        return self.provider_health.get(provider)
    
    def get_healthy_channels(self, provider: Optional[str] = None) -> List[str]:
        """获取健康的渠道列表"""
        healthy_channels = []
        for channel_id, result in self.health_results.items():
            if result.success and (provider is None or result.provider == provider):
                healthy_channels.append(channel_id)
        return healthy_channels
    
    def get_fastest_channels(self, provider: Optional[str] = None, limit: int = 5) -> List[Tuple[str, float]]:
        """获取最快的渠道列表"""
        fast_channels = []
        for channel_id, result in self.health_results.items():
            if (result.success and result.latency_ms is not None and 
                (provider is None or result.provider == provider)):
                fast_channels.append((channel_id, result.latency_ms))
        
        fast_channels.sort(key=lambda x: x[1])
        return fast_channels[:limit]
    
    def get_health_stats(self) -> Dict[str, Any]:
        """获取健康检查统计信息"""
        total = len(self.health_results)
        healthy = sum(1 for r in self.health_results.values() if r.success)
        
        if total == 0:
            return {
                'total_channels': 0,
                'healthy_channels': 0,
                'success_rate': 0,
                'avg_latency_ms': 0,
                'provider_stats': {}
            }
        
        latencies = [r.latency_ms for r in self.health_results.values() 
                    if r.success and r.latency_ms is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        
        provider_stats = {}
        for provider, health in self.provider_health.items():
            provider_stats[provider] = asdict(health)
        
        return {
            'total_channels': total,
            'healthy_channels': healthy,
            'success_rate': healthy / total,
            'avg_latency_ms': avg_latency,
            'provider_stats': provider_stats,
            'last_check': max(
                r.timestamp.isoformat() if isinstance(r.timestamp, datetime) else r.timestamp 
                for r in self.health_results.values()
            ) if self.health_results else None
        }

# 主要的任务执行函数
async def run_health_check_task(channels: List[Dict[str, Any]], 
                               discovered_models: Dict[str, List[Dict]] = None) -> Dict[str, Any]:
    """运行健康检查任务"""
    checker = ServiceHealthChecker()
    results = await checker.check_all_channels(channels, discovered_models)
    stats = checker.get_health_stats()
    
    return {
        'results': {k: asdict(v) for k, v in results.items()},
        'stats': stats,
        'timestamp': datetime.now().isoformat()
    }

if __name__ == "__main__":
    # 测试代码
    async def test_health_check():
        # 示例渠道配置
        test_channels = [
            {
                'id': 'test_channel_1',
                'provider': 'openai',
                'model_name': 'gpt-4o-mini',
                'api_key': 'sk-test-key',
                'base_url': 'https://api.openai.com'
            }
        ]
        
        result = await run_health_check_task(test_channels)
        print("健康检查结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    
    asyncio.run(test_health_check())