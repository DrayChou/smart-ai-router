"""
Model Group Channel mapping data model
模型组渠道映射数据模型
"""

from sqlalchemy import (
    DECIMAL,
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class ModelGroupChannel(Base):
    """模型组-渠道映射表"""

    __tablename__ = "model_group_channels"

    model_group_id = Column(
        Integer, ForeignKey("virtual_model_groups.id"), primary_key=True
    )
    channel_id = Column(Integer, ForeignKey("channels.id"), primary_key=True)
    priority = Column(Integer, default=1)  # 在该模型组中的优先级
    weight = Column(DECIMAL(3, 2), default=1.0)  # 负载均衡权重
    daily_limit = Column(Integer, default=1000)  # 在此模型组中的每日限额

    # 性能评分和能力配置
    speed_score = Column(DECIMAL(3, 2), default=1.0)  # 速度评分 (0.0-1.0)
    quality_score = Column(DECIMAL(3, 2), default=1.0)  # 质量评分 (0.0-1.0)
    reliability_score = Column(DECIMAL(3, 2), default=1.0)  # 可靠性评分 (0.0-1.0)
    capabilities = Column(JSON)  # 渠道特定能力覆盖
    overrides = Column(JSON)  # 模型组特定配置覆盖

    enabled = Column(Boolean, default=True)  # 是否在此模型组中启用

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关系
    model_group = relationship(
        "VirtualModelGroup", back_populates="model_group_channels"
    )
    channel = relationship("Channel", back_populates="model_group_channels")

    def __repr__(self):
        return f"<ModelGroupChannel(group_id={self.model_group_id}, channel_id={self.channel_id})>"
