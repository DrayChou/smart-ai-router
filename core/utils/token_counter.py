# -*- coding: utf-8 -*-
"""
Unified token counting and cost calculation utilities
"""
from typing import List, Dict, Any, Optional, Union
import logging

logger = logging.getLogger(__name__)

class TokenCounter:
    """统一的Token计算和成本计算工具"""
    
    _tiktoken_encoder = None
    
    @classmethod
    def get_tiktoken_encoder(cls):
        """获取tiktoken编码器（单例模式）"""
        if cls._tiktoken_encoder is None:
            try:
                import tiktoken
                cls._tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
                logger.info("tiktoken encoder loaded successfully.")
            except ImportError:
                logger.warning("tiktoken library not found, token calculation will be approximate.")
                cls._tiktoken_encoder = "simple"
            except Exception as e:
                logger.error(f"Failed to load tiktoken encoder: {e}")
                cls._tiktoken_encoder = "simple"
        return cls._tiktoken_encoder
    
    @classmethod
    def count_tokens_in_text(cls, text: str) -> int:
        """计算文本中的token数量"""
        encoder = cls.get_tiktoken_encoder()
        
        if encoder == "simple" or not hasattr(encoder, 'encode'):
            # 简单计算：按空格分割
            return len(text.split())
        
        try:
            return len(encoder.encode(text))
        except Exception as e:
            logger.warning(f"Failed to encode text with tiktoken: {e}")
            return len(text.split())
    
    @classmethod
    def count_tokens_in_messages(cls, messages: List[Dict[str, Any]]) -> int:
        """计算消息列表中的token数量（OpenAI格式）"""
        encoder = cls.get_tiktoken_encoder()
        
        if encoder == "simple" or not hasattr(encoder, 'encode'):
            # 简单计算
            return sum(len(str(msg.get("content", "")).split()) for msg in messages)
        
        try:
            num_tokens = 0
            for message in messages:
                num_tokens += 4  # 每条消息有4个token的开销
                for key, value in message.items():
                    if isinstance(value, str):
                        num_tokens += len(encoder.encode(value))
                    elif isinstance(value, list):
                        # 处理多模态内容
                        for item in value:
                            if isinstance(item, dict):
                                if item.get("type") == "text":
                                    text_content = item.get("text", "")
                                    num_tokens += len(encoder.encode(text_content))
                                elif item.get("type") == "image_url":
                                    # 图片token估算（简化）
                                    num_tokens += 85  # OpenAI图片大概token数
                            elif isinstance(item, str):
                                num_tokens += len(encoder.encode(item))
                    if key == "name":
                        num_tokens -= 1  # name字段特殊处理
            num_tokens += 2  # 响应的开头需要2个token
            return num_tokens
        except Exception as e:
            logger.warning(f"Failed to count tokens in messages: {e}")
            # 回退到简单计算
            return sum(len(str(msg.get("content", "")).split()) for msg in messages)
    
    @classmethod
    def estimate_completion_tokens(cls, prompt_tokens: int, max_tokens: Optional[int] = None) -> int:
        """估算完成token数量"""
        if max_tokens:
            # 使用用户指定的max_tokens
            return min(max_tokens, prompt_tokens // 4)  # 通常完成比提示短
        else:
            # 估算：通常完成token是提示token的10-30%
            return max(10, prompt_tokens // 5)
    
    @classmethod
    def calculate_cost(cls, prompt_tokens: int, completion_tokens: int, pricing: Dict[str, float], 
                      currency_exchange: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """计算请求成本，支持货币转换
        
        Args:
            prompt_tokens: 输入token数量
            completion_tokens: 输出token数量  
            pricing: 定价配置
            currency_exchange: 货币转换配置
            
        Returns:
            包含原始成本和转换后成本的字典
        """
        # 计算基础成本（美元）
        base_cost = 0.0
        
        # 输入token成本
        if "input" in pricing:
            base_cost += prompt_tokens * pricing["input"]
        elif "prompt" in pricing:
            base_cost += prompt_tokens * pricing["prompt"]
        
        # 输出token成本
        if "output" in pricing:
            base_cost += completion_tokens * pricing["output"]
        elif "completion" in pricing:
            base_cost += completion_tokens * pricing["completion"]
        
        result = {
            "base_cost": base_cost,
            "base_currency": "USD",
            "actual_cost": base_cost,
            "actual_currency": "USD",
            "exchange_rate": 1.0,
            "exchange_info": None
        }
        
        # 应用货币转换
        if currency_exchange:
            exchange_rate = currency_exchange.get("rate", 1.0)
            from_currency = currency_exchange.get("from", "USD")
            to_currency = currency_exchange.get("to", "CNY")
            description = currency_exchange.get("description", "")
            
            if from_currency == "USD" and exchange_rate != 1.0:
                # 应用汇率转换
                actual_cost = base_cost * exchange_rate
                result.update({
                    "actual_cost": actual_cost,
                    "actual_currency": to_currency,
                    "exchange_rate": exchange_rate,
                    "exchange_info": {
                        "description": description,
                        "from": from_currency,
                        "to": to_currency,
                        "rate": exchange_rate
                    }
                })
        
        return result
    
    @classmethod
    def calculate_cost_legacy(cls, prompt_tokens: int, completion_tokens: int, pricing: Dict[str, float]) -> float:
        """传统成本计算方法（保持向后兼容）"""
        result = cls.calculate_cost(prompt_tokens, completion_tokens, pricing)
        return result["actual_cost"]
    
    @classmethod
    def get_cost_per_1k_tokens(cls, pricing: Dict[str, float], token_type: str = "input") -> float:
        """获取每1K token的成本"""
        if token_type in pricing:
            return pricing[token_type] * 1000
        elif token_type == "input" and "prompt" in pricing:
            return pricing["prompt"] * 1000
        elif token_type == "output" and "completion" in pricing:
            return pricing["completion"] * 1000
        return 0.0
    
    @classmethod
    def format_cost(cls, cost: float, currency: str = "USD") -> str:
        """格式化成本显示"""
        # 根据货币类型选择符号
        symbol = "Y" if currency == "CNY" else "$"
        
        if cost < 0.001:
            return f"{symbol}{cost * 1000000:.2f}µ{currency}"  # 微单位
        elif cost < 1:
            return f"{symbol}{cost * 1000:.2f}m{currency}"  # 毫单位
        else:
            return f"{symbol}{cost:.4f} {currency}"
    
    @classmethod
    def format_cost_comparison(cls, cost_info: Dict[str, Any]) -> str:
        """格式化成本对比显示"""
        base_cost = cost_info.get("base_cost", 0)
        actual_cost = cost_info.get("actual_cost", 0)
        base_currency = cost_info.get("base_currency", "USD")
        actual_currency = cost_info.get("actual_currency", "USD")
        exchange_info = cost_info.get("exchange_info")
        
        base_str = cls.format_cost(base_cost, base_currency)
        actual_str = cls.format_cost(actual_cost, actual_currency)
        
        if exchange_info:
            return f"{actual_str} (原价: {base_str}, {exchange_info['description']})"
        else:
            return actual_str
    
    @classmethod
    def get_token_stats(cls, messages: List[Dict[str, Any]], max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """获取完整的token统计信息"""
        prompt_tokens = cls.count_tokens_in_messages(messages)
        estimated_completion_tokens = cls.estimate_completion_tokens(prompt_tokens, max_tokens)
        total_tokens = prompt_tokens + estimated_completion_tokens
        
        return {
            "prompt_tokens": prompt_tokens,
            "estimated_completion_tokens": estimated_completion_tokens,
            "estimated_total_tokens": total_tokens,
            "max_tokens_limit": max_tokens,
            "encoding_method": "tiktoken" if cls._tiktoken_encoder != "simple" else "simple"
        }


class CostTracker:
    """成本追踪器"""
    
    def __init__(self):
        self.session_costs = []
        self.total_cost = 0.0
    
    def add_request_cost(self, cost: float, model: str, channel_id: str, tokens: Dict[str, int]) -> None:
        """添加请求成本记录"""
        record = {
            "timestamp": __import__("time").time(),
            "cost": cost,
            "model": model,
            "channel_id": channel_id,
            "tokens": tokens
        }
        
        self.session_costs.append(record)
        self.total_cost += cost
        
        logger.info(f"💰 COST TRACKING: ${cost:.6f} for {tokens.get('total_tokens', 0)} tokens via {channel_id}")
    
    def get_session_summary(self) -> Dict[str, Any]:
        """获取会话成本摘要"""
        if not self.session_costs:
            return {"total_cost": 0.0, "total_requests": 0, "average_cost": 0.0}
        
        total_requests = len(self.session_costs)
        total_tokens = sum(record["tokens"].get("total_tokens", 0) for record in self.session_costs)
        
        return {
            "total_cost": self.total_cost,
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "average_cost": self.total_cost / total_requests,
            "cost_per_1k_tokens": (self.total_cost / total_tokens * 1000) if total_tokens > 0 else 0.0,
            "formatted_total_cost": TokenCounter.format_cost(self.total_cost)
        }
    
    def get_cost_by_channel(self) -> Dict[str, float]:
        """按渠道统计成本"""
        channel_costs = {}
        for record in self.session_costs:
            channel_id = record["channel_id"]
            channel_costs[channel_id] = channel_costs.get(channel_id, 0.0) + record["cost"]
        return channel_costs
    
    def reset(self) -> None:
        """重置成本追踪"""
        self.session_costs = []
        self.total_cost = 0.0


# 全局成本追踪器实例
_global_cost_tracker: Optional[CostTracker] = None

def get_cost_tracker() -> CostTracker:
    """获取全局成本追踪器"""
    global _global_cost_tracker
    if _global_cost_tracker is None:
        _global_cost_tracker = CostTracker()
    return _global_cost_tracker