#!/usr/bin/env python3
"""
模型发现任务 - 自动获取各渠道的模型列表并缓存
集成智能缓存机制，优化模型发现频率和性能
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx

from core.utils.api_key_cache import get_api_key_cache_manager
from core.utils.async_file_ops import get_async_file_manager
from core.utils.channel_cache_manager import get_channel_cache_manager
from core.utils.api_key_cache_manager import get_api_key_cache_manager as get_api_key_level_cache_manager

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
        self.cached_models: dict[str, dict] = {}
        self.merged_config: dict[str, Any] = {}
        self.last_update: Optional[datetime] = None

        # API Key缓存管理器 (旧版，用于验证)
        self.api_key_cache_manager = get_api_key_cache_manager()

        # 渠道缓存管理器 (兼容性保留)
        self.channel_cache_manager = get_channel_cache_manager()
        
        # API Key级别缓存管理器 (新版，解决定价问题)
        self.api_key_level_cache_manager = get_api_key_level_cache_manager()

        # 加载现有缓存
        self._load_cache()

    def _load_cache(self):
        """加载现有缓存数据（同步版本，为兼容性保留）"""
        try:
            if self.models_cache_file.exists():
                with open(self.models_cache_file, encoding='utf-8') as f:
                    self.cached_models = json.load(f)
                logger.info(f"已加载缓存的模型数据: {len(self.cached_models)} 个渠道")

            if self.merged_config_file.exists():
                with open(self.merged_config_file, encoding='utf-8') as f:
                    self.merged_config = json.load(f)
                logger.info("已加载合并后的配置数据")

        except Exception as e:
            logger.error(f"加载缓存失败: {e}")

    async def _load_cache_async(self):
        """异步加载现有缓存数据"""
        try:
            file_manager = get_async_file_manager()

            if await file_manager.file_exists(self.models_cache_file):
                self.cached_models = await file_manager.read_json(self.models_cache_file, {})
                logger.info(f"异步加载缓存的模型数据: {len(self.cached_models)} 个渠道")

            if await file_manager.file_exists(self.merged_config_file):
                self.merged_config = await file_manager.read_json(self.merged_config_file, {})
                logger.info("异步加载合并后的配置数据")

        except Exception as e:
            logger.error(f"异步加载缓存失败: {e}")

    def _save_cache(self):
        """保存缓存数据（同步版本，为兼容性保留）"""
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

    async def _save_cache_async(self):
        """异步保存缓存数据"""
        try:
            file_manager = get_async_file_manager()

            # 异步保存模型缓存
            models_success = await file_manager.write_json(
                self.models_cache_file,
                self.cached_models,
                indent=2
            )

            # 使用ChannelCacheManager保存各渠道详细缓存（带模型分析）
            for channel_id, cache_data in self.cached_models.items():
                # 使用ChannelCacheManager进行智能模型分析和缓存
                self.channel_cache_manager.save_channel_models(channel_id, cache_data)

            # 异步保存合并后的配置
            config_success = await file_manager.write_json(
                self.merged_config_file,
                self.merged_config,
                indent=2
            )

            if models_success and config_success:
                logger.info(f"异步缓存已保存到 {self.cache_dir}")
            else:
                logger.warning("部分异步缓存保存失败")

        except Exception as e:
            logger.error(f"异步保存缓存失败: {e}")

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

    def _get_fallback_models_from_config(self, channel: dict[str, Any]) -> list[str]:
        """从配置文件获取渠道的模型列表作为回退"""
        try:
            # 从配置的模型列表中获取
            configured_models = channel.get('configured_models', [])
            logger.info(f"渠道 {channel.get('id')} 回退检查: configured_models={configured_models}, model_name={channel.get('model_name')}")

            if configured_models:
                logger.info(f"使用配置的模型列表作为回退: {channel.get('id')} 获得 {len(configured_models)} 个模型")
                return configured_models

            # 如果没有配置模型列表，但有model_name，则返回单个模型
            model_name = channel.get('model_name')
            if model_name and model_name != 'auto':
                logger.info(f"使用单个模型作为回退: {channel.get('id')} 模型 {model_name}")
                return [model_name]

            logger.warning(f"渠道 {channel.get('id')} 没有可用的回退模型配置")
            return []

        except Exception as e:
            logger.warning(f"从配置获取模型回退失败: {e}")
            return []

    async def _fetch_models_from_channel(self, channel: dict[str, Any]) -> Optional[dict[str, Any]]:
        """从单个渠道获取模型列表"""
        channel_id = channel.get('id')
        provider = channel.get('provider')
        base_url = channel.get('base_url')
        api_key = channel.get('api_key')

        # 调试日志：检查渠道配置
        if channel_id in ['oneapi_13', 'oneapi_33', 'oneapi_55']:
            logger.info(f"调试渠道 {channel_id}: configured_models={channel.get('configured_models')}, keys={list(channel.keys())}")

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

                    # 解析不同格式的响应并提取详细信息
                    models = []
                    models_data = {}

                    if 'data' in data and isinstance(data['data'], list):
                        # OpenAI标准格式
                        for model in data['data']:
                            model_id = model.get('id')
                            if model_id:
                                models.append(model_id)
                                # 提取详细的模型信息
                                models_data[model_id] = self._extract_model_info(model)
                    elif isinstance(data, list):
                        # 直接是模型列表
                        for model in data:
                            if isinstance(model, dict):
                                model_id = model.get('id')
                                if model_id:
                                    models.append(model_id)
                                    models_data[model_id] = self._extract_model_info(model)
                            else:
                                models.append(str(model))
                    elif 'models' in data:
                        # 其他格式
                        models_list = data['models']
                        if isinstance(models_list, list):
                            for model in models_list:
                                if isinstance(model, dict):
                                    model_id = model.get('id')
                                    if model_id:
                                        models.append(model_id)
                                        models_data[model_id] = self._extract_model_info(model)
                                else:
                                    models.append(str(model))

                    # 🚀 提取模型定价信息用于多Provider免费策略
                    models_pricing = self._extract_models_pricing(models_data, data, provider)

                    result = {
                        'channel_id': channel_id,
                        'provider': provider,
                        'base_url': base_url,
                        'models_url': models_url,
                        'models': models,
                        'models_data': models_data,  # 添加详细的模型数据
                        'models_pricing': models_pricing,  # 🚀 新增：每个模型的定价信息
                        'model_count': len(models),
                        'last_updated': datetime.now().isoformat(),
                        'status': 'success',
                        'api_key': api_key,  # 保存API Key用于缓存
                        'user_level': self._detect_user_level(models, provider),
                        'response_data': data  # 保存原始响应用于调试
                    }

                    logger.info(f"成功获取 {channel_id} 的 {len(models)} 个模型")
                    return result

                else:
                    logger.warning(f"获取 {channel_id} 模型失败: {response.status_code} - {response.text[:100]}")
                    # 尝试从配置文件回退
                    fallback_models = self._get_fallback_models_from_config(channel)
                    if fallback_models:
                        return {
                            'channel_id': channel_id,
                            'provider': provider,
                            'base_url': base_url,
                            'models_url': models_url,
                            'models': fallback_models,
                            'model_count': len(fallback_models),
                            'last_updated': datetime.now().isoformat(),
                            'status': 'success_fallback',
                            'note': f'Fallback to configured models due to HTTP {response.status_code}'
                        }
                    else:
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
            logger.warning(f"获取 {channel_id} 模型时发生异常: {e}")
            # 尝试从配置文件回退
            fallback_models = self._get_fallback_models_from_config(channel)
            if fallback_models:
                return {
                    'channel_id': channel_id,
                    'provider': provider,
                    'base_url': base_url,
                    'models_url': models_url,
                    'models': fallback_models,
                    'model_count': len(fallback_models),
                    'last_updated': datetime.now().isoformat(),
                    'status': 'success_fallback',
                    'note': f'Fallback to configured models due to exception: {str(e)}'
                }
            else:
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

    async def discover_models(self, channels: list[dict[str, Any]]) -> dict[str, dict]:
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
                    
                    # 保存到API Key级别缓存 (新架构)
                    try:
                        # 从结果中获取API Key信息
                        api_key = result.get('api_key', '')
                        provider = result.get('provider', 'unknown')
                        
                        self.api_key_level_cache_manager.save_api_key_models(
                            channel_id, api_key, result, provider
                        )
                        logger.debug(f"✅ Saved API key level cache for {channel_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to save API key level cache for {channel_id}: {e}")
                    
                    # 兼容性：仍然保存到旧的渠道缓存
                    try:
                        self.channel_cache_manager.save_channel_models(channel_id, result)
                        logger.debug(f"✅ Also saved to legacy channel cache for {channel_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to save legacy channel cache for {channel_id}: {e}")
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

    def merge_with_config(self, original_config_data: dict[str, Any], discovered_models: dict[str, dict]) -> dict[str, Any]:
        """将发现的模型与原始配置数据合并"""
        merged = original_config_data.copy()

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
                    'provider': info.get('provider', 'unknown') # 确保provider存在
                }
                for channel_id, info in discovered_models.items()
            }
        }

        return merged

    async def run_discovery_task(self, channels: list[dict[str, Any]], original_config_data: dict[str, Any]):
        """运行完整的模型发现任务"""
        logger.info("启动模型发现任务")

        try:
            # 发现模型
            discovered_models = await self.discover_models(channels)

            # 更新缓存
            self.cached_models.update(discovered_models)

            # 合并配置
            self.merged_config = self.merge_with_config(original_config_data, discovered_models)

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

    def get_cached_models(self, max_age_hours: int = 24) -> Optional[dict[str, dict]]:
        """获取缓存的模型数据（如果未过期）"""
        if not self.last_update:
            return None

        age = datetime.now() - self.last_update
        if age > timedelta(hours=max_age_hours):
            logger.info(f"缓存已过期 (超过 {max_age_hours} 小时)")
            return None

        return self.cached_models

    def _extract_model_info(self, model_data: dict[str, Any]) -> dict[str, Any]:
        """从模型数据中提取详细信息

        Args:
            model_data: 模型的原始数据

        Returns:
            包含详细信息的字典
        """
        model_info = {
            'id': model_data.get('id'),
            'object': model_data.get('object', 'model'),
            'created': model_data.get('created'),
            'owned_by': model_data.get('owned_by'),
        }

        # 提取上下文长度信息
        context_length = None
        if 'context_length' in model_data:
            context_length = model_data['context_length']
        elif 'top_provider' in model_data and 'context_length' in model_data['top_provider']:
            context_length = model_data['top_provider']['context_length']

        if context_length:
            model_info['context_length'] = context_length
            model_info['max_input_tokens'] = context_length

        # 提取最大输出令牌数
        max_completion_tokens = None
        if 'max_completion_tokens' in model_data:
            max_completion_tokens = model_data['max_completion_tokens']
        elif 'top_provider' in model_data and 'max_completion_tokens' in model_data['top_provider']:
            max_completion_tokens = model_data['top_provider']['max_completion_tokens']

        if max_completion_tokens:
            model_info['max_output_tokens'] = max_completion_tokens

        # 提取参数信息（从描述或其他字段）
        parameter_info = self._extract_parameter_info(model_data)
        if parameter_info:
            model_info.update(parameter_info)

        # 提取定价信息
        if 'pricing' in model_data:
            pricing = model_data['pricing']
            model_info['pricing'] = {
                'prompt': pricing.get('prompt'),
                'completion': pricing.get('completion'),
                'request': pricing.get('request'),
            }

        # 提取架构信息
        if 'architecture' in model_data:
            model_info['architecture'] = model_data['architecture']

        return model_info

    def _extract_parameter_info(self, model_data: dict[str, Any]) -> dict[str, Any]:
        """从模型数据中提取参数信息

        Args:
            model_data: 模型的原始数据

        Returns:
            包含参数信息的字典
        """
        # 从描述中提取参数信息
        description = model_data.get('description', '')
        name = model_data.get('name', '')
        id = model_data.get('id', '')

        # 合并所有可能的文本来源
        all_texts = [description, name, id]

        # 参数大小模式
        param_patterns = [
            r'(\d+\.?\d*)\s*[Bb](?:illion)?\s*(?:parameter|mixture-of-experts)?',
            r'(\d+\.?\d*)\s*[Mm](?:illion)?\s*parameter',
            r'(\d+\.?\d*)\s*[Bb]\s*param',
            r'(\d+\.?\d*)[Bb](?![A-Za-z])',  # 避免匹配 "bit", "byte"
        ]

        for text in all_texts:
            for pattern in param_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        param_value = float(match.group(1))
                        # 根据单位转换
                        if 'b' in match.group(0).lower() and 'm' not in match.group(0).lower():
                            # billions
                            param_count = int(param_value * 1000)  # 转换为百万单位
                        else:
                            # millions
                            param_count = int(param_value)

                        return {
                            'parameter_count': param_count,
                            'parameter_size_text': match.group(0)
                        }
                    except (ValueError, IndexError):
                        continue

        # 从模型ID中提取参数信息
        id_patterns = [
            r'-(\d+\.?\d*)[Bb]-',
            r'_(\d+\.?\d*)[Bb]_',
            r'(\d+\.?\d*)[Bb](?![A-Za-z])',
        ]

        for pattern in id_patterns:
            match = re.search(pattern, id)
            if match:
                try:
                    param_value = float(match.group(1))
                    return {
                        'parameter_count': int(param_value * 1000),  # 转换为百万单位
                        'parameter_size_text': f"{param_value}b"
                    }
                except (ValueError, IndexError):
                    continue

        return {}

    def get_merged_config(self) -> dict[str, Any]:
        """获取合并后的配置"""
        return self.merged_config.copy()

    def is_cache_valid(self, max_age_hours: int = 24) -> bool:
        """检查缓存是否有效"""
        if not self.last_update:
            return False

        age = datetime.now() - self.last_update
        return age <= timedelta(hours=max_age_hours)

    def _extract_models_pricing(self, models_data: dict, response_data: dict, provider: str) -> dict[str, dict]:
        """提取模型定价信息用于多Provider免费策略
        
        Args:
            models_data: 模型详细数据字典
            response_data: API原始响应数据
            provider: 提供商名称
            
        Returns:
            模型定价字典 {model_id: {'prompt': price, 'completion': price, 'is_free': bool}}
        """
        pricing_info = {}
        
        try:
            # 方法1: 从models_data中提取详细定价
            for model_id, model_data in models_data.items():
                if 'pricing' in model_data:
                    pricing = model_data['pricing']
                    prompt_price = pricing.get('prompt', 0)
                    completion_price = pricing.get('completion', 0)
                    
                    # 转换字符串价格到数值
                    try:
                        prompt_price = float(prompt_price) if prompt_price else 0
                        completion_price = float(completion_price) if completion_price else 0
                    except (ValueError, TypeError):
                        prompt_price = completion_price = 0
                    
                    is_free = (prompt_price == 0 and completion_price == 0)
                    
                    pricing_info[model_id] = {
                        'prompt': prompt_price,
                        'completion': completion_price,
                        'is_free': is_free,
                        'provider': provider
                    }
            
            # 方法2: OpenRouter特殊处理 - 从data字段直接提取
            if provider == 'openrouter' and 'data' in response_data:
                for model in response_data['data']:
                    if isinstance(model, dict):
                        model_id = model.get('id')
                        if model_id and 'pricing' in model:
                            pricing = model['pricing']
                            prompt_price = pricing.get('prompt', 0)
                            completion_price = pricing.get('completion', 0)
                            
                            # 转换字符串价格到数值
                            try:
                                prompt_price = float(prompt_price) if prompt_price else 0
                                completion_price = float(completion_price) if completion_price else 0
                            except (ValueError, TypeError):
                                prompt_price = completion_price = 0
                            
                            is_free = (prompt_price == 0 and completion_price == 0)
                            
                            # 如果还没有定价信息或这次检测到免费，更新信息
                            if model_id not in pricing_info or is_free:
                                pricing_info[model_id] = {
                                    'prompt': prompt_price,
                                    'completion': completion_price,
                                    'is_free': is_free,
                                    'provider': provider
                                }
            
            logger.debug(f"提取到 {len(pricing_info)} 个模型的定价信息 (Provider: {provider})")
            free_models = [mid for mid, info in pricing_info.items() if info.get('is_free')]
            if free_models:
                logger.info(f"🆓 发现免费模型 ({provider}): {len(free_models)} 个")
                
        except Exception as e:
            logger.warning(f"提取定价信息失败 (Provider: {provider}): {e}")
        
        return pricing_info

    def _detect_user_level(self, models: list[str], provider: str) -> str:
        """检测用户等级（基于模型列表和提供商）"""
        if not models:
            return 'unknown'

        # SiliconFlow用户等级检测
        if provider == 'siliconflow':
            pro_models = [m for m in models if 'Pro/' in m or '/Pro' in m]
            if pro_models:
                return 'pro'
            return 'free'

        # OpenRouter用户等级检测
        if provider == 'openrouter':
            model_count = len(models)
            if model_count > 100:
                return 'premium'
            elif model_count > 50:
                return 'pro'
            return 'free'

        # Groq用户等级检测
        if provider == 'groq':
            # Groq的免费模型通常较少
            return 'free' if len(models) <= 10 else 'pro'

        # 其他提供商的默认检测逻辑
        model_count = len(models)
        if model_count > 50:
            return 'premium'
        elif model_count > 20:
            return 'pro'
        elif model_count > 0:
            return 'free'

        return 'unknown'


# 全局实例
_model_discovery_task = None

def get_model_discovery_task() -> ModelDiscoveryTask:
    """获取全局模型发现任务实例"""
    global _model_discovery_task
    if _model_discovery_task is None:
        _model_discovery_task = ModelDiscoveryTask()
    return _model_discovery_task


async def run_model_discovery(channels: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    """运行模型发现任务的便捷函数"""
    task = get_model_discovery_task()
    return await task.run_discovery_task(channels, config)


def get_cached_models(max_age_hours: int = 24) -> Optional[dict[str, dict]]:
    """获取缓存模型的便捷函数"""
    task = get_model_discovery_task()
    return task.get_cached_models(max_age_hours)


def get_merged_config() -> dict[str, Any]:
    """获取合并配置的便捷函数"""
    task = get_model_discovery_task()
    return task.get_merged_config()
