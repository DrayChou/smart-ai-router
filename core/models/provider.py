"""
Provider data model
Provider数据模型
"""

from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .base import Base


class Provider(Base):
    """Provider表 - AI服务提供商"""
    __tablename__ = "providers"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)  # openai, anthropic等
    display_name = Column(String(100), nullable=False)     # OpenAI Official
    type = Column(String(20), nullable=False)              # official, aggregator, reseller
    adapter_class = Column(String(100), nullable=False)    # OpenAIAdapter
    base_url = Column(String(200))                         # 基础API端点
    auth_type = Column(String(20), default="bearer")       # bearer, x-api-key
    
    # 配置信息 (JSON字段)
    pricing_config = Column(JSON)                          # 价格配置
    discovery_config = Column(JSON)                        # 模型发现配置
    capability_mapping = Column(JSON)                      # 能力映射
    request_adapter_config = Column(JSON)                  # 请求适配配置
    rate_limits = Column(JSON)                            # 速率限制
    default_pricing = Column(JSON)                        # 默认价格
    
    # 状态
    status = Column(String(20), default="active")         # active, disabled
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # 关系
    channels = relationship("Channel", back_populates="provider")
    
    def __repr__(self):
        return f"<Provider(name='{self.name}', type='{self.type}')>"