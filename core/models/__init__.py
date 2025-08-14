"""数据模型模块 - SQLAlchemy data models"""

from .base import Base

# 导入所有模型以确保它们被注册到Base.metadata
# 注意：避免循环导入，只导入必要的类

__all__ = [
    "Base",
]


# 懒加载模型，避免重复定义表的问题
def get_all_models():
    """获取所有模型类"""
    from .api_key import APIKey
    from .channel import Channel
    from .model_group import ModelGroupChannel
    from .provider import Provider
    from .request_log import RequestLog
    from .stats import ChannelStats, RouterAPIKey
    from .virtual_model import VirtualModelGroup

    return {
        "Provider": Provider,
        "Channel": Channel,
        "VirtualModelGroup": VirtualModelGroup,
        "ModelGroupChannel": ModelGroupChannel,
        "APIKey": APIKey,
        "RequestLog": RequestLog,
        "ChannelStats": ChannelStats,
        "RouterAPIKey": RouterAPIKey,
    }
