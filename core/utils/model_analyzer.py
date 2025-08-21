"""
模型分析工具 - 提取参数数量、上下文长度等信息
"""

import re
import logging
from typing import Dict, Optional, Tuple, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ModelSpecs:
    """模型规格信息"""
    model_name: str
    parameter_count: Optional[int] = None  # 参数数量（以百万为单位）
    context_length: Optional[int] = None   # 上下文长度
    parameter_size_text: Optional[str] = None  # 原始参数文本，如 "7b", "270m"
    context_text: Optional[str] = None     # 原始上下文文本，如 "32k", "128k"
    
    def __post_init__(self):
        """后处理，计算数值"""
        if self.parameter_size_text and not self.parameter_count:
            self.parameter_count = self._parse_parameter_size(self.parameter_size_text)
        if self.context_text and not self.context_length:
            self.context_length = self._parse_context_length(self.context_text)
    
    def _parse_parameter_size(self, size_text: str) -> Optional[int]:
        """解析参数大小文本为数值（百万参数）"""
        try:
            size_text = size_text.lower().strip()
            if 'b' in size_text:  # billions
                return int(float(size_text.replace('b', '')) * 1000)
            elif 'm' in size_text:  # millions
                return int(float(size_text.replace('m', '')))
            elif 'k' in size_text:  # thousands (rare)
                return int(float(size_text.replace('k', '')) / 1000)
        except (ValueError, TypeError):
            pass
        return None
    
    def _parse_context_length(self, context_text: str) -> Optional[int]:
        """解析上下文长度文本为数值"""
        try:
            context_text = context_text.lower().strip()
            if 'k' in context_text:
                return int(float(context_text.replace('k', '')) * 1000)
            elif 'm' in context_text:
                return int(float(context_text.replace('m', '')) * 1000000)
            else:
                return int(context_text)
        except (ValueError, TypeError):
            pass
        return None

