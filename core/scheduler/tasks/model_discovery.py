#!/usr/bin/env python3
"""
模型发现任务 - 自动获取各渠道的模型列表并缓存
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse
import httpx
import logging

logger = logging.getLogger(__name__)

class ModelDiscoveryTask:
    """模型发现任务类"""
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # 缓存文件路径
        self.models_cache_file = self.cache_dir / "discovered_models.json"
        self.merged_config_file = self.cache_dir / "merged_config.json"
        self.discovery_log_file = self.cache_dir / "model_discovery_log.json"
        
        # 全局缓存变量
        self.cached_models: Dict[str, Dict] = {}
        self.merged_config: Dict[str, Any] = {}
        self.last_update: Optional[datetime] = None
        
        # 加载现有缓存
        self._load_cache()
    
    def _load_cache(self):
        """加载现有缓存数据"""
        try:
            if self.models_cache_file.exists():
                with open(self.models_cache_file, 'r', encoding='utf-8') as f:
                    self.cached_models = json.load(f)
                logger.info(f"已加载缓存的模型数据: {len(self.cached_models)} 个渠道")
            
            if self.merged_config_file.exists():
                with open(self.merged_config_file, 'r', encoding='utf-8') as f:
                    self.merged_config = json.load(f)
                logger.info("已加载合并后的配置数据")
                
        except Exception as e:
            logger.error(f"加载缓存失败: {e}")
    
    def _save_cache(self):
        """保存缓存数据"""
        try:
            # 保存模型缓存
            with open(self.models_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cached_models, f, indent=2, ensure_ascii=False)
            
            # 保存合并后的配置
            with open(self.merged_config_file, 'w', encoding='utf-8') as f:
                json.dump(self.merged_config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"缓存已保存到 {self.cache_dir}")
            
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
    
    def _get_models_endpoint(self, base_url: str) -> str:
        """根据base_url自适应计算models端点"""
        base_url = base_url.rstrip('/')
        
        # 常见的模式匹配
        patterns = [
            # OpenAI标准格式
            ("/v1", "/v1/models"),
            ("/openai/v1", "/openai/v1/models"),
            
            # 特殊厂商格式
            ("", "/v1/models"),  # 默认添加v1
        ]
        
        for pattern, endpoint in patterns:
            if base_url.endswith(pattern):
                if pattern:
                    return base_url.replace(pattern, endpoint)
                else:
                    return f"{base_url}/v1/models"
        
        # 如果都不匹配，尝试直接添加
        if not base_url.endswith('/v1'):
            return f"{base_url}/v1/models"
        else:
            return f"{base_url}/models"
    
    async def _fetch_models_from_channel(self, channel: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从单个渠道获取模型列表"""
        channel_id = channel.get('id')
        provider = channel.get('provider')
        base_url = channel.get('base_url')
        api_key = channel.get('api_key')
        
        if not all([base_url, api_key]):
            logger.warning(f"渠道 {channel_id} 缺少必要信息，跳过")
            return None
        
        # 获取模型端点URL
        models_url = self._get_models_endpoint(base_url)
        
        # 构建请求头
        headers = {
            "User-Agent": "smart-ai-router/0.1.0",
            "Accept": "application/json"
        }
        
        # 根据provider类型设置认证头
        if provider in ['openai', 'burn_hair', 'groq', 'siliconflow']:
            headers["Authorization"] = f"Bearer {api_key}"
        elif provider == 'anthropic':
            headers["x-api-key"] = api_key
        else:
            # 默认使用Bearer认证
            headers["Authorization"] = f"Bearer {api_key}"
        
        try:
            timeout = httpx.Timeout(30.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                logger.info(f"正在获取 {channel_id} 的模型列表: {models_url}")
                
                response = await client.get(models_url, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    models = []
                    
                    # 解析不同格式的响应
                    if 'data' in data and isinstance(data['data'], list):
                        # OpenAI标准格式
                        models = [model.get('id') for model in data['data'] if model.get('id')]
                    elif isinstance(data, list):
                        # 直接是模型列表
                        models = [model.get('id') if isinstance(model, dict) else str(model) for model in data]
                    elif 'models' in data:
                        # 其他格式
                        models_data = data['models']
                        if isinstance(models_data, list):
                            models = [model.get('id') if isinstance(model, dict) else str(model) for model in models_data]
                    
                    result = {
                        'channel_id': channel_id,
                        'provider': provider,
                        'base_url': base_url,
                        'models_url': models_url,
                        'models': models,
                        'model_count': len(models),
                        'last_updated': datetime.now().isoformat(),
                        'status': 'success',
                        'response_data': data  # 保存原始响应用于调试
                    }
                    
                    logger.info(f"成功获取 {channel_id} 的 {len(models)} 个模型")
                    return result
                    
                else:
                    logger.error(f"获取 {channel_id} 模型失败: {response.status_code} - {response.text}")
                    return {
                        'channel_id': channel_id,
                        'provider': provider,
                        'base_url': base_url,
                        'models_url': models_url,
                        'models': [],
                        'model_count': 0,
                        'last_updated': datetime.now().isoformat(),
                        'status': 'error',
                        'error': f"HTTP {response.status_code}: {response.text[:200]}"
                    }
                    
        except Exception as e:
            logger.error(f"获取 {channel_id} 模型时发生异常: {e}")
            return {
                'channel_id': channel_id,
                'provider': provider,
                'base_url': base_url,
                'models_url': models_url,
                'models': [],
                'model_count': 0,
                'last_updated': datetime.now().isoformat(),
                'status': 'error',
                'error': str(e)
            }
    
    async def discover_models(self, channels: List[Dict[str, Any]]) -> Dict[str, Dict]:
        """发现所有渠道的模型"""
        logger.info(f"开始模型发现任务，共 {len(channels)} 个渠道")
        
        # 过滤启用的渠道
        enabled_channels = [ch for ch in channels if ch.get('enabled', True)]
        logger.info(f"启用的渠道数量: {len(enabled_channels)}")
        
        # 并发获取模型
        tasks = []
        for channel in enabled_channels:
            task = self._fetch_models_from_channel(channel)
            tasks.append(task)
        
        # 执行并发请求
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 整理结果
        discovered_models = {}
        successful_count = 0
        failed_count = 0
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"任务执行异常: {result}")
                failed_count += 1
                continue
            
            if result:
                channel_id = result['channel_id']
                discovered_models[channel_id] = result
                
                if result['status'] == 'success':
                    successful_count += 1
                else:
                    failed_count += 1
        
        # 记录发现日志
        discovery_log = {
            'timestamp': datetime.now().isoformat(),
            'total_channels': len(channels),
            'enabled_channels': len(enabled_channels),
            'successful_requests': successful_count,
            'failed_requests': failed_count,
            'discovered_models': discovered_models
        }
        
        # 保存发现日志
        try:
            with open(self.discovery_log_file, 'w', encoding='utf-8') as f:
                json.dump(discovery_log, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存发现日志失败: {e}")
        
        logger.info(f"模型发现完成: 成功 {successful_count}, 失败 {failed_count}")
        
        return discovered_models
    
    def merge_with_config(self, original_config: Dict[str, Any], discovered_models: Dict[str, Dict]) -> Dict[str, Any]:
        """将发现的模型与原始配置合并"""
        merged = original_config.copy()
        
        # 更新渠道信息
        if 'channels' in merged:
            for channel in merged['channels']:
                channel_id = channel.get('id')
                if channel_id in discovered_models:
                    model_info = discovered_models[channel_id]
                    
                    # 添加发现的模型信息
                    channel['discovered_models'] = model_info['models']
                    channel['model_count'] = model_info['model_count']
                    channel['models_last_updated'] = model_info['last_updated']
                    channel['discovery_status'] = model_info['status']
                    
                    # 如果发现了模型但配置中没有model_name，使用第一个模型
                    if not channel.get('model_name') and model_info['models']:
                        channel['suggested_model'] = model_info['models'][0]
                    
                    # 验证配置的模型是否在发现的模型列表中
                    config_model = channel.get('model_name')
                    if config_model and config_model not in model_info['models']:
                        channel['model_validation_warning'] = f"配置的模型 '{config_model}' 不在发现的模型列表中"
        
        # 添加发现统计信息
        merged['model_discovery'] = {
            'last_updated': datetime.now().isoformat(),
            'total_channels_discovered': len(discovered_models),
            'total_models_discovered': sum(info['model_count'] for info in discovered_models.values()),
            'discovery_summary': {
                channel_id: {
                    'model_count': info['model_count'],
                    'status': info['status'],
                    'provider': info['provider']
                }
                for channel_id, info in discovered_models.items()
            }
        }
        
        return merged
    
    async def run_discovery_task(self, channels: List[Dict[str, Any]], original_config: Dict[str, Any]):
        """运行完整的模型发现任务"""
        logger.info("启动模型发现任务")
        
        try:
            # 发现模型
            discovered_models = await self.discover_models(channels)
            
            # 更新缓存
            self.cached_models.update(discovered_models)
            
            # 合并配置
            self.merged_config = self.merge_with_config(original_config, discovered_models)
            
            # 保存缓存
            self._save_cache()
            
            # 更新时间戳
            self.last_update = datetime.now()
            
            logger.info(f"模型发现任务完成，共发现 {len(discovered_models)} 个渠道的模型")
            
            return {
                'success': True,
                'discovered_channels': len(discovered_models),
                'total_models': sum(info['model_count'] for info in discovered_models.values()),
                'last_update': self.last_update.isoformat()
            }
            
        except Exception as e:
            logger.error(f"模型发现任务失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'last_update': datetime.now().isoformat()
            }
    
    def get_cached_models(self, max_age_hours: int = 24) -> Optional[Dict[str, Dict]]:
        """获取缓存的模型数据（如果未过期）"""
        if not self.last_update:
            return None
        
        age = datetime.now() - self.last_update
        if age > timedelta(hours=max_age_hours):
            logger.info(f"缓存已过期 (超过 {max_age_hours} 小时)")
            return None
        
        return self.cached_models
    
    def get_merged_config(self) -> Dict[str, Any]:
        """获取合并后的配置"""
        return self.merged_config.copy()
    
    def is_cache_valid(self, max_age_hours: int = 24) -> bool:
        """检查缓存是否有效"""
        if not self.last_update:
            return False
        
        age = datetime.now() - self.last_update
        return age <= timedelta(hours=max_age_hours)


# 全局实例
_model_discovery_task = None

def get_model_discovery_task() -> ModelDiscoveryTask:
    """获取全局模型发现任务实例"""
    global _model_discovery_task
    if _model_discovery_task is None:
        _model_discovery_task = ModelDiscoveryTask()
    return _model_discovery_task


async def run_model_discovery(channels: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    """运行模型发现任务的便捷函数"""
    task = get_model_discovery_task()
    return await task.run_discovery_task(channels, config)


def get_cached_models(max_age_hours: int = 24) -> Optional[Dict[str, Dict]]:
    """获取缓存模型的便捷函数"""
    task = get_model_discovery_task()
    return task.get_cached_models(max_age_hours)


def get_merged_config() -> Dict[str, Any]:
    """获取合并配置的便捷函数"""
    task = get_model_discovery_task()
    return task.get_merged_config()