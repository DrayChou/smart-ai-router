"""
Statistics and monitoring data models
统计和监控数据模型
"""

from sqlalchemy import (
    Column, Integer, String, Text, JSON, DateTime, Boolean,
    DECIMAL, ForeignKey, Date
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .base import Base


class RequestLog(Base):
    """请求日志表"""
    __tablename__ = "request_logs"
    
    id = Column(Integer, primary_key=True)
    request_id = Column(String(50))                        # 请求唯一ID
    model_group_name = Column(String(50))                  # 使用的模型组名称
    channel_id = Column(Integer, ForeignKey("channels.id"))
    api_key_id = Column(Integer, ForeignKey("api_keys.id"))
    client_api_key_id = Column(Integer, ForeignKey("router_api_keys.id"))
    
    # 请求详情
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens = Column(Integer)
    request_size = Column(Integer)                         # 请求体大小
    response_size = Column(Integer)                        # 响应体大小
    
    # 成本和性能
    estimated_cost = Column(DECIMAL(10,4))                 # 预估成本
    actual_cost = Column(DECIMAL(10,4))                    # 实际成本
    effective_cost = Column(DECIMAL(10,4))                 # 考虑倍率后的有效成本
    latency_ms = Column(Integer)                           # 响应延迟(毫秒)
    ttft_ms = Column(Integer)                              # Time to First Token (毫秒)
    throughput_tps = Column(DECIMAL(6,2))                  # 吞吐量 tokens/second
    
    # 路由决策信息
    routing_strategy_used = Column(JSON)                   # 使用的路由策略
    routing_scores = Column(JSON)                          # 各渠道的评分
    fallback_attempts = Column(Integer, default=0)        # 故障转移尝试次数
    
    # 结果状态
    status = Column(String(20))                           # success, error, timeout
    error_code = Column(String(50))                       # 错误代码
    error_message = Column(Text)                          # 错误信息
    error_type = Column(String(20))                       # 错误类型: permanent, temporary, rate_limit
    
    # 请求特征
    has_function_calls = Column(Boolean, default=False)   # 是否包含工具调用
    has_images = Column(Boolean, default=False)           # 是否包含图片
    stream_enabled = Column(Boolean, default=False)       # 是否启用流式
    
    created_at = Column(DateTime, default=func.now())
    
    # 关系
    channel = relationship("Channel", back_populates="request_logs")
    api_key = relationship("ApiKey", back_populates="request_logs")
    client_api_key = relationship("RouterApiKey", back_populates="request_logs")
    
    def __repr__(self):
        return f"<RequestLog(id='{self.request_id}', status='{self.status}')>"


class ChannelStats(Base):
    """渠道统计表"""
    __tablename__ = "channel_stats"
    
    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    date = Column(Date, nullable=False)                    # 统计日期
    hour = Column(Integer)                                 # 小时(0-23, NULL表示全天统计)
    
    # 请求统计
    request_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    timeout_count = Column(Integer, default=0)
    rate_limit_count = Column(Integer, default=0)
    
    # 性能统计  
    total_tokens = Column(Integer, default=0)
    total_cost = Column(DECIMAL(10,4), default=0)
    avg_latency_ms = Column(Integer, default=0)
    min_latency_ms = Column(Integer, default=0)
    max_latency_ms = Column(Integer, default=0)
    avg_ttft_ms = Column(Integer, default=0)              # 平均首字延迟
    avg_throughput_tps = Column(DECIMAL(6,2), default=0)  # 平均吞吐量
    
    # 质量统计
    success_rate = Column(DECIMAL(5,4), default=0.0)      # 成功率 (0.0-1.0)
    error_rate = Column(DECIMAL(5,4), default=0.0)        # 错误率
    timeout_rate = Column(DECIMAL(5,4), default=0.0)      # 超时率
    
    # 评分计算 (0.0-1.0)
    speed_score = Column(DECIMAL(3,2), default=1.0)       # 速度评分
    reliability_score = Column(DECIMAL(3,2), default=1.0) # 可靠性评分
    cost_efficiency = Column(DECIMAL(3,2), default=1.0)   # 性价比评分
    overall_health_score = Column(DECIMAL(3,2), default=1.0) # 综合健康评分
    
    # 详细错误统计
    error_breakdown = Column(JSON)                         # 错误类型分解统计
    
    created_at = Column(DateTime, default=func.now())
    
    # 关系
    channel = relationship("Channel", back_populates="channel_stats")
    
    def __repr__(self):
        return f"<ChannelStats(channel_id={self.channel_id}, date={self.date})>"