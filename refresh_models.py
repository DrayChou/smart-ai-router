#!/usr/bin/env python3
"""
手动刷新模型发现任务，获取最新的渠道模型数据
"""

import asyncio
import json
from datetime import datetime
from core.scheduler.tasks.model_discovery import get_model_discovery_task
from core.yaml_config import get_yaml_config_loader

async def refresh_models():
    print("🔄 手动刷新模型发现任务")
    print("=" * 50)
    
    # 获取配置加载器
    config_loader = get_yaml_config_loader()
    print(f"📋 已加载配置: {len(config_loader.config.channels)} 个渠道")
    
    # 获取模型发现任务
    task = get_model_discovery_task()
    print(f"📊 当前缓存: {len(task.cached_models)} 个渠道的模型")
    
    # 准备渠道数据
    channels = []
    for channel in config_loader.config.channels:
        channels.append({
            'id': channel.id,
            'provider': channel.provider,
            'base_url': channel.base_url,
            'models_url': channel.models_url,
            'enabled': channel.enabled
        })
    
    enabled_channels = [ch for ch in channels if ch.get('enabled', True)]
    print(f"🔍 将发现 {len(enabled_channels)} 个启用渠道的模型")
    
    # 运行发现任务
    print("\n🚀 开始模型发现...")
    start_time = datetime.now()
    
    try:
        # 使用原始配置数据
        original_config = {
            'channels': channels,
            'providers': [{'id': p.id, 'type': p.type} for p in config_loader.config.providers]
        }
        
        result = await task.run_discovery_task(enabled_channels, original_config)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"\n✅ 发现任务完成 (耗时 {duration:.1f}s)")
        
        # 统计结果
        total_models = 0
        successful_channels = 0
        failed_channels = 0
        
        if isinstance(result, dict) and 'channels' in result:
            for channel_data in result['channels']:
                if 'models' in channel_data:
                    channel_models = len(channel_data.get('models', []))
                    total_models += channel_models
                    successful_channels += 1
                    print(f"  ✅ {channel_data.get('id', 'unknown')}: {channel_models} 个模型")
                else:
                    failed_channels += 1
                    print(f"  ❌ {channel_data.get('id', 'unknown')}: 失败")
        
        # 更新后的缓存统计
        updated_cache_count = len(task.cached_models)
        
        print(f"\n📈 统计结果:")
        print(f"  成功渠道: {successful_channels}")
        print(f"  失败渠道: {failed_channels}")  
        print(f"  总模型数: {total_models}")
        print(f"  缓存条目: {updated_cache_count}")
        
        if total_models > 3000:
            print(f"\n🎉 太棒了！发现了 {total_models} 个模型")
        elif total_models > 1000:
            print(f"\n👍 不错！发现了 {total_models} 个模型")
        else:
            print(f"\n⚠️  发现的模型数量偏少: {total_models}")
            
        return True
        
    except Exception as e:
        print(f"\n❌ 发现任务失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(refresh_models())
    if success:
        print("\n✅ 模型刷新完成！请重启服务器以加载新数据。")
    else:
        print("\n❌ 模型刷新失败！请检查错误信息。")