#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
请求前成本估算器 - Token预估优化系统
"""

import time
import re
from typing import Dict, List, Any, Optional, Tuple, NamedTuple
from dataclasses import dataclass
import logging

from .token_counter import TokenCounter
from ..yaml_config import get_yaml_config_loader

logger = logging.getLogger(__name__)


def normalize_model_name(model_name: str) -> List[str]:
    """
    标准化模型名称，处理日期戳后缀
    
    返回可能的模型名称变体，优先级从高到低：
    1. 原始名称
    2. 去除日期戳后的名称
    """
    candidates = [model_name]
    
    # 匹配日期戳模式：YYYY-MM-DD, YYYYMMDD, YYYY-MM, YYYYMM
    # 示例：gpt-5-2025-08-07 -> gpt-5
    #      claude-sonnet-4-20250514 -> claude-sonnet-4
    #      但不匹配版本号如 kimi-k2-0905 (非年份)
    date_patterns = [
        r'-20\d{2}-\d{2}-\d{2}$',     # -2025-08-07
        r'-20\d{6}$',                 # -20250514  
        r'-20\d{2}-\d{2}$',           # -2025-08
        r'-20\d{4}$',                 # -202508
    ]
    
    for pattern in date_patterns:
        if re.search(pattern, model_name):
            normalized = re.sub(pattern, '', model_name)
            if normalized != model_name and normalized not in candidates:
                candidates.append(normalized)
                logger.debug(f"DATE NORMALIZATION: {model_name} -> {normalized}")
    
    return candidates


@dataclass
class CostEstimate:
    """成本估算结果"""
    model_name: str
    channel_id: str
    prompt_tokens: int
    estimated_completion_tokens: int
    estimated_total_tokens: int
    input_cost: float
    output_cost: float
    total_estimated_cost: float
    cost_per_1k_tokens: float
    pricing_info: Dict[str, Any]
    confidence_level: str  # "high", "medium", "low"
    estimation_method: str


class ModelCostProfile(NamedTuple):
    """模型成本配置"""
    input_price_per_1k: float
    output_price_per_1k: float
    context_length: int
    typical_completion_ratio: float  # 典型完成/提示token比例


class CostEstimator:
    """请求前成本估算器"""
    
    def __init__(self):
        self.config_loader = get_yaml_config_loader()
        self._model_profiles_cache = {}
        self._last_cache_update = 0
        self._cache_ttl = 300  # 5分钟缓存
        # 🚀 添加成本估算缓存
        self._cost_preview_cache = {}
        self._preview_cache_ttl = 60  # 1分钟缓存
        
    def _get_model_pricing(self, channel_id: str, model_name: str) -> Optional[Dict[str, float]]:
        """获取模型定价信息（支持OpenRouter基准定价和渠道折扣）"""
        try:
            # 从配置中获取渠道信息
            channel = self.config_loader.get_channel_by_id(channel_id)
            if not channel:
                return None
                
            # 🚀 优先获取 OpenRouter 基准定价
            openrouter_pricing = self._get_openrouter_base_pricing(model_name)
            logger.info(f"💰 PRICING DEBUG: {channel_id} | {model_name}")
            logger.info(f"  OpenRouter baseline: {openrouter_pricing}")
            
            # 如果渠道有特定定价源，使用特定定价
            pricing_sources = [
                self._get_pricing_from_siliconflow,
                self._get_pricing_from_doubao,
                self._get_pricing_from_openai,
                self._get_pricing_from_anthropic,
            ]
            
            channel_specific_pricing = None
            for source in pricing_sources:
                pricing = source(channel, model_name)
                if pricing:
                    channel_specific_pricing = pricing
                    logger.info(f"  Channel-specific pricing: {pricing}")
                    break
            
            # 决定使用哪个定价作为基准
            # 🔧 修复：对于github provider，强制使用OpenRouter基准定价避免错误的channel_specific_pricing
            if channel.provider.lower() == 'github' and openrouter_pricing:
                base_pricing = openrouter_pricing
                logger.info(f"  🔧 GITHUB PROVIDER FIX: Using OpenRouter baseline instead of channel-specific pricing")
            else:
                base_pricing = channel_specific_pricing or openrouter_pricing or self._get_pricing_from_fallback(channel, model_name)
            logger.info(f"  Base pricing: {base_pricing}")
            
            if not base_pricing:
                logger.info(f"  ❌ No pricing found for {model_name} in {channel_id}")
                return None
                
            # 🚀 应用渠道的货币汇率折扣
            final_pricing = self._apply_currency_exchange_discount(channel, base_pricing)
            logger.info(f"  Final pricing after currency discount: {final_pricing}")
            
            logger.debug(f"PRICING: {channel_id} -> {model_name}: input=${final_pricing['input']:.6f}, output=${final_pricing['output']:.6f}")
            return final_pricing
            
        except Exception as e:
            logger.error(f"获取模型定价失败 ({channel_id}, {model_name}): {e}")
            return None
    
    def _get_pricing_from_siliconflow(self, channel, model_name: str) -> Optional[Dict[str, float]]:
        """从SiliconFlow获取定价"""
        try:
            if 'siliconflow' not in channel.provider.lower():
                return None
                
            # 🚀 改为使用新的静态定价加载器
            from .static_pricing import get_static_pricing_loader
            loader = get_static_pricing_loader()
            
            result = loader.get_siliconflow_pricing(model_name)
            if result:
                return {
                    "input": result.input_price / 1000000,  # 配置中是每百万token价格，转为每token
                    "output": result.output_price / 1000000,
                }
                
            return None
            
        except Exception as e:
            logger.debug(f"SiliconFlow定价获取失败: {e}")
            return None
    
    def _get_pricing_from_doubao(self, channel, model_name: str) -> Optional[Dict[str, float]]:
        """从豆包获取定价"""
        try:
            if 'doubao' not in channel.provider.lower() and 'bytedance' not in channel.provider.lower():
                return None
                
            # 🚀 改为使用新的静态定价加载器（统一接口）
            from .static_pricing import get_static_pricing_loader
            loader = get_static_pricing_loader()
            
            # 使用固定的输入输出token数量进行估算（实际使用时会根据真实值重新计算）
            result = loader.get_doubao_pricing(model_name, 10000, 2000)  # 默认10k输入，2k输出
            if result:
                return {
                    "input": result.input_price / 1000000,  # 配置中是每百万token价格，转为每token
                    "output": result.output_price / 1000000,
                }
                
            return None
            
        except Exception as e:
            logger.debug(f"豆包定价获取失败: {e}")
            return None
    
    def _get_pricing_from_openai(self, channel, model_name: str) -> Optional[Dict[str, float]]:
        """从OpenAI获取定价（基于模型名称的启发式定价）"""
        try:
            if 'openai' not in channel.provider.lower():
                return None
                
            # OpenAI标准定价 (2025年1月价格)
            openai_pricing = {
                "gpt-4o": {"input": 0.015, "output": 0.060},
                "gpt-4o-mini": {"input": 0.0006, "output": 0.0018},
                "gpt-4-turbo": {"input": 0.010, "output": 0.030},
                "gpt-4": {"input": 0.030, "output": 0.060},
                "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
            }
            
            # 模糊匹配模型名称
            model_lower = model_name.lower()
            for pattern, pricing in openai_pricing.items():
                if pattern in model_lower or model_lower in pattern:
                    return {
                        "input": pricing["input"] / 1000,
                        "output": pricing["output"] / 1000,
                    }
                    
            return None
            
        except Exception as e:
            logger.debug(f"OpenAI定价获取失败: {e}")
            return None
    
    def _get_pricing_from_anthropic(self, channel, model_name: str) -> Optional[Dict[str, float]]:
        """从Anthropic获取定价"""
        try:
            if 'anthropic' not in channel.provider.lower():
                return None
                
            # Anthropic标准定价
            anthropic_pricing = {
                "claude-3-5-sonnet": {"input": 0.015, "output": 0.075},
                "claude-3-5-haiku": {"input": 0.001, "output": 0.005},
                "claude-3-opus": {"input": 0.075, "output": 0.225},
            }
            
            model_lower = model_name.lower()
            for pattern, pricing in anthropic_pricing.items():
                if pattern in model_lower:
                    return {
                        "input": pricing["input"] / 1000,
                        "output": pricing["output"] / 1000,
                    }
                    
            return None
            
        except Exception as e:
            logger.debug(f"Anthropic定价获取失败: {e}")
            return None
    
    def _get_pricing_from_fallback(self, channel, model_name: str) -> Dict[str, float]:
        """回退定价策略"""
        # 基于模型名称和大小的启发式定价
        model_lower = model_name.lower()
        
        # 免费模型判断
        free_keywords = ['free', '免费', 'qwen2.5-7b', 'glm-4-9b', '1.5b', '3b', '7b']
        if any(keyword in model_lower for keyword in free_keywords):
            return {"input": 0.0, "output": 0.0}
        
        # 基于参数量估算价格
        if any(size in model_lower for size in ['1b', '3b', '7b', '9b']):
            return {"input": 0.0001, "output": 0.0002}  # 小模型
        elif any(size in model_lower for size in ['14b', '32b']):
            return {"input": 0.0007, "output": 0.0007}  # 中等模型
        elif any(size in model_lower for size in ['70b', '72b']):
            return {"input": 0.004, "output": 0.004}    # 大模型
        else:
            return {"input": 0.001, "output": 0.002}    # 默认定价
    
    def _get_openrouter_base_pricing(self, model_name: str) -> Optional[Dict[str, float]]:
        """获取OpenRouter基准定价（作为其他渠道的参考价格）"""
        try:
            # 🚀 直接使用全局model_pricing.json中已经转换的价格数据
            import json
            from pathlib import Path
            
            model_pricing_file = Path("cache/model_pricing.json")
            if not model_pricing_file.exists():
                logger.debug(f"OpenRouter基准定价文件不存在: {model_pricing_file}")
                return None
            
            with open(model_pricing_file, 'r', encoding='utf-8') as f:
                pricing_data = json.load(f)
            
            # 寻找模型定价（可能有多个变体）
            found_pricing = None
            max_price = {"input": 0.0, "output": 0.0}
            
            # 尝试精确匹配（包括日期戳变体）
            model_candidates = normalize_model_name(model_name)
            
            for candidate in model_candidates:
                if candidate in pricing_data:
                    pricing_info = pricing_data[candidate]
                    if pricing_info.get("source") == "openrouter":
                        # 🔧 UNIT FIX: 直接使用raw_pricing字段中的per_token价格
                        raw_pricing = pricing_info.get("raw_pricing", {})
                        if raw_pricing and "prompt" in raw_pricing and "completion" in raw_pricing:
                            found_pricing = {
                                "input": float(raw_pricing["prompt"]),
                                "output": float(raw_pricing["completion"])
                            }
                            logger.debug(f"OPENROUTER MATCH: {model_name} -> {candidate} -> per_token: {found_pricing}")
                        else:
                            # 缓存数据已经是per_million_tokens，直接除以1000000转为per_token
                            found_pricing = {
                                "input": pricing_info.get("input", 0) / 1000000,
                                "output": pricing_info.get("output", 0) / 1000000
                            }
                            logger.debug(f"OPENROUTER MATCH (fallback): {model_name} -> {candidate} -> per_token: {found_pricing}")
                        break  # 找到第一个匹配就停止
            
            # 如果没有精确匹配，尝试模糊匹配OpenRouter相关模型
            if not found_pricing:
                for cached_model, pricing_info in pricing_data.items():
                    if (pricing_info.get("source") == "openrouter" and 
                        model_name.lower() in cached_model.lower()):
                        
                        input_price = pricing_info.get("input", 0)
                        output_price = pricing_info.get("output", 0)
                        
                        # 跳过免费模型，寻找付费价格作为基准
                        if input_price == 0 and output_price == 0:
                            continue
                        
                        # 记录最高价格作为基准
                        if input_price > max_price["input"]:
                            max_price["input"] = input_price
                        if output_price > max_price["output"]:
                            max_price["output"] = output_price
                
                if max_price["input"] > 0 or max_price["output"] > 0:
                    # 🔧 UNIT FIX: 缓存中的价格已经是per_million_tokens，转换为per_token
                    found_pricing = {
                        "input": max_price["input"] / 1000000,
                        "output": max_price["output"] / 1000000
                    }
                    logger.debug(f"OPENROUTER FUZZY MATCH: {model_name} -> per_token: {found_pricing}")
            
            if found_pricing and (found_pricing["input"] > 0 or found_pricing["output"] > 0):
                logger.debug(f"OPENROUTER BASE: {model_name} -> input=${found_pricing['input']:.6f}, output=${found_pricing['output']:.6f}")
                return found_pricing
                
            logger.debug(f"OPENROUTER BASE: No pricing found for {model_name}")
            return None
                
        except Exception as e:
            logger.debug(f"OpenRouter基准定价获取失败: {e}")
            return None
    
    def _apply_currency_exchange_discount(self, channel, base_pricing: Dict[str, float]) -> Dict[str, float]:
        """应用渠道的货币汇率折扣"""
        try:
            # 检查渠道是否有currency_exchange配置
            if not hasattr(channel, 'currency_exchange') or not channel.currency_exchange:
                return base_pricing
            
            exchange_config = channel.currency_exchange
            if not isinstance(exchange_config, dict):
                return base_pricing
                
            exchange_rate = exchange_config.get("rate", 1.0)
            from_currency = exchange_config.get("from", "USD")
            to_currency = exchange_config.get("to", "CNY")
            description = exchange_config.get("description", "")
            
            # 应用汇率折扣 (如 0.7 汇率意味着打七折)
            discounted_pricing = {
                "input": base_pricing["input"] * exchange_rate,
                "output": base_pricing["output"] * exchange_rate,
            }
            
            logger.info(f"CURRENCY DISCOUNT: {channel.name} applied {exchange_rate}x rate ({from_currency}->{to_currency})")
            logger.info(f"  Before: input=${base_pricing['input']:.6f}, output=${base_pricing['output']:.6f}")
            logger.info(f"  After:  input=${discounted_pricing['input']:.6f}, output=${discounted_pricing['output']:.6f}")
            
            return discounted_pricing
            
        except Exception as e:
            logger.debug(f"货币汇率折扣应用失败: {e}")
            return base_pricing
    
    def estimate_cost(self, channel, model_name: str, messages: List[Dict[str, Any]], max_output_tokens: int = 1000):
        """兼容性方法：估算请求成本（用于路由器调用）"""
        try:
            estimate = self.estimate_request_cost(
                messages=messages,
                model_name=model_name,
                channel_id=channel.id,
                max_tokens=max_output_tokens
            )
            
            # 返回一个简单的成本对象，包含total_cost属性
            class SimpleCostResult:
                def __init__(self, total_cost: float):
                    self.total_cost = total_cost
                    
            return SimpleCostResult(estimate.total_estimated_cost)
            
        except Exception as e:
            logger.debug(f"成本估算失败: {e}")
            return None
    
    def estimate_request_cost(
        self, 
        messages: List[Dict[str, Any]], 
        model_name: str,
        channel_id: str,
        max_tokens: Optional[int] = None
    ) -> CostEstimate:
        """估算单个请求的成本"""
        
        # 1. Token计算
        token_stats = TokenCounter.get_token_stats(messages, max_tokens)
        prompt_tokens = token_stats["prompt_tokens"]
        estimated_completion_tokens = token_stats["estimated_completion_tokens"]
        estimated_total_tokens = token_stats["estimated_total_tokens"]
        
        # 2. 获取定价信息
        pricing = self._get_model_pricing(channel_id, model_name)
        if not pricing:
            pricing = {"input": 0.001, "output": 0.002}  # 极端回退
            confidence_level = "low"
            estimation_method = "fallback_default"
        elif pricing.get("input", 0) == 0 and pricing.get("output", 0) == 0:
            confidence_level = "high"
            estimation_method = "free_model"
        else:
            confidence_level = "medium"
            estimation_method = "pricing_database"
        
        # 3. 成本计算
        input_cost = prompt_tokens * pricing.get("input", 0)
        output_cost = estimated_completion_tokens * pricing.get("output", 0)
        total_estimated_cost = input_cost + output_cost
        
        # 4. 每1K token成本
        cost_per_1k = (total_estimated_cost / estimated_total_tokens * 1000) if estimated_total_tokens > 0 else 0
        
        return CostEstimate(
            model_name=model_name,
            channel_id=channel_id,
            prompt_tokens=prompt_tokens,
            estimated_completion_tokens=estimated_completion_tokens,
            estimated_total_tokens=estimated_total_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_estimated_cost=total_estimated_cost,
            cost_per_1k_tokens=cost_per_1k,
            pricing_info=pricing,
            confidence_level=confidence_level,
            estimation_method=estimation_method
        )
    
    def compare_channel_costs(
        self, 
        messages: List[Dict[str, Any]], 
        candidate_channels: List[Dict[str, Any]],
        max_tokens: Optional[int] = None
    ) -> List[CostEstimate]:
        """比较多个渠道的成本估算"""
        
        estimates = []
        
        for channel_info in candidate_channels:
            try:
                channel_id = channel_info.get("id", "unknown")
                model_name = channel_info.get("model_name", "unknown")
                
                estimate = self.estimate_request_cost(
                    messages=messages,
                    model_name=model_name,
                    channel_id=channel_id,
                    max_tokens=max_tokens
                )
                
                estimates.append(estimate)
                
            except Exception as e:
                logger.warning(f"成本估算失败 (渠道: {channel_info.get('id', 'unknown')}): {e}")
                continue
        
        # 按成本排序
        estimates.sort(key=lambda x: x.total_estimated_cost)
        
        return estimates
    
    def get_cost_optimization_recommendation(
        self, 
        estimates: List[CostEstimate],
        budget_limit: Optional[float] = None
    ) -> Dict[str, Any]:
        """获取成本优化建议"""
        
        if not estimates:
            return {"status": "no_estimates", "message": "没有可用的成本估算"}
        
        cheapest = estimates[0]
        most_expensive = estimates[-1] if len(estimates) > 1 else cheapest
        
        recommendation = {
            "status": "success",
            "total_candidates": len(estimates),
            "cheapest_option": {
                "channel_id": cheapest.channel_id,
                "model_name": cheapest.model_name,
                "estimated_cost": cheapest.total_estimated_cost,
                "formatted_cost": TokenCounter.format_cost(cheapest.total_estimated_cost),
                "confidence": cheapest.confidence_level
            },
            "cost_range": {
                "min_cost": cheapest.total_estimated_cost,
                "max_cost": most_expensive.total_estimated_cost,
                "cost_variation": most_expensive.total_estimated_cost - cheapest.total_estimated_cost
            }
        }
        
        # 预算检查
        if budget_limit is not None:
            within_budget = [e for e in estimates if e.total_estimated_cost <= budget_limit]
            recommendation["budget_analysis"] = {
                "limit": budget_limit,
                "within_budget_count": len(within_budget),
                "over_budget_count": len(estimates) - len(within_budget),
                "cheapest_within_budget": within_budget[0] if within_budget else None
            }
        
        # 免费选项检查
        free_options = [e for e in estimates if e.total_estimated_cost == 0]
        if free_options:
            recommendation["free_options"] = {
                "count": len(free_options),
                "channels": [{"channel_id": e.channel_id, "model_name": e.model_name} 
                           for e in free_options]
            }
        
        # 节省建议
        if len(estimates) > 1 and most_expensive.total_estimated_cost > cheapest.total_estimated_cost:
            savings = most_expensive.total_estimated_cost - cheapest.total_estimated_cost
            savings_percentage = (savings / most_expensive.total_estimated_cost) * 100
            
            recommendation["savings_potential"] = {
                "absolute_savings": savings,
                "percentage_savings": savings_percentage,
                "recommendation": f"选择最便宜的选项可节省 {TokenCounter.format_cost(savings)} ({savings_percentage:.1f}%)"
            }
        
        return recommendation
    
    def _get_preview_cache_key(
        self, 
        messages: List[Dict[str, Any]], 
        candidate_channels: List[Dict[str, Any]],
        max_tokens: Optional[int] = None
    ) -> str:
        """生成成本预览缓存键"""
        import hashlib
        
        # 提取关键信息用于缓存键
        message_content = str([msg.get('content', '')[:100] for msg in messages])  # 截取前100字符
        channel_ids = sorted([ch.get('id', '') for ch in candidate_channels])
        key_data = f"{message_content}_{channel_ids}_{max_tokens}"
        
        return hashlib.sha256(key_data.encode()).hexdigest()
    
    def create_cost_preview(
        self, 
        messages: List[Dict[str, Any]], 
        candidate_channels: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        budget_limit: Optional[float] = None
    ) -> Dict[str, Any]:
        """创建完整的成本预览"""
        
        start_time = time.time()
        
        # 🚀 检查缓存
        cache_key = self._get_preview_cache_key(messages, candidate_channels, max_tokens)
        current_time = time.time()
        
        if cache_key in self._cost_preview_cache:
            cached_time, cached_result = self._cost_preview_cache[cache_key]
            if (current_time - cached_time) < self._preview_cache_ttl:
                cache_hit_time = round((time.time() - start_time) * 1000, 2)
                logger.info(f"💰 COST CACHE: Cache hit for preview ({len(candidate_channels)} channels) in {cache_hit_time}ms")
                # 🚀 修复：正确显示缓存命中时间，但保留原始计算时间用于统计
                cached_result_copy = cached_result.copy()
                cached_result_copy['calculation_time_ms'] = cache_hit_time
                cached_result_copy['cache_hit'] = True
                return cached_result_copy
        
        # 1. 估算所有候选渠道的成本
        estimates = self.compare_channel_costs(messages, candidate_channels, max_tokens)
        
        # 2. 获取优化建议
        recommendation = self.get_cost_optimization_recommendation(estimates, budget_limit)
        
        # 3. 生成预览摘要
        preview = {
            "timestamp": time.time(),
            "calculation_time_ms": round((time.time() - start_time) * 1000, 2),
            "request_info": {
                "message_count": len(messages),
                "estimated_prompt_tokens": estimates[0].prompt_tokens if estimates else 0,
                "estimated_completion_tokens": estimates[0].estimated_completion_tokens if estimates else 0,
                "max_tokens_limit": max_tokens
            },
            "estimates": [
                {
                    "channel_id": e.channel_id,
                    "model_name": e.model_name,
                    "total_cost": e.total_estimated_cost,
                    "formatted_cost": TokenCounter.format_cost(e.total_estimated_cost),
                    "cost_per_1k_tokens": e.cost_per_1k_tokens,
                    "confidence": e.confidence_level,
                    "method": e.estimation_method
                }
                for e in estimates[:10]  # 限制前10个结果
            ],
            "recommendation": recommendation
        }
        
        # 🚀 缓存结果
        self._cost_preview_cache[cache_key] = (current_time, preview)
        
        # 清理过期缓存（简单策略：每10次调用清理一次）
        if len(self._cost_preview_cache) > 10:
            expired_keys = [
                k for k, (cached_time, _) in self._cost_preview_cache.items()
                if (current_time - cached_time) > self._preview_cache_ttl
            ]
            for k in expired_keys:
                del self._cost_preview_cache[k]
        
        logger.debug(f"💰 COST ESTIMATION: Computed {len(estimates)} estimates in {preview['calculation_time_ms']}ms")
        
        return preview


# 全局成本估算器实例
_global_cost_estimator: Optional[CostEstimator] = None

def get_cost_estimator() -> CostEstimator:
    """获取全局成本估算器"""
    global _global_cost_estimator
    if _global_cost_estimator is None:
        _global_cost_estimator = CostEstimator()
    return _global_cost_estimator