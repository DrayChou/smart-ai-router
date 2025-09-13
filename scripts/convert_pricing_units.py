#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定价单位转换脚本
将现有的科学计数法定价转换为更直观的百万token单位
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def convert_per_token_to_per_million(price: float) -> float:
    """将per_token价格转换为per_million_tokens"""
    return price * 1000000


def convert_pricing_file(file_path: Path) -> bool:
    """转换定价文件的单位"""
    try:
        print(f"[转换] 正在转换文件: {file_path.name}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 检查当前单位
        current_unit = data.get("unit", "per_token")
        if current_unit == "per_million_tokens":
            print(f"[跳过] {file_path.name} 已经是百万token单位")
            return True

        if current_unit != "per_token":
            print(f"[警告] {file_path.name} 使用未知单位 {current_unit}，跳过")
            return False

        # 转换单位
        data["unit"] = "per_million_tokens"
        converted_count = 0

        # 转换所有模型的定价
        for model_id, model_data in data.get("models", {}).items():
            if "pricing" in model_data and model_data["pricing"]:
                pricing = model_data["pricing"]

                # 转换核心定价字段
                if "prompt" in pricing:
                    old_price = pricing["prompt"]
                    new_price = convert_per_token_to_per_million(old_price)
                    pricing["prompt"] = round(new_price, 6)  # 保留6位精度

                if "completion" in pricing:
                    old_price = pricing["completion"]
                    new_price = convert_per_token_to_per_million(old_price)
                    pricing["completion"] = round(new_price, 6)

                # 其他价格字段保持不变(request, image等通常不是per_token)
                converted_count += 1

        # 保存转换后的文件
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[成功] {file_path.name} 转换完成: {converted_count} 个模型")
        return True

    except Exception as e:
        print(f"[错误] {file_path.name} 转换失败: {e}")
        return False


def main():
    """批量转换定价文件"""
    pricing_dir = project_root / "config" / "pricing"

    print("开始批量转换定价单位...")
    print(f"目标目录: {pricing_dir}")

    if not pricing_dir.exists():
        print(f"定价目录不存在: {pricing_dir}")
        return

    # 查找所有统一格式定价文件
    pricing_files = list(pricing_dir.glob("*_unified.json"))

    if not pricing_files:
        print("未找到统一格式定价文件 (*_unified.json)")
        return

    print(f"找到 {len(pricing_files)} 个定价文件")

    success_count = 0
    for file_path in pricing_files:
        if convert_pricing_file(file_path):
            success_count += 1

    print(f"\n转换结果: {success_count}/{len(pricing_files)} 个文件成功转换")

    if success_count == len(pricing_files):
        print("所有定价文件已成功转换为百万token单位!")
    else:
        print("部分文件转换失败，请检查日志")


if __name__ == "__main__":
    main()
