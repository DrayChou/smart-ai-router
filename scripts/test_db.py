#!/usr/bin/env python3
"""
数据库连接和基础功能测试脚本
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.database import get_db_session
from core.models.model_group import VirtualModelGroup
from core.models.provider import Provider
from core.utils.logger import get_logger

logger = get_logger(__name__)


async def test_database_connection():
    """测试数据库连接"""
    logger.info("测试数据库连接...")

    try:
        async with get_db_session() as session:
            # 简单查询测试
            result = await session.execute("SELECT 1")
            row = result.fetchone()
            if row and row[0] == 1:
                logger.info("数据库连接成功！")
                return True
            else:
                logger.error("数据库连接测试失败")
                return False
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return False


async def test_provider_crud():
    """测试Provider的CRUD操作"""
    logger.info("测试Provider CRUD操作...")

    try:
        async with get_db_session() as session:
            # 创建Provider
            provider = Provider(
                name="test_provider",
                display_name="Test Provider",
                type="test",
                adapter_class="TestAdapter",
                status="active",
            )
            session.add(provider)
            await session.flush()

            provider_id = provider.id
            logger.info(f"创建Provider成功，ID: {provider_id}")

            # 查询Provider
            from sqlalchemy import select

            result = await session.execute(
                select(Provider).where(Provider.name == "test_provider")
            )
            found_provider = result.scalar()

            if found_provider:
                logger.info(f"查询Provider成功: {found_provider.display_name}")

                # 更新Provider
                found_provider.display_name = "Updated Test Provider"
                await session.flush()
                logger.info("更新Provider成功")

                # 删除Provider
                await session.delete(found_provider)
                await session.flush()
                logger.info("删除Provider成功")

                return True
            else:
                logger.error("查询Provider失败")
                return False

    except Exception as e:
        logger.error(f"Provider CRUD测试失败: {e}", exc_info=True)
        return False


async def test_model_group_crud():
    """测试Model Group的CRUD操作"""
    logger.info("测试Model Group CRUD操作...")

    try:
        async with get_db_session() as session:
            # 创建Model Group
            model_group = VirtualModelGroup(
                name="test:group",
                display_name="测试模型组",
                description="这是一个测试模型组",
                routing_strategy=[
                    {"field": "effective_cost", "order": "asc", "weight": 1.0}
                ],
                filters={"max_cost_per_1k": 1.0, "required_capabilities": ["text"]},
                status="active",
            )
            session.add(model_group)
            await session.flush()

            group_id = model_group.id
            logger.info(f"创建Model Group成功，ID: {group_id}")

            # 查询Model Group
            from sqlalchemy import select

            result = await session.execute(
                select(VirtualModelGroup).where(VirtualModelGroup.name == "test:group")
            )
            found_group = result.scalar()

            if found_group:
                logger.info(f"查询Model Group成功: {found_group.display_name}")
                logger.info(f"路由策略: {found_group.routing_strategy}")
                logger.info(f"筛选条件: {found_group.filters}")

                # 删除Model Group
                await session.delete(found_group)
                await session.flush()
                logger.info("删除Model Group成功")

                return True
            else:
                logger.error("查询Model Group失败")
                return False

    except Exception as e:
        logger.error(f"Model Group CRUD测试失败: {e}", exc_info=True)
        return False


async def list_all_tables():
    """列出所有数据库表"""
    logger.info("列出所有数据库表...")

    try:
        async with get_db_session() as session:
            # SQLite查询所有表
            result = await session.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = result.fetchall()

            logger.info("数据库表列表:")
            for table in tables:
                logger.info(f"  - {table[0]}")

                # 查询表结构
                schema_result = await session.execute(f"PRAGMA table_info({table[0]})")
                columns = schema_result.fetchall()
                logger.info("    表结构:")
                for col in columns:
                    logger.info(
                        f"      {col[1]} {col[2]} {'NOT NULL' if col[3] else ''} {'PK' if col[5] else ''}"
                    )

            return True

    except Exception as e:
        logger.error(f"列出表失败: {e}")
        return False


async def main():
    """主函数"""
    logger.info("开始数据库测试...")

    test_results = []

    # 测试数据库连接
    test_results.append(await test_database_connection())

    # 列出所有表
    test_results.append(await list_all_tables())

    # 测试Provider CRUD
    test_results.append(await test_provider_crud())

    # 测试Model Group CRUD
    test_results.append(await test_model_group_crud())

    # 汇总结果
    passed = sum(test_results)
    total = len(test_results)

    logger.info(f"测试结果: {passed}/{total} 通过")

    if passed == total:
        logger.info("所有数据库测试通过！")
        sys.exit(0)
    else:
        logger.error("部分数据库测试失败！")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
