#!/usr/bin/env python3
"""检查缓存加载过程的脚本"""

import logging
import json
from pathlib import Path
from core.yaml_config import YAMLConfigLoader
from core.utils.api_key_cache import get_api_key_cache_manager

# 设置详细的日志级别
logging.basicConfig(level=logging.DEBUG)

def check_cache_loading():
    print("=== Checking Cache Loading Process ===")
    
    # 检查缓存文件
    cache_file = Path(__file__).parent / "cache" / "discovered_models.json"
    print(f"Cache file exists: {cache_file.exists()}")
    
    if cache_file.exists():
        # 读取原始缓存文件
        with open(cache_file, 'r', encoding='utf-8') as f:
            raw_cache = json.load(f)
        
        print(f"Raw cache keys: {list(raw_cache.keys())}")
        print(f"Raw cache is empty: {not bool(raw_cache)}")
        
        # 检查是否需要迁移
        config_loader = YAMLConfigLoader()
        needs_migration = config_loader._needs_cache_migration(raw_cache)
        print(f"Needs migration: {needs_migration}")
        
        # 检查每个缓存键
        manager = get_api_key_cache_manager()
        for cache_key in raw_cache.keys():
            is_api_key = manager.is_api_key_cache(cache_key)
            print(f"  {cache_key}: is_api_key={is_api_key}")
            if not is_api_key:
                channel_id, api_key_hash = manager.parse_cache_key(cache_key)
                print(f"    channel_id={channel_id}, hash={api_key_hash}, hash_length={len(api_key_hash)}")
    
    # 测试配置加载器的缓存加载
    print(f"\n=== Testing Config Loader Cache Loading ===")
    
    config_loader = YAMLConfigLoader()
    
    # 检查迁移状态
    migration_completed = getattr(config_loader, '_migration_completed', 'Not set')
    migration_in_progress = getattr(config_loader, '_migration_in_progress', 'Not set')
    print(f"Migration completed: {migration_completed}")
    print(f"Migration in progress: {migration_in_progress}")
    
    # 检查模型缓存
    model_cache = config_loader.get_model_cache()
    print(f"Model cache keys: {list(model_cache.keys())}")
    print(f"Model cache is empty: {not bool(model_cache)}")
    
    # 检查特定渠道的缓存
    print(f"\n=== Testing Channel-Specific Cache ===")
    
    channels = config_loader.get_enabled_channels()
    for channel in channels[:5]:  # 只测试前5个渠道
        channel_cache = config_loader.get_model_cache_by_channel(channel.id)
        models = channel_cache.get('models', [])
        print(f"Channel {channel.id}: {len(models)} models")
        if models:
            print(f"  Models: {models[:3]}{'...' if len(models) > 3 else ''}")

if __name__ == "__main__":
    check_cache_loading()