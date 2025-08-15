"""
基于YAML的配置加载器 - 简化版本
"""
import yaml
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
    # 兼容字段
    base_url: str = ""
    daily_limit: int = 1000
    cost_per_token: Dict[str, float] = field(default_factory=dict)
    original_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ProviderConfig:
    """Provider配置"""
    name: str
    display_name: str
    adapter_class: str
    base_url: str
    auth_type: str = "bearer"
    rate_limit: int = 60
    enabled: bool = True
    capabilities: List[str] = field(default_factory=list)
    pricing_multiplier: float = 1.0
    # 兼容字段
    type: str = ""

@dataclass
class ModelGroupConfig:
    """模型组配置"""
    name: str
    display_name: str
    description: str
    enabled: bool = True
    routing_strategy: str = "multi_layer"
    filters: Dict[str, Any] = field(default_factory=dict)
    # 兼容字段
    budget_controls: Dict[str, Any] = field(default_factory=dict)
    routing_weights: Dict[str, float] = field(default_factory=dict)
    channels: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class RuntimeState:
    """运行时状态"""
    channel_stats: Dict[str, Any] = field(default_factory=dict)
    request_history: List[Dict[str, Any]] = field(default_factory=list)
    health_scores: Dict[str, float] = field(default_factory=dict)
    cost_tracking: Dict[str, Any] = field(default_factory=dict)

class YAMLConfigLoader:
    """YAML配置加载器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config_data: Dict[str, Any] = {}
        self.providers: Dict[str, ProviderConfig] = {}
        self.channels: Dict[str, ChannelConfig] = {}
        self.model_groups: Dict[str, ModelGroupConfig] = {}
        self.runtime_state: RuntimeState = RuntimeState()
        
        # 模型缓存
        self.model_cache: Dict[str, Dict] = {}
        
        self.load_config()
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        project_root = Path(__file__).parent.parent
        
        # 优先使用用户配置
        user_config = project_root / "config" / "router_config.yaml"
        if user_config.exists():
            return str(user_config)
        
        # 回退到模板配置 (用于测试)
        template_config = project_root / "config" / "router_config.yaml.template"
        if template_config.exists():
            logger.warning("使用模板配置文件，请复制为 router_config.yaml 并填入API密钥")
            return str(template_config)
        
        # 最后回退到JSON配置
        json_config = project_root / "config" / "simple_config.json"
        if json_config.exists():
            logger.warning("YAML配置不存在，回退到JSON配置")
            # 这里应该调用JSON配置加载器，但为了简化，先抛出异常
            raise FileNotFoundError("YAML配置文件不存在，请创建 config/router_config.yaml")
        
        raise FileNotFoundError("没有找到任何配置文件")
    
    def load_config(self) -> None:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config_data = yaml.safe_load(f)
            
            self._load_providers()
            self._load_channels()
            self._load_model_groups()
            self._load_runtime_state()
            
            logger.info(f"YAML配置加载成功: {len(self.providers)} providers, {len(self.channels)} channels, {len(self.model_groups)} model groups")
            
        except FileNotFoundError:
            logger.error(f"配置文件不存在: {self.config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"配置文件YAML格式错误: {e}")
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
            # 检查API密钥是否有效
            api_key = channel_data.get("api_key", "")
            if not api_key or api_key.startswith("填入") or len(api_key.strip()) < 10:
                logger.warning(f"渠道 {channel_data.get('name')} 的API密钥无效，将被禁用")
                channel_data["enabled"] = False
            
            channel = ChannelConfig(**channel_data)
            self.channels[channel.id] = channel
    
    def _load_model_groups(self) -> None:
        """加载Model Group配置"""
        model_groups_data = self.config_data.get("model_groups", {})
        
        for group_name, group_data in model_groups_data.items():
            # 处理特殊的组名格式 (auto:free -> auto:free)
            if group_name.startswith("auto:"):
                group_data["name"] = group_name
            
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
                if channel.api_key and len(channel.api_key.strip()) > 10 and not channel.api_key.startswith("填入"):
                    channels.append(channel)
        
        return channels
    
    def get_enabled_channels(self) -> List[ChannelConfig]:
        """获取所有启用的渠道"""
        return [ch for ch in self.channels.values() 
                if ch.enabled and ch.api_key and len(ch.api_key.strip()) > 10 and not ch.api_key.startswith("填入")]
    
    def get_channels_by_model(self, model_name: str) -> List[ChannelConfig]:
        """按模型名称获取渠道"""
        return [ch for ch in self.channels.values() 
                if ch.enabled and ch.model_name == model_name and ch.api_key and len(ch.api_key.strip()) > 10]
    
    def get_channels_by_capability(self, capability: str) -> List[ChannelConfig]:
        """按能力获取渠道"""
        return [ch for ch in self.channels.values() 
                if ch.enabled and capability in ch.capabilities and ch.api_key and len(ch.api_key.strip()) > 10]
    
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
            if "system" not in self.config_data:
                self.config_data["system"] = {}
            self.config_data["system"]["updated_at"] = datetime.now().isoformat()
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config_data, f, default_flow_style=False, allow_unicode=True, indent=2)
            
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
            "host": "127.0.0.1",
            "port": 8000,
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
    
    def get_system_config(self) -> Dict[str, Any]:
        """获取系统配置"""
        return self.config_data.get("system", {
            "name": "Smart AI Router",
            "version": "0.1.0",
            "storage_mode": "json"
        })
    
    def get_tasks_config(self) -> Dict[str, Any]:
        """获取任务配置"""
        return self.config_data.get("tasks", {
            "model_discovery": {
                "enabled": True,
                "interval_hours": 6,
                "run_on_startup": True
            },
            "health_check": {
                "enabled": True,
                "interval_minutes": 30
            },
            "cache_cleanup": {
                "enabled": True,
                "interval_hours": 24
            }
        })
    
    def update_model_cache(self, model_cache: Dict[str, Dict]) -> None:
        """更新模型缓存"""
        self.model_cache.update(model_cache)
        logger.info(f"模型缓存已更新，包含 {len(self.model_cache)} 个渠道的模型信息")
    
    def get_model_cache(self) -> Dict[str, Dict]:
        """获取模型缓存"""
        return self.model_cache.copy()
    
    def get_merged_config_with_models(self) -> Dict[str, Any]:
        """获取合并了模型信息的配置"""
        config = self.config_data.copy()
        
        # 如果有模型缓存，合并到渠道信息中
        if self.model_cache and 'channels' in config:
            for channel in config['channels']:
                channel_id = channel.get('id')
                if channel_id in self.model_cache:
                    model_info = self.model_cache[channel_id]
                    channel['discovered_models'] = model_info.get('models', [])
                    channel['model_count'] = model_info.get('model_count', 0)
                    channel['models_last_updated'] = model_info.get('last_updated')
                    channel['discovery_status'] = model_info.get('status', 'unknown')
        
        return config

# 全局配置实例
_yaml_config_loader: Optional[YAMLConfigLoader] = None

def get_yaml_config_loader() -> YAMLConfigLoader:
    """获取全局YAML配置加载器实例"""
    global _yaml_config_loader
    if _yaml_config_loader is None:
        _yaml_config_loader = YAMLConfigLoader()
    return _yaml_config_loader

def reload_yaml_config() -> YAMLConfigLoader:
    """重新加载YAML配置"""
    global _yaml_config_loader
    _yaml_config_loader = YAMLConfigLoader()
    return _yaml_config_loader