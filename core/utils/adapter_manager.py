# -*- coding: utf-8 -*-
"""
适配器管理器 - 动态选择和使用正确的Provider适配器
"""

import logging
from typing import Dict, Any, Optional, Type
from ..providers.base import BaseAdapter
from ..providers.adapters.openai import OpenAIAdapter
from ..providers.adapters.anthropic import AnthropicAdapter
from ..providers.adapters.groq import GroqAdapter
from ..providers.adapters.openrouter import OpenRouterAdapter
from ..models.chat_request import ChatRequest
from ..config_models import Channel

logger = logging.getLogger(__name__)


class AdapterManager:
    """适配器管理器 - 智能选择和使用合适的Provider适配器"""
    
    def __init__(self):
        self._adapters = {}
        self._register_adapters()
    
    def _register_adapters(self):
        """注册所有可用的适配器"""
        # 按优先级注册，更专用的适配器优先
        self._adapters = {
            "openrouter": OpenRouterAdapter(),
            "anthropic": AnthropicAdapter(),
            "groq": GroqAdapter(), 
            "openai": OpenAIAdapter(),  # 默认OpenAI兼容适配器
        }
        logger.info(f"注册了 {len(self._adapters)} 个适配器")
    
    def get_adapter_for_channel(self, channel: Channel, provider: Any) -> BaseAdapter:
        """为指定渠道选择最合适的适配器"""
        provider_name = getattr(provider, 'name', channel.provider).lower()
        base_url = channel.base_url or getattr(provider, 'base_url', '')
        
        # 1. 优先匹配专用适配器
        for adapter_name, adapter in self._adapters.items():
            if hasattr(adapter, 'is_provider_match') and adapter.is_provider_match(provider_name, base_url):
                logger.debug(f"✅ 选择专用适配器: {adapter_name} for {provider_name}")
                return adapter
        
        # 2. 基于provider名称匹配
        if provider_name in self._adapters:
            logger.debug(f"✅ 选择匹配适配器: {provider_name}")
            return self._adapters[provider_name]
        
        # 3. 基于base_url特征匹配
        if base_url:
            if "openrouter.ai" in base_url.lower():
                logger.debug(f"✅ 基于URL选择OpenRouter适配器: {base_url}")
                return self._adapters["openrouter"]
            elif "anthropic" in base_url.lower():
                logger.debug(f"✅ 基于URL选择Anthropic适配器: {base_url}")
                return self._adapters["anthropic"]
            elif "groq" in base_url.lower():
                logger.debug(f"✅ 基于URL选择Groq适配器: {base_url}")
                return self._adapters["groq"]
        
        # 4. 默认使用OpenAI兼容适配器
        logger.debug(f"🔄 使用默认OpenAI适配器: {provider_name}")
        return self._adapters["openai"]
    
    def prepare_request_with_adapter(
        self,
        channel: Channel,
        provider: Any,
        request: ChatRequest,
        matched_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """使用适配器准备请求"""
        # 选择合适的适配器
        adapter = self.get_adapter_for_channel(channel, provider)
        
        # 构建ChatRequest对象（如果还不是）
        if not isinstance(request, ChatRequest):
            # 从字典构建ChatRequest
            request_dict = request if isinstance(request, dict) else request.dict()
            request = ChatRequest(**request_dict)
        
        # 设置匹配的模型
        if matched_model:
            request.model = matched_model
        
        # 使用适配器转换请求
        try:
            request_data = adapter.transform_request(request)
            headers = adapter.get_request_headers(channel, request)
            
            # 构建完整的URL
            base_url = (channel.base_url or getattr(provider, 'base_url', '')).rstrip('/')
            if not base_url.endswith('/v1'):
                base_url += '/v1'
            url = f"{base_url}/chat/completions"
            
            logger.debug(f"📡 使用适配器 {adapter.__class__.__name__} 准备请求: {request.model}")
            
            return {
                "url": url,
                "headers": headers,
                "request_data": request_data,
                "adapter": adapter
            }
            
        except Exception as e:
            logger.error(f"❌ 适配器准备请求失败: {e}")
            # 回退到基础准备方式
            return self._prepare_fallback_request(channel, provider, request, matched_model)
    
    def _prepare_fallback_request(
        self,
        channel: Channel,
        provider: Any,
        request: ChatRequest,
        matched_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """回退的请求准备方式（兼容原有逻辑）"""
        base_url = (channel.base_url or getattr(provider, 'base_url', '')).rstrip('/')
        if not base_url.endswith('/v1'):
            base_url += '/v1'
        url = f"{base_url}/chat/completions"

        headers = {"Content-Type": "application/json", "User-Agent": "smart-ai-router/0.2.0"}
        auth_type = getattr(provider, 'auth_type', 'bearer')
        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {channel.api_key}"
        elif auth_type == "x-api-key":
            headers["x-api-key"] = channel.api_key

        request_data = request.dict(exclude_unset=True) if hasattr(request, 'dict') else request
        if matched_model:
            request_data["model"] = matched_model
        
        return {
            "url": url,
            "headers": headers,
            "request_data": request_data,
            "adapter": None
        }
    
    def enhance_request_for_cost_optimization(
        self,
        request_data: Dict[str, Any],
        adapter: BaseAdapter,
        routing_strategy: str = "balanced"
    ) -> Dict[str, Any]:
        """为成本优化增强请求（特别是OpenRouter）"""
        if not isinstance(adapter, OpenRouterAdapter):
            return request_data
        
        # 🔥 核心功能：为成本优化策略自动启用价格排序
        if routing_strategy in ['cost_first', 'free_first'] or 'cost' in routing_strategy.lower():
            if "extra_body" not in request_data:
                request_data["extra_body"] = {}
            
            request_data["extra_body"]["provider"] = {"sort": "price"}
            logger.info(f"🎯 COST OPTIMIZATION: 为 {routing_strategy} 策略启用OpenRouter价格排序")
        
        return request_data


# 全局适配器管理器实例
_global_adapter_manager: Optional[AdapterManager] = None


def get_adapter_manager() -> AdapterManager:
    """获取全局适配器管理器实例"""
    global _global_adapter_manager
    if _global_adapter_manager is None:
        _global_adapter_manager = AdapterManager()
    return _global_adapter_manager