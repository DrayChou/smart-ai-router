#!/usr/bin/env python3
"""
定价发现任务 - 自动获取各厂商的模型定价信息
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from decimal import Decimal
import httpx
import logging

logger = logging.getLogger(__name__)

class PricingDiscoveryTask:
    """定价发现任务类"""
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # 缓存文件路径
        self.pricing_cache_file = self.cache_dir / "model_pricing.json"
        self.pricing_log_file = self.cache_dir / "pricing_discovery_log.json"
        self.provider_pricing_file = self.cache_dir / "provider_pricing.json"
        
        # 全局定价缓存
        self.cached_pricing: Dict[str, Dict] = {}
        self.provider_pricing: Dict[str, Dict] = {}
        self.last_update: Optional[datetime] = None
        
        # 定价数据源配置
        self.pricing_sources = {
            "openrouter": {
                "url": "https://openrouter.ai/api/v1/models",
                "headers": {"Content-Type": "application/json"},
                "timeout": 30
            },
            "openai_official": {
                "url": "https://api.openai.com/v1/models", 
                "pricing_url": "https://openai.com/api/pricing/",
                "static_pricing": self._get_openai_static_pricing()
            },
            "anthropic_official": {
                "url": "https://api.anthropic.com/v1/models",
                "static_pricing": self._get_anthropic_static_pricing()
            }
        }
        
        # 加载现有缓存
        self._load_cache()
    
    def _get_openai_static_pricing(self) -> Dict[str, Dict]:
        """OpenAI官方静态定价 (2025年最新)"""
        return {
            "gpt-4o": {"input": 5.0, "output": 15.0, "unit": "per_million_tokens"},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60, "unit": "per_million_tokens"},
            "gpt-4-turbo": {"input": 10.0, "output": 30.0, "unit": "per_million_tokens"},
            "gpt-4": {"input": 30.0, "output": 60.0, "unit": "per_million_tokens"},
            "gpt-3.5-turbo": {"input": 0.50, "output": 1.50, "unit": "per_million_tokens"},
            "gpt-3.5-turbo-0125": {"input": 0.50, "output": 1.50, "unit": "per_million_tokens"},
            "gpt-3.5-turbo-instruct": {"input": 1.50, "output": 2.0, "unit": "per_million_tokens"},
            "text-embedding-3-small": {"input": 0.02, "output": 0.0, "unit": "per_million_tokens"},
            "text-embedding-3-large": {"input": 0.13, "output": 0.0, "unit": "per_million_tokens"},
            "text-embedding-ada-002": {"input": 0.10, "output": 0.0, "unit": "per_million_tokens"},
        }
    
    def _get_anthropic_static_pricing(self) -> Dict[str, Dict]:
        """Anthropic官方静态定价 (2025年最新)"""
        return {
            "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0, "unit": "per_million_tokens"},
            "claude-3-5-sonnet-20240620": {"input": 3.0, "output": 15.0, "unit": "per_million_tokens"}, 
            "claude-3-5-haiku-20241022": {"input": 1.0, "output": 5.0, "unit": "per_million_tokens"},
            "claude-3-opus-20240229": {"input": 15.0, "output": 75.0, "unit": "per_million_tokens"},
            "claude-3-sonnet-20240229": {"input": 3.0, "output": 15.0, "unit": "per_million_tokens"},
            "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25, "unit": "per_million_tokens"},
        }
    
    def _load_cache(self):
        """加载现有缓存数据"""
        try:
            if self.pricing_cache_file.exists():
                with open(self.pricing_cache_file, 'r', encoding='utf-8') as f:
                    self.cached_pricing = json.load(f)
                logger.info(f"已加载缓存的定价数据: {len(self.cached_pricing)} 个模型")
            
            if self.provider_pricing_file.exists():
                with open(self.provider_pricing_file, 'r', encoding='utf-8') as f:
                    self.provider_pricing = json.load(f)
                logger.info(f"已加载Provider定价数据: {len(self.provider_pricing)} 个Provider")
                
        except Exception as e:
            logger.error(f"加载定价缓存失败: {e}")
    
    def _save_cache(self):
        """保存缓存数据"""
        try:
            # 保存模型定价缓存
            with open(self.pricing_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cached_pricing, f, indent=2, ensure_ascii=False)
            
            # 保存Provider定价数据
            with open(self.provider_pricing_file, 'w', encoding='utf-8') as f:
                json.dump(self.provider_pricing, f, indent=2, ensure_ascii=False)
            
            logger.info(f"定价缓存已保存到 {self.cache_dir}")
            
        except Exception as e:
            logger.error(f"保存定价缓存失败: {e}")
    
    async def _fetch_openrouter_pricing(self) -> Dict[str, Dict]:
        """从OpenRouter获取定价信息"""
        source = self.pricing_sources["openrouter"]
        pricing_data = {}
        
        try:
            timeout = httpx.Timeout(source["timeout"])
            async with httpx.AsyncClient(timeout=timeout) as client:
                logger.info("正在从OpenRouter获取模型定价...")
                
                response = await client.get(source["url"], headers=source["headers"])
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if "data" in data:
                        for model in data["data"]:
                            model_id = model.get("id", "")
                            if not model_id:
                                continue
                            
                            pricing = model.get("pricing", {})
                            if pricing:
                                # 转换定价单位 (OpenRouter通常使用per-token pricing)
                                input_price = float(pricing.get("prompt", 0)) * 1000000  # 转为per million tokens
                                output_price = float(pricing.get("completion", 0)) * 1000000
                                
                                pricing_data[model_id] = {
                                    "input": input_price,
                                    "output": output_price,
                                    "unit": "per_million_tokens",
                                    "context_length": model.get("context_length", 0),
                                    "source": "openrouter",
                                    "last_updated": datetime.now().isoformat(),
                                    "raw_pricing": pricing  # 保留原始数据
                                }
                    
                    logger.info(f"从OpenRouter获取了 {len(pricing_data)} 个模型的定价")
                    return pricing_data
                else:
                    logger.error(f"OpenRouter API请求失败: {response.status_code}")
                    return {}
                    
        except Exception as e:
            logger.error(f"获取OpenRouter定价时发生异常: {e}")
            return {}
    
    def _apply_static_pricing(self, provider: str, pricing_data: Dict[str, Dict]) -> Dict[str, Dict]:
        """应用静态定价数据"""
        if provider in self.pricing_sources:
            static_pricing = self.pricing_sources[provider].get("static_pricing", {})
            
            for model_id, prices in static_pricing.items():
                pricing_data[model_id] = {
                    **prices,
                    "source": f"{provider}_static",
                    "last_updated": datetime.now().isoformat()
                }
                
            logger.info(f"应用了 {len(static_pricing)} 个 {provider} 静态定价")
        
        return pricing_data
    
    async def discover_pricing(self) -> Dict[str, Any]:
        """发现所有来源的定价信息"""
        logger.info("开始定价发现任务")
        
        all_pricing = {}
        sources_status = {}
        
        # 1. 从OpenRouter获取定价
        try:
            openrouter_pricing = await self._fetch_openrouter_pricing()
            all_pricing.update(openrouter_pricing)
            sources_status["openrouter"] = {
                "success": True,
                "models_count": len(openrouter_pricing),
                "last_updated": datetime.now().isoformat()
            }
        except Exception as e:
            sources_status["openrouter"] = {
                "success": False,
                "error": str(e),
                "last_updated": datetime.now().isoformat()
            }
        
        # 2. 应用OpenAI静态定价
        all_pricing = self._apply_static_pricing("openai_official", all_pricing)
        sources_status["openai_official"] = {
            "success": True,
            "models_count": len(self._get_openai_static_pricing()),
            "type": "static_pricing"
        }
        
        # 3. 应用Anthropic静态定价
        all_pricing = self._apply_static_pricing("anthropic_official", all_pricing)
        sources_status["anthropic_official"] = {
            "success": True,
            "models_count": len(self._get_anthropic_static_pricing()),
            "type": "static_pricing"
        }
        
        # 4. 处理特殊厂商 (Groq免费等)
        groq_models = [
            "llama-3.1-8b-instant", "llama-3.1-70b-versatile", "llama-3.2-1b-preview",
            "llama-3.2-3b-preview", "llama-3.2-11b-text-preview", "llama-3.2-90b-text-preview",
            "mixtral-8x7b-32768", "gemma2-9b-it", "gemma-7b-it"
        ]
        
        for model in groq_models:
            all_pricing[model] = {
                "input": 0.0,
                "output": 0.0,
                "unit": "per_million_tokens",
                "source": "groq_free",
                "last_updated": datetime.now().isoformat(),
                "note": "Groq提供免费服务"
            }
        
        sources_status["groq_free"] = {
            "success": True,
            "models_count": len(groq_models),
            "type": "free_tier"
        }
        
        # 记录发现日志
        discovery_log = {
            "timestamp": datetime.now().isoformat(),
            "total_models": len(all_pricing),
            "sources_status": sources_status,
            "pricing_summary": {
                "free_models": len([m for m in all_pricing.values() if m.get("input", 0) == 0 and m.get("output", 0) == 0]),
                "paid_models": len([m for m in all_pricing.values() if m.get("input", 0) > 0 or m.get("output", 0) > 0]),
                "average_input_price": sum(m.get("input", 0) for m in all_pricing.values()) / len(all_pricing) if all_pricing else 0,
                "average_output_price": sum(m.get("output", 0) for m in all_pricing.values()) / len(all_pricing) if all_pricing else 0
            }
        }
        
        # 保存发现日志
        try:
            with open(self.pricing_log_file, 'w', encoding='utf-8') as f:
                json.dump(discovery_log, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存定价发现日志失败: {e}")
        
        logger.info(f"定价发现完成: 共 {len(all_pricing)} 个模型")
        
        return {
            "success": True,
            "total_models": len(all_pricing),
            "sources": sources_status,
            "pricing_data": all_pricing,
            "last_update": datetime.now().isoformat()
        }
    
    def get_model_pricing(self, model_id: str) -> Optional[Dict[str, Any]]:
        """获取特定模型的定价信息"""
        return self.cached_pricing.get(model_id)
    
    def get_cheapest_models(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最便宜的模型"""
        models_with_prices = []
        
        for model_id, pricing in self.cached_pricing.items():
            if pricing.get("input", 0) == 0 and pricing.get("output", 0) == 0:
                # 免费模型
                cost_score = 0.0
            else:
                # 计算综合成本 (假设input:output = 1:1的比例)
                input_cost = pricing.get("input", 0)
                output_cost = pricing.get("output", 0)
                cost_score = (input_cost + output_cost) / 2
            
            models_with_prices.append({
                "model_id": model_id,
                "cost_score": cost_score,
                "pricing": pricing
            })
        
        # 按成本排序
        models_with_prices.sort(key=lambda x: x["cost_score"])
        
        return models_with_prices[:limit]
    
    def estimate_request_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> Optional[float]:
        """估算请求成本"""
        pricing = self.get_model_pricing(model_id)
        if not pricing:
            return None
        
        input_cost = pricing.get("input", 0) * input_tokens / 1000000
        output_cost = pricing.get("output", 0) * output_tokens / 1000000
        
        return input_cost + output_cost
    
    async def run_pricing_discovery_task(self) -> Dict[str, Any]:
        """运行完整的定价发现任务"""
        logger.info("启动定价发现任务")
        
        try:
            # 发现定价
            result = await self.discover_pricing()
            
            if result.get("success"):
                # 更新缓存
                self.cached_pricing = result["pricing_data"]
                
                # 保存缓存
                self._save_cache()
                
                # 更新时间戳
                self.last_update = datetime.now()
            
            return result
            
        except Exception as e:
            logger.error(f"定价发现任务失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "last_update": datetime.now().isoformat()
            }
    
    def is_cache_valid(self, max_age_hours: int = 24) -> bool:
        """检查定价缓存是否有效"""
        if not self.last_update:
            return False
        
        age = datetime.now() - self.last_update
        return age <= timedelta(hours=max_age_hours)


# 全局实例
_pricing_discovery_task = None

def get_pricing_discovery_task() -> PricingDiscoveryTask:
    """获取全局定价发现任务实例"""
    global _pricing_discovery_task
    if _pricing_discovery_task is None:
        _pricing_discovery_task = PricingDiscoveryTask()
    return _pricing_discovery_task


async def run_pricing_discovery() -> Dict[str, Any]:
    """运行定价发现任务的便捷函数"""
    task = get_pricing_discovery_task()
    return await task.run_pricing_discovery_task()


def get_model_pricing(model_id: str) -> Optional[Dict[str, Any]]:
    """获取模型定价的便捷函数"""
    task = get_pricing_discovery_task()
    return task.get_model_pricing(model_id)


def get_cheapest_models(limit: int = 10) -> List[Dict[str, Any]]:
    """获取最便宜模型的便捷函数"""
    task = get_pricing_discovery_task()
    return task.get_cheapest_models(limit)