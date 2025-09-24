"""
Channel data model
Channel数据模型
"""

from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    JSON,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.sql import func

from .base import Base


class Channel(Base):
    """Channel表 - 具体的API渠道"""

    __tablename__ = "channels"

    id = Column(Integer, primary_key=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    name = Column(String(100), nullable=False)  # 渠道友好名称
    model_name = Column(String(50), nullable=False)  # gpt-4o, claude-3-5-sonnet等
    endpoint = Column(String(300))  # 完整API端点
    priority = Column(Integer, default=1)  # 优先级 (1=最高)
    weight: Mapped[Decimal] = Column(
        DECIMAL(3, 2), default=Decimal("1.0")
    )  # 负载均衡权重

    # 成本配置 (可动态更新)
    input_cost_per_1k: Mapped[Decimal] = Column(
        DECIMAL(10, 4), default=Decimal("0")
    )  # 输入成本 $/1K tokens
    output_cost_per_1k: Mapped[Decimal] = Column(
        DECIMAL(10, 4), default=Decimal("0")
    )  # 输出成本 $/1K tokens

    # 每日限额管理
    daily_request_limit = Column(Integer, default=1000)  # 每日请求限额
    daily_request_count = Column(Integer, default=0)  # 当日已使用数量
    quota_reset_date = Column(Date)  # 配额重置日期

    # 性能和能力配置 (JSON字段)
    capabilities = Column(JSON)  # 模型能力
    performance_scores = Column(JSON)  # 性能评分

    # 运行状态
    status = Column(
        String(20), default="active"
    )  # active, disabled, cooling, quota_exceeded
    health_score: Mapped[Decimal] = Column(
        DECIMAL(3, 2), default=Decimal("1.0")
    )  # 0.0-1.0 健康度
    last_success_at = Column(DateTime)
    last_error_at = Column(DateTime)
    cooldown_until = Column(DateTime)  # 冷却结束时间

    # 速率限制控制
    min_request_interval = Column(Integer, default=0)  # 最小请求间隔(秒)，0表示无限制
    last_request_at = Column(DateTime)  # 上次请求时间

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关系
    provider = relationship("Provider", back_populates="channels")
    api_keys = relationship("APIKey", back_populates="channel")
    model_group_channels = relationship("ModelGroupChannel", back_populates="channel")
    request_logs = relationship("RequestLog", back_populates="channel")
    channel_stats = relationship("ChannelStats", back_populates="channel")

    def __repr__(self) -> str:
        return f"<Channel(name='{self.name}', model='{self.model_name}')>"