class ModelAnalyzer:
    """模型分析器"""
    
    # 参数大小模式（优先级从高到低）
    PARAMETER_PATTERNS = [
        # 明确的参数模式
        r'(\d+\.?\d*)b(?:illions?)?(?:\W|$)',  # 70b, 8b, 1.5b
        r'(\d+\.?\d*)m(?:illions?)?(?:\W|$)',  # 270m, 400m
        r'(\d+\.?\d*)k(?:ilo)?(?:\W|$)',       # 500k (rare)
        # 模型名称中的参数模式
        r'-(\d+\.?\d*)b-',    # model-7b-instruct
        r'-(\d+\.?\d*)m-',    # model-270m-chat
        r'_(\d+\.?\d*)b_',    # model_8b_v1
        r'_(\d+\.?\d*)m_',    # model_400m_base
        # 较宽松的模式
        r'(\d+)b(?!it|yte)',  # 避免匹配 bit, byte
        r'(\d+)m(?!in|ax)',   # 避免匹配 min, max
    ]
    
    # 上下文长度模式
    CONTEXT_PATTERNS = [
        r'(\d+\.?\d*)k(?:tok|token|ctx|context)?(?:\W|$)',  # 32k, 128k
        r'(\d+\.?\d*)m(?:tok|token|ctx|context)?(?:\W|$)',  # 2m (rare)
        r'-(\d+\.?\d*)k-',    # model-32k-chat
        r'_(\d+\.?\d*)k_',    # model_128k_v1
        r'(\d+)k(?!ey|now)',  # 避免匹配 key, know
    ]
    
    # 已知模型参数映射（用于无法从名称推断的情况）
    KNOWN_MODEL_PARAMS = {
        # OpenAI系列
        'gpt-4o': 1760000,         # 1.76T (估计)
        'gpt-4': 1760000,          # 1.76T 
        'gpt-4-turbo': 1760000,    # 1.76T
        'gpt-4o-mini': 8000,       # 8B (估计)
        'gpt-3.5-turbo': 175000,   # 175B
        'o1': 1760000,             # 1.76T (估计)
        'o1-mini': 8000,           # 8B (估计)
        'o3-mini': 8000,           # 8B (估计)
        
        # Anthropic系列
        'claude-3-5-sonnet': 180000,   # 180B (估计)
        'claude-3-opus': 400000,       # 400B (估计)
        'claude-3-sonnet': 180000,     # 180B
        'claude-3-haiku': 9000,        # 9B
        
        # Google系列
        'gemini-1.5-pro': 1000000,     # 1T (估计)
        'gemini-1.5-flash': 8000,      # 8B (估计)
        'gemma-2-9b': 9000,           # 9B
        'gemma-2-2b': 2000,           # 2B
        'gemma-3-27b': 27000,         # 27B
        'gemma-3-12b': 12000,         # 12B
        'gemma-3-270m': 270,          # 270M
        
        # Meta系列
        'llama-3.1-405b': 405000,     # 405B
        'llama-3.1-70b': 70000,       # 70B
        'llama-3.1-8b': 8000,         # 8B
        'llama-3.3-70b': 70000,       # 70B
        
        # Qwen系列
        'qwen2.5-72b': 72000,         # 72B
        'qwen2.5-32b': 32000,         # 32B
        'qwen2.5-14b': 14000,         # 14B
        'qwen2.5-7b': 7000,           # 7B
        'qwen2.5-3b': 3000,           # 3B
        'qwen2.5-1.5b': 1500,         # 1.5B
        'qwen2.5-0.5b': 500,          # 0.5B
        
        # DeepSeek系列
        'deepseek-v3': 670000,        # 670B
        'deepseek-r1': 670000,        # 670B (基于v3)
        'deepseek-coder': 33000,      # 33B
        
        # Moonshot系列
        'moonshot-v1-8k': 8000,       # 8B (估计)
        'moonshot-v1-32k': 8000,      # 8B (估计)
        'moonshot-v1-128k': 8000,     # 8B (估计)
    }
    
    # 已知模型上下文长度映射（基于OpenRouter和官方文档）
    KNOWN_MODEL_CONTEXT = {
        # OpenAI系列
        'gpt-4o': 128000,
        'gpt-4': 8192,
        'gpt-4-turbo': 128000,
        'gpt-4o-mini': 128000,
        'gpt-3.5-turbo': 16385,
        'gpt-3.5-turbo-16k': 16385,
        'o1': 200000,
        'o1-mini': 128000,
        'o1-preview': 128000,
        'o3-mini': 128000,
        'text-davinci-003': 4096,
        'text-davinci-002': 4096,
        
        # Anthropic系列
        'claude-3-5-sonnet': 200000,
        'claude-3-5-haiku': 200000,
        'claude-3-opus': 200000,
        'claude-3-sonnet': 200000,
        'claude-3-haiku': 200000,
        'claude-2.1': 200000,
        'claude-2.0': 100000,
        'claude-instant-1.2': 100000,
        'claude-instant': 100000,
        
        # Google系列
        'gemini-1.5-pro': 2097152,    # 2M
        'gemini-1.5-flash': 1048576,  # 1M
        'gemini-1.0-pro': 32768,      # 32k
        'gemma-2-9b': 8192,
        'gemma-2-2b': 8192,
        'gemma-2-27b': 8192,
        'gemma-3-27b': 96000,
        'gemma-3-12b': 96000,
        'gemma-3-9b': 8192,
        'gemma-3-4b': 8192,
        'gemma-3-270m': 8192,
        'gemma-3-1b': 8192,
        
        # Meta系列
        'llama-3.1-405b': 131072,     # 128k
        'llama-3.1-70b': 131072,      # 128k
        'llama-3.1-8b': 131072,       # 128k
        'llama-3.2-90b': 131072,      # 128k
        'llama-3.2-11b': 131072,      # 128k
        'llama-3.2-3b': 131072,       # 128k
        'llama-3.2-1b': 131072,       # 128k
        'llama-3.3-70b': 131072,      # 128k
        'llama-3-70b': 8192,
        'llama-3-8b': 8192,
        'llama-2-70b': 4096,
        'llama-2-13b': 4096,
        'llama-2-7b': 4096,
        
        # Qwen系列
        'qwen2.5-72b': 131072,        # 128k
        'qwen2.5-32b': 131072,        # 128k
        'qwen2.5-14b': 131072,        # 128k
        'qwen2.5-7b': 131072,         # 128k
        'qwen2.5-3b': 32768,          # 32k
        'qwen2.5-1.5b': 32768,        # 32k
        'qwen2.5-0.5b': 32768,        # 32k
        'qwen2-72b': 32768,           # 32k
        'qwen2-57b': 32768,           # 32k
        'qwen2-7b': 131072,           # 128k
        'qwen2-1.5b': 32768,          # 32k
        'qwen2-0.5b': 32768,          # 32k
        'qwen3-0.6b': 8192,           # 8k
        'qwen3-1.7b': 8192,           # 8k
        'qwen3-4b': 32768,            # 32k
        'qwen3-8b': 32768,            # 32k
        'qwen3-14b': 32768,           # 32k
        'qwen3-30b': 32768,           # 32k
        'qwen3-32b': 32768,           # 32k
        'qwen3-coder': 65536,         # 64k
        
        # DeepSeek系列
        'deepseek-v3': 65536,         # 64k
        'deepseek-r1': 65536,         # 64k
        'deepseek-v2.5': 65536,       # 64k
        'deepseek-v2': 32768,         # 32k
        'deepseek-coder': 16384,      # 16k
        'deepseek-coder-v2': 65536,   # 64k
        'deepseek-math': 4096,        # 4k
        
        # Moonshot系列 (从名称可知)
        'moonshot-v1-8k': 8192,
        'moonshot-v1-32k': 32768,
        'moonshot-v1-128k': 131072,
        
        # Mistral系列
        'mistral-large': 32768,       # 32k
        'mistral-medium': 32768,      # 32k
        'mistral-small': 32768,       # 32k
        'mistral-7b': 32768,          # 32k
        'mistral-8x7b': 32768,        # 32k
        'mixtral-8x7b': 32768,        # 32k
        'mixtral-8x22b': 65536,       # 64k
        
        # 01.AI系列
        'yi-large': 32768,            # 32k
        'yi-medium': 16384,           # 16k
        'yi-lightning': 16384,        # 16k
        'yi-spark': 16384,            # 16k
        'yi-34b': 200000,             # 200k
        'yi-6b': 4096,                # 4k
        
        # Zhipu系列
        'glm-4': 128000,              # 128k
        'glm-4v': 8192,               # 8k (vision)
        'glm-3-turbo': 128000,        # 128k
        'chatglm3-6b': 8192,          # 8k
        'codegeex2-6b': 8192,         # 8k
        
        # Baichuan系列
        'baichuan2-53b': 4096,        # 4k
        'baichuan2-13b': 4096,        # 4k
        'baichuan2-7b': 4096,         # 4k
        
        # ChatGLM系列
        'chatglm-6b': 2048,           # 2k
        'chatglm2-6b': 8192,          # 8k
        'chatglm3-6b': 8192,          # 8k
        
        # 其他开源模型
        'vicuna-33b': 2048,           # 2k
        'vicuna-13b': 2048,           # 2k
        'vicuna-7b': 2048,            # 2k
        'alpaca-7b': 2048,            # 2k
        'wizard-13b': 2048,           # 2k
        'wizard-7b': 2048,            # 2k
        'orca-13b': 2048,             # 2k
        'orca-7b': 2048,              # 2k
        'nous-hermes-13b': 2048,      # 2k
        'nous-hermes-7b': 2048,       # 2k
        
        # 专业模型
        'codellama-34b': 16384,       # 16k
        'codellama-13b': 16384,       # 16k
        'codellama-7b': 16384,        # 16k
        'starcoder-15b': 8192,        # 8k
        'starcoder-7b': 8192,         # 8k
        'phi-3-medium': 131072,       # 128k
        'phi-3-mini': 131072,         # 128k
        'phi-4': 131072,              # 128k
    }
    
    def analyze_model(self, model_name: str, model_data: Dict[str, Any] = None) -> ModelSpecs:
        """分析单个模型，提取参数和上下文信息"""
        
        specs = ModelSpecs(model_name=model_name)
        
        # 1. 从API返回的数据中提取（最准确）
        if model_data:
            if 'context_length' in model_data:
                specs.context_length = model_data['context_length']
                specs.context_text = f"{specs.context_length}"
            
            # 有些API返回参数信息
            if 'parameters' in model_data:
                specs.parameter_count = model_data['parameters']
            elif 'parameter_count' in model_data:
                specs.parameter_count = model_data['parameter_count']
        
        # 2. 从已知映射中查找
        model_key = self._normalize_model_name(model_name)
        if not specs.parameter_count and model_key in self.KNOWN_MODEL_PARAMS:
            specs.parameter_count = self.KNOWN_MODEL_PARAMS[model_key]
            logger.debug(f"Found known parameter count for {model_name}: {specs.parameter_count}M")
        
        if not specs.context_length and model_key in self.KNOWN_MODEL_CONTEXT:
            specs.context_length = self.KNOWN_MODEL_CONTEXT[model_key]
            logger.debug(f"Found known context length for {model_name}: {specs.context_length}")
        
        # 3. 从模型名称中提取参数数量
        if not specs.parameter_count:
            param_info = self._extract_parameter_size(model_name)
            if param_info:
                specs.parameter_size_text = param_info[1]
                specs.parameter_count = param_info[0]
                logger.debug(f"Extracted parameter size from name {model_name}: {specs.parameter_size_text} -> {specs.parameter_count}M")
        
        # 4. 从模型名称中提取上下文长度
        if not specs.context_length:
            context_info = self._extract_context_length(model_name)
            if context_info:
                specs.context_text = context_info[1]
                specs.context_length = context_info[0]
                logger.debug(f"Extracted context length from name {model_name}: {specs.context_text} -> {specs.context_length}")
        
        return specs
    
    def _normalize_model_name(self, model_name: str) -> str:
        """标准化模型名称用于查找"""
        # 移除常见前缀
        name = model_name.lower()
        for prefix in ['google/', 'openai/', 'anthropic/', 'meta/', 'qwen/', 'deepseek/', 'moonshot/']:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        
        # 移除常见后缀
        for suffix in ['-instruct', '-chat', '-it', '-base', '-latest', '-preview']:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        
        return name
    
    def _extract_parameter_size(self, model_name: str) -> Optional[Tuple[int, str]]:
        """从模型名称提取参数大小"""
        name_lower = model_name.lower()
        
        for pattern in self.PARAMETER_PATTERNS:
            match = re.search(pattern, name_lower)
            if match:
                size_text = match.group(1)
                try:
                    if 'b' in pattern:  # billions
                        param_count = int(float(size_text) * 1000)
                        return param_count, f"{size_text}b"
                    elif 'm' in pattern:  # millions
                        param_count = int(float(size_text))
                        return param_count, f"{size_text}m"
                    elif 'k' in pattern:  # thousands
                        param_count = int(float(size_text) / 1000)
                        return param_count, f"{size_text}k"
                except (ValueError, TypeError):
                    continue
        
        return None
    
    def _extract_context_length(self, model_name: str) -> Optional[Tuple[int, str]]:
        """从模型名称提取上下文长度"""
        name_lower = model_name.lower()
        
        for pattern in self.CONTEXT_PATTERNS:
            match = re.search(pattern, name_lower)
            if match:
                context_text = match.group(1)
                try:
                    if 'k' in pattern:
                        context_length = int(float(context_text) * 1000)
                        return context_length, f"{context_text}k"
                    elif 'm' in pattern:
                        context_length = int(float(context_text) * 1000000)
                        return context_length, f"{context_text}m"
                    else:
                        context_length = int(context_text)
                        return context_length, context_text
                except (ValueError, TypeError):
                    continue
        
        return None
    
    def batch_analyze_models(self, models_data: Dict[str, Any]) -> Dict[str, ModelSpecs]:
        """批量分析模型"""
        results = {}
        
        for model_name, model_info in models_data.items():
            specs = self.analyze_model(model_name, model_info)
            results[model_name] = specs
        
        return results
    
    def extract_tags_from_model_name(self, model_name: str) -> List[str]:
        """从模型名称中提取标签"""
        import re
        
        if not model_name:
            return []
        
        # 使用多种分隔符进行拆分
        separators = r'[:/\-_@,]'
        parts = re.split(separators, model_name.lower())
        
        tags = []
        for part in parts:
            part = part.strip()
            if part and len(part) > 0:
                tags.append(part)
        
        # 去重并保持顺序
        seen = set()
        unique_tags = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)
        
        return unique_tags

# 全局分析器实例
_analyzer: Optional[ModelAnalyzer] = None

def get_model_analyzer() -> ModelAnalyzer:
    """获取全局模型分析器实例"""
    global _analyzer
    if _analyzer is None:
        _analyzer = ModelAnalyzer()
    return _analyzer