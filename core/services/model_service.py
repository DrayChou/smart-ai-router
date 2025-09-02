"""
统一模型服务
按照架构规划文档Phase 1设计：单一数据源，统一接口，分层缓存
遵循KISS原则，提供简单直接的API
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from ..routing_models import ChannelCandidate, RoutingRequest, RoutingScore
from ..config_models import Channel
from ..models.model_info import ModelInfo, ModelCapabilities, ModelSpecs
from ..utils.openrouter_loader import get_openrouter_loader
from .cache_service import get_cache_service
from .config_service import get_config_service

logger = logging.getLogger(__name__)


class ModelService:
    """统一模型服务 - 按照规划文档设计的单一模型管理接口"""
    
    def __init__(self):
        self.cache_service = get_cache_service()
        self.config_service = get_config_service()
        
        # 恢复OpenRouter模型管理功能
        self.openrouter_loader = get_openrouter_loader()
        self._models_cache: Optional[Dict[str, ModelInfo]] = None
        
        # 恢复覆盖管理功能
        self._provider_overrides: Dict[str, Dict[str, Any]] = {}
        self._channel_overrides: Dict[str, Dict[str, Any]] = {}
        self._load_override_configs()
        
        # 路由策略配置
        self.routing_strategies = {
            'cost_first': [
                {'factor': 'cost_score', 'weight': 3.0},
                {'factor': 'free_score', 'weight': 2.0},
                {'factor': 'quality_score', 'weight': 1.0}
            ],
            'quality_optimized': [
                {'factor': 'quality_score', 'weight': 3.0},
                {'factor': 'reliability_score', 'weight': 2.0},
                {'factor': 'cost_score', 'weight': 1.0}
            ],
            'speed_optimized': [
                {'factor': 'speed_score', 'weight': 3.0},
                {'factor': 'reliability_score', 'weight': 2.0},
                {'factor': 'quality_score', 'weight': 1.0}
            ],
            'balanced': [
                {'factor': 'quality_score', 'weight': 2.0},
                {'factor': 'cost_score', 'weight': 2.0},
                {'factor': 'speed_score', 'weight': 1.5},
                {'factor': 'reliability_score', 'weight': 1.5}
            ],
            'free_first': [
                {'factor': 'free_score', 'weight': 5.0},
                {'factor': 'cost_score', 'weight': 2.0},
                {'factor': 'quality_score', 'weight': 1.0}
            ],
            'local_first': [
                {'factor': 'local_score', 'weight': 5.0},
                {'factor': 'cost_score', 'weight': 2.0},
                {'factor': 'quality_score', 'weight': 1.0}
            ]
        }
        
        logger.info("模型服务初始化完成")
    
    def get_model_info(self, model_name: str, provider: str = None, channel_id: str = None) -> Optional[ModelInfo]:
        """
        获取完整模型信息 - 支持三层覆盖机制
        1. OpenRouter基础数据 (权威数据源)
        2. Provider级别覆盖 (提供商特定调整)  
        3. Channel级别覆盖 (渠道特定的模型变化)
        """
        # 1. 从OpenRouter获取基础数据
        openrouter_models = self.openrouter_loader.load_models()
        model_info = openrouter_models.get(model_name)
        
        if not model_info:
            # 2. 如果OpenRouter没有，尝试从配置中推断
            model_info = self._create_model_info_from_config(model_name, provider)
        
        if not model_info:
            return None
        
        # 3. 应用提供商级别覆盖配置
        if provider:
            model_info = self._apply_provider_overrides(model_info, provider)
        
        # 4. 应用渠道级别覆盖配置（最高优先级）
        if channel_id:
            model_info = self.apply_channel_overrides(model_info, channel_id)
            
        return model_info
    
    def get_model_capabilities(self, model_name: str, provider: str = None) -> ModelCapabilities:
        """获取模型能力信息"""
        model_info = self.get_model_info(model_name, provider)
        return model_info.capabilities if model_info else ModelCapabilities()
    
    def get_model_specs(self, model_name: str, provider: str = None) -> ModelSpecs:
        """获取模型规格信息"""
        model_info = self.get_model_info(model_name, provider)
        return model_info.specs if model_info else ModelSpecs()
    
    def search_models_by_capabilities(self, required_capabilities: Dict[str, bool]) -> List[str]:
        """根据能力搜索模型"""
        openrouter_models = self.openrouter_loader.load_models()
        matching_models = []
        
        for model_name, model_info in openrouter_models.items():
            capabilities_dict = model_info.capabilities.to_legacy_dict()
            
            # 检查是否满足所有要求的能力
            if all(capabilities_dict.get(cap, False) >= required 
                   for cap, required in required_capabilities.items() if required):
                matching_models.append(model_name)
        
        return sorted(matching_models)
    
    async def refresh_models_cache(self) -> bool:
        """
        刷新模型缓存 - 简化版模型发现功能
        按照KISS原则，只保留核心功能
        """
        try:
            # 强制重新加载OpenRouter数据
            self.openrouter_loader._models_cache = None
            openrouter_models = self.openrouter_loader.load_models()
            
            if openrouter_models:
                # 缓存到本地
                await self.cache_service.set(
                    "openrouter_models", 
                    {k: {
                        'id': v.id,
                        'name': v.name,
                        'capabilities': v.capabilities.to_legacy_dict(),
                        'specs': {
                            'parameter_count': v.specs.parameter_count,
                            'context_length': v.specs.context_length,
                            'parameter_size_text': v.specs.parameter_size_text,
                            'context_text': v.specs.context_text
                        }
                    } for k, v in openrouter_models.items()},
                    "models",
                    ttl=3600
                )
                
                self._models_cache = openrouter_models
                logger.info(f"成功刷新 {len(openrouter_models)} 个模型的缓存")
                return True
            else:
                logger.warning("OpenRouter模型数据为空")
                return False
                
        except Exception as e:
            logger.error(f"刷新模型缓存失败: {e}")
            return False
    
    async def get_cached_models_count(self) -> int:
        """获取缓存中的模型数量"""
        try:
            openrouter_models = self.openrouter_loader.load_models()
            return len(openrouter_models)
        except Exception as e:
            logger.error(f"获取缓存模型数量失败: {e}")
            return 0
    
    async def find_candidates(self, request: RoutingRequest) -> List[ChannelCandidate]:
        """查找候选渠道 - 按照规划文档的模型查找逻辑"""
        model = request.model.strip()
        
        # 获取所有渠道
        all_channels = self.config_service.get_channels()
        if not all_channels:
            logger.warning("没有可用的渠道配置")
            return []
        
        # 处理标签模型
        if model.startswith('tag:'):
            return self._get_channels_by_tags(model, all_channels)
        
        # 处理普通模型
        return self._get_channels_by_model_name(model, all_channels)
    
    async def calculate_scores(self, candidates: List[ChannelCandidate], 
                             request: RoutingRequest) -> List[RoutingScore]:
        """计算渠道评分 - 统一评分逻辑"""
        if not candidates:
            return []
        
        # 获取路由策略
        strategy = self._get_routing_strategy(request.model, request.strategy)
        
        scores = []
        for candidate in candidates:
            try:
                score = await self._score_single_channel(candidate, request, strategy)
                if score:
                    scores.append(score)
            except Exception as e:
                logger.warning(f"评分渠道 {candidate.channel_id} 失败: {e}")
                continue
        
        return scores
    
    def get_available_models(self) -> List[str]:
        """获取所有可用模型列表 - 统一模型接口"""
        try:
            all_channels = self.config_service.get_channels()
            models = set()
            
            for channel in all_channels:
                # 使用配置的模型列表
                channel_models = getattr(channel, 'configured_models', None) or []
                models.update(channel_models)
            
            return sorted(list(models))
            
        except Exception as e:
            logger.error(f"获取可用模型列表失败: {e}")
            return []
    
    def get_channel_info(self, channel_id: str) -> Optional[dict]:
        """获取指定渠道信息"""
        try:
            all_channels = self.config_service.get_channels()
            
            for channel in all_channels:
                if channel.id == channel_id:
                    return {
                        'id': channel.id,
                        'provider': channel.provider,
                        'models_count': len(getattr(channel, 'configured_models', []) or []),
                        'priority': channel.priority,
                        'status': getattr(channel, 'status', 'unknown')
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"获取渠道信息失败: {e}")
            return None
    
    # 内部方法
    
    def _get_channels_by_tags(self, model: str, all_channels: List[Channel]) -> List[ChannelCandidate]:
        """通过标签获取渠道"""
        tag_part = model[4:]  # 移除 'tag:' 前缀
        required_tags = [tag.strip().lower() for tag in tag_part.split(',')]
        
        candidates = []
        for channel in all_channels:
            # 使用configured_models属性
            models = getattr(channel, 'configured_models', None) or []
            if not models:
                continue
                
            for model_name in models:
                model_tags = self._extract_tags_from_model_name(model_name)
                if all(tag in model_tags for tag in required_tags):
                    candidates.append(ChannelCandidate(
                        channel_id=channel.id,
                        model_name=model_name
                    ))
        
        return candidates
    
    def _get_channels_by_model_name(self, model: str, all_channels: List[Channel]) -> List[ChannelCandidate]:
        """通过模型名获取渠道"""
        candidates = []
        
        for channel in all_channels:
            models = getattr(channel, 'configured_models', None) or []
            if not models:
                continue
                
            for model_name in models:
                if model_name.lower() == model.lower():
                    candidates.append(ChannelCandidate(
                        channel_id=channel.id,
                        model_name=model_name
                    ))
        
        return candidates
    
    def _extract_tags_from_model_name(self, model_name: str) -> List[str]:
        """从模型名称中提取标签"""
        import re
        # 使用多种分隔符拆分模型名称
        separators = [':', '/', '@', '-', '_', ',']
        tags = [model_name.lower()]
        
        for sep in separators:
            new_tags = []
            for tag in tags:
                new_tags.extend([t.strip() for t in tag.split(sep) if t.strip()])
            tags = new_tags
        
        # 去重并返回
        return list(set(tag for tag in tags if tag))
    
    def _get_routing_strategy(self, model: str, strategy: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取路由策略"""
        if strategy and strategy in self.routing_strategies:
            return self.routing_strategies[strategy]
        
        # 推断策略
        model_lower = model.lower()
        if model_lower.startswith('tag:free') or 'free' in model_lower:
            return self.routing_strategies['free_first']
        elif model_lower.startswith('tag:local') or 'local' in model_lower:
            return self.routing_strategies['local_first']
        
        # 默认策略
        return self.routing_strategies['balanced']
    
    async def _score_single_channel(self, candidate: ChannelCandidate, request: RoutingRequest, 
                                  strategy: List[Dict[str, Any]]) -> Optional[RoutingScore]:
        """为单个渠道计算评分"""
        try:
            # 简化的评分计算
            scores = {}
            scores['cost_score'] = 70.0  # 基础成本评分
            scores['quality_score'] = 80.0  # 基础质量评分
            scores['speed_score'] = 75.0  # 基础速度评分
            scores['reliability_score'] = 85.0  # 基础可靠性评分
            scores['free_score'] = 100.0 if 'free' in candidate.model_name.lower() else 0.0
            scores['local_score'] = 100.0 if 'local' in candidate.model_name.lower() else 0.0
            
            # 计算总分
            total_score = 0.0
            total_weight = 0.0
            
            for factor in strategy:
                factor_name = factor.get('factor')
                weight = factor.get('weight', 1.0)
                
                if factor_name in scores:
                    total_score += scores[factor_name] * weight
                    total_weight += weight
            
            final_score = total_score / total_weight if total_weight > 0 else 0.0
            
            return RoutingScore(
                channel_id=candidate.channel_id,
                total_score=final_score,
                scores=scores,
                estimated_cost=0.001,  # 简化成本估算
                estimated_tokens=100,  # 简化token估算
                matched_model=candidate.model_name
            )
            
        except Exception as e:
            logger.error(f"评分计算失败: {e}")
            return None
    
    def _create_model_info_from_config(self, model_name: str, provider: str = None) -> Optional[ModelInfo]:
        """从配置推断模型信息（当OpenRouter没有数据时）"""
        try:
            # 基础推断逻辑
            capabilities = ModelCapabilities()
            specs = ModelSpecs()
            
            # 根据模型名称推断能力
            model_lower = model_name.lower()
            
            # 视觉能力推断
            if any(keyword in model_lower for keyword in ['vision', 'gpt-4o', 'claude-3', 'gemini-pro']):
                capabilities.supports_vision = True
            
            # 函数调用能力推断
            if any(keyword in model_lower for keyword in ['gpt-4', 'gpt-3.5', 'claude-3', 'gemini']):
                capabilities.supports_function_calling = True
            
            # 参数数量推断
            import re
            param_match = re.search(r'(\d+(?:\.\d+)?)\s*([kmb])', model_lower)
            if param_match:
                value, unit = param_match.groups()
                multiplier = {'k': 1, 'm': 1, 'b': 1000}
                specs.parameter_count = int(float(value) * multiplier.get(unit, 1))
                specs.parameter_size_text = f"{value}{unit}"
            
            # 上下文长度推断
            context_match = re.search(r'(\d+)\s*k', model_lower)
            if context_match:
                context_k = int(context_match.group(1))
                specs.context_length = context_k * 1024
                specs.context_text = f"{context_k}k"
            
            from ..models.model_info import DataSource
            
            return ModelInfo(
                model_id=model_name,
                provider=provider or "unknown",
                display_name=model_name,
                capabilities=capabilities,
                specs=specs,
                data_source=DataSource.BASIC_INFERENCE
            )
            
        except Exception as e:
            logger.warning(f"从配置推断模型信息失败 {model_name}: {e}")
            return None
    
    def _load_override_configs(self):
        """加载覆盖配置文件"""
        cache_dir = Path("cache")
        cache_dir.mkdir(exist_ok=True)
        
        # 加载提供商覆盖配置
        provider_file = cache_dir / "provider_overrides.json"
        if provider_file.exists():
            try:
                import json
                with open(provider_file, 'r', encoding='utf-8') as f:
                    self._provider_overrides = json.load(f)
                logger.info(f"加载了 {len(self._provider_overrides)} 个提供商覆盖配置")
            except Exception as e:
                logger.error(f"加载提供商覆盖配置失败: {e}")
        else:
            # 创建默认提供商覆盖配置
            self._create_default_provider_overrides(provider_file)
        
        # 加载渠道覆盖配置
        channel_file = cache_dir / "channel_overrides.json"
        if channel_file.exists():
            try:
                import json
                with open(channel_file, 'r', encoding='utf-8') as f:
                    self._channel_overrides = json.load(f)
                logger.info(f"加载了 {len(self._channel_overrides)} 个渠道覆盖配置")
            except Exception as e:
                logger.error(f"加载渠道覆盖配置失败: {e}")
    
    def _create_default_provider_overrides(self, provider_file: Path):
        """创建默认提供商覆盖配置"""
        default_overrides = {
            "siliconflow": {
                "pricing_multiplier": 0.1,  # SiliconFlow便宜10倍
                "free_models": ["qwen2.5-coder-7b-instruct", "internlm2.5-7b-chat"],
                "quality_boost": 0.0,
                "description": "SiliconFlow - 国内高性价比提供商"
            },
            "groq": {
                "pricing_multiplier": 0.0,  # Groq基本免费
                "speed_boost": 0.3,  # Groq速度提升
                "free_models": ["*"],  # 所有模型免费
                "description": "Groq - 高速推理提供商"
            },
            "ollama": {
                "pricing_multiplier": 0.0,  # 本地模型免费
                "quality_boost": -0.1,  # 质量稍低
                "is_local": True,
                "free_models": ["*"],
                "description": "Ollama - 本地部署"
            },
            "anthropic": {
                "quality_boost": 0.2,  # Claude质量提升
                "reliability_boost": 0.1,
                "description": "Anthropic - 高质量对话模型"
            },
            "openai": {
                "quality_boost": 0.15,  # OpenAI质量提升
                "reliability_boost": 0.15,
                "description": "OpenAI - 业界标准"
            }
        }
        
        try:
            import json
            with open(provider_file, 'w', encoding='utf-8') as f:
                json.dump(default_overrides, f, indent=2, ensure_ascii=False)
            self._provider_overrides = default_overrides
            logger.info(f"创建了默认提供商覆盖配置: {len(default_overrides)} 个提供商")
        except Exception as e:
            logger.error(f"创建默认提供商配置失败: {e}")
    
    def _apply_provider_overrides(self, model_info: ModelInfo, provider: str) -> ModelInfo:
        """应用提供商级别的覆盖配置 - 恢复完整逻辑"""
        provider_config = self._provider_overrides.get(provider, {})
        if not provider_config:
            return model_info
        
        # 创建副本避免修改原始数据
        import copy
        overridden_info = copy.deepcopy(model_info)
        
        # 应用价格覆盖
        pricing_multiplier = provider_config.get("pricing_multiplier", 1.0)
        if pricing_multiplier != 1.0 and overridden_info.pricing.input_price:
            overridden_info.pricing.input_price *= pricing_multiplier
            if overridden_info.pricing.output_price:
                overridden_info.pricing.output_price *= pricing_multiplier
        
        # 应用免费模型标记
        free_models = provider_config.get("free_models", [])
        if "*" in free_models or model_info.model_id in free_models:
            overridden_info.pricing.is_free = True
            overridden_info.pricing.input_price = 0.0
            overridden_info.pricing.output_price = 0.0
        
        # 应用质量提升
        quality_boost = provider_config.get("quality_boost", 0.0)
        if quality_boost != 0.0:
            overridden_info.quality_score = min(1.0, max(0.0, overridden_info.quality_score + quality_boost))
        
        # 应用可靠性提升
        reliability_boost = provider_config.get("reliability_boost", 0.0)
        if reliability_boost != 0.0:
            # 这里可以存储到额外属性，因为ModelInfo可能没有reliability_score
            pass
        
        # 应用本地标记
        if provider_config.get("is_local", False):
            overridden_info.is_local = True
        
        logger.debug(f"应用了提供商 {provider} 的覆盖配置到模型 {model_info.model_id}")
        return overridden_info
    
    def apply_channel_overrides(self, model_info: ModelInfo, channel_id: str) -> ModelInfo:
        """
        应用渠道特定覆盖配置 - 支持模型参数的细粒度覆盖
        典型场景：某渠道的同一模型价格便宜1/4但上下文减少一半
        """
        channel_config = self._channel_overrides.get(channel_id, {})
        if not channel_config:
            return model_info
        
        import copy
        overridden_info = copy.deepcopy(model_info)
        
        # 处理模型特定的覆盖配置
        model_overrides = channel_config.get("model_specific", {}).get(model_info.model_id, {})
        general_overrides = {k: v for k, v in channel_config.items() if k != "model_specific"}
        
        # 模型特定覆盖优先于通用覆盖
        all_overrides = {**general_overrides, **model_overrides}
        
        for field, value in all_overrides.items():
            # 定价覆盖
            if field == "pricing_input":
                overridden_info.pricing.input_price = value
            elif field == "pricing_output":
                overridden_info.pricing.output_price = value
            elif field == "pricing_multiplier":
                # 价格倍数覆盖
                if overridden_info.pricing.input_price:
                    overridden_info.pricing.input_price *= value
                if overridden_info.pricing.output_price:
                    overridden_info.pricing.output_price *= value
            elif field == "is_free":
                overridden_info.pricing.is_free = value
                if value:  # 如果是免费的，价格设为0
                    overridden_info.pricing.input_price = 0.0
                    overridden_info.pricing.output_price = 0.0
            
            # 模型规格覆盖
            elif field == "context_length":
                overridden_info.specs.context_length = value
                # 自动生成文本表示
                if value >= 1000:
                    overridden_info.specs.context_text = f"{value//1000}k"
                else:
                    overridden_info.specs.context_text = str(value)
            elif field == "context_multiplier":
                # 上下文长度倍数
                if overridden_info.specs.context_length:
                    overridden_info.specs.context_length = int(overridden_info.specs.context_length * value)
                    new_length = overridden_info.specs.context_length
                    overridden_info.specs.context_text = f"{new_length//1000}k" if new_length >= 1000 else str(new_length)
            elif field == "parameter_count":
                overridden_info.specs.parameter_count = value
            elif field == "max_output_tokens":
                overridden_info.specs.max_output_tokens = value
            
            # 能力覆盖
            elif field == "supports_vision":
                overridden_info.capabilities.supports_vision = value
            elif field == "supports_function_calling":
                overridden_info.capabilities.supports_function_calling = value
            elif field == "supports_streaming":
                overridden_info.capabilities.supports_streaming = value
            elif field == "supports_code_generation":
                overridden_info.capabilities.supports_code_generation = value
            
            # 质量和性能覆盖
            elif field == "quality_score":
                overridden_info.quality_score = value
            elif field == "quality_multiplier":
                overridden_info.quality_score = min(1.0, max(0.0, overridden_info.quality_score * value))
            
            # 元数据覆盖
            elif field == "is_local":
                overridden_info.is_local = value
            elif field == "display_name":
                overridden_info.display_name = value
            elif field == "provider":
                overridden_info.provider = value
        
        logger.debug(f"应用了渠道 {channel_id} 的覆盖配置到模型 {model_info.model_id}")
        return overridden_info
    
    def get_provider_override_config(self, provider: str) -> Dict[str, Any]:
        """获取提供商覆盖配置"""
        return self._provider_overrides.get(provider, {})
    
    def get_channel_override_config(self, channel_id: str) -> Dict[str, Any]:
        """获取渠道覆盖配置"""
        return self._channel_overrides.get(channel_id, {})


# 全局模型服务实例
_global_model_service: Optional[ModelService] = None


def get_model_service() -> ModelService:
    """获取全局模型服务实例"""
    global _global_model_service
    if _global_model_service is None:
        _global_model_service = ModelService()
    return _global_model_service