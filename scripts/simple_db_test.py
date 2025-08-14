#!/usr/bin/env python3
"""
简化版数据库测试脚本 - 避免relationship引用问题
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text

from core.database import get_db_session
from core.utils.logger import get_logger

logger = get_logger(__name__)


async def test_database_tables():
    """测试数据库表结构"""
    logger.info("测试数据库表结构...")

    try:
        async with get_db_session() as session:
            # 查询所有表
            result = await session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            tables = result.fetchall()

            expected_tables = [
                "providers",
                "channels",
                "api_keys",
                "virtual_model_groups",
                "model_group_channels",
                "request_logs",
                "channel_stats",
                "router_api_keys",
                "alembic_version",
            ]

            actual_tables = [row[0] for row in tables]
            logger.info(f"实际表: {actual_tables}")
            logger.info(f"期望表: {expected_tables}")

            missing_tables = [t for t in expected_tables if t not in actual_tables]
            if missing_tables:
                logger.error(f"缺失表: {missing_tables}")
                return False

            logger.info("所有必需的表都存在")
            return True

    except Exception as e:
        logger.error(f"表结构测试失败: {e}")
        return False


async def test_basic_crud():
    """测试基础CRUD操作（不使用ORM relationship）"""
    logger.info("测试基础CRUD操作...")

    try:
        async with get_db_session() as session:
            # 插入Provider
            await session.execute(
                text(
                    """
                INSERT INTO providers (name, display_name, type, adapter_class, status)
                VALUES ('test_provider', 'Test Provider', 'test', 'TestAdapter', 'active')
            """
                )
            )

            # 查询Provider
            result = await session.execute(
                text(
                    """
                SELECT id, name, display_name FROM providers WHERE name = 'test_provider'
            """
                )
            )
            row = result.fetchone()

            if not row:
                logger.error("插入Provider失败")
                return False

            provider_id = row[0]
            logger.info(f"插入Provider成功，ID: {provider_id}, 名称: {row[1]}")

            # 插入VirtualModelGroup
            await session.execute(
                text(
                    """
                INSERT INTO virtual_model_groups (name, display_name, description, status, routing_strategy)
                VALUES ('test:group', '测试组', '测试模型组', 'active', '[]')
            """
                )
            )

            # 查询VirtualModelGroup
            result = await session.execute(
                text(
                    """
                SELECT id, name, display_name FROM virtual_model_groups WHERE name = 'test:group'
            """
                )
            )
            row = result.fetchone()

            if not row:
                logger.error("插入VirtualModelGroup失败")
                return False

            group_id = row[0]
            logger.info(f"插入VirtualModelGroup成功，ID: {group_id}, 名称: {row[1]}")

            # 清理测试数据
            await session.execute(
                text("DELETE FROM virtual_model_groups WHERE name = 'test:group'")
            )
            await session.execute(
                text("DELETE FROM providers WHERE name = 'test_provider'")
            )

            logger.info("基础CRUD测试成功")
            return True

    except Exception as e:
        logger.error(f"基础CRUD测试失败: {e}", exc_info=True)
        return False


async def test_json_fields():
    """测试JSON字段功能"""
    logger.info("测试JSON字段...")

    try:
        async with get_db_session() as session:
            # 插入包含JSON数据的记录
            await session.execute(
                text(
                    """
                INSERT INTO virtual_model_groups 
                (name, display_name, status, routing_strategy, filters, budget_limits)
                VALUES (
                    'test:json', 
                    '测试JSON', 
                    'active',
                    '[{"field": "cost", "order": "asc", "weight": 1.0}]',
                    '{"max_cost": 5.0, "capabilities": ["text"]}',
                    '{"daily_budget": 10.0}'
                )
            """
                )
            )

            # 查询JSON数据
            result = await session.execute(
                text(
                    """
                SELECT routing_strategy, filters, budget_limits 
                FROM virtual_model_groups 
                WHERE name = 'test:json'
            """
                )
            )
            row = result.fetchone()

            if row:
                logger.info("JSON字段测试成功:")
                logger.info(f"  routing_strategy: {row[0]}")
                logger.info(f"  filters: {row[1]}")
                logger.info(f"  budget_limits: {row[2]}")

                # 清理
                await session.execute(
                    text("DELETE FROM virtual_model_groups WHERE name = 'test:json'")
                )
                return True
            else:
                logger.error("JSON字段测试失败")
                return False

    except Exception as e:
        logger.error(f"JSON字段测试失败: {e}")
        return False


async def main():
    """主函数"""
    logger.info("开始简化版数据库测试...")

    tests = [
        test_database_tables,
        test_basic_crud,
        test_json_fields,
    ]

    results = []
    for test in tests:
        results.append(await test())

    passed = sum(results)
    total = len(results)

    logger.info(f"测试结果: {passed}/{total} 通过")

    if passed == total:
        logger.info("✅ 所有数据库测试通过！")
        return True
    else:
        logger.error("❌ 部分数据库测试失败！")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
