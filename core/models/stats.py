"""
Statistics data model
统计数据模型
"""

from sqlalchemy import (
    DECIMAL,
    JSON,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class ChannelStats(Base):
    """渠道统计表"""

    __tablename__ = "channel_stats"

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    date = Column(Date, nullable=False)  # 统计日期
    hour = Column(Integer)  # 小时(0-23, NULL表示全天统计)

    # 请求统计
    request_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    timeout_count = Column(Integer, default=0)
    rate_limit_count = Column(Integer, default=0)

    # 性能统计
    total_tokens = Column(Integer, default=0)
    total_cost = Column(DECIMAL(10, 4), default=0)
    avg_latency_ms = Column(Integer, default=0)
    min_latency_ms = Column(Integer, default=0)
    max_latency_ms = Column(Integer, default=0)
    avg_ttft_ms = Column(Integer, default=0)  # 平均首字延迟
    avg_throughput_tps = Column(DECIMAL(6, 2), default=0)  # 平均吞吐量

    # 质量统计
    success_rate = Column(DECIMAL(5, 4), default=0.0)  # 成功率 (0.0-1.0)
    error_rate = Column(DECIMAL(5, 4), default=0.0)  # 错误率
    timeout_rate = Column(DECIMAL(5, 4), default=0.0)  # 超时率

    # 评分计算 (0.0-1.0)
    speed_score = Column(DECIMAL(3, 2), default=1.0)  # 速度评分
    reliability_score = Column(DECIMAL(3, 2), default=1.0)  # 可靠性评分
    cost_efficiency = Column(DECIMAL(3, 2), default=1.0)  # 性价比评分
    overall_health_score = Column(DECIMAL(3, 2), default=1.0)  # 综合健康评分

    # 详细错误统计
    error_breakdown = Column(JSON)  # 错误类型分解统计

    created_at = Column(DateTime, default=func.now())

    # 关系
    channel = relationship("Channel", back_populates="channel_stats")

    def __repr__(self):
        return f"<ChannelStats(channel_id={self.channel_id}, date={self.date})>"
