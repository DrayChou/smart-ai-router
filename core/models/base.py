"""
Base model configuration
基础模型配置
"""

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 创建基础模型类
Base = declarative_base()

# 数据库引擎和会话配置
engine = None
SessionLocal = None


def init_database(database_url: str = "sqlite:///./smart_router.db") -> Any:
    """初始化数据库连接"""
    global engine, SessionLocal

    engine = create_engine(
        database_url,
        echo=False,  # 在开发环境设置为True以查看SQL
        pool_pre_ping=True,
    )

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    return engine


def get_db() -> Any:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """创建所有表"""
    Base.metadata.create_all(bind=engine)
