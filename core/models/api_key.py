"""
API Key data models
API密钥数据模型
"""

from sqlalchemy import (
    DECIMAL,
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class APIKey(Base):
    """API密钥表 - Provider的API密钥"""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    key_name = Column(String(100))  # 密钥友好名称
    key_value = Column(String(500), nullable=False)  # 加密存储的API key

    # 使用状态
    status = Column(String(20), default="active")  # active, disabled, exhausted
    last_used_at = Column(DateTime)
    usage_count = Column(Integer, default=0)

    # 配额管理
    daily_quota = Column(DECIMAL(10, 2))  # 每日配额 ($)
    monthly_quota = Column(DECIMAL(10, 2))  # 月度配额 ($)
    remaining_quota = Column(DECIMAL(10, 2))  # 剩余配额
    quota_reset_at = Column(DateTime)  # 配额重置时间

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关系
    channel = relationship("Channel", back_populates="api_keys")
    request_logs = relationship("RequestLog", back_populates="api_key")

    def __repr__(self):
        return f"<APIKey(name='{self.key_name}', channel_id={self.channel_id})>"


class RouterAPIKey(Base):
    """路由器API密钥表 - 客户端访问密钥"""

    __tablename__ = "router_api_keys"

    id = Column(Integer, primary_key=True)
    key_hash = Column(String(64), nullable=False, unique=True)  # API key 哈希
    key_name = Column(String(100))  # 密钥名称

    # 权限配置
    allowed_model_groups = Column(JSON)  # 允许访问的模型组
    daily_budget = Column(DECIMAL(10, 2))  # 每日预算限制
    monthly_budget = Column(DECIMAL(10, 2))  # 月度预算限制
    rate_limit = Column(String(20))  # 速率限制 "100/hour"
    role = Column(String(20), default="user")  # admin, user

    # 使用统计
    last_used_at = Column(DateTime)
    request_count = Column(Integer, default=0)
    total_cost = Column(DECIMAL(10, 4), default=0)

    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关系
    request_logs = relationship("RequestLog", back_populates="client_api_key")

    def __repr__(self):
        return f"<RouterAPIKey(name='{self.key_name}', role='{self.role}')>"
