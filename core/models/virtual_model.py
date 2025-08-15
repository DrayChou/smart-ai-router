"""
Virtual Model Group data model
虚拟模型组数据模型
"""

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class VirtualModelGroup(Base):
    """虚拟模型组表"""

    __tablename__ = "virtual_model_groups"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)  # auto:free, auto:fast等
    display_name = Column(String(100))  # 免费模型组, 快速模型组
    description = Column(Text)  # 模型组描述

    # 多层路由策略配置 (JSON字段)
    routing_strategy = Column(JSON)  # 多层路由策略数组
    filters = Column(JSON)  # 模型筛选条件
    budget_limits = Column(JSON)  # 预算限制配置
    time_policies = Column(JSON)  # 时间策略配置
    load_balancing = Column(JSON)  # 负载均衡配置

    # 模型组状态
    status = Column(String(20), default="active")  # active, disabled, maintenance
    priority = Column(Integer, default=100)  # 优先级 (数字越小优先级越高)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关系
    model_group_channels = relationship(
        "ModelGroupChannel", back_populates="model_group"
    )

    def __repr__(self):
        return f"<VirtualModelGroup(name='{self.name}')>"