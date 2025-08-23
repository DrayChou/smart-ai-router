#!/usr/bin/env python3
"""
任务管理器 - 统一管理所有后台任务
"""

import asyncio
from typing import Dict, Any, Optional
import logging

from .scheduler import get_scheduler, add_task, start_scheduler, stop_scheduler, get_task_status
from .tasks.model_discovery import run_model_discovery, get_model_discovery_task
from .tasks.pricing_discovery import run_pricing_discovery, get_pricing_discovery_task
from .tasks.service_health_check import run_health_check_task, ServiceHealthChecker
# SiliconFlow定价现在使用静态配置文件 (cache/siliconflow_pricing_accurate.json)
# Doubao pricing now uses static configuration (removed dynamic scraping)
from ..utils.api_key_validator import run_api_key_validation_task

logger = logging.getLogger(__name__)

class TaskManager:
    """任务管理器"""
    
    def __init__(self, config_loader=None):
        self.config_loader = config_loader
        self.scheduler = get_scheduler()
        self.is_initialized = False
    
    def initialize_tasks(self, config: Dict[str, Any]):
        """初始化所有定时任务"""
        if self.is_initialized:
            logger.warning("任务已初始化，跳过")
            return
        
        # 从配置中获取任务设置
        task_config = config.get('tasks', {})
        
        # 1. 模型发现任务 - 🚀 修复：正确读取配置文件的 run_on_startup 设置
        model_discovery_config = task_config.get('model_discovery', {})
        if model_discovery_config.get('enabled', True):
            interval = model_discovery_config.get('interval_hours', 6) * 3600  # 转换为秒
            run_immediately = model_discovery_config.get('run_on_startup', True)  # 🚀 修复：恢复配置文件控制
            
            add_task(
                name='model_discovery',
                func=self._run_model_discovery_task,
                interval_seconds=interval,
                run_immediately=run_immediately
            )
            logger.info(f"已添加模型发现任务，间隔 {interval/3600}h")
        
        # 2. 定价发现任务
        pricing_discovery_config = task_config.get('pricing_discovery', {})
        if pricing_discovery_config.get('enabled', True):
            interval = pricing_discovery_config.get('interval_hours', 12) * 3600  # 转换为秒
            run_immediately = pricing_discovery_config.get('run_on_startup', False)
            
            add_task(
                name='pricing_discovery',
                func=self._run_pricing_discovery_task,
                interval_seconds=interval,
                run_immediately=run_immediately
            )
            logger.info(f"已添加定价发现任务，间隔 {interval/3600}h")
        
        # 2. API密钥验证任务
        # 2. API密钥验证任务 - 🚀 修复：正确读取配置文件的 run_on_startup 设置  
        api_key_config = task_config.get('api_key_validation', {})
        if api_key_config.get('enabled', True):
            interval = api_key_config.get('interval_hours', 6) * 3600  # 转换为秒
            run_immediately = api_key_config.get('run_on_startup', True)  # 🚀 修复：恢复配置文件控制
            
            add_task(
                name='api_key_validation',
                func=self._run_api_key_validation_task,
                interval_seconds=interval,
                run_immediately=run_immediately
            )
            logger.info(f"已添加API密钥验证任务，间隔 {interval/3600}h")
        
        # 3. 健康检查任务
        health_check_config = task_config.get('health_check', {})
        if health_check_config.get('enabled', True):
            interval = health_check_config.get('interval_minutes', 30) * 60  # 转换为秒
            run_immediately = health_check_config.get('run_on_startup', False)  # 从配置文件读取
            
            add_task(
                name='health_check',
                func=self._run_health_check_task,
                interval_seconds=interval,
                run_immediately=run_immediately
            )
            logger.info(f"已添加健康检查任务，间隔 {interval/60}min")
        
        # 4. 缓存清理任务
        cache_cleanup_config = task_config.get('cache_cleanup', {})
        if cache_cleanup_config.get('enabled', True):
            interval = cache_cleanup_config.get('interval_hours', 24) * 3600
            
            add_task(
                name='cache_cleanup',
                func=self._run_cache_cleanup_task,
                interval_seconds=interval,
                run_immediately=False
            )
            logger.info(f"已添加缓存清理任务，间隔 {interval/3600}h")
        
        # 5. SiliconFlow定价 - 现在使用静态配置文件 (cache/siliconflow_pricing_accurate.json)
        # 移除了动态抓取任务，改用手动维护的准确价格数据
        logger.info("SiliconFlow定价使用静态配置文件，已移除动态抓取任务")
        
        # 6. 豆包定价 - 现在使用静态配置文件 (doubao_pricing_accurate.json)  
        # 移除了动态抓取任务，改用手动维护的准确价格数据
        logger.info("豆包定价使用静态配置文件，已移除动态抓取任务")
        
        # 7. 统计报告任务
        stats_config = task_config.get('stats_report', {})
        if stats_config.get('enabled', False):  # 默认禁用
            interval = stats_config.get('interval_hours', 12) * 3600
            
            add_task(
                name='stats_report',
                func=self._run_stats_report_task,
                interval_seconds=interval,
                run_immediately=False
            )
            logger.info(f"已添加统计报告任务，间隔 {interval/3600}h")
        
        self.is_initialized = True
        logger.info("所有后台任务初始化完成")
    
    async def _run_model_discovery_task(self):
        """运行模型发现任务"""
        logger.info("开始执行模型发现任务")
        
        try:
            if not self.config_loader or not self.config_loader.config_data:
                logger.error("配置加载器或配置数据未设置")
                return {'success': False, 'error': '配置加载器或配置数据未设置'}
            
            # 直接从 config_data 获取纯字典，避免序列化问题
            channels_data = self.config_loader.config_data.get('channels', [])
            config_data = self.config_loader.config_data
            
            # 运行模型发现
            result = await run_model_discovery(channels_data, config_data)
            
            # 如果成功，更新配置加载器的缓存
            if result.get('success'):
                discovery_task = get_model_discovery_task()
                if hasattr(self.config_loader, 'update_model_cache'):
                    self.config_loader.update_model_cache(discovery_task.cached_models)
            
            logger.info(f"模型发现任务完成: {result}")
            return result
            
        except Exception as e:
            logger.error(f"模型发现任务异常: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    async def _run_pricing_discovery_task(self):
        """运行定价发现任务"""
        logger.info("开始执行定价发现任务")
        
        try:
            # 运行定价发现
            result = await run_pricing_discovery()
            
            logger.info(f"定价发现任务完成: {result}")
            return result
            
        except Exception as e:
            logger.error(f"定价发现任务异常: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    async def _run_api_key_validation_task(self):
        """运行API密钥验证任务"""
        logger.info("开始执行API密钥验证任务")
        
        try:
            if not self.config_loader or not self.config_loader.config_data:
                return {'success': False, 'error': '配置加载器或配置数据未设置'}
            
            # 直接从 config_data 获取纯字典
            channels_data = self.config_loader.config_data.get('channels', [])
            
            # 运行API密钥验证
            result = await run_api_key_validation_task(channels_data)
            
            stats = result.get('stats', {})
            logger.info(f"API密钥验证完成: {stats.get('valid_keys', 0)}/{stats.get('total_keys', 0)} 密钥有效")
            
            return result
            
        except Exception as e:
            logger.error(f"API密钥验证任务异常: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    async def _run_health_check_task(self):
        """运行健康检查任务"""
        logger.info("开始执行健康检查任务")
        
        try:
            if not self.config_loader or not self.config_loader.config_data:
                return {'success': False, 'error': '配置加载器或配置数据未设置'}
            
            # 直接从 config_data 获取纯字典
            channels_data = self.config_loader.config_data.get('channels', [])
            
            # 获取已发现的模型数据（用于选择测试模型）
            discovered_models = get_model_discovery_task().cached_models
            
            # 运行健康检查
            result = await run_health_check_task(channels_data, discovered_models)
            
            stats = result.get('stats', {})
            logger.info(f"健康检查完成: {stats.get('healthy_channels', 0)}/{stats.get('total_channels', 0)} 渠道健康")
            
            return result
            
        except Exception as e:
            logger.error(f"健康检查任务异常: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    async def _run_cache_cleanup_task(self):
        """运行缓存清理任务"""
        logger.info("开始执行缓存清理任务")
        
        try:
            # 清理过期的缓存文件
            from pathlib import Path
            import time
            import os
            
            cache_dir = Path("cache")
            if not cache_dir.exists():
                return {'success': True, 'message': '缓存目录不存在'}
            
            # 清理7天前的文件
            cutoff_time = time.time() - (7 * 24 * 3600)
            cleaned_files = 0
            
            for file_path in cache_dir.rglob('*'):
                if file_path.is_file():
                    if file_path.stat().st_mtime < cutoff_time:
                        try:
                            os.remove(file_path)
                            cleaned_files += 1
                            logger.debug(f"删除过期缓存文件: {file_path}")
                        except Exception as e:
                            logger.warning(f"删除缓存文件失败 {file_path}: {e}")
            
            result = {
                'success': True,
                'cleaned_files': cleaned_files
            }
            
            logger.info(f"缓存清理完成，删除 {cleaned_files} 个过期文件")
            return result
            
        except Exception as e:
            logger.error(f"缓存清理任务异常: {e}")
            return {'success': False, 'error': str(e)}
    
    # SiliconFlow定价任务已移除 - 现在使用静态配置文件 (cache/siliconflow_pricing_accurate.json)
    
    # 豆包定价任务已移除 - 现在使用静态配置文件 (cache/doubao_pricing_accurate.json)
    
    async def _run_stats_report_task(self):
        """运行统计报告任务"""
        logger.info("开始执行统计报告任务")
        
        try:
            # 生成统计报告
            stats = {
                'timestamp': time.time(),
                'task_status': get_task_status(),
                'system_info': {
                    'cache_dir_size': self._get_cache_dir_size(),
                    'config_status': bool(self.config_loader)
                }
            }
            
            # 保存统计报告
            import json
            from pathlib import Path
            
            cache_dir = Path("cache")
            cache_dir.mkdir(exist_ok=True)
            
            stats_file = cache_dir / f"stats_report_{int(time.time())}.json"
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, indent=2, ensure_ascii=False)
            
            logger.info(f"统计报告已保存: {stats_file}")
            return {'success': True, 'report_file': str(stats_file)}
            
        except Exception as e:
            logger.error(f"统计报告任务异常: {e}")
            return {'success': False, 'error': str(e)}
    
    def _get_cache_dir_size(self) -> int:
        """获取缓存目录大小"""
        try:
            from pathlib import Path
            cache_dir = Path("cache")
            if not cache_dir.exists():
                return 0
            
            total_size = 0
            for file_path in cache_dir.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
            
            return total_size
        except:
            return 0
    
    async def start(self):
        """启动任务管理器"""
        logger.info("启动任务管理器")
        await start_scheduler()
    
    async def stop(self):
        """停止任务管理器"""
        logger.info("停止任务管理器")
        await stop_scheduler()
    
    def get_status(self) -> Dict[str, Any]:
        """获取任务管理器状态"""
        return {
            'initialized': self.is_initialized,
            'config_loader_set': bool(self.config_loader),
            'scheduler_status': get_task_status()
        }
    
    def set_config_loader(self, config_loader):
        """设置配置加载器"""
        self.config_loader = config_loader
        logger.info("配置加载器已设置")


# 全局任务管理器实例
_task_manager = None

def get_task_manager() -> TaskManager:
    """获取全局任务管理器实例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager


# 便捷函数
async def initialize_background_tasks(config: Dict[str, Any], config_loader=None):
    """初始化后台任务的便捷函数"""
    manager = get_task_manager()
    if config_loader:
        manager.set_config_loader(config_loader)
    manager.initialize_tasks(config)
    await manager.start()
    return manager


async def stop_background_tasks():
    """停止后台任务的便捷函数"""
    manager = get_task_manager()
    await manager.stop()


def get_task_manager_status() -> Dict[str, Any]:
    """获取任务管理器状态的便捷函数"""
    manager = get_task_manager()
    return manager.get_status()