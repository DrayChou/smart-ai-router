#!/usr/bin/env python3
"""
Phase 1 测试套件 - 数据库和基础功能验证
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量

from dotenv import load_dotenv

load_dotenv(project_root / ".env")

import logging

from sqlalchemy import text

from core.database import get_db_session

# 设置基础日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestPhase1Database:
    """Phase 1 数据库测试"""

    async def test_database_connection(self):
        """测试数据库连接"""
        async with get_db_session() as session:
            result = await session.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            assert row[0] == 1, "数据库连接失败"

    async def test_database_tables_exist(self):
        """测试所有必需的表都存在"""
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

        async with get_db_session() as session:
            result = await session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            actual_tables = [row[0] for row in result.fetchall()]

            for table in expected_tables:
                assert table in actual_tables, f"表 '{table}' 不存在"

    async def test_providers_table_structure(self):
        """测试providers表结构"""
        async with get_db_session() as session:
            # 测试插入和查询
            await session.execute(
                text(
                    """
                INSERT INTO providers (name, display_name, type, adapter_class, status)
                VALUES ('test_provider', 'Test Provider', 'test', 'TestAdapter', 'active')
            """
                )
            )

            result = await session.execute(
                text(
                    """
                SELECT name, display_name, type, adapter_class, status 
                FROM providers WHERE name = 'test_provider'
            """
                )
            )
            row = result.fetchone()

            assert row is not None, "插入Provider失败"
            assert row[0] == "test_provider"
            assert row[1] == "Test Provider"
            assert row[2] == "test"
            assert row[3] == "TestAdapter"
            assert row[4] == "active"

            # 清理
            await session.execute(
                text("DELETE FROM providers WHERE name = 'test_provider'")
            )

    async def test_virtual_model_groups_json_fields(self):
        """测试virtual_model_groups表的JSON字段"""
        async with get_db_session() as session:
            # 插入包含JSON数据的记录
            await session.execute(
                text(
                    """
                INSERT INTO virtual_model_groups 
                (name, display_name, status, routing_strategy, filters, budget_limits)
                VALUES (
                    'test:json', 
                    '测试JSON字段', 
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
                SELECT name, routing_strategy, filters, budget_limits 
                FROM virtual_model_groups 
                WHERE name = 'test:json'
            """
                )
            )
            row = result.fetchone()

            assert row is not None, "插入VirtualModelGroup失败"
            assert row[0] == "test:json"

            # 验证JSON字段内容
            routing_strategy = row[1]
            filters = row[2]
            budget_limits = row[3]

            assert routing_strategy is not None
            assert filters is not None
            assert budget_limits is not None

            # 清理
            await session.execute(
                text("DELETE FROM virtual_model_groups WHERE name = 'test:json'")
            )

    async def test_foreign_key_constraints(self):
        """测试外键约束"""
        async with get_db_session() as session:
            # 先插入provider
            await session.execute(
                text(
                    """
                INSERT INTO providers (name, display_name, type, adapter_class, status)
                VALUES ('fk_test_provider', 'FK Test Provider', 'test', 'TestAdapter', 'active')
            """
                )
            )

            # 获取provider_id
            result = await session.execute(
                text(
                    """
                SELECT id FROM providers WHERE name = 'fk_test_provider'
            """
                )
            )
            provider_id = result.fetchone()[0]

            # 插入channel
            await session.execute(
                text(
                    f"""
                INSERT INTO channels (provider_id, name, model_name, status)
                VALUES ({provider_id}, 'test_channel', 'test_model', 'active')
            """
                )
            )

            # 验证关系
            result = await session.execute(
                text(
                    """
                SELECT c.name, p.name as provider_name
                FROM channels c
                JOIN providers p ON c.provider_id = p.id
                WHERE c.name = 'test_channel'
            """
                )
            )
            row = result.fetchone()

            assert row is not None
            assert row[0] == "test_channel"
            assert row[1] == "fk_test_provider"

            # 清理 (注意顺序，先删除子表)
            await session.execute(
                text("DELETE FROM channels WHERE name = 'test_channel'")
            )
            await session.execute(
                text("DELETE FROM providers WHERE name = 'fk_test_provider'")
            )


class TestPhase1Configuration:
    """Phase 1 配置测试"""

    def test_env_file_exists(self):
        """测试.env文件存在"""
        env_file = project_root / ".env"
        assert env_file.exists(), ".env文件不存在"

    def test_alembic_configuration(self):
        """测试Alembic配置"""
        alembic_ini = project_root / "alembic.ini"
        assert alembic_ini.exists(), "alembic.ini文件不存在"

        # 检查versions目录
        versions_dir = project_root / "migrations" / "versions"
        assert versions_dir.exists(), "migrations/versions目录不存在"

        # 检查是否有迁移文件
        migration_files = list(versions_dir.glob("*.py"))
        assert len(migration_files) > 0, "没有迁移文件"


async def test_database_integration():
    """集成测试 - 完整的数据库操作流程"""
    async with get_db_session() as session:
        # 1. 创建Provider
        await session.execute(
            text(
                """
            INSERT INTO providers (name, display_name, type, adapter_class, status, pricing_config)
            VALUES ('integration_test', 'Integration Test Provider', 'test', 'TestAdapter', 'active', '{}')
        """
            )
        )

        # 2. 创建VirtualModelGroup
        await session.execute(
            text(
                """
            INSERT INTO virtual_model_groups (name, display_name, status, routing_strategy)
            VALUES ('integration:test', 'Integration Test Group', 'active', '[]')
        """
            )
        )

        # 3. 获取IDs
        provider_result = await session.execute(
            text(
                """
            SELECT id FROM providers WHERE name = 'integration_test'
        """
            )
        )
        provider_id = provider_result.fetchone()[0]

        group_result = await session.execute(
            text(
                """
            SELECT id FROM virtual_model_groups WHERE name = 'integration:test'
        """
            )
        )
        group_id = group_result.fetchone()[0]

        # 4. 创建Channel
        await session.execute(
            text(
                f"""
            INSERT INTO channels (provider_id, name, model_name, status)
            VALUES ({provider_id}, 'integration_channel', 'test_model', 'active')
        """
            )
        )

        # 5. 获取Channel ID
        channel_result = await session.execute(
            text(
                """
            SELECT id FROM channels WHERE name = 'integration_channel'
        """
            )
        )
        channel_id = channel_result.fetchone()[0]

        # 6. 创建ModelGroup-Channel映射
        await session.execute(
            text(
                f"""
            INSERT INTO model_group_channels (model_group_id, channel_id, enabled)
            VALUES ({group_id}, {channel_id}, 1)
        """
            )
        )

        # 7. 验证完整关系
        result = await session.execute(
            text(
                f"""
            SELECT 
                p.name as provider_name,
                c.name as channel_name,
                vmg.name as group_name
            FROM model_group_channels mgc
            JOIN channels c ON mgc.channel_id = c.id
            JOIN providers p ON c.provider_id = p.id  
            JOIN virtual_model_groups vmg ON mgc.model_group_id = vmg.id
            WHERE mgc.model_group_id = {group_id} AND mgc.channel_id = {channel_id}
        """
            )
        )

        row = result.fetchone()
        assert row is not None, "集成测试：关系查询失败"
        assert row[0] == "integration_test"
        assert row[1] == "integration_channel"
        assert row[2] == "integration:test"

        # 8. 清理（按依赖顺序）
        await session.execute(
            text(
                f"DELETE FROM model_group_channels WHERE model_group_id = {group_id} AND channel_id = {channel_id}"
            )
        )
        await session.execute(text(f"DELETE FROM channels WHERE id = {channel_id}"))
        await session.execute(
            text(f"DELETE FROM virtual_model_groups WHERE id = {group_id}")
        )
        await session.execute(text(f"DELETE FROM providers WHERE id = {provider_id}"))

        logger.info("[PASS] 集成测试通过")


if __name__ == "__main__":
    # 直接运行测试
    async def run_tests():
        logger.info("开始Phase 1测试...")

        db_tests = TestPhase1Database()
        config_tests = TestPhase1Configuration()

        try:
            # 数据库测试
            await db_tests.test_database_connection()
            logger.info("[PASS] 数据库连接测试通过")

            await db_tests.test_database_tables_exist()
            logger.info("[PASS] 数据库表结构测试通过")

            await db_tests.test_providers_table_structure()
            logger.info("[PASS] Providers表测试通过")

            await db_tests.test_virtual_model_groups_json_fields()
            logger.info("[PASS] JSON字段测试通过")

            await db_tests.test_foreign_key_constraints()
            logger.info("[PASS] 外键约束测试通过")

            # 配置测试
            config_tests.test_env_file_exists()
            logger.info("[PASS] 环境配置测试通过")

            config_tests.test_alembic_configuration()
            logger.info("[PASS] Alembic配置测试通过")

            # 集成测试
            await test_database_integration()

            logger.info("🎉 Phase 1 所有测试通过！")
            return True

        except Exception as e:
            logger.error(f"[FAIL] 测试失败: {e}")
            return False

    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
