#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基础定价文件生成器

从OpenRouter统一格式数据生成基础定价文件，作为其他平台的回退定价参考
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.pricing.unified_format import UnifiedPricingFile, UnifiedModelData


def load_openrouter_unified():
    """加载OpenRouter统一格式数据"""
    openrouter_file = project_root / "config" / "pricing" / "openrouter_unified.json"
    
    if not openrouter_file.exists():
        print(f"OpenRouter统一格式文件不存在: {openrouter_file}")
        return None
    
    print(f"加载OpenRouter统一格式数据: {openrouter_file}")
    return UnifiedPricingFile.load_from_file(openrouter_file)


def generate_base_pricing(openrouter_unified):
    """从OpenRouter数据生成基础定价"""
    print(f"基于OpenRouter数据生成基础定价文件，共{len(openrouter_unified.models)}个模型")
    
    # 创建基础定价文件
    base_pricing = UnifiedPricingFile(
        provider="base_pricing",
        source="openrouter_unified_extraction", 
        description=f"基础定价数据，提取自OpenRouter官方API，包含{len(openrouter_unified.models)}个模型的完整定价和元数据信息"
    )
    
    # 统计信息
    stats = {
        'total_models': 0,
        'free_models': 0,
        'vision_models': 0,
        'reasoning_models': 0,
        'code_models': 0,
        'function_calling_models': 0,
        'price_ranges': {
            'very_cheap': 0,  # < $0.001/M tokens
            'cheap': 0,       # $0.001-0.01/M tokens
            'medium': 0,      # $0.01-0.1/M tokens  
            'expensive': 0,   # > $0.1/M tokens
        },
        'context_ranges': {
            'short': 0,   # < 8K
            'medium': 0,  # 8K-32K
            'long': 0,    # 32K-128K
            'very_long': 0, # > 128K
        }
    }
    
    for model_id, model_data in openrouter_unified.models.items():
        # 复制模型数据，但修改数据源
        base_model = UnifiedModelData(
            id=model_id,
            canonical_slug=model_data.canonical_slug,
            hugging_face_id=model_data.hugging_face_id,
            name=model_data.name,
            parameter_count=model_data.parameter_count,
            context_length=model_data.context_length,
            created=model_data.created,
            architecture=model_data.architecture,
            capabilities=model_data.capabilities,
            pricing=model_data.pricing,
            top_provider=model_data.top_provider,
            description=model_data.description,
            category=model_data.category,
            data_source=model_data.data_source,  # 保持原始数据源标识
            last_updated=datetime.now(),
            aliases=model_data.aliases
        )
        
        base_pricing.models[model_id] = base_model
        
        # 更新统计
        stats['total_models'] += 1
        
        if model_data.pricing:
            if model_data.pricing.prompt == 0 and model_data.pricing.completion == 0:
                stats['free_models'] += 1
            else:
                # 价格范围统计 (转换为每百万tokens)
                avg_price = (model_data.pricing.prompt + model_data.pricing.completion) / 2 * 1_000_000
                if avg_price < 0.001:
                    stats['price_ranges']['very_cheap'] += 1
                elif avg_price < 0.01:
                    stats['price_ranges']['cheap'] += 1
                elif avg_price < 0.1:
                    stats['price_ranges']['medium'] += 1
                else:
                    stats['price_ranges']['expensive'] += 1
        
        if model_data.capabilities:
            if 'vision' in model_data.capabilities:
                stats['vision_models'] += 1
            if 'reasoning' in model_data.capabilities:
                stats['reasoning_models'] += 1  
            if 'code' in model_data.capabilities:
                stats['code_models'] += 1
            if 'function_calling' in model_data.capabilities:
                stats['function_calling_models'] += 1
        
        if model_data.context_length:
            ctx_len = model_data.context_length
            if ctx_len < 8000:
                stats['context_ranges']['short'] += 1
            elif ctx_len < 32000:
                stats['context_ranges']['medium'] += 1
            elif ctx_len < 128000:
                stats['context_ranges']['long'] += 1
            else:
                stats['context_ranges']['very_long'] += 1
    
    print_base_pricing_stats(stats)
    return base_pricing


