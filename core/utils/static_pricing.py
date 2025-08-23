#!/usr/bin/env python3
"""
静态定价配置加载器 - 统一管理硅基流动和豆包的静态定价数据
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .tiered_pricing import get_pricing_calculator, TieredPricingCalculator

logger = logging.getLogger(__name__)

@dataclass
class StaticPricingResult:
    """静态定价结果"""
    input_price: float
    output_price: float
    provider: str
    model_id: str
    pricing_info: str
    is_free: bool = False

class StaticPricingLoader:
    """静态定价配置加载器"""
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.siliconflow_file = self.cache_dir / "siliconflow_pricing_accurate.json"
        self.doubao_calculator = get_pricing_calculator()
        
        # 加载硅基流动定价
        self.siliconflow_data = self._load_siliconflow_pricing()
    
    def _load_siliconflow_pricing(self) -> Dict[str, Any]:
        """加载硅基流动定价配置"""
        try:
            if not self.siliconflow_file.exists():
                logger.warning(f"硅基流动定价配置文件不存在: {self.siliconflow_file}")
                return {"models": {}}
            
            with open(self.siliconflow_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载硅基流动定价配置失败: {e}")
            return {"models": {}}
    
    def get_siliconflow_pricing(self, model_name: str) -> Optional[StaticPricingResult]:
        """获取硅基流动模型定价"""
        try:
            models = self.siliconflow_data.get("models", {})
            model_data = models.get(model_name)
            
            if not model_data:
                # 尝试模糊匹配
                for cached_model, data in models.items():
                    if (model_name.lower() in cached_model.lower() or 
                        cached_model.lower() in model_name.lower()):
                        model_data = data
                        break
            
            if not model_data:
                return None
            
            pricing = model_data.get("online_pricing", {})
            input_price = pricing.get("input_price", 0.0)
            output_price = pricing.get("output_price", 0.0)
            
            return StaticPricingResult(
                input_price=input_price,
                output_price=output_price,
                provider="siliconflow",
                model_id=model_data.get("model_id", model_name),
                pricing_info=f"静态配置 - {model_data.get('category', '未知分类')}",
                is_free=(input_price == 0.0 and output_price == 0.0)
            )
            
        except Exception as e:
            logger.error(f"获取硅基流动定价失败 ({model_name}): {e}")
            return None
    
    def get_doubao_pricing(self, model_name: str, input_tokens: int = 10000, output_tokens: int = 2000) -> Optional[StaticPricingResult]:
        """获取豆包模型定价"""
        try:
            # 使用阶梯定价计算器
            pricing_result = self.doubao_calculator.get_model_pricing(
                model_name, input_tokens, output_tokens
            )
            
            if not pricing_result:
                return None
            
            return StaticPricingResult(
                input_price=pricing_result.input_price,
                output_price=pricing_result.output_price,
                provider="doubao",
                model_id=model_name,
                pricing_info=f"阶梯定价 - {pricing_result.tier_info}",
                is_free=(pricing_result.input_price == 0.0 and pricing_result.output_price == 0.0)
            )
            
        except Exception as e:
            logger.error(f"获取豆包定价失败 ({model_name}): {e}")
            return None
    
    def get_model_pricing(self, provider_name: str, model_name: str, 
                         input_tokens: int = 10000, output_tokens: int = 2000) -> Optional[StaticPricingResult]:
        """根据提供商获取模型定价"""
        provider_lower = provider_name.lower()
        
        if 'siliconflow' in provider_lower:
            return self.get_siliconflow_pricing(model_name)
        elif 'doubao' in provider_lower or 'bytedance' in provider_lower:
            return self.get_doubao_pricing(model_name, input_tokens, output_tokens)
        else:
            return None
    
    def list_siliconflow_models(self) -> Dict[str, Any]:
        """列出所有硅基流动模型"""
        return self.siliconflow_data.get("models", {})
    
    def list_doubao_models(self) -> list:
        """列出所有豆包模型"""
        return self.doubao_calculator.list_supported_models()
    
    def get_free_models(self, provider: Optional[str] = None) -> Dict[str, StaticPricingResult]:
        """获取免费模型列表"""
        free_models = {}
        
        # 硅基流动免费模型
        if provider is None or 'siliconflow' in provider.lower():
            for model_name, model_data in self.siliconflow_data.get("models", {}).items():
                pricing = model_data.get("online_pricing", {})
                if pricing.get("input_price", 0.0) == 0.0 and pricing.get("output_price", 0.0) == 0.0:
                    result = self.get_siliconflow_pricing(model_name)
                    if result:
                        free_models[f"siliconflow:{model_name}"] = result
        
        # 豆包免费模型（如果有的话）
        if provider is None or 'doubao' in provider.lower():
            for model_name in self.doubao_calculator.list_supported_models():
                result = self.get_doubao_pricing(model_name)
                if result and result.is_free:
                    free_models[f"doubao:{model_name}"] = result
        
        return free_models

# 全局实例
_static_pricing_loader: Optional[StaticPricingLoader] = None

def get_static_pricing_loader() -> StaticPricingLoader:
    """获取全局静态定价加载器实例"""
    global _static_pricing_loader
    if _static_pricing_loader is None:
        _static_pricing_loader = StaticPricingLoader()
    return _static_pricing_loader

def get_provider_pricing(provider_name: str, model_name: str, 
                        input_tokens: int = 10000, output_tokens: int = 2000) -> Optional[Tuple[float, float, str]]:
    """便捷函数：获取提供商模型定价"""
    loader = get_static_pricing_loader()
    result = loader.get_model_pricing(provider_name, model_name, input_tokens, output_tokens)
    
    if result:
        return (
            result.input_price / 1000000,  # 转换为每token价格
            result.output_price / 1000000,
            result.pricing_info
        )
    return None

if __name__ == "__main__":
    # 测试代码
    loader = StaticPricingLoader()
    
    # 测试硅基流动
    print("=== 硅基流动定价测试 ===")
    test_models = ["Qwen/Qwen2.5-7B-Instruct", "deepseek-ai/DeepSeek-V3", "Pro/deepseek-ai/DeepSeek-V3"]
    
    for model in test_models:
        result = loader.get_siliconflow_pricing(model)
        if result:
            print(f"{model}: 输入 {result.input_price} 元/M tokens, 输出 {result.output_price} 元/M tokens ({result.pricing_info})")
        else:
            print(f"{model}: 未找到定价")
    
    # 测试豆包
    print("\n=== 豆包定价测试 ===")
    doubao_models = ["doubao-pro-4k", "doubao-seed-1.6", "deepseek-v3.1"]
    
    for model in doubao_models:
        result = loader.get_doubao_pricing(model, 10000, 2000)
        if result:
            print(f"{model}: 输入 {result.input_price} 元/M tokens, 输出 {result.output_price} 元/M tokens ({result.pricing_info})")
        else:
            print(f"{model}: 未找到定价")
    
    # 测试免费模型
    print("\n=== 免费模型列表 ===")
    free_models = loader.get_free_models()
    print(f"共找到 {len(free_models)} 个免费模型")
    for model_key, result in list(free_models.items())[:5]:  # 显示前5个
        print(f"{model_key}: {result.pricing_info}")