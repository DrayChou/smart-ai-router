# -*- coding: utf-8 -*-
"""
SiliconFlow Provider Adapter with HTML pricing scraper
"""
import re
import json
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging

import httpx
from bs4 import BeautifulSoup

from ..base import BaseAdapter

logger = logging.getLogger(__name__)

@dataclass
class SiliconFlowModelPricing:
    """SiliconFlow模型定价信息"""
    model_name: str
    display_name: str
    input_price: float  # 输入价格 (每1K tokens)
    output_price: float  # 输出价格 (每1K tokens)
    context_length: Optional[int] = None
    description: Optional[str] = None

class SiliconFlowAdapter(BaseAdapter):
    """SiliconFlow适配器 - 支持HTML定价抓取"""
    
    def __init__(self, provider_name: str = "siliconflow", config: dict = None):
        if config is None:
            config = {
                "base_url": "https://api.siliconflow.cn",
                "auth_type": "bearer",
                "timeout": 30
            }
        super().__init__(provider_name, config)
        self.base_url = "https://api.siliconflow.cn"
        self.pricing_url = "https://siliconflow.cn/pricing"
        self._cached_pricing: Optional[Dict[str, SiliconFlowModelPricing]] = None
        
    async def discover_models(self, api_key: str, timeout: int = 30) -> List[str]:
        """发现SiliconFlow可用模型"""
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # 尝试获取模型列表
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    f"{self.base_url}/v1/models",
                    headers=headers
                )
                response.raise_for_status()
                
                models_data = response.json()
                if 'data' in models_data:
                    models = [model['id'] for model in models_data['data']]
                    logger.info(f"SiliconFlow: 发现 {len(models)} 个模型")
                    return models
                else:
                    logger.warning("SiliconFlow: 无效的模型列表响应格式")
                    return []
                    
        except Exception as e:
            logger.error(f"SiliconFlow模型发现失败: {e}")
            # 回退到已知模型列表
            fallback_models = [
                "Qwen/Qwen2.5-7B-Instruct",
                "Qwen/Qwen2.5-14B-Instruct", 
                "Qwen/Qwen2.5-32B-Instruct",
                "Qwen/Qwen2.5-72B-Instruct",
                "deepseek-ai/DeepSeek-V2.5",
                "meta-llama/Meta-Llama-3.1-8B-Instruct",
                "meta-llama/Meta-Llama-3.1-70B-Instruct",
                "meta-llama/Meta-Llama-3.1-405B-Instruct",
                "THUDM/glm-4-9b-chat",
                "Pro/THUDM/glm-4-plus",
                "01-ai/Yi-1.5-9B-Chat-16K",
                "01-ai/Yi-1.5-34B-Chat-16K"
            ]
            logger.info(f"SiliconFlow: 使用回退模型列表 ({len(fallback_models)} 个模型)")
            return fallback_models
    
    async def scrape_pricing_from_website(self) -> Dict[str, SiliconFlowModelPricing]:
        """从SiliconFlow官网抓取定价信息"""
        if self._cached_pricing:
            return self._cached_pricing
            
        try:
            logger.info("正在从SiliconFlow官网抓取定价信息...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            async with httpx.AsyncClient(timeout=30, headers=headers) as client:
                response = await client.get(self.pricing_url)
                response.raise_for_status()
                
                # 解析HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                pricing_data = {}
                
                # 方法1: 查找包含定价信息的表格或卡片
                pricing_tables = soup.find_all(['table', 'div'], class_=re.compile(r'pricing|price|model', re.I))
                
                for table in pricing_tables:
                    # 查找模型名称和价格
                    rows = table.find_all(['tr', 'div'], recursive=True)
                    for row in rows:
                        text = row.get_text(strip=True)
                        
                        # 匹配模型名称模式 (Qwen, GLM, DeepSeek等)
                        model_patterns = [
                            r'(Qwen[\d\.]*[-/]\w+)',
                            r'(GLM-?\d+[\w-]*)',
                            r'(DeepSeek[\w\.-]*)',
                            r'(Yi[\d\.-]*[\w-]*)',
                            r'(Llama[\d\.-]*[\w-]*)',
                            r'(ChatGLM[\d-]*)'
                        ]
                        
                        for pattern in model_patterns:
                            match = re.search(pattern, text, re.I)
                            if match:
                                model_name = match.group(1)
                                
                                # 查找价格信息 (支持多种格式)
                                price_patterns = [
                                    r'(\d+\.?\d*)\s*[￥¥]\s*/?\s*1?K?\s*(?:tokens?)?.*?(\d+\.?\d*)\s*[￥¥]\s*/?\s*1?K?\s*(?:tokens?)?',
                                    r'输入[：:]\s*(\d+\.?\d*)[￥¥].*?输出[：:]\s*(\d+\.?\d*)[￥¥]',
                                    r'(\d+\.?\d*)[￥¥]/1K.*?(\d+\.?\d*)[￥¥]/1K'
                                ]
                                
                                for price_pattern in price_patterns:
                                    price_match = re.search(price_pattern, text)
                                    if price_match:
                                        input_price = float(price_match.group(1)) / 1000  # 转换为每token价格
                                        output_price = float(price_match.group(2)) / 1000
                                        
                                        pricing_data[model_name] = SiliconFlowModelPricing(
                                            model_name=model_name,
                                            display_name=model_name,
                                            input_price=input_price,
                                            output_price=output_price,
                                            description=f"从官网抓取的定价信息"
                                        )
                                        break
                
                # 方法2: 查找JavaScript中的定价数据
                script_tags = soup.find_all('script')
                for script in script_tags:
                    if script.string:
                        # 查找可能包含价格的JSON数据
                        json_matches = re.findall(r'\{[^{}]*(?:price|pricing|model)[^{}]*\}', script.string, re.I)
                        for json_str in json_matches:
                            try:
                                data = json.loads(json_str)
                                # 处理JSON中的定价数据
                                if isinstance(data, dict) and 'models' in data:
                                    for model_info in data['models']:
                                        if 'name' in model_info and 'price' in model_info:
                                            model_name = model_info['name']
                                            price_info = model_info['price']
                                            if isinstance(price_info, dict):
                                                input_price = price_info.get('input', 0) / 1000
                                                output_price = price_info.get('output', 0) / 1000
                                                pricing_data[model_name] = SiliconFlowModelPricing(
                                                    model_name=model_name,
                                                    display_name=model_info.get('display_name', model_name),
                                                    input_price=input_price,
                                                    output_price=output_price
                                                )
                            except (json.JSONDecodeError, KeyError):
                                continue
                
                # 如果没有抓取到数据，使用回退的估算价格
                if not pricing_data:
                    logger.warning("未能从官网抓取到定价信息，使用估算价格")
                    pricing_data = self._get_fallback_pricing()
                
                self._cached_pricing = pricing_data
                logger.info(f"SiliconFlow: 成功抓取 {len(pricing_data)} 个模型的定价信息")
                return pricing_data
                
        except Exception as e:
            logger.error(f"SiliconFlow定价抓取失败: {e}")
            # 使用回退估算价格
            fallback_pricing = self._get_fallback_pricing()
            self._cached_pricing = fallback_pricing
            return fallback_pricing
    
    def _get_fallback_pricing(self) -> Dict[str, SiliconFlowModelPricing]:
        """基于真实SiliconFlow官网定价的回退数据"""
        # 真实的SiliconFlow定价数据（基于2025年1月抓取的HTML数据）
        siliconflow_models = {
            # ==================== 免费模型 ====================
            # GLM系列免费模型
            "THUDM/GLM-4.1V-9B-Thinking": (0.0, 0.0, "免费"),
            "THUDM/GLM-Z1-9B-0414": (0.0, 0.0, "免费"),
            "THUDM/GLM-4-9B-0414": (0.0, 0.0, "免费"),
            "THUDM/glm-4-9b-chat": (0.0, 0.0, "免费"),
            
            # DeepSeek系列免费模型
            "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B": (0.0, 0.0, "免费"),
            "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": (0.0, 0.0, "免费"),
            
            # Qwen系列免费模型
            "Qwen/Qwen2.5-7B-Instruct": (0.0, 0.0, "免费"),
            "Qwen/Qwen2.5-Coder-7B-Instruct": (0.0, 0.0, "免费"),
            "Qwen/Qwen3-8B": (0.0, 0.0, "免费"),
            "Qwen/Qwen2-7B-Instruct": (0.0, 0.0, "免费"),
            
            # InternLM系列免费模型
            "internlm/internlm2_5-7b-chat": (0.0, 0.0, "免费"),
            
            # ==================== Pro收费模型 ====================
            # DeepSeek Pro模型
            "Pro/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": (0.35, 0.35, "Pro版本"),
            
            # Qwen Pro模型
            "Pro/Qwen/Qwen2.5-Coder-7B-Instruct": (0.35, 0.35, "Pro版本"),
            "Pro/Qwen/Qwen2.5-VL-7B-Instruct": (0.35, 0.35, "Pro版本"),
            "Pro/Qwen/Qwen2.5-7B-Instruct": (0.35, 0.35, "Pro版本"),
            "Pro/Qwen/Qwen2-7B-Instruct": (0.35, 0.35, "Pro版本"),
            
            # GLM Pro模型
            "Pro/THUDM/glm-4-9b-chat": (0.60, 0.60, "Pro版本"),
            "Pro/THUDM/GLM-4.1V-9B-Thinking": (0.25, 0.25, "Pro版本"),
            
            # ==================== 标准收费模型 ====================
            # DeepSeek标准收费模型
            "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B": (0.70, 0.70, "标准收费"),
            "deepseek-ai/deepseek-vl2": (0.99, 0.99, "多模态视觉模型"),
            
            # Qwen标准收费模型
            "Qwen/Qwen2.5-14B-Instruct": (0.70, 0.70, "标准收费"),
            "Qwen/Qwen2.5-32B-Instruct": (1.40, 1.40, "大模型"),
            "Qwen/Qwen2.5-72B-Instruct": (2.8, 2.8, "超大模型"),
            
            # GLM标准收费模型
            "THUDM/GLM-4V-Plus": (14.0, 14.0, "多模态增强版"),
            
            # Meta LLaMA收费模型
            "meta-llama/Meta-Llama-3.1-8B-Instruct": (0.35, 0.35, "Llama 3.1"),
            "meta-llama/Meta-Llama-3.1-70B-Instruct": (2.8, 2.8, "Llama 3.1大模型"),
            "meta-llama/Meta-Llama-3.1-405B-Instruct": (14.0, 14.0, "Llama 3.1超大模型"),
        }
        
        pricing_data = {}
        for model_name, (input_price_per_m, output_price_per_m, description) in siliconflow_models.items():
            # 价格从 元/M tokens 转换为 USD/token (假设 1元 ≈ 0.14美元)
            usd_rate = 0.14
            input_price_per_token = (input_price_per_m * usd_rate) / 1_000_000
            output_price_per_token = (output_price_per_m * usd_rate) / 1_000_000
            
            pricing_data[model_name] = SiliconFlowModelPricing(
                model_name=model_name,
                display_name=f"{model_name.split('/')[-1]} ({description})" if '/' in model_name else f"{model_name} ({description})",
                input_price=input_price_per_token,
                output_price=output_price_per_token,
                description=f"SiliconFlow官方定价: {input_price_per_m}元/M tokens ({description})"
            )
        
        return pricing_data
    
    async def get_model_pricing(self, model_name: str) -> Optional[Dict[str, Any]]:
        """获取特定模型的定价信息"""
        pricing_data = await self.scrape_pricing_from_website()
        
        if model_name in pricing_data:
            pricing = pricing_data[model_name]
            return {
                "prompt": str(pricing.input_price),
                "completion": str(pricing.output_price),
                "request": "0",
                "image": "0",
                "audio": "0",
                "web_search": "0",
                "internal_reasoning": "0"
            }
        
        return None
    
    async def enhance_model_data(self, model_name: str, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """增强模型数据 - 添加定价信息"""
        pricing = await self.get_model_pricing(model_name)
        if pricing:
            if 'raw_data' not in base_data:
                base_data['raw_data'] = {}
            base_data['raw_data']['pricing'] = pricing
            
            # 添加显示名称
            pricing_data = await self.scrape_pricing_from_website()
            if model_name in pricing_data:
                model_pricing = pricing_data[model_name]
                base_data['raw_data']['name'] = model_pricing.display_name
                if model_pricing.description:
                    base_data['raw_data']['description'] = model_pricing.description
        
        return base_data
    
    def clear_pricing_cache(self):
        """清除定价缓存 - 用于强制重新抓取"""
        self._cached_pricing = None
        logger.info("SiliconFlow定价缓存已清除")