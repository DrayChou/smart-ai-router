#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复的SiliconFlow HTML解析脚本

处理JSON中的额外数据问题
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def extract_and_parse_json(html_content):
    """提取并解析JSON，处理额外数据"""
    print("正在提取JSON数据...")

    # 找到 self.__next_f.push([1, "4:..."]) 的部分
    pattern = r'self\.__next_f\.push\(\[1,\s*"4:(.*)"\]\)'
    match = re.search(pattern, html_content, re.DOTALL)

    if not match:
        print("未找到JSON数据结构")
        return None

    json_str = match.group(1)
    print(f"提取的原始JSON长度: {len(json_str)}")

    # 处理转义字符
    json_str = json_str.replace('\\"', '"')
    json_str = json_str.replace("\\\\", "\\")

    # 尝试找到第一个完整的JSON数组结构
    # 通常数据以 [ 开始，我们需要找到匹配的 ]
    if not json_str.startswith("["):
        print("JSON不以数组开始，查找数组开始位置...")
        return None

    # 计算括号匹配，找到完整的JSON结构
    bracket_count = 0
    in_string = False
    escape_next = False

    for i, char in enumerate(json_str):
        if escape_next:
            escape_next = False
            continue

        if char == "\\":
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if not in_string:
            if char == "[" or char == "{":
                bracket_count += 1
            elif char == "]" or char == "}":
                bracket_count -= 1

                # 当bracket_count回到0时，我们找到了完整的JSON
                if bracket_count == 0:
                    json_str = json_str[: i + 1]
                    print(f"截取到完整JSON长度: {len(json_str)}")
                    break

    try:
        # 解析JSON
        data = json.loads(json_str)
        print(
            f"JSON解析成功，类型: {type(data)}, 长度: {len(data) if isinstance(data, (list, dict)) else 'N/A'}"
        )

        # 递归查找models
        models = find_models_recursive(data)
        return models

    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        # 尝试更激进的截断
        lines = json_str.split("\n")
        print(f"尝试逐行解析，共{len(lines)}行")

        # 尝试只解析前面的部分
        for end_line in [len(lines) // 2, len(lines) // 4, 100, 50]:
            try:
                partial_json = "\n".join(lines[:end_line])
                # 确保以完整的结构结束
                if partial_json.count("[") > partial_json.count("]"):
                    partial_json += "]" * (
                        partial_json.count("[") - partial_json.count("]")
                    )
                if partial_json.count("{") > partial_json.count("}"):
                    partial_json += "}" * (
                        partial_json.count("{") - partial_json.count("}")
                    )

                data = json.loads(partial_json)
                print(f"部分JSON解析成功，使用前{end_line}行")
                models = find_models_recursive(data)
                if models:
                    return models
            except:
                continue

        return None


def find_models_recursive(data, path="root", max_depth=10):
    """递归查找models数组，限制深度防止无限递归"""
    if max_depth <= 0:
        return None

    if isinstance(data, dict):
        # 检查是否直接包含models
        if "models" in data:
            models_value = data["models"]
            if isinstance(models_value, list) and len(models_value) > 0:
                # 检查第一个元素是否看起来像模型数据
                first_item = models_value[0]
                if isinstance(first_item, dict) and "modelName" in first_item:
                    print(
                        f"在路径 {path} 找到models数组，包含 {len(models_value)} 个模型"
                    )
                    return models_value

        # 递归查找
        for key, value in data.items():
            result = find_models_recursive(value, f"{path}.{key}", max_depth - 1)
            if result is not None:
                return result

    elif isinstance(data, list):
        for i, item in enumerate(data):
            result = find_models_recursive(item, f"{path}[{i}]", max_depth - 1)
            if result is not None:
                return result

    return None


def process_model_data(models_list):
    """处理模型数据"""
    print(f"开始处理 {len(models_list)} 个模型...")

    models_data = {}
    success_count = 0

    for i, model in enumerate(models_list):
        try:
            if not isinstance(model, dict):
                print(f"模型 {i} 不是字典类型: {type(model)}")
                continue

            if "modelName" not in model:
                print(f"模型 {i} 缺少modelName字段")
                continue

            model_name = model.get("modelName")

            # 基础数据
            input_price = float(model.get("inputPrice", 0))
            output_price = float(model.get("outputPrice", 0))
            context_len = int(model.get("contextLen", 32768))
            size = int(model.get("size", 0))

            # 能力标志
            function_call = model.get("functionCallSupport", False)
            vision = model.get("vlm", False)
            json_mode = model.get("jsonModeSupport", False)
            fim_completion = model.get("fimCompletionSupport", False)
            prefix_completion = model.get("chatPrefixCompletionSupport", False)

            # 类型和标签
            model_type = model.get("type", "text")
            sub_type = model.get("subType", "chat")
            tags = model.get("tags", [])

            # 构建能力
            capabilities = ["chat"] if model_type == "text" else []

            if function_call:
                capabilities.append("function_calling")
            if vision:
                capabilities.append("vision")
            if json_mode:
                capabilities.append("json_mode")
            if fim_completion:
                capabilities.append("fim_completion")
            if prefix_completion:
                capabilities.append("prefix_completion")

            # 处理非文本模型
            if model_type == "audio":
                capabilities = ["audio", "tts"]
            elif model_type == "video":
                capabilities = ["video"]
                if sub_type == "text-to-video":
                    capabilities.append("text-to-video")
                elif sub_type == "image-to-video":
                    capabilities.append("image-to-video")
            elif model_type == "image":
                capabilities = ["image"]

            # 分类
            category = "standard"
            description = "标准模型"

            if input_price == 0 and output_price == 0:
                category = "free"
                description = "免费"
            elif model_name.lower().startswith("pro/"):
                category = "pro"
                description = "Pro版本"
            elif size >= 500:
                category = "xxlarge"
                description = "超超大模型"
            elif size >= 50:
                category = "xlarge"
                description = "超大模型"
            elif size >= 10:
                category = "large"
                description = "大模型"
            elif vision:
                category = "vision"
                description = "多模态视觉模型"
            elif max(input_price, output_price) >= 15:
                category = "premium"
                description = "高端模型"
            elif max(input_price, output_price) >= 5:
                if category == "standard":
                    category = "large"
                description = "高性能模型"

            if model_type != "text":
                description = f"{model_type}生成模型"

            models_data[model_name] = {
                "input_price_per_m": input_price,
                "output_price_per_m": output_price,
                "context_length": context_len,
                "capabilities": list(set(capabilities)),
                "category": category,
                "description": description,
                "model_size": size,
                "function_call_support": function_call,
                "vision_support": vision,
                "json_mode_support": json_mode,
                "fim_completion_support": fim_completion,
                "prefix_completion_support": prefix_completion,
                "tags": tags,
                "type": model_type,
                "subType": sub_type,
                "display_name": model.get("DisplayName", model_name),
                "status": model.get("status", "normal"),
            }

            success_count += 1

        except Exception as e:
            print(f"处理模型 {i} ({model.get('modelName', 'unknown')}) 时出错: {e}")
            continue

    print(f"成功处理 {success_count} 个模型")
    return models_data


def main():
    """主函数"""
    print("=== SiliconFlow HTML修复解析脚本 ===")

    html_path = project_root / "cache" / "siliconflow" / "model.html"

    if not html_path.exists():
        print(f"HTML文件不存在: {html_path}")
        return 1

    print(f"读取HTML文件: {html_path}")

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        print(f"文件大小: {len(html_content):,} 字符")
    except Exception as e:
        print(f"读取文件失败: {e}")
        return 1

    # 解析JSON
    models_list = extract_and_parse_json(html_content)

    if not models_list:
        print("未能提取到模型数据")
        return 1

    # 处理模型
    models_data = process_model_data(models_list)

    if not models_data:
        print("未能处理模型数据")
        return 1

    # 生成配置
    config = {
        "provider": "SiliconFlow",
        "currency": "CNY",
        "currency_symbol": "￥",
        "unit": "1M tokens",
        "exchange_rate_to_usd": 0.14,
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "pricing_source": "https://siliconflow.cn/pricing",
        "data_source": "HTML Cache from SiliconFlow Website (Fixed Parser)",
        "extraction_timestamp": datetime.now().isoformat(),
        "models": models_data,
        "categories": {
            "free": {
                "name": "免费模型",
                "description": "完全免费使用，适合测试和轻量级应用",
            },
            "pro": {
                "name": "Pro版本",
                "description": "专业版本，提供更好的性能和稳定性",
            },
            "standard": {
                "name": "标准收费",
                "description": "标准定价模型，平衡性能和成本",
            },
            "large": {"name": "大模型", "description": "参数量较大的模型，性能更强"},
            "xlarge": {"name": "超大模型", "description": "超大参数量模型，顶级性能"},
            "xxlarge": {
                "name": "超超大模型",
                "description": "最大参数量模型，极致性能",
            },
            "vision": {
                "name": "视觉模型",
                "description": "支持图像理解和处理的多模态模型",
            },
            "premium": {"name": "高端模型", "description": "高端定价，顶级性能和功能"},
        },
    }

    # 保存文件
    config_path = (
        project_root / "config" / "pricing" / "siliconflow_pricing_from_html.json"
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        backup_path = (
            config_path.parent
            / f"siliconflow_pricing_html_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        import shutil

        shutil.copy2(config_path, backup_path)
        print(f"已备份到: {backup_path}")

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"配置文件已保存: {config_path}")

    # 统计信息
    print_statistics(models_data)

    return 0


def print_statistics(models_data):
    """打印统计信息"""
    print("\n" + "=" * 60)
    print("SiliconFlow 模型统计 (来自HTML真实数据)")
    print("=" * 60)

    total = len(models_data)
    print(f"总模型数量: {total}")

    # 分类统计
    categories = {}
    free_models = []
    vision_models = []
    function_models = []
    long_context = []

    for name, data in models_data.items():
        cat = data.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

        if cat == "free":
            free_models.append((name, data.get("context_length", 0)))
        if data.get("vision_support"):
            vision_models.append(name)
        if data.get("function_call_support"):
            function_models.append(name)
        if data.get("context_length", 0) >= 128000:  # 128K+
            long_context.append((name, data.get("context_length", 0)))

    print(f"\n分类分布:")
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total) * 100
        print(f"  {cat:>10}: {count:>3} 个 ({percentage:>4.1f}%)")

    print(f"\n免费模型: {len(free_models)} 个")
    if free_models[:3]:
        print("   前3个免费模型:")
        for name, ctx in sorted(free_models, key=lambda x: x[1], reverse=True)[:3]:
            print(f"     * {name}: {ctx:,} tokens")

    print(f"\n视觉模型: {len(vision_models)} 个")
    if vision_models[:3]:
        print("   视觉模型:")
        for name in vision_models[:3]:
            print(f"     * {name}")

    print(f"\n函数调用: {len(function_models)} 个")

    print(f"\n长上下文: {len(long_context)} 个 (>=128K)")
    if long_context:
        print("   长上下文模型:")
        for name, ctx in sorted(long_context, key=lambda x: x[1], reverse=True):
            print(f"     * {name}: {ctx:,} tokens")

    # 关键统计
    context_lengths = [data.get("context_length", 0) for data in models_data.values()]
    if context_lengths:
        print(f"\n上下文长度统计:")
        print(f"   最短: {min(context_lengths):,} tokens")
        print(f"   最长: {max(context_lengths):,} tokens")
        print(f"   平均: {sum(context_lengths)//len(context_lengths):,} tokens")

    # 价格统计
    free_count = len(
        [
            m
            for m in models_data.values()
            if m.get("input_price_per_m", 0) == 0
            and m.get("output_price_per_m", 0) == 0
        ]
    )
    paid_count = total - free_count
    print(f"\n价格分布:")
    print(f"   免费模型: {free_count} 个 ({(free_count/total)*100:.1f}%)")
    print(f"   付费模型: {paid_count} 个 ({(paid_count/total)*100:.1f}%)")


if __name__ == "__main__":
    sys.exit(main())
