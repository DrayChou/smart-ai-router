"""
基于JSON配置的轻量路由引擎
"""
import random
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import time
import logging

from .yaml_config import YAMLConfigLoader, get_yaml_config_loader
from .config_models import Channel

logger = logging.getLogger(__name__)

class TagNotFoundError(Exception):
    """标签未找到错误"""
    def __init__(self, tags: List[str], message: str = None):
        self.tags = tags
        if message is None:
            if len(tags) == 1:
                message = f"没有找到匹配标签 '{tags[0]}' 的模型"
            else:
                message = f"没有找到同时匹配标签 {tags} 的模型"
        super().__init__(message)

@dataclass
class RoutingScore:
    """路由评分结果"""
    channel: Channel
    total_score: float
    cost_score: float
    speed_score: float
    quality_score: float
    reliability_score: float
    reason: str
    matched_model: Optional[str] = None  # 对于标签路由，记录实际匹配的模型

@dataclass
class ChannelCandidate:
    """候选渠道信息"""
    channel: Channel
    matched_model: Optional[str] = None  # 对于标签路由，记录实际匹配的模型

@dataclass
class RoutingRequest:
    """路由请求"""
    model: str
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    functions: Optional[List[Dict[str, Any]]] = None
    required_capabilities: List[str] = None

