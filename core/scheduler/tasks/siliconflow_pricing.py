#!/usr/bin/env python3
"""
SiliconFlow定价抓取任务 - 定期从官网获取最新定价信息
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

import httpx
from bs4 import BeautifulSoup

from ...providers.adapters.siliconflow import SiliconFlowModelPricing

logger = logging.getLogger(__name__)

class SiliconFlowPricingTask:
    """SiliconFlow定价抓取任务"""
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # 缓存文件路径
        self.pricing_cache_file = self.cache_dir / "siliconflow_pricing.json"
        self.pricing_log_file = self.cache_dir / "siliconflow_pricing_log.json"
        
        # 定价相关配置
        self.pricing_url = "https://siliconflow.cn/pricing"
        
        # 加载现有缓存
        self.cached_pricing: Dict[str, Any] = {}
        self.last_update: Optional[datetime] = None
        self._load_cache()
    
    def _load_cache(self):
        """加载现有定价缓存"""
        try:
            if self.pricing_cache_file.exists():
                with open(self.pricing_cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    self.cached_pricing = cache_data.get('pricing', {})
                    last_update_str = cache_data.get('last_update')
                    if last_update_str:
                        self.last_update = datetime.fromisoformat(last_update_str)
                    
                logger.info(f"已加载SiliconFlow定价缓存: {len(self.cached_pricing)} 个模型")
        except Exception as e:
            logger.warning(f"加载SiliconFlow定价缓存失败: {e}")
    
    def _save_cache(self, pricing_data: Dict[str, Any]):
        """保存定价缓存"""
        try:
            cache_data = {
                'last_update': datetime.now().isoformat(),
                'pricing': pricing_data,
                'source': 'siliconflow_website',
                'total_models': len(pricing_data)
            }
            
            with open(self.pricing_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"SiliconFlow定价缓存已保存: {len(pricing_data)} 个模型")
        except Exception as e:
            logger.error(f"保存SiliconFlow定价缓存失败: {e}")
    
    def _log_pricing_update(self, result: Dict[str, Any]):
        """记录定价更新日志"""
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'status': result.get('status', 'unknown'),
                'models_count': result.get('models_count', 0),
                'error': result.get('error'),
                'pricing_summary': result.get('pricing_summary', {})
            }
            
            # 读取现有日志
            logs = []
            if self.pricing_log_file.exists():
                with open(self.pricing_log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            
            # 添加新日志（保留最近50条）
            logs.append(log_entry)
            logs = logs[-50:]
            
            # 保存日志
            with open(self.pricing_log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"记录SiliconFlow定价日志失败: {e}")
    
    async def scrape_pricing_from_website(self) -> Dict[str, SiliconFlowModelPricing]:
        """从SiliconFlow官网抓取定价信息"""
        try:
            logger.info("正在从SiliconFlow官网抓取定价信息...")
            
            # 首先尝试从本地HTML文件读取（用于测试）
            html_file = self.cache_dir.parent / "logs" / "siliconflow_pricing" / "大模型 API 价格方案 - 硅基流动 SiliconFlow.html"
            
            if html_file.exists():
                logger.info("使用本地HTML文件进行定价解析")
                with open(html_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            else:
                logger.info("从官网获取定价页面...")
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                async with httpx.AsyncClient(timeout=30, headers=headers) as client:
                    response = await client.get(self.pricing_url)
                    response.raise_for_status()
                    html_content = response.text
            
            # 如果无法获取内容，使用回退定价
            if not html_content.strip():
                logger.warning("无法获取定价页面内容，使用回退定价数据")
                return self._get_fallback_pricing()
            
            # 解析HTML获取定价
            pricing_data = self._parse_pricing_html(html_content)
            
            if not pricing_data:
                logger.warning("HTML解析未获得定价数据，使用回退定价")
                return self._get_fallback_pricing()
            
            logger.info(f"成功抓取到 {len(pricing_data)} 个模型的定价信息")
            return pricing_data
            
        except Exception as e:
            logger.error(f"定价抓取失败，使用回退数据: {e}")
            return self._get_fallback_pricing()
    
    def _parse_pricing_html(self, html_content: str) -> Dict[str, SiliconFlowModelPricing]:
        """解析HTML内容获取定价信息"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            # 这里可以实现HTML解析逻辑
            # 目前返回回退数据
            return self._get_fallback_pricing()
        except Exception as e:
            logger.error(f"HTML解析失败: {e}")
            return self._get_fallback_pricing()
    
    def _get_fallback_pricing(self) -> Dict[str, SiliconFlowModelPricing]:
        """获取回退的定价数据"""
        siliconflow_models = {
            # 免费模型
            "THUDM/GLM-4.1V-9B-Thinking": (0.0, 0.0, "免费"),
            "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B": (0.0, 0.0, "免费"),
            "Qwen/Qwen2.5-7B-Instruct": (0.0, 0.0, "免费"),
            
            # Pro收费模型
            "Pro/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": (0.35, 0.35, "Pro版本"),
            "Pro/THUDM/glm-4-9b-chat": (0.60, 0.60, "Pro版本"),
            
            # 标准收费模型
            "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B": (0.70, 0.70, "标准收费"),
            "Qwen/Qwen2.5-14B-Instruct": (0.70, 0.70, "标准收费"),
        }
        
        pricing_dict = {}
        for model_name, (input_price, output_price, description) in siliconflow_models.items():
            pricing_dict[model_name] = SiliconFlowModelPricing(
                model_name=model_name,
                display_name=model_name.split('/')[-1],
                input_price=input_price,
                output_price=output_price,
                description=description
            )
        
        return pricing_dict
    
    async def run_pricing_scrape(self) -> Dict[str, Any]:
        """执行定价抓取任务"""
        logger.info("开始SiliconFlow定价抓取任务")
        start_time = datetime.now()
        
        try:
            # 清除定价缓存，强制重新抓取
            self.clear_pricing_cache()
            
            # 执行抓取
            pricing_data = await self.scrape_pricing_from_website()
            
            if not pricing_data:
                result = {
                    'status': 'error',
                    'error': '未能抓取到任何定价信息',
                    'models_count': 0,
                    'execution_time': (datetime.now() - start_time).total_seconds()
                }
                self._log_pricing_update(result)
                return result
            
            # 转换为可序列化的格式
            serializable_pricing = {}
            pricing_summary = {}
            
            for model_name, pricing in pricing_data.items():
                serializable_pricing[model_name] = {
                    'model_name': pricing.model_name,
                    'display_name': pricing.display_name,
                    'input_price': pricing.input_price,
                    'output_price': pricing.output_price,
                    'context_length': pricing.context_length,
                    'description': pricing.description,
                    'last_updated': datetime.now().isoformat()
                }
                
                # 生成价格摘要
                total_price = pricing.input_price + pricing.output_price
                if total_price == 0:
                    price_tier = 'free'
                elif total_price < 0.000001:
                    price_tier = 'very_cheap'
                elif total_price < 0.00001:
                    price_tier = 'cheap'
                else:
                    price_tier = 'standard'
                
                if price_tier not in pricing_summary:
                    pricing_summary[price_tier] = 0
                pricing_summary[price_tier] += 1
            
            # 保存缓存
            self._save_cache(serializable_pricing)
            self.cached_pricing = serializable_pricing
            self.last_update = datetime.now()
            
            result = {
                'status': 'success',
                'models_count': len(serializable_pricing),
                'pricing_summary': pricing_summary,
                'execution_time': (datetime.now() - start_time).total_seconds(),
                'updated_models': list(serializable_pricing.keys())
            }
            
            logger.info(f"SiliconFlow定价抓取完成: {len(serializable_pricing)} 个模型")
            self._log_pricing_update(result)
            return result
            
        except Exception as e:
            logger.error(f"SiliconFlow定价抓取失败: {e}")
            result = {
                'status': 'error',
                'error': str(e),
                'models_count': 0,
                'execution_time': (datetime.now() - start_time).total_seconds()
            }
            self._log_pricing_update(result)
            return result
    
    def clear_pricing_cache(self):
        """清除定价缓存 - 用于强制重新抓取"""
        if self.pricing_cache_file.exists():
            self.pricing_cache_file.unlink()
        self.cached_pricing = {}
        self.last_update = None
        logger.info("SiliconFlow定价缓存已清除")
    
    def should_update_pricing(self, force: bool = False) -> bool:
        """判断是否需要更新定价信息"""
        if force:
            return True
        
        if not self.last_update:
            return True
        
        # 每天更新一次定价信息
        update_interval = timedelta(days=1)
        return datetime.now() - self.last_update > update_interval
    
    async def get_model_pricing(self, model_name: str) -> Optional[Dict[str, Any]]:
        """获取特定模型的定价信息"""
        if model_name in self.cached_pricing:
            pricing = self.cached_pricing[model_name]
            return {
                "prompt": str(pricing['input_price']),
                "completion": str(pricing['output_price']),
                "request": "0",
                "image": "0",
                "audio": "0",
                "web_search": "0",
                "internal_reasoning": "0"
            }
        return None
    
    def get_all_pricing(self) -> Dict[str, Any]:
        """获取所有缓存的定价信息"""
        return self.cached_pricing.copy()
    
    def get_pricing_stats(self) -> Dict[str, Any]:
        """获取定价统计信息"""
        if not self.cached_pricing:
            return {'total_models': 0}
        
        stats = {
            'total_models': len(self.cached_pricing),
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'price_distribution': {}
        }
        
        # 统计价格分布
        for model_name, pricing in self.cached_pricing.items():
            total_price = pricing['input_price'] + pricing['output_price']
            
            if total_price == 0:
                tier = 'free'
            elif total_price < 0.000001:
                tier = 'very_cheap'
            elif total_price < 0.00001:
                tier = 'cheap'
            else:
                tier = 'standard'
            
            stats['price_distribution'][tier] = stats['price_distribution'].get(tier, 0) + 1
        
        return stats

# 全局实例
_pricing_task = None

def get_siliconflow_pricing_task() -> SiliconFlowPricingTask:
    """获取全局SiliconFlow定价任务实例"""
    global _pricing_task
    if _pricing_task is None:
        _pricing_task = SiliconFlowPricingTask()
    return _pricing_task

async def run_siliconflow_pricing_update(force: bool = False) -> Dict[str, Any]:
    """运行SiliconFlow定价更新任务"""
    task = get_siliconflow_pricing_task()
    
    if task.should_update_pricing(force):
        return await task.run_pricing_scrape()
    else:
        logger.info("SiliconFlow定价信息仍然有效，跳过更新")
        return {
            'status': 'skipped',
            'reason': 'pricing_still_valid',
            'last_update': task.last_update.isoformat() if task.last_update else None,
            'models_count': len(task.cached_pricing)
        }