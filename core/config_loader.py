"""
基于JSON的配置加载器 - 无数据库依赖的轻量版本
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class ChannelConfig:
    """渠道配置"""
    id: str
    name: str
    provider: str
    model_name: str
    api_key: str
    enabled: bool = True
    priority: int = 1
    weight: float = 1.0
    capabilities: List[str] = field(default_factory=list)
    pricing: Dict[str, Any] = field(default_factory=dict)
    limits: Dict[str, Any] = field(default_factory=dict)
    performance: Dict[str, float] = field(default_factory=dict)

@dataclass
class ProviderConfig:
    """Provider配置"""
    name: str
    display_name: str
    type: str
    adapter_class: str
    base_url: str
    auth_type: str = "bearer"
    enabled: bool = True
    capabilities: List[str] = field(default_factory=list)
    pricing_multiplier: float = 1.0

@dataclass
class ModelGroupConfig:
    """模型组配置"""
    name: str
    display_name: str
    description: str
    enabled: bool = True
    routing_strategy: List[Dict[str, Any]] = field(default_factory=list)
    filters: Dict[str, Any] = field(default_factory=dict)
    channels: List[str] = field(default_factory=list)

@dataclass
class RuntimeState:
    """运行时状态"""
    channel_stats: Dict[str, Any] = field(default_factory=dict)
    request_history: List[Dict[str, Any]] = field(default_factory=list)
    health_scores: Dict[str, float] = field(default_factory=dict)
    cost_tracking: Dict[str, Any] = field(default_factory=dict)

class ConfigLoader:
    """配置加载器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config_data: Dict[str, Any] = {}
        self.providers: Dict[str, ProviderConfig] = {}
        self.channels: Dict[str, ChannelConfig] = {}
        self.model_groups: Dict[str, ModelGroupConfig] = {}
        self.runtime_state: RuntimeState = RuntimeState()
        
        self.load_config()
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        project_root = Path(__file__).parent.parent
        
        # 优先使用简化配置
        simple_config = project_root / "config" / "simple_config.json"
        if simple_config.exists():
            return str(simple_config)
        
        # 回退到完整配置
        return str(project_root / "config" / "channels_config.json")
    
    def load_config(self) -> None:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config_data = json.load(f)
            
            self._load_providers()
            self._load_channels()
            self._load_model_groups()
            self._load_runtime_state()
            
            logger.info(f"配置加载成功: {len(self.providers)} providers, {len(self.channels)} channels, {len(self.model_groups)} model groups")
            
        except FileNotFoundError:
            logger.error(f"配置文件不存在: {self.config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"配置文件JSON格式错误: {e}")
            raise
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            raise
    
    def _load_providers(self) -> None:
        """加载Provider配置"""
        providers_data = self.config_data.get("providers", {})
        
        for provider_name, provider_data in providers_data.items():
            self.providers[provider_name] = ProviderConfig(**provider_data)
    
    def _load_channels(self) -> None:
        """加载Channel配置"""
        channels_data = self.config_data.get("channels", [])
        
        for channel_data in channels_data:
            # 解析环境变量中的API密钥
            api_key = channel_data.get("api_key", "")
            if api_key.startswith("${") and api_key.endswith("}"):
                env_var = api_key[2:-1]
                api_key = os.getenv(env_var, "")
                if not api_key:
                    logger.warning(f"环境变量 {env_var} 未设置，渠道 {channel_data.get('name')} 将被禁用")
                    channel_data["enabled"] = False
                else:
                    channel_data["api_key"] = api_key
            
            channel = ChannelConfig(**channel_data)
            self.channels[channel.id] = channel
    
    def _load_model_groups(self) -> None:
        """加载Model Group配置"""
        model_groups_data = self.config_data.get("model_groups", {})
        
        for group_name, group_data in model_groups_data.items():
            self.model_groups[group_name] = ModelGroupConfig(**group_data)
    
    def _load_runtime_state(self) -> None:
        """加载运行时状态"""
        runtime_data = self.config_data.get("runtime_state", {})
        self.runtime_state = RuntimeState(**runtime_data)
    
    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        """获取Provider配置"""
        return self.providers.get(name)
    
    def get_channel(self, channel_id: str) -> Optional[ChannelConfig]:
        """获取Channel配置"""
        return self.channels.get(channel_id)
    
    def get_model_group(self, name: str) -> Optional[ModelGroupConfig]:
        """获取Model Group配置"""
        return self.model_groups.get(name)
    
    def get_channels_for_group(self, group_name: str) -> List[ChannelConfig]:
        """获取模型组的所有可用渠道"""
        group = self.get_model_group(group_name)
        if not group or not group.enabled:
            return []
        
        channels = []
        for channel_id in group.channels:
            channel = self.get_channel(channel_id)
            if channel and channel.enabled:
                # 检查API密钥是否可用
                if channel.api_key and len(channel.api_key.strip()) > 0:
                    channels.append(channel)
        
        return channels
    
    def get_enabled_channels(self) -> List[ChannelConfig]:
        """获取所有启用的渠道"""
        return [ch for ch in self.channels.values() if ch.enabled and ch.api_key]
    
    def get_channels_by_model(self, model_name: str) -> List[ChannelConfig]:
        """按模型名称获取渠道"""
        return [ch for ch in self.channels.values() 
                if ch.enabled and ch.model_name == model_name and ch.api_key]
    
    def get_channels_by_capability(self, capability: str) -> List[ChannelConfig]:
        """按能力获取渠道"""
        return [ch for ch in self.channels.values() 
                if ch.enabled and capability in ch.capabilities and ch.api_key]
    
    def save_config(self) -> None:
        """保存配置到文件"""
        try:
            # 更新runtime_state
            self.config_data["runtime_state"] = {
                "channel_stats": self.runtime_state.channel_stats,
                "request_history": self.runtime_state.request_history[-1000:],  # 只保留最近1000条记录
                "health_scores": self.runtime_state.health_scores,
                "cost_tracking": self.runtime_state.cost_tracking
            }
            
            # 更新时间戳
            self.config_data["system"]["updated_at"] = datetime.now().isoformat()
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
            
            logger.info("配置已保存")
            
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
    
    def update_channel_health(self, channel_id: str, health_score: float) -> None:
        """更新渠道健康分数"""
        self.runtime_state.health_scores[channel_id] = health_score
    
    def add_request_log(self, log_entry: Dict[str, Any]) -> None:
        """添加请求日志"""
        log_entry["timestamp"] = datetime.now().isoformat()
        self.runtime_state.request_history.append(log_entry)
        
        # 只保留最近1000条记录
        if len(self.runtime_state.request_history) > 1000:
            self.runtime_state.request_history = self.runtime_state.request_history[-1000:]
    
    def update_cost_tracking(self, cost: float, tokens: int = 0) -> None:
        """更新成本追踪"""
        if "daily_spent" not in self.runtime_state.cost_tracking:
            self.runtime_state.cost_tracking["daily_spent"] = 0.0
        if "monthly_spent" not in self.runtime_state.cost_tracking:
            self.runtime_state.cost_tracking["monthly_spent"] = 0.0
        
        self.runtime_state.cost_tracking["daily_spent"] += cost
        self.runtime_state.cost_tracking["monthly_spent"] += cost
        
        if tokens > 0:
            if "total_tokens" not in self.runtime_state.cost_tracking:
                self.runtime_state.cost_tracking["total_tokens"] = 0
            self.runtime_state.cost_tracking["total_tokens"] += tokens
    
    def get_server_config(self) -> Dict[str, Any]:
        """获取服务器配置"""
        return self.config_data.get("server", {
            "host": "0.0.0.0",
            "port": 7601,
            "debug": False
        })
    
    def get_routing_config(self) -> Dict[str, Any]:
        """获取路由配置"""
        return self.config_data.get("routing", {
            "default_strategy": "auto:balanced",
            "fallback_enabled": True,
            "max_fallback_attempts": 3
        })
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """获取监控配置"""
        return self.config_data.get("monitoring", {
            "enabled": True,
            "log_requests": True,
            "log_responses": False
        })

# 全局配置实例
_config_loader: Optional[ConfigLoader] = None

def get_config_loader() -> ConfigLoader:
    """获取全局配置加载器实例"""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader

def reload_config() -> ConfigLoader:
    """重新加载配置"""
    global _config_loader
    _config_loader = ConfigLoader()
    return _config_loader