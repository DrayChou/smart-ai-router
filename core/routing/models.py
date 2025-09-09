"""
路由相关的数据模型
"""
from dataclasses import dataclass
from typing import Any, Optional
from core.config_models import Channel


@dataclass
class RoutingScore:
    """路由评分结果"""
    final_score: float
    cost_score: float
    speed_score: float
    quality_score: float
    reliability_score: float
    capabilities_score: float
    
    def __post_init__(self):
        """确保评分在合理范围内"""
        self.final_score = max(0.0, min(100.0, self.final_score))
        self.cost_score = max(0.0, min(100.0, self.cost_score))
        self.speed_score = max(0.0, min(100.0, self.speed_score))
        self.quality_score = max(0.0, min(100.0, self.quality_score))
        self.reliability_score = max(0.0, min(100.0, self.reliability_score))
        self.capabilities_score = max(0.0, min(100.0, self.capabilities_score))


@dataclass  
class ChannelCandidate:
    """渠道候选者"""
    channel: Channel
    model_name: str
    score: Optional[RoutingScore] = None


@dataclass
class RoutingRequest:
    """路由请求参数"""
    model: str
    strategy: str = "balanced"
    required_capabilities: Optional[list[str]] = None
    exclude_channels: Optional[list[str]] = None
    debug: bool = False
    request_context: Optional[dict[str, Any]] = None
    
    def __post_init__(self):
        """初始化默认值"""
        if self.required_capabilities is None:
            self.required_capabilities = []
        if self.exclude_channels is None:
            self.exclude_channels = []
        if self.request_context is None:
            self.request_context = {}