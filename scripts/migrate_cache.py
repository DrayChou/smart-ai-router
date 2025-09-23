#!/usr/bin/env python3
"""
缓存迁移脚本 - 将旧的合并缓存迁移到新的按渠道分离格式
"""

import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from core.utils.channel_cache_manager import get_channel_cache_manager

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """主迁移函数"""
    logger.info(
        "🚀 Starting cache migration from old format to channel-separated format"
    )

    try:
        # 获取缓存管理器
        cache_manager = get_channel_cache_manager()

        # 执行迁移
        cache_manager.migrate_from_old_cache()

        # 清理旧缓存文件
        cache_manager.cleanup_old_caches()

        # 显示迁移后的摘要
        summary = cache_manager.get_channel_summary()

        logger.info("✅ Migration completed successfully!")
        logger.info("📊 Migration Summary:")
        logger.info(f"   • Total channels: {summary['total_channels']}")
        logger.info(f"   • Total models: {summary['total_models']}")
        logger.info(f"   • Models with parameter info: {summary['models_with_params']}")
        logger.info(f"   • Models with context info: {summary['models_with_context']}")

        # 显示各渠道详情
        logger.info("📋 Channel Details:")
        for channel_id, info in summary["channels"].items():
            logger.info(
                f"   • {channel_id} ({info['provider']}): "
                f"{info['model_count']} models, "
                f"{info['models_with_params']} with params, "
                f"{info['models_with_context']} with context"
            )

        logger.info("🎉 All done! The new cache structure is ready for use.")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
