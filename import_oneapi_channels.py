#!/usr/bin/env python3
"""
从One-API数据库导入渠道配置到Smart AI Router
"""

import sqlite3
import yaml
import json
from pathlib import Path

def import_channels_from_oneapi():
    """从One-API数据库导入活跃渠道"""
    
    # 连接One-API数据库
    conn = sqlite3.connect(r'D:\Docker\one-hub\one-api.db')
    
    # 查询活跃渠道
    cursor = conn.execute('''
        SELECT id, name, type, status, key, base_url, models, priority, other 
        FROM channels 
        WHERE status = 1 
        ORDER BY priority DESC
    ''')
    
    channels = cursor.fetchall()
    
    print(f"发现 {len(channels)} 个活跃渠道")
    
    # 加载现有配置
    config_path = Path("config/router_config.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 备份现有渠道
    existing_channels = config.get('channels', [])
    print(f"现有渠道数量: {len(existing_channels)}")
    
    # 创建新的渠道列表
    new_channels = []
    channel_id_map = {}
    
    for ch in channels:
        ch_id, name, ch_type, status, api_key, base_url, models, priority, other = ch
        
        # 跳过本地服务
        if name.lower() in ['ollama']:
            print(f"跳过本地服务: {name}")
            continue
            
        # 跳过测试或无效的渠道
        if not api_key or api_key in ['1234', 'test']:
            print(f"跳过测试渠道: {name}")
            continue
            
        # 构建渠道配置
        channel_config = {
            'id': f'oneapi_{ch_id}',
            'name': name,
            'provider': 'openai',  # 默认使用OpenAI适配器
            'model_name': 'auto',   # 自动从模型列表中选择
            'api_key': api_key,
            'enabled': True,
            'priority': priority,
            'weight': 1,
            'daily_limit': 1000,
            'cost_per_token': {
                'input': 1e-6,
                'output': 1e-6
            },
            'capabilities': ['text', 'function_calling']
        }
        
        # 设置base_url
        if base_url:
            channel_config['base_url'] = base_url
            
        # 设置模型名称和模型列表
        if models:
            model_list = [m.strip() for m in models.split(',') if m.strip()]
            if model_list:
                channel_config['model_name'] = model_list[0]
                channel_config['configured_models'] = model_list  # 保存完整的模型列表作为备选
                
        # 根据渠道类型调整配置
        if ch_type == 31:  # Groq类型
            channel_config['provider'] = 'openai'
            if not base_url:
                channel_config['base_url'] = 'https://api.groq.com/openai'
                
        elif ch_type == 8:  # 智谱/豆包等特殊类型
            if 'zhipu' in name.lower() or 'glm' in models.lower():
                channel_config['base_url'] = base_url or 'https://open.bigmodel.cn/api/paas'
            elif 'doubao' in name.lower():
                channel_config['base_url'] = base_url or 'https://ark.cn-beijing.volces.com/api'
                
        # 添加特殊标签
        tags = []
        if 'free' in models.lower() or 'free' in name.lower():
            tags.append('free')
        if 'local' in base_url.lower() if base_url else False:
            tags.append('local')
        if any(provider in name.lower() for provider in ['groq', 'openrouter', 'burn', 'moonshot']):
            tags.append('cloud')
            
        if tags:
            channel_config['tags'] = tags
            
        new_channels.append(channel_config)
        channel_id_map[ch_id] = channel_config
        
        print(f"[OK] 导入渠道: {name} (ID: {ch_id}, 优先级: {priority}, 模型数: {len(models.split(',')) if models else 0})")
    
    # 合并渠道：保留本地服务，添加新的云端服务
    final_channels = []
    
    # 保留现有的本地服务
    for ch in existing_channels:
        if ch.get('tags') and 'local' in ch['tags']:
            final_channels.append(ch)
            print(f"[KEEP] 保留本地服务: {ch['name']}")
            
    # 添加新的云端服务
    final_channels.extend(new_channels)
    
    # 更新配置
    config['channels'] = final_channels
    
    # 保存配置
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    print(f"\n[SUMMARY] 导入完成:")
    print(f"  - 新增云端渠道: {len(new_channels)}")
    print(f"  - 保留本地服务: {len([ch for ch in existing_channels if ch.get('tags') and 'local' in ch['tags']])}")
    print(f"  - 总渠道数量: {len(final_channels)}")
    
    conn.close()
    return final_channels

if __name__ == "__main__":
    import_channels_from_oneapi()