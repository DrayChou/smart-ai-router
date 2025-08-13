"""
Model Group data models
模型组数据模型
"""

from sqlalchemy import (
    Column, Integer, String, Text, JSON, DateTime, Boolean,
    DECIMAL, ForeignKey
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .base import Base


class VirtualModelGroup(Base):
    """虚拟模型组表"""
    __tablename__ = "virtual_model_groups"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)  # auto:free, auto:fast等
    display_name = Column(String(100))                      # 免费模型组, 快速模型组
    description = Column(Text)                              # 模型组描述
    
    # 多层路由策略配置 (JSON字段)
    routing_strategy = Column(JSON)                         # 多层路由策略数组
    filters = Column(JSON)                                  # 模型筛选条件
    budget_limits = Column(JSON)                            # 预算限制配置
    time_policies = Column(JSON)                            # 时间策略配置
    load_balancing = Column(JSON)                           # 负载均衡配置
    
    # 模型组状态
    status = Column(String(20), default="active")          # active, disabled, maintenance
    priority = Column(Integer, default=100)                # 优先级 (数字越小优先级越高)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # 关系
    model_group_channels = relationship("ModelGroupChannel", back_populates="model_group")
    
    def __repr__(self):
        return f"<VirtualModelGroup(name='{self.name}')>"


class ModelGroupChannel(Base):
    """模型组-渠道映射表"""
    __tablename__ = "model_group_channels"
    
    model_group_id = Column(Integer, ForeignKey("virtual_model_groups.id"), primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), primary_key=True)
    priority = Column(Integer, default=1)                  # 在该模型组中的优先级
    weight = Column(DECIMAL(3,2), default=1.0)            # 负载均衡权重
    daily_limit = Column(Integer, default=1000)            # 在此模型组中的每日限额
    
    # 性能评分和能力配置
    speed_score = Column(DECIMAL(3,2), default=1.0)       # 速度评分 (0.0-1.0)
    quality_score = Column(DECIMAL(3,2), default=1.0)     # 质量评分 (0.0-1.0)
    reliability_score = Column(DECIMAL(3,2), default=1.0) # 可靠性评分 (0.0-1.0)
    capabilities = Column(JSON)                            # 渠道特定能力覆盖
    overrides = Column(JSON)                              # 模型组特定配置覆盖
    
    enabled = Column(Boolean, default=True)               # 是否在此模型组中启用
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # 关系
    model_group = relationship("VirtualModelGroup", back_populates="model_group_channels")
    channel = relationship("Channel", back_populates="model_group_channels")
    
    def __repr__(self):
        return f"<ModelGroupChannel(group_id={self.model_group_id}, channel_id={self.channel_id})>"