class JSONRouter:
    """基于Pydantic验证后配置的路由器"""
    
    def __init__(self, config_loader: Optional[YAMLConfigLoader] = None):
        self.config_loader = config_loader or get_yaml_config_loader()
        self.config = self.config_loader.config
        
        # 标签缓存，避免重复计算
        self._tag_cache: Dict[str, List[str]] = {}
        self._available_tags_cache: Optional[set] = None
        self._available_models_cache: Optional[List[str]] = None
        
    def route_request(self, request: RoutingRequest) -> List[RoutingScore]:
        """
        路由请求，返回按评分排序的候选渠道列表。
        """
        logger.info(f"🚀 ROUTING START: Processing request for model '{request.model}'")
        try:
            # 第一步：获取候选渠道
            logger.info(f"🔍 STEP 1: Finding candidate channels...")
            candidates = self._get_candidate_channels(request)
            if not candidates:
                logger.warning(f"❌ ROUTING FAILED: No suitable channels found for model '{request.model}'")
                return []
            
            logger.info(f"✅ STEP 1 COMPLETE: Found {len(candidates)} candidate channels")
            
            # 第二步：过滤渠道
            logger.info(f"🔧 STEP 2: Filtering channels by health and availability...")
            filtered_candidates = self._filter_channels(candidates, request)
            if not filtered_candidates:
                logger.warning(f"❌ ROUTING FAILED: No available channels after filtering for model '{request.model}'")
                return []
            
            logger.info(f"✅ STEP 2 COMPLETE: {len(filtered_candidates)} channels passed filtering (filtered out {len(candidates) - len(filtered_candidates)})")
            
            # 第三步：评分和排序
            logger.info(f"🎯 STEP 3: Scoring and ranking channels...")
            scored_channels = self._score_channels(filtered_candidates, request)
            if not scored_channels:
                logger.warning(f"❌ ROUTING FAILED: Failed to score any channels for model '{request.model}'")
                return []
            
            logger.info(f"✅ STEP 3 COMPLETE: Scored {len(scored_channels)} channels")
            logger.info(f"🎉 ROUTING SUCCESS: Ready to attempt {len(scored_channels)} channels in ranked order for model '{request.model}'")
            
            return scored_channels
            
        except TagNotFoundError:
            # 让TagNotFoundError传播出去，以便上层处理
            raise
        except Exception as e:
            logger.error(f"❌ ROUTING ERROR: Request failed for model '{request.model}': {e}", exc_info=True)
            return []
    
    def _get_candidate_channels(self, request: RoutingRequest) -> List[ChannelCandidate]:
        """获取候选渠道，支持按标签集合或物理模型进行智能路由"""
        
        if request.model.startswith("tag:"):
            tag_query = request.model.split(":", 1)[1]
            
            # 支持多标签查询，用逗号分隔：tag:qwen,free
            if "," in tag_query:
                tags = [tag.strip().lower() for tag in tag_query.split(",")]
                logger.info(f"🏷️  TAG ROUTING: Processing multi-tag query '{request.model}' -> tags: {tags}")
                candidates = self._get_candidate_channels_by_auto_tags(tags)
                if not candidates:
                    logger.error(f"❌ TAG NOT FOUND: No models found matching all tags {tags}")
                    raise TagNotFoundError(tags)
                logger.info(f"🏷️  TAG ROUTING: Multi-tag query found {len(candidates)} candidate channels")
                return candidates
            else:
                # 单标签查询 - 直接从模型发现缓存中查找
                tag = tag_query.strip().lower()
                logger.info(f"🏷️  TAG ROUTING: Processing single tag query '{request.model}' -> tag: '{tag}'")
                
                candidates = self._get_candidate_channels_by_auto_tags([tag])
                if not candidates:
                    logger.error(f"❌ TAG NOT FOUND: No models found matching tag '{tag}'")
                    raise TagNotFoundError([tag])
                logger.info(f"🏷️  TAG ROUTING: Found {len(candidates)} candidate channels for tag '{tag}'")
                return candidates
        
        # 非tag:前缀的模型名称 - 首先尝试物理模型，然后尝试自动标签化
        candidate_channels = []
        all_enabled_channels = self.config_loader.get_enabled_channels()
        model_cache = self.config_loader.get_model_cache()

        # 1. 首先尝试作为物理模型查找
        for channel in all_enabled_channels:
            if channel.id in model_cache:
                discovered_info = model_cache[channel.id]
                if request.model in discovered_info.get("models", []):
                    # 对于物理模型，matched_model 就是请求的模型
                    candidate_channels.append(ChannelCandidate(
                        channel=channel,
                        matched_model=request.model
                    ))
        
        if candidate_channels:
            logger.info(f"Found {len(candidate_channels)} candidate channels for physical model '{request.model}'")
            return candidate_channels

        # 2. 如果作为物理模型没找到，尝试自动标签化
        logger.info(f"🔄 AUTO TAGGING: No physical model found for '{request.model}', trying automatic tag extraction")
        auto_tags = self._extract_tags_from_model_name(request.model)
        if auto_tags:
            logger.info(f"🏷️  AUTO TAGGING: Extracted tags {auto_tags} from model name '{request.model}'")
            candidates = self._get_candidate_channels_by_auto_tags(auto_tags)
            if candidates:
                logger.info(f"🏷️  AUTO TAGGING: Found {len(candidates)} candidate channels using auto-extracted tags")
                return candidates
            else:
                logger.warning(f"🏷️  AUTO TAGGING: No channels found for auto-extracted tags {auto_tags}")
        
        # 3. 最后尝试从配置中查找
        config_channels = self.config_loader.get_channels_by_model(request.model)
        if config_channels:
            logger.info(f"Found {len(config_channels)} channels in configuration for model '{request.model}'")
            return [ChannelCandidate(channel=ch, matched_model=request.model) for ch in config_channels]
        
        # 如果都没找到，返回空列表
        logger.warning(f"❌ NO MATCH: No channels found for model '{request.model}' (tried physical, auto-tag, and config)")
        return []
    
    def _filter_channels(self, channels: List[ChannelCandidate], request: RoutingRequest) -> List[ChannelCandidate]:
        """过滤渠道"""
        filtered = []
        for candidate in channels:
            channel = candidate.channel
            if not channel.enabled or not channel.api_key:
                continue
            
            health_score = self.config_loader.runtime_state.health_scores.get(channel.id, 1.0)
            if health_score < 0.3:
                continue
            
            # TODO: Add capability filtering when needed
            # if request.required_capabilities:
            #     if not all(cap in channel.capabilities for cap in request.required_capabilities):
            #         continue
            
            filtered.append(candidate)
        return filtered
    
    def _score_channels(self, channels: List[ChannelCandidate], request: RoutingRequest) -> List[RoutingScore]:
        """计算渠道评分"""
        logger.info(f"📊 SCORING: Evaluating {len(channels)} candidate channels for model '{request.model}'")
        
        scored_channels = []
        strategy = self._get_routing_strategy(request.model)
        
        logger.info(f"📊 SCORING: Using routing strategy with {len(strategy)} rules")
        for rule in strategy:
            logger.debug(f"📊 SCORING: Strategy rule: {rule['field']} (weight: {rule['weight']}, order: {rule['order']})")
        
        for candidate in channels:
            channel = candidate.channel
            cost_score = self._calculate_cost_score(channel, request)
            speed_score = self._calculate_speed_score(channel)
            quality_score = self._calculate_quality_score(channel, candidate.matched_model)
            reliability_score = self._calculate_reliability_score(channel)
            
            total_score = self._calculate_total_score(
                strategy, cost_score, speed_score, quality_score, reliability_score
            )
            
            # 为了减少日志冗余，只显示模型名称和总分
            model_display = candidate.matched_model or channel.model_name
            logger.info(f"📊 SCORE: '{channel.name}' -> '{model_display}' = {total_score:.3f} (Q:{quality_score:.2f})")
            
            scored_channels.append(RoutingScore(
                channel=channel, total_score=total_score, cost_score=cost_score,
                speed_score=speed_score, quality_score=quality_score,
                reliability_score=reliability_score, 
                reason=f"cost:{cost_score:.2f} speed:{speed_score:.2f} quality:{quality_score:.2f} reliability:{reliability_score:.2f}",
                matched_model=candidate.matched_model
            ))
        
        scored_channels.sort(key=lambda x: x.total_score, reverse=True)
        
        logger.info(f"🏆 SCORING RESULT: Channels ranked by score:")
        for i, scored in enumerate(scored_channels[:5]):  # 只显示前5个
            logger.info(f"🏆   #{i+1}: '{scored.channel.name}' (Score: {scored.total_score:.3f})")
        
        return scored_channels
    
    def _get_routing_strategy(self, model: str) -> List[Dict[str, Any]]:
        """获取并解析路由策略，始终返回规则列表"""
        strategy_name = self.config.routing.default_strategy

        predefined_strategies = {
            "cost_optimized": [
                {"field": "cost_score", "order": "desc", "weight": 0.7},
                {"field": "reliability_score", "order": "desc", "weight": 0.2},
                {"field": "speed_score", "order": "desc", "weight": 0.1}
            ],
            "speed_optimized": [
                {"field": "speed_score", "order": "desc", "weight": 0.6},
                {"field": "reliability_score", "order": "desc", "weight": 0.2},
                {"field": "cost_score", "order": "desc", "weight": 0.2}
            ],
            "quality_optimized": [
                {"field": "quality_score", "order": "desc", "weight": 0.6},
                {"field": "reliability_score", "order": "desc", "weight": 0.2},
                {"field": "cost_score", "order": "desc", "weight": 0.2}
            ],
            "balanced": [
                {"field": "cost_score", "order": "desc", "weight": 0.3},
                {"field": "speed_score", "order": "desc", "weight": 0.3},
                {"field": "quality_score", "order": "desc", "weight": 0.2},
                {"field": "reliability_score", "order": "desc", "weight": 0.2}
            ]
        }
        
        return predefined_strategies.get(strategy_name, predefined_strategies["balanced"])

    def _calculate_cost_score(self, channel: Channel, request: RoutingRequest) -> float:
        """计算成本评分(0-1，越低成本越高分)"""
        pricing = channel.pricing
        if not pricing:
            return 0.5
        
        # 估算token数量
        input_tokens = self._estimate_tokens(request.messages)
        max_output_tokens = request.max_tokens or 1000
        
        # 计算成本
        input_cost = pricing.get("input_cost_per_1k", 0.001) * input_tokens / 1000
        output_cost = pricing.get("output_cost_per_1k", 0.002) * max_output_tokens / 1000
        total_cost = (input_cost + output_cost) * pricing.get("effective_multiplier", 1.0)
        
        # 转换为评分 (成本越低分数越高)
        # 假设最高成本为0.1美元
        max_cost = 0.1
        score = max(0, 1 - (total_cost / max_cost))
        
        return min(1.0, score)
    
    # 内置模型质量排名 (分数越高越好, 满分100)
    MODEL_QUALITY_RANKING = {
        # OpenAI 系列
        "gpt-4o": 98, "gpt-4-turbo": 95, "gpt-4": 90, "gpt-4o-mini": 85, "gpt-3.5-turbo": 70,
        # Anthropic 系列
        "claude-3-5-sonnet": 99, "claude-3-opus": 97, "claude-3-sonnet": 92, "claude-3-haiku": 80,
        # Meta Llama 系列
        "llama-3.1-70b": 93, "llama-3.1-8b": 82, "llama-3-70b": 90, "llama-3-8b": 80,
        # Qwen 系列
        "qwen2.5-72b-instruct": 91, "qwen2-72b-instruct": 90, "qwen2-7b-instruct": 78,
        "qwen3-coder": 88, "qwen3-30b": 85, "qwen3-14b": 82, "qwen3-8b": 80, "qwen3-4b": 75, 
        "qwen3-1.7b": 65, "qwen3-0.6b": 60,
        # DeepSeek 系列
        "deepseek-r1": 89, "deepseek-v3": 87, "deepseek-coder": 85,
        # Moonshot 系列
        "moonshot-v1-128k": 88, "moonshot-v1-32k": 87, "moonshot-v1-8k": 86,
        # 01.AI 系列
        "yi-large": 89, "yi-lightning": 75,
        # Google 系列
        "gemma-3-12b": 78, "gemma-3-9b": 75, "gemma-3-270m": 55,
    }

    def _calculate_quality_score(self, channel: Channel, matched_model: Optional[str] = None) -> float:
        """根据内置排名动态计算质量评分"""
        # 优先使用匹配的模型，如果没有则使用渠道默认模型
        model_name = (matched_model or channel.model_name).lower()
        simple_model_name = model_name.split('/')[-1]
        quality_score = self.MODEL_QUALITY_RANKING.get(simple_model_name)
        
        if quality_score is None:
            for key, score in self.MODEL_QUALITY_RANKING.items():
                if key in model_name:
                    quality_score = score
                    break
        
        # 给本地模型一些质量分数调整
        if any(keyword in model_name for keyword in ['qwen3', 'qwen2.5']):
            base_score = quality_score or 75
            # 根据模型大小调整分数
            if '0.6b' in model_name or '1.7b' in model_name:
                base_score = max(60, base_score - 15)  # 小模型降分
            elif '4b' in model_name:
                base_score = max(70, base_score - 10)  # 中模型适当降分
            quality_score = base_score
        
        return (quality_score or 70) / 100.0

    def _calculate_speed_score(self, channel: Channel) -> float:
        """根据平均延迟动态计算速度评分"""
        channel_stats = self.config_loader.runtime_state.channel_stats.get(channel.id)
        if channel_stats and "avg_latency_ms" in channel_stats:
            avg_latency = channel_stats["avg_latency_ms"]
            base_latency = 2000.0
            score = max(0.0, 1.0 - (avg_latency / base_latency))
            return 0.1 + score * 0.9
        return channel.performance.get("speed_score", 0.8)

    def _calculate_reliability_score(self, channel: Channel) -> float:
        """计算可靠性评分"""
        health_score = self.config_loader.runtime_state.health_scores.get(channel.id, 1.0)
        return health_score
    
    def _calculate_total_score(self, strategy: List[Dict[str, Any]], 
                             cost_score: float, speed_score: float, 
                             quality_score: float, reliability_score: float) -> float:
        """根据策略计算总评分"""
        total_score = 0.0
        score_map = {
            "cost_score": cost_score, "speed_score": speed_score,
            "quality_score": quality_score, "reliability_score": reliability_score
        }
        
        total_weight = sum(rule.get("weight", 0.0) for rule in strategy)
        if total_weight == 0: 
            return 0.5

        for rule in strategy:
            field = rule.get("field", "")
            if field in score_map:
                score = score_map[field]
                if rule.get("order") == "asc": 
                    score = 1.0 - score
                total_score += score * rule.get("weight", 0.0)
        
        return total_score / total_weight
    
    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """使用tiktoken估算prompt tokens"""
        try:
            # 尝试从main模块获取已经初始化的encoder
            import main
            if hasattr(main, 'estimate_prompt_tokens'):
                return main.estimate_prompt_tokens(messages)
        except (ImportError, AttributeError):
            pass

        # 如果获取失败，使用简单回退方法
        logger.warning("无法从main模块获取tiktoken编码器, token计算将使用简单方法")
        total_chars = 0
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
        return max(1, total_chars // 4)
    
    def _is_suitable_for_chat(self, model_name: str) -> bool:
        """检查模型是否适合chat对话任务"""
        if not model_name:
            return False
            
        model_lower = model_name.lower()
        
        # 过滤embedding模型
        embedding_keywords = ['embedding', 'embed', 'text-embedding']
        if any(keyword in model_lower for keyword in embedding_keywords):
            return False
            
        # 过滤纯vision模型
        vision_only_keywords = ['vision-only', 'image-only']
        if any(keyword in model_lower for keyword in vision_only_keywords):
            return False
            
        # 过滤工具类模型
        tool_keywords = ['tokenizer', 'classifier', 'detector']
        if any(keyword in model_lower for keyword in tool_keywords):
            return False
            
        return True

    def _extract_tags_from_model_name(self, model_name: str) -> List[str]:
        """从模型名称中提取标签（带缓存）
        
        例如: "qwen/qwen3-30b-a3b:free" -> ["qwen", "qwen3", "30b", "a3b", "free"]
        """
        if not model_name or not isinstance(model_name, str):
            return []
        
        # 检查缓存
        if model_name in self._tag_cache:
            return self._tag_cache[model_name]
        
        import re
        
        # 使用多种分隔符进行拆分: :, /, @, -, _
        separators = r'[/:@\-_]'
        parts = re.split(separators, model_name.lower())
        
        # 清理和过滤标签
        tags = []
        for part in parts:
            part = part.strip()
            if part and len(part) > 1:  # 忽略单字符和空标签
                # 进一步分解数字和字母组合，如 "30b" -> ["30b"]
                tags.append(part)
        
        # 缓存结果
        self._tag_cache[model_name] = tags
        return tags

    def _get_candidate_channels_by_auto_tags(self, tags: List[str]) -> List[ChannelCandidate]:
        """根据自动提取的标签获取候选渠道（支持渐进式回退）"""
        if not tags:
            return []
        
        # 标准化标签
        normalized_tags = [tag.lower().strip() for tag in tags if tag and isinstance(tag, str)]
        if not normalized_tags:
            return []
        
        logger.info(f"🔍 TAG MATCHING: Searching for channels with tags: {normalized_tags}")
        
        model_cache = self.config_loader.get_model_cache()
        if not model_cache:
            logger.warning("🔍 TAG MATCHING: Model cache is empty, cannot perform tag routing")
            return []
        
        logger.info(f"🔍 TAG MATCHING: Searching through {len(model_cache)} cached channels")
        
        # 严格匹配：只返回同时包含所有标签的模型，不进行任何回退
        exact_candidates = self._find_channels_with_all_tags(normalized_tags, model_cache)
        
        if exact_candidates:
            logger.info(f"🎯 STRICT MATCH: Found {len(exact_candidates)} channels with ALL required tags {normalized_tags}")
            return exact_candidates
        
        logger.warning(f"❌ NO MATCH: No channels found with ALL required tags {normalized_tags}")
        return []
    
    def _find_channels_with_all_tags(self, tags: List[str], model_cache: dict) -> List[ChannelCandidate]:
        """查找包含所有指定标签的渠道和模型组合
        
        标签匹配规则：
        1. 首先检查渠道级别的标签 (channel.tags)
        2. 如果渠道标签匹配，该渠道下所有模型都被视为匹配
        3. 否则检查从模型名称提取的标签
        """
        candidate_channels = []
        matched_models = []
        
        # 遍历所有有效渠道
        for channel in self.config_loader.get_enabled_channels():
            if channel.id not in model_cache:
                continue
                
            discovered_info = model_cache[channel.id]
            if not isinstance(discovered_info, dict):
                continue
                
            models = discovered_info.get("models", [])
            if not models:
                continue
            
            logger.debug(f"🔍 TAG MATCHING: Checking channel {channel.id} ({channel.name}) with {len(models)} models")
            
            # 统一的标签合并匹配：渠道标签 + 模型标签
            channel_tags = getattr(channel, 'tags', []) or []
            channel_matches = 0
            
            for model_name in models:
                if not model_name:
                    continue
                    
                # 从模型名称提取标签
                model_tags = self._extract_tags_from_model_name(model_name)
                
                # 合并渠道标签和模型标签
                combined_tags = list(set(channel_tags + model_tags))
                
                # 验证所有查询标签都在合并后的标签中
                if all(tag in combined_tags for tag in tags):
                    # 过滤掉不适合chat的模型类型
                    if self._is_suitable_for_chat(model_name):
                        candidate_channels.append(ChannelCandidate(
                            channel=channel,
                            matched_model=model_name
                        ))
                        matched_models.append(model_name)
                        channel_matches += 1
                        logger.debug(f"✅ MERGED TAG MATCH: Channel '{channel.name}' model '{model_name}' -> tags: {combined_tags}")
                    else:
                        logger.debug(f"⚠️ FILTERED: Model '{model_name}' not suitable for chat (appears to be embedding/vision model)")
            
            if channel_matches > 0:
                logger.info(f"🎯 CHANNEL SUMMARY: Found {channel_matches} matching models in channel '{channel.name}' via merged channel+model tags")
        
        if matched_models:
            logger.info(f"🎯 TOTAL MATCHED MODELS: {len(matched_models)} models found: {matched_models[:5]}{'...' if len(matched_models) > 5 else ''}")
        
        return candidate_channels

    def get_available_models(self) -> List[str]:
        """获取用户可直接请求的、在配置中定义的模型列表（带缓存）"""
        # 检查缓存
        if self._available_models_cache is not None:
            return self._available_models_cache
        
        models = set()
        all_tags = set()
        
        # 添加物理模型名称
        for ch in self.config.channels:
            if ch.enabled and ch.model_name:
                models.add(ch.model_name)
                
                # 从配置的tags中添加
                for tag in ch.tags:
                    if tag:
                        all_tags.add(f"tag:{tag}")
        
        # 从模型缓存中提取自动标签
        model_cache = self.config_loader.get_model_cache()
        if model_cache:
            for channel_id, cache_info in model_cache.items():
                if not isinstance(cache_info, dict):
                    continue
                
                models_list = cache_info.get("models", [])
                if not isinstance(models_list, list):
                    continue
                    
                for model_name in models_list:
                    if model_name:
                        models.add(model_name)
                        # 提取自动标签
                        auto_tags = self._extract_tags_from_model_name(model_name)
                        for tag in auto_tags:
                            if tag:
                                all_tags.add(f"tag:{tag}")
        
        # 缓存结果
        result = sorted(list(models | all_tags))
        self._available_models_cache = result
        return result
    
    def clear_cache(self):
        """清除所有缓存"""
        self._tag_cache.clear()
        self._available_tags_cache = None
        self._available_models_cache = None
        logger.info("Router cache cleared")
    
    def update_channel_health(self, channel_id: str, success: bool, latency: Optional[float] = None):
        """更新渠道健康状态"""
        self.config_loader.update_channel_health(channel_id, success, latency)

# 全局路由器实例
_router: Optional[JSONRouter] = None

def get_router() -> JSONRouter:
    """获取全局路由器实例"""
    global _router
    if _router is None:
        _router = JSONRouter()
    return _router