def print_base_pricing_stats(stats):
    """打印基础定价统计信息"""
    total = stats['total_models']
    print(f"\n" + "=" * 60)
    print("基础定价文件统计")
    print("=" * 60)
    print(f"总模型数量: {total}")
    
    print(f"\n能力分布:")
    print(f"  免费模型: {stats['free_models']:>3} 个 ({stats['free_models']/total*100:>4.1f}%)")
    print(f"  视觉模型: {stats['vision_models']:>3} 个 ({stats['vision_models']/total*100:>4.1f}%)")
    print(f"  推理模型: {stats['reasoning_models']:>3} 个 ({stats['reasoning_models']/total*100:>4.1f}%)")
    print(f"  代码模型: {stats['code_models']:>3} 个 ({stats['code_models']/total*100:>4.1f}%)")
    print(f"函数调用: {stats['function_calling_models']:>3} 个 ({stats['function_calling_models']/total*100:>4.1f}%)")
    
    print(f"\n价格分布 (每百万tokens):")
    for range_name, count in stats['price_ranges'].items():
        if count > 0:
            print(f"  {range_name:>10}: {count:>3} 个 ({count/total*100:>4.1f}%)")
    
    print(f"\n上下文长度分布:")
    for range_name, count in stats['context_ranges'].items():
        if count > 0:
            print(f"  {range_name:>10}: {count:>3} 个 ({count/total*100:>4.1f}%)")


def create_lookup_index(base_pricing):
    """创建查找索引以便快速查找模型"""
    print("创建模型查找索引...")
    
    # 按能力分组
    capability_index = {}
    # 按参数数量分组  
    param_index = {}
    # 按提供商分组
    provider_index = {}
    # 价格排序索引
    price_index = []
    
    for model_id, model_data in base_pricing.models.items():
        # 能力索引
        if model_data.capabilities:
            for capability in model_data.capabilities:
                if capability not in capability_index:
                    capability_index[capability] = []
                capability_index[capability].append(model_id)
        
        # 参数索引
        if model_data.parameter_count:
            param_range = get_param_range(model_data.parameter_count)
            if param_range not in param_index:
                param_index[param_range] = []
            param_index[param_range].append(model_id)
        
        # 提供商索引 (从模型ID提取)
        if '/' in model_id:
            provider = model_id.split('/')[0]
            if provider not in provider_index:
                provider_index[provider] = []
            provider_index[provider].append(model_id)
        
        # 价格索引
        if model_data.pricing:
            avg_price = (model_data.pricing.prompt + model_data.pricing.completion) / 2
            price_index.append((model_id, avg_price))
    
    # 按价格排序
    price_index.sort(key=lambda x: x[1])
    
    index_data = {
        'capabilities': {k: len(v) for k, v in capability_index.items()},
        'parameter_ranges': {k: len(v) for k, v in param_index.items()},
        'providers': {k: len(v) for k, v in provider_index.items()},
        'cheapest_models': [model_id for model_id, price in price_index[:20]],
        'most_expensive_models': [model_id for model_id, price in price_index[-10:]],
        'generation_time': datetime.now().isoformat()
    }
    
    # 保存索引文件
    index_path = project_root / "config" / "pricing" / "base_pricing_index.json"
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)
    
    print(f"查找索引已保存: {index_path}")
    
    return index_data


def get_param_range(param_count):
    """获取参数数量范围"""
    if param_count < 1e9:  # < 1B
        return "small"
    elif param_count < 10e9:  # 1B-10B
        return "medium" 
    elif param_count < 100e9:  # 10B-100B
        return "large"
    else:  # > 100B
        return "xlarge"


def main():
    """主函数"""
    print("=== 基础定价文件生成器 ===")
    
    # 加载OpenRouter统一格式数据
    openrouter_unified = load_openrouter_unified()
    if not openrouter_unified:
        return 1
    
    # 生成基础定价
    base_pricing = generate_base_pricing(openrouter_unified)
    if not base_pricing:
        return 1
    
    # 保存基础定价文件
    base_pricing_path = project_root / "config" / "pricing" / "base_pricing_unified.json"
    base_pricing_path.parent.mkdir(parents=True, exist_ok=True)
    
    if base_pricing_path.exists():
        backup_path = (
            base_pricing_path.parent 
            / f"base_pricing_unified_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        import shutil
        shutil.copy2(base_pricing_path, backup_path)
        print(f"已备份到: {backup_path}")
    
    base_pricing.save_to_file(base_pricing_path)
    print(f"基础定价文件已保存: {base_pricing_path}")
    
    # 创建查找索引
    index_data = create_lookup_index(base_pricing)
    
    # 打印索引统计
    print(f"\n索引统计:")
    print(f"  能力类型: {len(index_data['capabilities'])} 种")
    print(f"  参数范围: {len(index_data['parameter_ranges'])} 种")
    print(f"  提供商数: {len(index_data['providers'])} 个")
    print(f"  最便宜模型: {len(index_data['cheapest_models'])} 个")
    
    print(f"\n主要能力分布:")
    for capability, count in sorted(index_data['capabilities'].items(), 
                                   key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {capability}: {count} 个模型")
    
    print(f"\n主要提供商:")
    for provider, count in sorted(index_data['providers'].items(), 
                                 key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {provider}: {count} 个模型")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())