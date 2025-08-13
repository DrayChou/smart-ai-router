"""数据模型模块 - SQLAlchemy data models"""

from .base import Base, init_database, get_db, create_tables
from .provider import Provider
from .channel import Channel
from .model_group import VirtualModelGroup, ModelGroupChannel
from .api_key import ApiKey, RouterApiKey
from .stats import RequestLog, ChannelStats

# 导入所有模型以确保它们被注册到Base.metadata
__all__ = [
    "Base",
    "init_database", 
    "get_db",
    "create_tables",
    "Provider",
    "Channel", 
    "VirtualModelGroup",
    "ModelGroupChannel",
    "ApiKey",
    "RouterApiKey",
    "RequestLog",
    "ChannelStats",
]