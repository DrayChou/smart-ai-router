#!/usr/bin/env python3
"""
SiliconFlow HTML解析脚本 - 统一格式版本

基于parse_siliconflow_fixed.py，输出统一格式而不是旧格式
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入统一格式定义
from core.pricing.unified_format import (
    Architecture,
    DataSource,
    ModelCapabilityInference,
    ModelCategory,
    Pricing,
    UnifiedModelData,
    UnifiedPricingFile,
)


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


def convert_to_unified_format(models_list, exchange_rate=0.14):
    """将SiliconFlow模型数据转换为统一格式"""
    print(f"开始转换 {len(models_list)} 个模型为统一格式...")

    # 创建统一格式文件
    unified_file = UnifiedPricingFile(
        provider="siliconflow",
        source="siliconflow_html_parsed",
        description=f"SiliconFlow HTML解析数据，包含{len(models_list)}个真实模型信息",
    )

    capability_inference = ModelCapabilityInference()
    success_count = 0

    for i, model in enumerate(models_list):
        try:
            if not isinstance(model, dict):
                print(f"模型 {i} 不是字典类型: {type(model)}")
                continue

            if "modelName" not in model:
                print(f"模型 {i} 缺少modelName字段")
                continue

            model_id = model.get("modelName")

            # 价格转换: 元/M tokens → USD/token
            input_price_yuan_per_m = float(model.get("inputPrice", 0))
            output_price_yuan_per_m = float(model.get("outputPrice", 0))

            input_price_usd_per_token = (
                input_price_yuan_per_m * exchange_rate
            ) / 1_000_000
            output_price_usd_per_token = (
                output_price_yuan_per_m * exchange_rate
            ) / 1_000_000

            # 基本信息
            context_length = int(model.get("contextLen", 32768))
            unified_model = UnifiedModelData(
                id=model_id,
                name=model.get("DisplayName", model_id),
                parameter_count=None,  # SiliconFlow不直接提供参数数量
                context_length=context_length,
                description=model.get("description", ""),
                data_source=DataSource.SILICONFLOW,
                last_updated=datetime.now(),
            )

            # 架构信息推断
            model_type = model.get("type", "text")
            sub_type = model.get("subType", "chat")
            vision_support = model.get("vlm", False)

            modality = "text->text"
            input_modalities = ["text"]
            output_modalities = ["text"]

            # 检查多模态能力
            if vision_support:
                modality = "text+image->text"
                input_modalities.append("image")

            if model_type == "audio":
                if sub_type == "text-to-speech":
                    modality = "text->audio"
                    output_modalities = ["audio"]
                elif sub_type == "speech-to-text":
                    modality = "audio->text"
                    input_modalities = ["audio"]

            unified_model.architecture = Architecture(
                modality=modality,
                input_modalities=input_modalities,
                output_modalities=output_modalities,
            )

            # 定价信息
            is_free = input_price_yuan_per_m == 0 and output_price_yuan_per_m == 0
            unified_model.pricing = Pricing(
                prompt=input_price_usd_per_token,
                completion=output_price_usd_per_token,
                original_currency="CNY",
                exchange_rate=exchange_rate,
                confidence_level=0.9,  # SiliconFlow数据较可信
            )

            # 能力推断
            capabilities = []
            if model_type == "text":
                capabilities.append("chat")

            if model.get("functionCallSupport", False):
                capabilities.append("function_calling")
            if vision_support:
                capabilities.append("vision")
            if model.get("jsonModeSupport", False):
                capabilities.append("json_mode")
            if model.get("fimCompletionSupport", False):
                capabilities.append("fim_completion")
            if model.get("chatPrefixCompletionSupport", False):
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

            unified_model.capabilities = list(set(capabilities))  # 去重

            # 分类推断
            model_size = int(model.get("size", 0))
            if is_free:
                unified_model.category = ModelCategory.FREE
            elif vision_support:
                unified_model.category = ModelCategory.VISION
            elif model_type != "text":
                unified_model.category = ModelCategory.PREMIUM
            elif model_size >= 50:
                unified_model.category = ModelCategory.XLARGE
            elif model_size >= 10:
                unified_model.category = ModelCategory.LARGE
            elif max(input_price_yuan_per_m, output_price_yuan_per_m) >= 15:
                unified_model.category = ModelCategory.PREMIUM
            else:
                unified_model.category = (
                    capability_inference.infer_category_from_params(
                        None, context_length
                    )
                )

            unified_file.models[model_id] = unified_model
            success_count += 1

        except Exception as e:
            print(f"转换模型 {i} ({model.get('modelName', 'unknown')}) 时出错: {e}")
            continue

    print(f"成功转换 {success_count} 个模型为统一格式")
    return unified_file


def main():
    """主函数"""
    print("=== SiliconFlow HTML统一格式解析脚本 ===")

    html_path = project_root / "cache" / "siliconflow" / "model.html"

    if not html_path.exists():
        print(f"HTML文件不存在: {html_path}")
        return 1

    print(f"读取HTML文件: {html_path}")

    try:
        with open(html_path, encoding="utf-8") as f:
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

    # 转换为统一格式
    unified_file = convert_to_unified_format(models_list)

    if not unified_file or not unified_file.models:
        print("未能转换模型数据")
        return 1

    # 保存统一格式文件
    output_path = project_root / "config" / "pricing" / "siliconflow_unified.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        backup_path = (
            output_path.parent
            / f"siliconflow_unified_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        import shutil

        shutil.copy2(output_path, backup_path)
        print(f"已备份到: {backup_path}")

    unified_file.save_to_file(output_path)
    print(f"统一格式文件已保存: {output_path}")

    # 打印统计信息
    print_statistics(unified_file.models)

    return 0


def print_statistics(models_data):
    """打印统计信息"""
    print("\n" + "=" * 60)
    print("SiliconFlow 模型统计 (统一格式)")
    print("=" * 60)

    total = len(models_data)
    print(f"总模型数量: {total}")

    # 分类统计
    categories = {}
    free_models = []
    vision_models = []
    function_models = []
    long_context = []

    for model_id, model_data in models_data.items():
        cat = model_data.category.value
        categories[cat] = categories.get(cat, 0) + 1

        if model_data.category == ModelCategory.FREE:
            free_models.append((model_id, model_data.context_length or 0))
        if "vision" in (model_data.capabilities or []):
            vision_models.append(model_id)
        if "function_calling" in (model_data.capabilities or []):
            function_models.append(model_id)
        if model_data.context_length and model_data.context_length >= 128000:  # 128K+
            long_context.append((model_id, model_data.context_length))

    print("\n分类分布:")
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total) * 100
        print(f"  {cat:>10}: {count:>3} 个 ({percentage:>4.1f}%)")

    print(f"\n免费模型: {len(free_models)} 个")
    if free_models[:3]:
        print("   前3个免费模型:")
        for model_id, ctx in sorted(free_models, key=lambda x: x[1], reverse=True)[:3]:
            print(f"     * {model_id}: {ctx:,} tokens")

    print(f"\n视觉模型: {len(vision_models)} 个")
    if vision_models[:3]:
        print("   视觉模型:")
        for model_id in vision_models[:3]:
            print(f"     * {model_id}")

    print(f"\n函数调用: {len(function_models)} 个")

    print(f"\n长上下文: {len(long_context)} 个 (>=128K)")
    if long_context:
        print("   长上下文模型:")
        for model_id, ctx in sorted(long_context, key=lambda x: x[1], reverse=True):
            print(f"     * {model_id}: {ctx:,} tokens")

    # 价格统计
    free_count = 0
    paid_count = 0

    for model_data in models_data.values():
        if (
            model_data.pricing
            and model_data.pricing.prompt == 0
            and model_data.pricing.completion == 0
        ):
            free_count += 1
        else:
            paid_count += 1

    print("\n价格分布:")
    print(f"   免费模型: {free_count} 个 ({(free_count/total)*100:.1f}%)")
    print(f"   付费模型: {paid_count} 个 ({(paid_count/total)*100:.1f}%)")


if __name__ == "__main__":
    sys.exit(main())
