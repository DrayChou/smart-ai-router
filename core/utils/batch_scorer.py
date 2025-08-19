# -*- coding: utf-8 -*-
"""
批量评分器 - 优化模型筛选性能
用于大幅减少单个模型评分时间，从70-80ms降低到10ms以下
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from core.config_models import Channel
from core.json_router import ChannelCandidate

logger = logging.getLogger(__name__)


@dataclass
class BatchedScoreComponents:
    """批量评分结果"""
    cost_scores: Dict[str, float]
    speed_scores: Dict[str, float] 
    quality_scores: Dict[str, float]
    reliability_scores: Dict[str, float]
    parameter_scores: Dict[str, float]
    context_scores: Dict[str, float]
    free_scores: Dict[str, float]
    local_scores: Dict[str, float]
    computation_time_ms: float


class BatchScorer:
    """批量评分器 - 优化模型筛选性能"""
    
    def __init__(self, router):
        """初始化批量评分器"""
        self.router = router
        self.cache = {}
        self.cache_timeout = 300  # 5分钟缓存
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
    
    def _get_cache_key(self, channels: List[ChannelCandidate], request) -> str:
        """生成缓存键"""
        channel_ids = sorted([c.channel.id for c in channels])
        model_name = getattr(request, 'model', 'unknown')
        return f"batch_score_{hash(tuple(channel_ids))}_{model_name}"
    
    def _check_cache(self, cache_key: str) -> Optional[BatchedScoreComponents]:
        """检查缓存"""
        if cache_key in self.cache:
            cached_time, cached_result = self.cache[cache_key]
            if (time.time() - cached_time) < self.cache_timeout:
                logger.debug(f"BATCH_SCORER: Cache hit for {cache_key}")
                return cached_result
        return None
    
    def _store_cache(self, cache_key: str, result: BatchedScoreComponents):
        """存储到缓存"""
        self.cache[cache_key] = (time.time(), result)
    
    def _batch_get_model_specs(self, channels: List[ChannelCandidate]) -> Dict[str, Dict[str, Any]]:
        """批量获取模型规格信息"""
        model_specs = {}
        
        # 按渠道分组以优化缓存访问
        specs_by_channel = defaultdict(list)
        for candidate in channels:
            if candidate.matched_model:
                specs_by_channel[candidate.channel.id].append(candidate.matched_model)
        
        # 批量加载每个渠道的模型缓存
        for channel_id, models in specs_by_channel.items():
            try:
                channel_cache = self.router.cache_manager.load_channel_models(channel_id)
                if channel_cache and 'models' in channel_cache:
                    for model_name in models:
                        key = f"{channel_id}_{model_name}"
                        cached_spec = channel_cache['models'].get(model_name)
                        if cached_spec:
                            model_specs[key] = cached_spec
                        else:
                            # 回退到分析器
                            analyzed_specs = self.router.model_analyzer.analyze_model(model_name)
                            model_specs[key] = {
                                'parameter_count': analyzed_specs.parameter_count,
                                'context_length': analyzed_specs.context_length
                            }
            except Exception as e:
                logger.debug(f"BATCH_SCORER: Failed to load specs for channel {channel_id}: {e}")
                # 对该渠道的所有模型使用分析器
                for model_name in models:
                    key = f"{channel_id}_{model_name}"
                    try:
                        analyzed_specs = self.router.model_analyzer.analyze_model(model_name)
                        model_specs[key] = {
                            'parameter_count': analyzed_specs.parameter_count,
                            'context_length': analyzed_specs.context_length
                        }
                    except:
                        model_specs[key] = {'parameter_count': 0, 'context_length': 0}
        
        return model_specs
    
    def _batch_calculate_parameter_scores(
        self, 
        channels: List[ChannelCandidate],
        model_specs: Dict[str, Dict[str, Any]]
    ) -> Dict[str, float]:
        """批量计算参数数量评分"""
        parameter_scores = {}
        
        for candidate in channels:
            channel_id = candidate.channel.id
            model_name = candidate.matched_model
            key = f"{channel_id}_{model_name}" if model_name else channel_id
            
            if model_name:
                spec_key = f"{channel_id}_{model_name}"
                specs = model_specs.get(spec_key, {})
                param_count = specs.get('parameter_count', 0)
            else:
                param_count = 0
            
            # 确保param_count不为None
            if param_count is None:
                param_count = 0
            
            # 参数数量评分逻辑
            if param_count >= 70000:         # 70B+
                score = 1.0
            elif param_count >= 30000:       # 30B+
                score = 0.9
            elif param_count >= 8000:        # 8B+
                score = 0.8
            elif param_count >= 3000:        # 3B+
                score = 0.7
            elif param_count >= 1000:        # 1B+
                score = 0.6
            elif param_count >= 500:         # 500M+
                score = 0.5
            elif param_count >= 100:         # 100M+
                score = 0.4
            else:                            # <100M or unknown
                score = 0.3
            
            parameter_scores[key] = score
        
        return parameter_scores
    
    def _batch_calculate_context_scores(
        self,
        channels: List[ChannelCandidate], 
        model_specs: Dict[str, Dict[str, Any]]
    ) -> Dict[str, float]:
        """批量计算上下文长度评分"""
        context_scores = {}
        
        for candidate in channels:
            channel_id = candidate.channel.id
            model_name = candidate.matched_model
            key = f"{channel_id}_{model_name}" if model_name else channel_id
            
            if model_name:
                spec_key = f"{channel_id}_{model_name}"
                specs = model_specs.get(spec_key, {})
                context_length = specs.get('context_length', 0)
            else:
                context_length = 0
            
            # 确保context_length不为None
            if context_length is None:
                context_length = 0
            
            # 上下文长度评分逻辑
            if context_length >= 1000000:       # 1M+
                score = 1.0
            elif context_length >= 200000:      # 200k+
                score = 0.9
            elif context_length >= 32000:       # 32k+
                score = 0.8
            elif context_length >= 16000:       # 16k+
                score = 0.7
            elif context_length >= 8000:        # 8k+
                score = 0.6
            elif context_length >= 4000:        # 4k+
                score = 0.5
            else:                               # <4k
                score = 0.3
            
            context_scores[key] = score
        
        return context_scores
    
    def _batch_calculate_free_scores(
        self,
        channels: List[ChannelCandidate],
        model_specs: Dict[str, Dict[str, Any]]
    ) -> Dict[str, float]:
        """批量计算免费优先评分"""
        free_scores = {}
        free_tags = {"free", "免费", "0cost", "nocost", "trial"}
        
        for candidate in channels:
            channel = candidate.channel
            model_name = candidate.matched_model
            key = f"{channel.id}_{model_name}" if model_name else channel.id
            score = 0.1  # 默认评分
            
            # 检查模型级别定价信息
            if model_name:
                spec_key = f"{channel.id}_{model_name}"
                specs = model_specs.get(spec_key, {})
                if 'raw_data' in specs and 'pricing' in specs['raw_data']:
                    pricing = specs['raw_data']['pricing']
                    prompt_cost = float(pricing.get('prompt', '0'))
                    completion_cost = float(pricing.get('completion', '0'))
                    if prompt_cost == 0.0 and completion_cost == 0.0:
                        score = 1.0
                    else:
                        score = 0.1
                # 检查模型名称中的免费标识
                elif any(tag in model_name.lower() for tag in [":free", "-free", "_free"]):
                    score = 1.0
            
            # 如果模型级别没有明确证据，检查渠道级别
            if score == 0.1:
                # 检查渠道成本配置
                cost_per_token = getattr(channel, 'cost_per_token', None)
                if cost_per_token:
                    input_cost = cost_per_token.get("input", 0.0)
                    output_cost = cost_per_token.get("output", 0.0)
                    if input_cost <= 0.0 and output_cost <= 0.0:
                        score = 1.0
                    elif model_name and any(tag in model_name.lower() for tag in [":free", "-free"]):
                        score = 1.0
                    else:
                        score = 0.1
                
                # 检查传统pricing配置
                elif hasattr(channel, 'pricing'):
                    pricing = channel.pricing
                    input_cost = pricing.get("input_cost_per_1k", 0.001)
                    output_cost = pricing.get("output_cost_per_1k", 0.002)
                    avg_cost = (input_cost + output_cost) / 2
                    if avg_cost <= 0.0001:
                        score = 0.9
                    elif avg_cost <= 0.001:
                        score = 0.7
                    elif model_name and any(tag in model_name.lower() for tag in [":free", "-free"]):
                        score = 1.0
                    else:
                        score = 0.1
                
                # 检查渠道标签
                elif any(tag.lower() in free_tags for tag in getattr(channel, 'tags', [])):
                    score = 1.0
            
            free_scores[key] = score
        
        return free_scores
    
    def _batch_calculate_basic_scores(
        self, 
        channels: List[ChannelCandidate],
        request
    ) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float]]:
        """批量计算基础评分（成本、速度、质量、可靠性、本地）"""
        cost_scores = {}
        speed_scores = {}
        quality_scores = {}
        reliability_scores = {}
        local_scores = {}
        
        # 批量获取运行时状态
        runtime_state = self.router.config_loader.runtime_state
        channel_stats = runtime_state.channel_stats
        health_scores_dict = runtime_state.health_scores
        
        local_tags = {"local", "本地", "localhost", "127.0.0.1", "offline", "edge"}
        
        for candidate in channels:
            channel = candidate.channel
            model_name = candidate.matched_model
            key = f"{channel.id}_{model_name}" if model_name else channel.id
            
            # 成本评分
            cost_scores[key] = self.router._calculate_cost_score(channel, request)
            
            # 速度评分 - 优化版本
            stats = channel_stats.get(channel.id)
            if stats and "avg_latency_ms" in stats:
                avg_latency = stats["avg_latency_ms"]
                base_latency = 2000.0
                score = max(0.0, 1.0 - (avg_latency / base_latency))
                speed_scores[key] = 0.1 + score * 0.9
            else:
                speed_scores[key] = channel.performance.get("speed_score", 0.8)
            
            # 质量评分 - 直接计算
            quality_scores[key] = self.router._calculate_quality_score(channel, model_name)
            
            # 可靠性评分
            reliability_scores[key] = health_scores_dict.get(channel.id, 1.0)
            
            # 本地评分
            score = 0.1
            channel_tags_lower = [tag.lower() for tag in channel.tags]
            if any(tag in local_tags for tag in channel_tags_lower):
                score = 1.0
            elif model_name:
                model_tags = self.router._extract_tags_from_model_name(model_name)
                model_tags_lower = [tag.lower() for tag in model_tags]
                if any(tag in local_tags for tag in model_tags_lower):
                    score = 1.0
            
            # 检查base_url
            if score == 0.1:
                base_url = getattr(channel, 'base_url', None)
                if base_url:
                    base_url_lower = base_url.lower()
                    local_indicators = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
                    if any(indicator in base_url_lower for indicator in local_indicators):
                        score = 1.0
            
            local_scores[key] = score
        
        return cost_scores, speed_scores, quality_scores, reliability_scores, local_scores
    
    async def batch_score_channels(
        self, 
        channels: List[ChannelCandidate], 
        request
    ) -> BatchedScoreComponents:
        """批量评分渠道列表"""
        start_time = time.time()
        
        # 检查缓存
        cache_key = self._get_cache_key(channels, request)
        cached_result = self._check_cache(cache_key)
        if cached_result:
            logger.info(f"BATCH_SCORER: Using cached scores for {len(channels)} channels")
            return cached_result
        
        logger.info(f"BATCH_SCORER: Computing scores for {len(channels)} channels")
        
        # 批量获取模型规格（最耗时的操作）
        model_specs = self._batch_get_model_specs(channels)
        
        # 并行计算各种评分
        async def compute_scores():
            # 在线程池中执行计算密集型任务
            loop = asyncio.get_event_loop()
            
            # 分批并行执行评分计算
            basic_scores_future = loop.run_in_executor(
                self.thread_pool,
                self._batch_calculate_basic_scores,
                channels, request
            )
            
            parameter_scores_future = loop.run_in_executor(
                self.thread_pool,
                self._batch_calculate_parameter_scores,
                channels, model_specs
            )
            
            context_scores_future = loop.run_in_executor(
                self.thread_pool,
                self._batch_calculate_context_scores,
                channels, model_specs
            )
            
            free_scores_future = loop.run_in_executor(
                self.thread_pool,
                self._batch_calculate_free_scores,
                channels, model_specs
            )
            
            # 等待所有计算完成
            basic_scores, parameter_scores, context_scores, free_scores = await asyncio.gather(
                basic_scores_future,
                parameter_scores_future, 
                context_scores_future,
                free_scores_future
            )
            
            cost_scores, speed_scores, quality_scores, reliability_scores, local_scores = basic_scores
            
            return BatchedScoreComponents(
                cost_scores=cost_scores,
                speed_scores=speed_scores,
                quality_scores=quality_scores,
                reliability_scores=reliability_scores,
                parameter_scores=parameter_scores,
                context_scores=context_scores,
                free_scores=free_scores,
                local_scores=local_scores,
                computation_time_ms=(time.time() - start_time) * 1000
            )
        
        result = await compute_scores()
        
        # 缓存结果
        self._store_cache(cache_key, result)
        
        logger.info(f"BATCH_SCORER: Computed {len(channels)} scores in {result.computation_time_ms:.1f}ms (avg: {result.computation_time_ms/len(channels):.1f}ms/channel)")
        
        return result
    
    def get_score_for_channel(
        self, 
        batch_result: BatchedScoreComponents,
        candidate: ChannelCandidate
    ) -> Dict[str, float]:
        """从批量结果中获取特定渠道的评分"""
        channel_id = candidate.channel.id
        model_name = candidate.matched_model
        key = f"{channel_id}_{model_name}" if model_name else channel_id
        
        return {
            'cost_score': batch_result.cost_scores.get(key, 0.5),
            'speed_score': batch_result.speed_scores.get(key, 0.5),
            'quality_score': batch_result.quality_scores.get(key, 0.5),
            'reliability_score': batch_result.reliability_scores.get(key, 0.5),
            'parameter_score': batch_result.parameter_scores.get(key, 0.5),
            'context_score': batch_result.context_scores.get(key, 0.5),
            'free_score': batch_result.free_scores.get(key, 0.1),
            'local_score': batch_result.local_scores.get(key, 0.1)
        }
    
    def cleanup_cache(self):
        """清理过期缓存"""
        current_time = time.time()
        expired_keys = []
        
        for key, (cached_time, _) in self.cache.items():
            if (current_time - cached_time) > self.cache_timeout:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.debug(f"BATCH_SCORER: Cleaned up {len(expired_keys)} expired cache entries")