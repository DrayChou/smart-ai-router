# -*- coding: utf-8 -*-
"""
候选渠道查找器
从json_router.py中提取的候选渠道查找功能
"""
import logging
from typing import List, Optional

from .exceptions import TagNotFoundError, ParameterComparisonError
from .models import ChannelCandidate, RoutingRequest
from .size_filters import parse_size_filter, apply_size_filters
from ..config_models import Channel

logger = logging.getLogger(__name__)


class CandidateFinder:
    """候选渠道查找器"""

    def __init__(self, config_loader, parameter_comparator):
        self.config_loader = config_loader
        self.parameter_comparator = parameter_comparator

    def find_candidates(self, request: RoutingRequest) -> List[ChannelCandidate]:
        """获取候选渠道，支持按标签集合、物理模型或参数量比较进行智能路由"""

        # 1. 检查是否为参数量比较查询
        if self.parameter_comparator.is_parameter_comparison(request.model):
            return self._find_by_parameter_comparison(request)

        # 2. 检查是否为隐式标签查询
        if "," in request.model and not request.model.startswith(("tag:", "tags:")):
            return self._find_by_implicit_tags(request)

        # 3. 检查是否为显式标签查询
        if request.model.startswith(("tag:", "tags:")):
            return self._find_by_explicit_tags(request)

        # 4. 物理模型查找
        return self._find_by_physical_model(request)

    def _find_by_parameter_comparison(
        self, request: RoutingRequest
    ) -> List[ChannelCandidate]:
        """通过参数量比较查找候选渠道"""
        logger.info(f"🔢 PARAMETER COMPARISON: Processing query '{request.model}'")

        comparison = self.parameter_comparator.parse_comparison(request.model)
        if not comparison:
            logger.error(
                f"PARAM PARSE FAILED: Could not parse parameter comparison '{request.model}'"
            )
            raise ParameterComparisonError(request.model)

        # 获取所有模型缓存
        model_cache = self.config_loader.get_model_cache()
        if not model_cache:
            logger.error(
                "NO MODEL CACHE: Model cache is empty for parameter comparison"
            )
            raise ParameterComparisonError(
                request.model, "模型缓存为空，无法进行参数量比较"
            )

        # 按参数量比较筛选模型
        matching_models = self.parameter_comparator.filter_models_by_comparison(
            comparison, model_cache
        )
        if not matching_models:
            logger.error(
                f"PARAM COMPARISON FAILED: No models found matching '{request.model}'"
            )
            raise ParameterComparisonError(request.model)

        logger.info("📝 First 5 matched models:")
        for i, (channel_id, model_name, model_params) in enumerate(matching_models[:5]):
            logger.info(f"  {i+1}. {channel_id} -> {model_name} ({model_params:.3f}B)")

        # 转换为候选渠道列表
        return self._convert_to_candidates(matching_models)

    def _find_by_implicit_tags(self, request: RoutingRequest) -> List[ChannelCandidate]:
        """通过隐式标签查找候选渠道"""
        logger.info(
            f"IMPLICIT TAG QUERY: Detected comma-separated query '{request.model}', treating as tag query"
        )

        tag_parts = [tag.strip() for tag in request.model.split(",")]
        positive_tags = []
        negative_tags = []

        for tag_part in tag_parts:
            if tag_part.startswith("!"):
                negative_tags.append(tag_part[1:].lower())
            else:
                size_filter = parse_size_filter(tag_part)
                if not size_filter:
                    positive_tags.append(tag_part.lower())

        logger.info(
            f"IMPLICIT TAG ROUTING: Processing query '{request.model}' -> positive: {positive_tags}, negative: {negative_tags}"
        )

        candidates = self._get_candidate_channels_by_auto_tags(
            positive_tags, negative_tags
        )
        if not candidates:
            logger.error(
                f"IMPLICIT TAG NOT FOUND: No models found matching tags {positive_tags} excluding {negative_tags}"
            )
            raise TagNotFoundError(positive_tags + [f"!{tag}" for tag in negative_tags])

        # 应用大小过滤器
        size_filters = [
            parse_size_filter(tag_part)
            for tag_part in tag_parts
            if parse_size_filter(tag_part)
        ]
        if size_filters:
            candidates = apply_size_filters(candidates, size_filters)

        if not candidates:
            logger.error("SIZE FILTERS: No candidates left after applying size filters")
            raise TagNotFoundError(positive_tags + [f"!{tag}" for tag in negative_tags])

        logger.info(f"IMPLICIT TAG ROUTING: Found {len(candidates)} candidate channels")
        return candidates

    def _find_by_explicit_tags(self, request: RoutingRequest) -> List[ChannelCandidate]:
        """通过显式标签查找候选渠道"""
        # 统一处理 tag: 和 tags: 前缀
        tag_query = (
            request.model[4:] if request.model.startswith("tag:") else request.model[5:]
        )

        if "," in tag_query:
            # 多标签查询
            tag_parts = [tag.strip() for tag in tag_query.split(",")]
            positive_tags = []
            negative_tags = []

            for tag_part in tag_parts:
                if tag_part.startswith("!"):
                    negative_tags.append(tag_part[1:].lower())
                else:
                    size_filter = parse_size_filter(tag_part)
                    if not size_filter:
                        positive_tags.append(tag_part.lower())

            logger.info(
                f"MULTI-TAG ROUTING: positive: {positive_tags}, negative: {negative_tags}"
            )
            candidates = self._get_candidate_channels_by_auto_tags(
                positive_tags, negative_tags
            )

            # 应用大小过滤器
            size_filters = [
                parse_size_filter(tag_part)
                for tag_part in tag_parts
                if parse_size_filter(tag_part)
            ]
            if size_filters:
                candidates = apply_size_filters(candidates, size_filters)
        else:
            # 单标签查询
            size_filter = parse_size_filter(tag_query)
            if size_filter:
                # 这是一个大小过滤查询
                all_candidates = self._get_all_enabled_candidates()
                candidates = apply_size_filters(all_candidates, [size_filter])
            else:
                # 正常单标签查询
                candidates = self._get_candidate_channels_by_auto_tags(
                    [tag_query.lower()]
                )

        if not candidates:
            logger.error(f"TAG NOT FOUND: No models found for query '{request.model}'")
            raise TagNotFoundError([tag_query])

        logger.info(f"TAG ROUTING: Found {len(candidates)} candidate channels")
        return candidates

    def _find_by_physical_model(
        self, request: RoutingRequest
    ) -> List[ChannelCandidate]:
        """通过物理模型名称查找候选渠道"""
        all_enabled_channels = self.config_loader.get_enabled_channels()
        model_cache = self.config_loader.get_model_cache()

        # 1. 首先尝试作为物理模型查找（精确匹配）
        physical_candidates = []
        for channel in all_enabled_channels:
            if channel.id in model_cache:
                discovered_info = model_cache[channel.id]
                models_data = (
                    discovered_info.get("models_data", {})
                    if isinstance(discovered_info, dict)
                    else {}
                )

                # 检查是否存在精确匹配的模型
                if request.model in discovered_info.get("models", []):
                    real_model_id = request.model
                    if models_data and request.model in models_data:
                        model_info = models_data[request.model]
                        real_model_id = model_info.get("id", request.model)

                    logger.debug(
                        f"PHYSICAL MODEL: Found '{request.model}' -> '{real_model_id}' in channel '{channel.name}'"
                    )
                    physical_candidates.append(
                        ChannelCandidate(channel=channel, matched_model=real_model_id)
                    )

        # 2. 尝试完整子段标签匹配
        complete_segment_candidates = self._get_candidate_channels_by_complete_segment(
            [request.model.lower()]
        )

        # 3. 合并结果，去重
        all_candidates = physical_candidates.copy()
        for segment_candidate in complete_segment_candidates:
            duplicate_found = any(
                existing.channel.id == segment_candidate.channel.id
                and existing.matched_model == segment_candidate.matched_model
                for existing in all_candidates
            )
            if not duplicate_found:
                all_candidates.append(segment_candidate)

        if all_candidates:
            logger.info(
                f"COMPREHENSIVE SEARCH: Found {len(all_candidates)} total candidates"
            )
            return all_candidates

        # 4. 最后尝试从配置中查找
        config_channels = self.config_loader.get_channels_by_model(request.model)
        if config_channels:
            logger.info(
                f"CONFIG FALLBACK: Found {len(config_channels)} channels in configuration"
            )
            config_candidates = []
            for ch in config_channels:
                real_model_id = request.model
                if ch.id in model_cache:
                    discovered_info = model_cache[ch.id]
                    models_data = (
                        discovered_info.get("models_data", {})
                        if isinstance(discovered_info, dict)
                        else {}
                    )
                    if models_data and request.model in models_data:
                        model_info = models_data[request.model]
                        real_model_id = model_info.get("id", request.model)

                config_candidates.append(
                    ChannelCandidate(channel=ch, matched_model=real_model_id)
                )
            return config_candidates

        logger.warning(f"NO MATCH: No channels found for model '{request.model}'")
        return []

    def _convert_to_candidates(self, matching_models: List) -> List[ChannelCandidate]:
        """将匹配的模型转换为候选渠道列表"""
        candidates = []
        disabled_count = 0
        not_found_count = 0

        for channel_id, model_name, model_params in matching_models:
            # 从 API key-level cache key 中提取真实的 channel ID
            real_channel_id = self._extract_real_channel_id(channel_id)

            channel = self.config_loader.get_channel_by_id(real_channel_id)
            if channel:
                if channel.enabled:
                    candidates.append(
                        ChannelCandidate(channel=channel, matched_model=model_name)
                    )
                else:
                    disabled_count += 1
            else:
                not_found_count += 1

        logger.info(
            f"CHANNEL LOOKUP: Found {len(candidates)} enabled channels, "
            f"disabled: {disabled_count}, not_found: {not_found_count}"
        )
        return candidates

    def _extract_real_channel_id(self, channel_id: str) -> str:
        """从API key级别的缓存键中提取真实的渠道ID"""
        if "_" in channel_id:
            parts = channel_id.split("_")
            if len(parts) >= 2:
                potential_hash = parts[-1]
                if len(potential_hash) == 8 and all(
                    c in "0123456789abcdef" for c in potential_hash.lower()
                ):
                    return "_".join(parts[:-1])
        return channel_id

    def _get_candidate_channels_by_auto_tags(
        self, positive_tags: List[str], negative_tags: List[str] = None
    ) -> List[ChannelCandidate]:
        """通过自动标签获取候选渠道"""
        # 这里需要实现标签匹配逻辑，暂时返回空列表
        # 实际实现需要从原JSONRouter中移植相关方法
        return []

    def _get_candidate_channels_by_complete_segment(
        self, segments: List[str]
    ) -> List[ChannelCandidate]:
        """通过完整段落获取候选渠道"""
        # 这里需要实现完整段落匹配逻辑，暂时返回空列表
        return []

    def _get_all_enabled_candidates(self) -> List[ChannelCandidate]:
        """获取所有启用的候选渠道"""
        all_enabled_channels = self.config_loader.get_enabled_channels()
        return [ChannelCandidate(channel=ch) for ch in all_enabled_channels]
