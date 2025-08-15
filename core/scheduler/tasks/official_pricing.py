#!/usr/bin/env python3
"""
官方定价数据 - 2025年最新各大厂商官方API定价
基于搜索结果和官方文档整理
"""

from typing import Dict, Any
from datetime import datetime

class OfficialPricingData:
    """官方定价数据管理器"""
    
    def __init__(self):
        self.official_pricing = self._load_official_pricing()
        self.last_updated = datetime.now()
    
    def _load_official_pricing(self) -> Dict[str, Dict[str, Any]]:
        """加载官方定价数据"""
        return {
            # ========== OpenAI 官方定价 ==========
            "gpt-4o": {
                "input_per_million_tokens": 5.0,
                "output_per_million_tokens": 15.0,
                "source": "openai_official",
                "context_length": 128000,
                "notes": "OpenAI官方API定价，2025年最新"
            },
            "gpt-4o-mini": {
                "input_per_million_tokens": 0.15,
                "output_per_million_tokens": 0.60,
                "source": "openai_official", 
                "context_length": 128000,
                "notes": "比GPT-3.5 Turbo便宜60%以上"
            },
            "gpt-4o-2024-11-20": {
                "input_per_million_tokens": 2.50,
                "output_per_million_tokens": 10.0,
                "source": "openai_official",
                "context_length": 128000,
                "notes": "最新GPT-4o版本"
            },
            "gpt-4": {
                "input_per_million_tokens": 30.0,
                "output_per_million_tokens": 60.0,
                "source": "openai_official",
                "context_length": 8192
            },
            "gpt-4-turbo": {
                "input_per_million_tokens": 10.0,
                "output_per_million_tokens": 30.0,
                "source": "openai_official",
                "context_length": 128000
            },
            "gpt-3.5-turbo": {
                "input_per_million_tokens": 0.50,
                "output_per_million_tokens": 1.50,
                "source": "openai_official",
                "context_length": 16385
            },
            "gpt-3.5-turbo-0125": {
                "input_per_million_tokens": 0.50,
                "output_per_million_tokens": 1.50,
                "source": "openai_official",
                "context_length": 16385
            },
            "gpt-3.5-turbo-instruct": {
                "input_per_million_tokens": 1.50,
                "output_per_million_tokens": 2.0,
                "source": "openai_official",
                "context_length": 4096
            },
            
            # ========== Anthropic 官方定价 ==========
            "claude-3-5-sonnet-20241022": {
                "input_per_million_tokens": 3.0,
                "output_per_million_tokens": 15.0,
                "source": "anthropic_official",
                "context_length": 200000,
                "notes": "最新Claude 3.5 Sonnet版本"
            },
            "claude-3-5-sonnet-20240620": {
                "input_per_million_tokens": 3.0,
                "output_per_million_tokens": 15.0,
                "source": "anthropic_official",
                "context_length": 200000
            },
            "claude-3-7-sonnet": {
                "input_per_million_tokens": 3.0,
                "output_per_million_tokens": 15.0,
                "source": "anthropic_official",
                "context_length": 200000,
                "notes": "包含thinking tokens，支持推理模式"
            },
            "claude-sonnet-4": {
                "input_per_million_tokens": 3.0,
                "output_per_million_tokens": 15.0,
                "source": "anthropic_official",
                "context_length": 200000,
                "notes": "最新Claude Sonnet 4，支持prompt caching可节省90%成本"
            },
            "claude-3-5-haiku-20241022": {
                "input_per_million_tokens": 0.80,
                "output_per_million_tokens": 4.0,
                "source": "anthropic_official",
                "context_length": 200000,
                "notes": "通用版本，支持prompt caching"
            },
            "claude-3-5-haiku-bedrock": {
                "input_per_million_tokens": 1.0,
                "output_per_million_tokens": 5.0,
                "source": "anthropic_official",
                "context_length": 200000,
                "notes": "Amazon Bedrock版本，60%更快推理速度"
            },
            "claude-3-opus-20240229": {
                "input_per_million_tokens": 15.0,
                "output_per_million_tokens": 75.0,
                "source": "anthropic_official",
                "context_length": 200000
            },
            "claude-3-sonnet-20240229": {
                "input_per_million_tokens": 3.0,
                "output_per_million_tokens": 15.0,
                "source": "anthropic_official",
                "context_length": 200000
            },
            "claude-3-haiku-20240307": {
                "input_per_million_tokens": 0.25,
                "output_per_million_tokens": 1.25,
                "source": "anthropic_official",
                "context_length": 200000
            },
            
            # ========== Google 官方定价 ==========
            "gemini-2.5-flash": {
                "input_per_million_tokens": 0.30,
                "output_per_million_tokens": 2.50,
                "source": "google_official",
                "context_length": 1000000,
                "notes": "支持thinking模式，费用已合并"
            },
            "gemini-2.5-flash-lite": {
                "input_per_million_tokens": 0.10,
                "output_per_million_tokens": 0.40,
                "source": "google_official",
                "context_length": 1000000,
                "notes": "最具成本效益的2.5系列模型"
            },
            "gemini-2.5-pro": {
                "input_per_million_tokens": 1.25,
                "output_per_million_tokens": 10.0,
                "source": "google_official",
                "context_length": 200000,
                "notes": "适用于200K以下提示"
            },
            "gemini-2.5-pro-long": {
                "input_per_million_tokens": 2.50,
                "output_per_million_tokens": 15.0,
                "source": "google_official",
                "context_length": 2000000,
                "notes": "适用于200K以上提示"
            },
            "gemini-1.5-pro": {
                "input_per_million_tokens": 1.25,
                "output_per_million_tokens": 5.0,
                "source": "google_official",
                "context_length": 2000000
            },
            "gemini-1.5-flash": {
                "input_per_million_tokens": 0.075,
                "output_per_million_tokens": 0.30,
                "source": "google_official",
                "context_length": 1000000
            },
            
            # ========== DeepSeek 官方定价 ==========
            "deepseek-chat": {
                "input_per_million_tokens": 0.27,
                "output_per_million_tokens": 1.10,
                "source": "deepseek_official",
                "context_length": 64000,
                "notes": "标准时段价格(UTC 00:30-16:30)，非高峰期50%折扣"
            },
            "deepseek-chat-off-peak": {
                "input_per_million_tokens": 0.135,
                "output_per_million_tokens": 0.550,
                "source": "deepseek_official",
                "context_length": 64000,
                "notes": "折扣时段价格(UTC 16:30-00:30)"
            },
            "deepseek-r1": {
                "input_per_million_tokens": 0.55,
                "output_per_million_tokens": 2.19,
                "source": "deepseek_official",
                "context_length": 64000,
                "notes": "推理模型，标准时段价格，非高峰期75%折扣"
            },
            "deepseek-r1-off-peak": {
                "input_per_million_tokens": 0.135,
                "output_per_million_tokens": 0.550,
                "source": "deepseek_official",
                "context_length": 64000,
                "notes": "推理模型，折扣时段价格"
            },
            
            # ========== Meta Llama 模型定价 ==========
            "llama-3.3-70b-instruct": {
                "input_per_million_tokens": 0.924,
                "output_per_million_tokens": 0.924,
                "source": "aimlapi_pricing",
                "context_length": 128000,
                "notes": "Meta Llama 3.3 70B Instruct Turbo"
            },
            "llama-3.2-3b-instruct": {
                "input_per_million_tokens": 0.003,
                "output_per_million_tokens": 0.006,
                "source": "openrouter_min",
                "context_length": 20000,
                "notes": "基于OpenRouter最低价格"
            },
            "llama-3.2-1b-instruct": {
                "input_per_million_tokens": 0.005,
                "output_per_million_tokens": 0.01,
                "source": "openrouter_min",
                "context_length": 131072,
                "notes": "基于OpenRouter最低价格"
            },
            
            # ========== 免费模型 ==========
            # Groq 免费模型
            "llama-3.1-8b-instant": {
                "input_per_million_tokens": 0.0,
                "output_per_million_tokens": 0.0,
                "source": "groq_free",
                "context_length": 8192,
                "notes": "Groq提供免费服务"
            },
            "llama-3.1-70b-versatile": {
                "input_per_million_tokens": 0.0,
                "output_per_million_tokens": 0.0,
                "source": "groq_free",
                "context_length": 8192,
                "notes": "Groq提供免费服务"
            },
            "llama-3.2-1b-preview": {
                "input_per_million_tokens": 0.0,
                "output_per_million_tokens": 0.0,
                "source": "groq_free",
                "context_length": 8192,
                "notes": "Groq提供免费服务"
            },
            "llama-3.2-3b-preview": {
                "input_per_million_tokens": 0.0,
                "output_per_million_tokens": 0.0,
                "source": "groq_free",
                "context_length": 8192,
                "notes": "Groq提供免费服务"
            },
            "llama-3.2-11b-text-preview": {
                "input_per_million_tokens": 0.0,
                "output_per_million_tokens": 0.0,
                "source": "groq_free",
                "context_length": 8192,
                "notes": "Groq提供免费服务"
            },
            "llama-3.2-90b-text-preview": {
                "input_per_million_tokens": 0.0,
                "output_per_million_tokens": 0.0,
                "source": "groq_free",
                "context_length": 8192,
                "notes": "Groq提供免费服务"
            },
            "mixtral-8x7b-32768": {
                "input_per_million_tokens": 0.0,
                "output_per_million_tokens": 0.0,
                "source": "groq_free",
                "context_length": 32768,
                "notes": "Groq提供免费服务"
            },
            "gemma2-9b-it": {
                "input_per_million_tokens": 0.0,
                "output_per_million_tokens": 0.0,
                "source": "groq_free",
                "context_length": 8192,
                "notes": "Groq提供免费服务"
            },
            "gemma-7b-it": {
                "input_per_million_tokens": 0.0,
                "output_per_million_tokens": 0.0,
                "source": "groq_free",
                "context_length": 8192,
                "notes": "Groq提供免费服务"
            }
        }
    
    def get_official_pricing(self, model_id: str) -> Dict[str, Any]:
        """获取模型的官方定价"""
        # 直接匹配
        if model_id in self.official_pricing:
            return self.official_pricing[model_id]
        
        # 模糊匹配
        model_lower = model_id.lower()
        for official_id, pricing in self.official_pricing.items():
            if official_id.lower() in model_lower or model_lower in official_id.lower():
                return pricing
        
        return None
    
    def get_all_official_models(self) -> Dict[str, Dict[str, Any]]:
        """获取所有官方定价模型"""
        return self.official_pricing.copy()
    
    def update_pricing_data(self, model_id: str, pricing_data: Dict[str, Any]):
        """更新特定模型的定价数据"""
        self.official_pricing[model_id] = pricing_data
        self.last_updated = datetime.now()
    
    def get_pricing_by_provider(self, provider: str) -> Dict[str, Dict[str, Any]]:
        """按提供商获取定价数据"""
        provider_lower = provider.lower()
        source_mapping = {
            "openai": "openai_official",
            "anthropic": "anthropic_official", 
            "google": "google_official",
            "deepseek": "deepseek_official",
            "meta": "openrouter_min",
            "groq": "groq_free"
        }
        
        target_source = source_mapping.get(provider_lower)
        if not target_source:
            return {}
        
        return {
            model_id: pricing 
            for model_id, pricing in self.official_pricing.items() 
            if pricing.get("source") == target_source
        }


# 全局实例
_official_pricing = None

def get_official_pricing_data() -> OfficialPricingData:
    """获取全局官方定价数据实例"""
    global _official_pricing
    if _official_pricing is None:
        _official_pricing = OfficialPricingData()
    return _official_pricing


def get_model_official_pricing(model_id: str) -> Dict[str, Any]:
    """获取模型官方定价的便捷函数"""
    pricing_data = get_official_pricing_data()
    return pricing_data.get_official_pricing(model_id)


def list_official_models() -> Dict[str, Dict[str, Any]]:
    """列出所有官方定价模型的便捷函数"""
    pricing_data = get_official_pricing_data()
    return pricing_data.get_all_official_models()