#!/usr/bin/env python3
"""
使用日志归档脚本 - 定期归档旧的使用记录
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.utils.usage_tracker import get_usage_tracker


def archive_logs(days_to_keep: int = 30):
    """归档旧日志"""
    print(f"开始归档超过{days_to_keep}天的使用日志...")

    tracker = get_usage_tracker()

    try:
        tracker.archive_old_logs(days_to_keep)
        print("✅ 日志归档完成")
    except Exception as e:
        print(f"❌ 日志归档失败: {e}")
        return False

    return True


def generate_summary_report(target_date: date = None):
    """生成汇总报告"""
    if target_date is None:
        target_date = date.today()

    tracker = get_usage_tracker()

    print(f"\n📊 使用统计报告 - {target_date.isoformat()}")
    print("=" * 50)

    # 每日统计
    daily_stats = tracker.get_daily_stats(target_date)
    print("今日统计:")
    print(f"  总请求数: {daily_stats['total_requests']}")
    print(f"  总成本: ${daily_stats['total_cost']:.6f}")
    print(f"  总Tokens: {daily_stats['total_tokens']:,}")
    print(
        f"  成功率: {daily_stats['successful_requests']}/{daily_stats['total_requests']} ({daily_stats['successful_requests']/max(1, daily_stats['total_requests'])*100:.1f}%)"
    )
    if daily_stats["total_requests"] > 0:
        print(f"  平均每请求成本: ${daily_stats['avg_cost_per_request']:.6f}")
        print(f"  平均每1K Tokens成本: ${daily_stats['avg_cost_per_1k_tokens']:.6f}")

    # 本周统计
    weekly_stats = tracker.get_weekly_stats(target_date)
    print(
        f"\n本周统计 ({weekly_stats.get('week_start')} - {weekly_stats.get('week_end')}):"
    )
    print(f"  总请求数: {weekly_stats['total_requests']}")
    print(f"  总成本: ${weekly_stats['total_cost']:.6f}")
    print(f"  总Tokens: {weekly_stats['total_tokens']:,}")

    # 本月统计
    monthly_stats = tracker.get_monthly_stats(target_date.year, target_date.month)
    print(f"\n本月统计 ({target_date.year}-{target_date.month:02d}):")
    print(f"  总请求数: {monthly_stats['total_requests']}")
    print(f"  总成本: ${monthly_stats['total_cost']:.6f}")
    print(f"  总Tokens: {monthly_stats['total_tokens']:,}")

    # 热门模型
    if monthly_stats["models"]:
        print("\n🔥 本月热门模型 (Top 5):")
        sorted_models = sorted(
            monthly_stats["models"].items(),
            key=lambda x: x[1]["requests"],
            reverse=True,
        )
        for i, (model, stats) in enumerate(sorted_models[:5], 1):
            print(f"  {i}. {model}: {stats['requests']} 请求, ${stats['cost']:.6f}")

    # 热门渠道
    if monthly_stats["channels"]:
        print("\n📡 本月热门渠道 (Top 5):")
        sorted_channels = sorted(
            monthly_stats["channels"].items(), key=lambda x: x[1]["cost"], reverse=True
        )
        for i, (channel, stats) in enumerate(sorted_channels[:5], 1):
            print(f"  {i}. {channel}: {stats['requests']} 请求, ${stats['cost']:.6f}")

    # 提供商分布
    if monthly_stats["providers"]:
        print("\n🏢 提供商成本分布:")
        total_cost = monthly_stats["total_cost"]
        for provider, stats in monthly_stats["providers"].items():
            percentage = (stats["cost"] / total_cost * 100) if total_cost > 0 else 0
            print(f"  {provider}: ${stats['cost']:.6f} ({percentage:.1f}%)")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="使用日志归档和统计工具")
    parser.add_argument("--archive", action="store_true", help="归档旧日志")
    parser.add_argument(
        "--days-to-keep", type=int, default=30, help="保留最近多少天的日志 (默认30天)"
    )
    parser.add_argument("--report", action="store_true", help="生成统计报告")
    parser.add_argument("--date", type=str, help="指定日期 (YYYY-MM-DD格式)")

    args = parser.parse_args()

    if not args.archive and not args.report:
        print("请指定 --archive 或 --report 参数")
        parser.print_help()
        return

    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print("❌ 日期格式错误，请使用 YYYY-MM-DD 格式")
            return

    success = True

    if args.archive:
        success = archive_logs(args.days_to_keep)

    if args.report and success:
        generate_summary_report(target_date)


if __name__ == "__main__":
    main()
