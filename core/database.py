"""
数据库连接和会话管理
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.models.base import Base
from core.utils.logger import get_logger

logger = get_logger(__name__)

# 数据库URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./smart_ai_router.db")

# 创建异步引擎
if "sqlite" in DATABASE_URL:
    # SQLite特殊配置
    engine = create_async_engine(
        DATABASE_URL,
        poolclass=StaticPool,
        connect_args={
            "check_same_thread": False,
        },
        echo=os.getenv("DEBUG", "false").lower() == "true",
    )
else:
    # PostgreSQL配置
    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        echo=os.getenv("DEBUG", "false").lower() == "true",
    )

# 创建异步会话工厂
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话上下文管理器"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI依赖注入的数据库会话生成器"""
    async with get_db_session() as session:
        yield session


async def init_db() -> None:
    """初始化数据库"""
    logger.info("正在初始化数据库...")

    try:
        # 创建所有表
        async with engine.begin() as conn:
            # 注意：在实际环境中应该使用Alembic迁移
            # 这里只是为了测试方便
            if os.getenv("DEVELOPMENT_MODE", "false").lower() == "true":
                await conn.run_sync(Base.metadata.create_all)

        logger.info("数据库初始化完成")

    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise


async def close_db() -> None:
    """关闭数据库连接"""
    logger.info("正在关闭数据库连接...")
    await engine.dispose()
    logger.info("数据库连接已关闭")


# SQLite特殊处理：启用外键约束
if "sqlite" in DATABASE_URL:

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
