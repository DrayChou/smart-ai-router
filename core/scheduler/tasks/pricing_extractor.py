#!/usr/bin/env python3
"""
定价信息提取器 - 从discovered_models.json中提取和处理定价信息
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from decimal import Decimal
import logging

from .official_pricing import get_official_pricing_data, get_model_official_pricing

logger = logging.getLogger(__name__)

class PricingExtractor:
    """定价信息提取器"""
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # 输入文件
        self.discovered_models_file = self.cache_dir / "discovered_models.json"
        
        # 输出文件
        self.extracted_pricing_file = self.cache_dir / "extracted_pricing.json"
        self.pricing_summary_file = self.cache_dir / "pricing_summary.json"
        
        # 缓存数据
        self.model_pricing: Dict[str, Dict] = {}
        self.pricing_stats: Dict[str, Any] = {}
    
    def extract_pricing_from_discovered_models(self) -> Dict[str, Any]:
        """从discovered_models.json中提取定价信息"""
        
        if not self.discovered_models_file.exists():
            logger.error(f"未找到discovered_models.json文件: {self.discovered_models_file}")
            return {"success": False, "error": "未找到discovered_models文件"}
        
        try:
            with open(self.discovered_models_file, 'r', encoding='utf-8') as f:
                discovered_data = json.load(f)
            
            # 首先收集所有模型的OpenRouter定价，用于后续选择最高价格
            openrouter_pricing_map = {}
            
            extracted_pricing = {}
            pricing_stats = {
                "total_models": 0,
                "free_models": 0,
                "paid_models": 0,
                "official_pricing_used": 0,
                "openrouter_pricing_used": 0,
                "pricing_sources": set(),
                "price_ranges": {
                    "input_min": float('inf'),
                    "input_max": 0,
                    "output_min": float('inf'),
                    "output_max": 0
                },
                "by_provider": {},
                "special_features": {
                    "with_vision": 0,
                    "with_audio": 0,
                    "with_web_search": 0,
                    "with_reasoning": 0
                }
            }
            
            # 第一轮：收集所有OpenRouter定价，为每个模型记录最高价格
            for channel_id, channel_data in discovered_data.items():
                if not isinstance(channel_data, dict):
                    continue
                
                response_data = channel_data.get("response_data", {})
                if "data" not in response_data:
                    continue
                
                models = response_data["data"]
                if not isinstance(models, list):
                    continue
                
                # 收集每个模型的OpenRouter定价
                for model in models:
                    if not isinstance(model, dict):
                        continue
                    
                    model_id = model.get("id", "")
                    if not model_id:
                        continue
                    
                    pricing_info = model.get("pricing", {})
                    if not pricing_info:
                        continue
                    
                    try:
                        prompt_price = float(pricing_info.get("prompt", 0))
                        completion_price = float(pricing_info.get("completion", 0))
                        
                        # 转换为per million tokens
                        input_per_million = prompt_price * 1000000
                        output_per_million = completion_price * 1000000
                        
                        # 记录最高价格（如果模型已存在，选择更高的价格）
                        if model_id not in openrouter_pricing_map:
                            openrouter_pricing_map[model_id] = {
                                "input_per_million": input_per_million,
                                "output_per_million": output_per_million,
                                "model_data": model
                            }
                        else:
                            # 选择更高的价格
                            current = openrouter_pricing_map[model_id]
                            if (input_per_million + output_per_million) > (current["input_per_million"] + current["output_per_million"]):
                                openrouter_pricing_map[model_id] = {
                                    "input_per_million": input_per_million,
                                    "output_per_million": output_per_million,
                                    "model_data": model
                                }
                    
                    except (ValueError, TypeError):
                        continue
            
            logger.info(f"收集到 {len(openrouter_pricing_map)} 个模型的OpenRouter定价信息")
            
            # 第二轮：整合官方定价和OpenRouter定价
            for model_id, openrouter_data in openrouter_pricing_map.items():
                model = openrouter_data["model_data"]
                
                try:
                    # 获取基础价格信息
                    openrouter_input = openrouter_data["input_per_million"]
                    openrouter_output = openrouter_data["output_per_million"]
                    
                    pricing_info = model.get("pricing", {})
                    request_price = float(pricing_info.get("request", 0))
                    image_price = float(pricing_info.get("image", 0))
                    audio_price = float(pricing_info.get("audio", 0))
                    web_search_price = float(pricing_info.get("web_search", 0))
                    reasoning_price = float(pricing_info.get("internal_reasoning", 0))
                    
                    # 检查是否有官方定价
                    official_pricing = get_model_official_pricing(model_id)
                    if official_pricing:
                        # 使用官方定价
                        input_per_million = official_pricing["input_per_million_tokens"]
                        output_per_million = official_pricing["output_per_million_tokens"]
                        pricing_source = f"official_{official_pricing['source']}"
                        pricing_method = "official"
                        pricing_stats["official_pricing_used"] += 1
                        logger.info(f"使用官方定价: {model_id} - {pricing_source}")
                    else:
                        # 使用OpenRouter最高定价
                        input_per_million = openrouter_input
                        output_per_million = openrouter_output
                        pricing_source = "openrouter_highest"
                        pricing_method = "openrouter_highest"
                        pricing_stats["openrouter_pricing_used"] += 1
                    
                    # 构建定价信息
                    model_pricing_info = {
                        "model_id": model_id,
                        "model_name": model.get("name", model_id),
                        "pricing": {
                            "input_per_million_tokens": input_per_million,
                            "output_per_million_tokens": output_per_million,
                            "per_token": {
                                "input": input_per_million / 1000000,
                                "output": output_per_million / 1000000
                            },
                            "per_request": request_price,
                            "special_features": {
                                "image": image_price,
                                "audio": audio_price, 
                                "web_search": web_search_price,
                                "internal_reasoning": reasoning_price
                            }
                        },
                        "context_length": model.get("context_length", 0),
                        "capabilities": {
                            "modality": model.get("architecture", {}).get("modality", ""),
                            "input_modalities": model.get("architecture", {}).get("input_modalities", []),
                            "output_modalities": model.get("architecture", {}).get("output_modalities", [])
                        },
                        "source": pricing_source,
                        "provider_info": {
                            "context_length": model.get("top_provider", {}).get("context_length", 0),
                            "max_completion_tokens": model.get("top_provider", {}).get("max_completion_tokens"),
                            "is_moderated": model.get("top_provider", {}).get("is_moderated", False)
                        },
                        "extracted_at": datetime.now().isoformat(),
                        "raw_pricing": pricing_info if not official_pricing else official_pricing,
                        "pricing_method": pricing_method
                    }
                    
                    extracted_pricing[model_id] = model_pricing_info
                    
                    # 更新统计信息
                    pricing_stats["total_models"] += 1
                    
                    if input_per_million == 0 and output_per_million == 0:
                        pricing_stats["free_models"] += 1
                    else:
                        pricing_stats["paid_models"] += 1
                        
                        # 更新价格范围
                        if input_per_million > 0:
                            pricing_stats["price_ranges"]["input_min"] = min(pricing_stats["price_ranges"]["input_min"], input_per_million)
                            pricing_stats["price_ranges"]["input_max"] = max(pricing_stats["price_ranges"]["input_max"], input_per_million)
                        
                        if output_per_million > 0:
                            pricing_stats["price_ranges"]["output_min"] = min(pricing_stats["price_ranges"]["output_min"], output_per_million)
                            pricing_stats["price_ranges"]["output_max"] = max(pricing_stats["price_ranges"]["output_max"], output_per_million)
                        
                    # 统计特殊功能
                    if image_price > 0:
                        pricing_stats["special_features"]["with_vision"] += 1
                    if audio_price > 0:
                        pricing_stats["special_features"]["with_audio"] += 1
                    if web_search_price > 0:
                        pricing_stats["special_features"]["with_web_search"] += 1
                    if reasoning_price > 0:
                        pricing_stats["special_features"]["with_reasoning"] += 1
                    
                    # 按Provider分类 (从model_id推断)
                    provider = self._infer_provider_from_model_id(model_id)
                    if provider not in pricing_stats["by_provider"]:
                        pricing_stats["by_provider"][provider] = {
                            "model_count": 0,
                            "free_count": 0,
                            "paid_count": 0,
                            "avg_input_price": 0,
                            "avg_output_price": 0
                        }
                    
                    provider_stats = pricing_stats["by_provider"][provider]
                    provider_stats["model_count"] += 1
                    
                    if input_per_million == 0 and output_per_million == 0:
                        provider_stats["free_count"] += 1
                    else:
                        provider_stats["paid_count"] += 1
                        provider_stats["avg_input_price"] += input_per_million
                        provider_stats["avg_output_price"] += output_per_million
                    
                    pricing_stats["pricing_sources"].add(pricing_source)
                        
                except (ValueError, TypeError) as e:
                    logger.warning(f"处理模型 {model_id} 定价时出错: {e}")
                    continue
            
            # 计算平均价格
            for provider, stats in pricing_stats["by_provider"].items():
                if stats["paid_count"] > 0:
                    stats["avg_input_price"] /= stats["paid_count"]
                    stats["avg_output_price"] /= stats["paid_count"]
            
            # 处理无限值
            if pricing_stats["price_ranges"]["input_min"] == float('inf'):
                pricing_stats["price_ranges"]["input_min"] = 0
            if pricing_stats["price_ranges"]["output_min"] == float('inf'):
                pricing_stats["price_ranges"]["output_min"] = 0
            
            # 转换set为list以便JSON序列化
            pricing_stats["pricing_sources"] = list(pricing_stats["pricing_sources"])
            
            # 保存提取的定价数据
            self.model_pricing = extracted_pricing
            self.pricing_stats = pricing_stats
            
            self._save_extracted_data()
            
            logger.info(f"成功提取 {len(extracted_pricing)} 个模型的定价信息")
            
            return {
                "success": True,
                "total_models": len(extracted_pricing),
                "free_models": pricing_stats["free_models"],
                "paid_models": pricing_stats["paid_models"],
                "pricing_data": extracted_pricing,
                "statistics": pricing_stats
            }
            
        except Exception as e:
            logger.error(f"提取定价信息时发生异常: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    def _infer_provider_from_model_id(self, model_id: str) -> str:
        """从model_id推断Provider"""
        if "/" in model_id:
            provider_prefix = model_id.split("/")[0].lower()
            
            # 常见Provider映射
            provider_mapping = {
                "openai": "OpenAI",
                "anthropic": "Anthropic", 
                "google": "Google",
                "mistralai": "Mistral",
                "meta-llama": "Meta",
                "qwen": "Qwen",
                "deepseek": "DeepSeek",
                "groq": "Groq",
                "claude": "Anthropic",
                "gpt": "OpenAI"
            }
            
            return provider_mapping.get(provider_prefix, provider_prefix.title())
        
        # 从模型名称推断
        model_lower = model_id.lower()
        if "gpt" in model_lower or "openai" in model_lower:
            return "OpenAI"
        elif "claude" in model_lower:
            return "Anthropic"
        elif "gemini" in model_lower or "palm" in model_lower:
            return "Google"
        elif "llama" in model_lower:
            return "Meta"
        elif "mistral" in model_lower:
            return "Mistral"
        elif "qwen" in model_lower:
            return "Qwen"
        else:
            return "Unknown"
    
    def _save_extracted_data(self):
        """保存提取的数据"""
        try:
            # 保存详细定价数据
            with open(self.extracted_pricing_file, 'w', encoding='utf-8') as f:
                json.dump(self.model_pricing, f, indent=2, ensure_ascii=False)
            
            # 保存统计摘要
            with open(self.pricing_summary_file, 'w', encoding='utf-8') as f:
                json.dump(self.pricing_stats, f, indent=2, ensure_ascii=False)
            
            logger.info(f"定价数据已保存到 {self.cache_dir}")
            
        except Exception as e:
            logger.error(f"保存定价数据失败: {e}")
    
    def get_cheapest_models(self, limit: int = 10, exclude_free: bool = False) -> List[Dict]:
        """获取最便宜的模型"""
        models_with_cost = []
        
        for model_id, data in self.model_pricing.items():
            pricing = data["pricing"]
            input_cost = pricing["input_per_million_tokens"]
            output_cost = pricing["output_per_million_tokens"]
            
            # 计算综合成本（假设input:output = 1:1）
            total_cost = (input_cost + output_cost) / 2
            
            if exclude_free and total_cost == 0:
                continue
            
            models_with_cost.append({
                "model_id": model_id,
                "model_name": data["model_name"],
                "total_cost_per_million": total_cost,
                "input_cost": input_cost,
                "output_cost": output_cost,
                "provider": self._infer_provider_from_model_id(model_id),
                "context_length": data["context_length"]
            })
        
        # 按成本排序
        models_with_cost.sort(key=lambda x: x["total_cost_per_million"])
        return models_with_cost[:limit]
    
    def get_models_by_provider(self, provider: str) -> List[Dict]:
        """获取特定Provider的模型"""
        provider_models = []
        
        for model_id, data in self.model_pricing.items():
            if self._infer_provider_from_model_id(model_id).lower() == provider.lower():
                provider_models.append({
                    "model_id": model_id,
                    "model_name": data["model_name"],
                    "pricing": data["pricing"],
                    "context_length": data["context_length"],
                    "capabilities": data["capabilities"]
                })
        
        return provider_models
    
    def estimate_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> Optional[float]:
        """估算请求成本"""
        if model_id not in self.model_pricing:
            return None
        
        pricing = self.model_pricing[model_id]["pricing"]
        input_cost = pricing["input_per_million_tokens"] * input_tokens / 1000000
        output_cost = pricing["output_per_million_tokens"] * output_tokens / 1000000
        
        return input_cost + output_cost


# 全局实例
_pricing_extractor = None

def get_pricing_extractor() -> PricingExtractor:
    """获取全局定价提取器实例"""
    global _pricing_extractor
    if _pricing_extractor is None:
        _pricing_extractor = PricingExtractor()
    return _pricing_extractor


def extract_pricing_from_discovered_models() -> Dict[str, Any]:
    """提取定价信息的便捷函数"""
    extractor = get_pricing_extractor()
    return extractor.extract_pricing_from_discovered_models()


def get_cheapest_models(limit: int = 10, exclude_free: bool = False) -> List[Dict]:
    """获取最便宜模型的便捷函数"""
    extractor = get_pricing_extractor()
    return extractor.get_cheapest_models(limit, exclude_free)