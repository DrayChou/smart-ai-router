"""
模型能力检测模块
使用OpenRouter数据库作为通用模型能力参考
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# 文件内容缓存
_cache_content: Optional[Dict] = None
_cache_file_path = Path("cache/channels/openrouter.free.json")


def _load_openrouter_cache() -> Dict:
    """加载OpenRouter缓存数据（带内存缓存）"""
    global _cache_content
    
    if _cache_content is not None:
        return _cache_content
    
    try:
        if not _cache_file_path.exists():
            logger.warning(f"OpenRouter数据文件不存在: {_cache_file_path}")
            _cache_content = {}
            return _cache_content
        
        with open(_cache_file_path, 'r', encoding='utf-8') as f:
            _cache_content = json.load(f)
        
        logger.debug(f"OpenRouter缓存已加载: {len(_cache_content.get('models', {}))} 个模型")
        return _cache_content
        
    except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
        logger.warning(f"读取OpenRouter数据失败: {type(e).__name__}: {e}")
        _cache_content = {}
        return _cache_content


def _extract_capabilities_from_data(raw_data: Dict) -> List[str]:
    """从OpenRouter原始数据中提取能力信息"""
    capabilities = ["text"]  # 默认支持文本
    
    # 从architecture.input_modalities获取多模态能力
    architecture = raw_data.get('architecture', {})
    input_modalities = architecture.get('input_modalities', [])
    
    if "image" in input_modalities:
        capabilities.append("vision")
    
    # 从supported_parameters获取高级能力
    supported_params = raw_data.get('supported_parameters', [])
    
    if any(param in supported_params for param in ["tools", "tool_choice"]):
        capabilities.append("function_calling")
    
    if any(param in supported_params for param in ["response_format", "structured_outputs"]):
        capabilities.append("json_mode")
    
    return capabilities


def _extract_context_length(raw_data: Dict) -> int:
    """从OpenRouter原始数据中提取上下文长度"""
    return raw_data.get('context_length', 0)


def _models_match(model_name_1: str, model_name_2: str) -> bool:
    """
    检查两个模型名称是否指向同一个模型（支持不同provider前缀）
    例如: gpt-4o-mini 匹配 openai/gpt-4o-mini
    """
    # 移除provider前缀
    clean_1 = model_name_1.split('/')[-1].lower()
    clean_2 = model_name_2.split('/')[-1].lower()
    
    # 精确匹配
    if clean_1 == clean_2:
        return True
    
    # 模糊匹配：检查核心模型名称
    # 移除常见的变体后缀
    variants = ['-instruct', '-chat', '-v1', '-v2', '-v3', '-latest', ':free', ':beta']
    
    for variant in variants:
        clean_1 = clean_1.replace(variant, '')
        clean_2 = clean_2.replace(variant, '')
    
    return clean_1 == clean_2


@lru_cache(maxsize=1000)
def get_model_capabilities_from_openrouter(model_name: str) -> Tuple[List[str], int]:
    """
    使用OpenRouter数据库作为通用模型能力参考
    所有渠道（OpenRouter、OpenAI、Anthropic等）的模型能力都参考OpenRouter的模型列表
    
    Args:
        model_name: 模型名称
        
    Returns:
        tuple[capabilities, context_length]: 模型能力列表和上下文长度
    """
    capabilities = ["text"]  # 默认支持文本
    context_length = 0
    
    cache_data = _load_openrouter_cache()
    models_data = cache_data.get("models", {})
    
    # 直接查找模型
    if model_name in models_data:
        model_info = models_data[model_name]
        raw_data = model_info.get("raw_data", {})
        
        capabilities = _extract_capabilities_from_data(raw_data)
        context_length = _extract_context_length(raw_data)
        
        logger.debug(f"🔍 从OpenRouter数据库获取 {model_name}: {capabilities}, context: {context_length}")
        return capabilities, context_length
    
    # 如果直接查找失败，尝试模糊匹配（处理不同provider的相同模型）
    for openrouter_model, model_info in models_data.items():
        if _models_match(model_name, openrouter_model):
            raw_data = model_info.get("raw_data", {})
            
            capabilities = _extract_capabilities_from_data(raw_data)
            context_length = _extract_context_length(raw_data)
            
            logger.debug(f"🔍 通过模糊匹配获取 {model_name} -> {openrouter_model}: {capabilities}, context: {context_length}")
            return capabilities, context_length
    
    # 如果OpenRouter数据不可用，只提供基础文本能力
    logger.debug(f"⚠️ 未找到 {model_name} 的OpenRouter数据，使用默认能力")
    return capabilities, context_length


def clear_cache() -> None:
    """清除缓存，强制重新加载数据"""
    global _cache_content
    _cache_content = None
    # 清除LRU缓存
    get_model_capabilities_from_openrouter.cache_clear()
    logger.debug("模型能力缓存已清除")


def get_cache_stats() -> Dict:
    """获取缓存统计信息"""
    cache_info = get_model_capabilities_from_openrouter.cache_info()
    return {
        "lru_hits": cache_info.hits,
        "lru_misses": cache_info.misses,
        "lru_current_size": cache_info.currsize,
        "lru_max_size": cache_info.maxsize,
        "file_cached": _cache_content is not None,
        "total_models": len(_cache_content.get("models", {})) if _cache_content else 0
    }