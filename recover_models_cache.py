#!/usr/bin/env python3
"""
模型缓存恢复脚本
从 model_discovery_log.json 恢复完整的 discovered_models.json 缓存
"""

import json
import os
from datetime import datetime

def recover_models_cache():
    """从发现日志恢复模型缓存"""
    
    # 读取发现日志
    log_file = "cache/model_discovery_log.json"
    cache_file = "cache/discovered_models.json"
    
    if not os.path.exists(log_file):
        print(f"ERROR: 发现日志文件不存在: {log_file}")
        return False
    
    print(f"INFO: 读取发现日志: {log_file}")
    with open(log_file, 'r', encoding='utf-8') as f:
        log = json.load(f)
    
    discovered = log.get('discovered_models', {})
    if not discovered:
        print("ERROR: 日志中没有发现的模型数据")
        return False
    
    print(f"SUCCESS: 发现 {len(discovered)} 个渠道的模型数据")
    
    # 统计模型数量
    total_models = 0
    new_cache = {}
    
    for channel_id, data in discovered.items():
        models = data.get('models', [])
        model_count = len(models)
        total_models += model_count
        
        # 生成API key级别的缓存键
        api_key_hash = data.get('api_key_hash', 'unknown')
        if api_key_hash == 'unknown':
            # 如果没有API key hash，生成一个简单的
            api_key_hash = channel_id[-8:] if len(channel_id) >= 8 else channel_id
            
        cache_key = f"{channel_id}_{api_key_hash}"
        
        # 构建缓存条目
        cache_entry = {
            "channel_id": channel_id,
            "provider": data.get('provider', 'unknown'),
            "base_url": data.get('base_url', ''),
            "models_url": data.get('models_url', ''),
            "models": models,
            "model_count": model_count,
            "last_updated": data.get('last_updated', datetime.now().isoformat()),
            "status": "success",
            "cache_key": cache_key,
            "api_key_hash": api_key_hash,
            "user_level": data.get('user_level', 'unknown'),
            "response_data": data.get('response_data', {}),
            "migrated_from_legacy": False,
            "recovered_from_log": True,
            "recovered_at": datetime.now().isoformat()
        }
        
        new_cache[cache_key] = cache_entry
        print(f"  ✅ {channel_id}: {model_count} models -> {cache_key}")
    
    print(f"\n📊 恢复统计:")
    print(f"  - 总渠道数: {len(new_cache)}")
    print(f"  - 总模型数: {total_models}")
    
    # 备份现有缓存
    if os.path.exists(cache_file):
        backup_file = f"{cache_file}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"💾 备份现有缓存: {backup_file}")
        with open(backup_file, 'w', encoding='utf-8') as f:
            with open(cache_file, 'r', encoding='utf-8') as original:
                f.write(original.read())
    
    # 写入新缓存
    print(f"💾 写入恢复的缓存: {cache_file}")
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(new_cache, f, indent=2, ensure_ascii=False)
    
    print(f"🎉 缓存恢复完成！")
    print(f"   - 恢复了 {len(new_cache)} 个渠道")
    print(f"   - 恢复了 {total_models} 个模型")
    print(f"   - 从原来的 18 个模型增加到 {total_models} 个模型")
    
    return True

if __name__ == "__main__":
    print("🔧 智能AI路由器 - 模型缓存恢复工具")
    print("=" * 50)
    
    if recover_models_cache():
        print("\n✅ 恢复成功！请重新启动服务器以加载新的缓存数据。")
    else:
        print("\n❌ 恢复失败！请检查日志文件和权限。")