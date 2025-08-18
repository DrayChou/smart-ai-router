"""
基于YAML的配置加载器 - Pydantic版本
"""
import yaml
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

from .config_models import Config, Channel, Provider
from .auth.token_generator import generate_random_token

logger = logging.getLogger(__name__)

@dataclass
class RuntimeState:
    """运行时状态"""
    channel_stats: Dict[str, Any] = field(default_factory=dict)
    request_history: List[Dict[str, Any]] = field(default_factory=list)
    health_scores: Dict[str, float] = field(default_factory=dict)
    cost_tracking: Dict[str, Any] = field(default_factory=dict)

class YAMLConfigLoader:
    """基于Pydantic的YAML配置加载器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_path("router_config.yaml")
        
        # 运行时状态
        self.runtime_state: RuntimeState = RuntimeState()
        
        # 模型缓存
        self.model_cache: Dict[str, Dict] = {}
        
        # 加载并解析配置
        self.config: Config = self._load_and_validate_config()
        
        # 创建渠道映射
        self.channels_map = {ch.id: ch for ch in self.config.channels}
        
        # 加载模型缓存
        self._load_model_cache_from_disk()
        
        logger.info(f"Config loaded: {len(self.config.providers)} providers, {len(self.config.channels)} channels")

    def _get_default_path(self, filename: str) -> str:
        """获取配置文件的默认路径"""
        project_root = Path(__file__).parent.parent
        config_file = project_root / "config" / filename
        if config_file.exists():
            return str(config_file)
        
        # 尝试其他常见配置文件
        alternatives = ["test_config.yaml", "router_config.yaml.template"]
        for alt in alternatives:
            alt_file = project_root / "config" / alt
            if alt_file.exists():
                logger.warning(f"Using fallback config: {alt}")
                return str(alt_file)

        raise FileNotFoundError(f"Configuration file {filename} not found in 'config' directory.")

    def _load_and_validate_config(self) -> Config:
        """加载并验证配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                raw_data = yaml.safe_load(f) or {}
            
            # 检查Token配置并自动生成
            config_modified = self._ensure_auth_token(raw_data)
            
            # 使用Pydantic进行验证和解析
            config = Config.parse_obj(raw_data)
            
            # 如果配置被修改，保存回文件
            if config_modified:
                self._save_config_to_file(raw_data)
                
            return config
            
        except Exception as e:
            logger.error(f"Failed to load config from {self.config_path}: {e}")
            raise

    def _ensure_auth_token(self, config_data: Dict[str, Any]) -> bool:
        """
        确保认证配置中有Token，如果启用认证但没有Token则自动生成
        
        Returns:
            bool: 如果配置被修改则返回True
        """
        auth_config = config_data.get('auth', {})
        
        # 如果认证启用但没有api_token，自动生成
        if auth_config.get('enabled', False) and not auth_config.get('api_token'):
            new_token = generate_random_token()
            auth_config['api_token'] = new_token
            config_data['auth'] = auth_config
            
            logger.info(f"Auto-generated API token for authentication: {new_token}")
            logger.warning("Please save this token! You will need it to access the API.")
            
            return True
            
        return False

    def _save_config_to_file(self, config_data: Dict[str, Any]) -> None:
        """
        保存配置数据到文件
        """
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(
                    config_data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    indent=2
                )
            logger.info(f"Configuration updated and saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save config to {self.config_path}: {e}")
            raise

    def _load_model_cache_from_disk(self):
        """从磁盘加载模型发现任务的缓存"""
        try:
            # 直接从缓存文件加载
            cache_file = Path(__file__).parent.parent / "cache" / "discovered_models.json"
            if cache_file.exists():
                with open(cache_file, 'r', encoding='utf-8') as f:
                    self.model_cache = json.load(f)
                    logger.info(f"Loaded model cache for {len(self.model_cache)} channels")
            else:
                logger.warning("Model cache file not found")
        except Exception as e:
            # 作为后备方案，尝试从任务模块加载
            try:
                from .scheduler.tasks.model_discovery import get_model_discovery_task
                task = get_model_discovery_task()
                self.model_cache = task.cached_models
                if self.model_cache:
                    logger.info(f"Loaded model cache from task for {len(self.model_cache)} channels")
            except Exception as e2:
                logger.warning(f"Failed to load model cache from both sources: {e}, {e2}")
                self.model_cache = {}

    def get_enabled_channels(self) -> List[Channel]:
        """获取所有启用的渠道"""
        return [ch for ch in self.config.channels if ch.enabled]

    def get_channels_by_model(self, model_name: str) -> List[Channel]:
        """根据模型名称获取渠道"""
        return [ch for ch in self.get_enabled_channels() if ch.model_name == model_name]

    def get_channels_by_tag(self, tag: str) -> List[Channel]:
        """根据标签获取渠道"""
        return [ch for ch in self.get_enabled_channels() if tag in ch.tags]

    def get_model_cache(self) -> Dict[str, Dict]:
        """获取模型缓存"""
        return self.model_cache
    
    def update_model_cache(self, new_cache: Dict[str, Dict]):
        """更新模型缓存"""
        self.model_cache = new_cache
        logger.info(f"Updated model cache with {len(new_cache)} channels")

    def update_channel_health(self, channel_id: str, success: bool, latency: Optional[float] = None):
        """更新渠道健康状态"""
        current_health = self.runtime_state.health_scores.get(channel_id, 1.0)
        
        if success:
            new_health = min(1.0, current_health * 1.01 + 0.01)
        else:
            new_health = max(0.0, current_health * 0.9 - 0.1)
        
        self.runtime_state.health_scores[channel_id] = new_health
        
        # 更新统计信息
        if success and latency is not None:
            if channel_id not in self.runtime_state.channel_stats:
                self.runtime_state.channel_stats[channel_id] = {
                    "request_count": 0,
                    "total_latency": 0.0,
                    "avg_latency_ms": 0.0
                }
            
            stats = self.runtime_state.channel_stats[channel_id]
            stats["total_latency"] = stats.get("total_latency", 0.0) + latency
            stats["request_count"] = stats.get("request_count", 0) + 1
            stats["avg_latency_ms"] = (stats["total_latency"] * 1000) / stats["request_count"]
        
        if new_health < 0.3:
            logger.warning(f"Channel {channel_id} health score is low: {new_health:.3f}")

    def get_server_config(self) -> Dict[str, Any]:
        """获取服务器配置"""
        return {
            "host": self.config.server.host,
            "port": self.config.server.port,
            "debug": self.config.server.debug,
            "cors_origins": self.config.server.cors_origins
        }

    def get_routing_config(self) -> Dict[str, Any]:
        """获取路由配置"""
        return {
            "default_strategy": self.config.routing.default_strategy,
            "enable_fallback": self.config.routing.enable_fallback,
            "max_retry_attempts": self.config.routing.max_retry_attempts
        }

    def get_tasks_config(self) -> Dict[str, Any]:
        """获取任务配置"""
        return {
            "model_discovery": {
                "enabled": self.config.tasks.model_discovery.enabled,
                "interval_hours": self.config.tasks.model_discovery.interval_hours,
                "run_on_startup": self.config.tasks.model_discovery.run_on_startup
            },
            "pricing_discovery": {
                "enabled": self.config.tasks.pricing_discovery.enabled,
                "interval_hours": self.config.tasks.pricing_discovery.interval_hours,
                "run_on_startup": self.config.tasks.pricing_discovery.run_on_startup
            },
            "health_check": {
                "enabled": self.config.tasks.health_check.enabled,
                "interval_minutes": self.config.tasks.health_check.interval_minutes,
                "run_on_startup": self.config.tasks.health_check.run_on_startup
            },
            "api_key_validation": {
                "enabled": self.config.tasks.api_key_validation.enabled,
                "interval_hours": self.config.tasks.api_key_validation.interval_hours,
                "run_on_startup": self.config.tasks.api_key_validation.run_on_startup
            }
        }

    def get_system_config(self) -> Dict[str, Any]:
        """获取系统配置"""
        return {
            "name": self.config.system.name,
            "version": self.config.system.version,
            "storage_mode": self.config.system.storage_mode
        }

    def get_provider(self, provider_name: str) -> Optional[Provider]:
        """根据名称获取Provider配置"""
        provider = self.config.providers.get(provider_name)
        if provider:
            return provider
        
        # 如果找不到provider，返回一个默认的OpenAI兼容配置
        logger.warning(f"Provider '{provider_name}' not found, using default OpenAI-compatible config")
        return Provider(
            name=provider_name,
            display_name=provider_name.title(),
            adapter_class="OpenAIAdapter",
            base_url="https://api.openai.com",
            auth_type="bearer",
            rate_limit=60,
            capabilities=["text", "function_calling"]
        )

    def get_enabled_channels(self) -> List[Channel]:
        """获取所有启用的渠道"""
        return [ch for ch in self.config.channels if ch.enabled]

    @property
    def config_data(self) -> Dict[str, Any]:
        """为兼容性提供config_data属性"""
        return {
            "system": self.get_system_config(),
            "server": self.get_server_config(),
            "providers": {k: v.dict() for k, v in self.config.providers.items()},
            "channels": [ch.dict() for ch in self.config.channels],
            "routing": self.get_routing_config(),
            "tasks": self.get_tasks_config()
        }

# 全局配置加载器实例
_yaml_config_loader: Optional[YAMLConfigLoader] = None

def get_yaml_config_loader() -> YAMLConfigLoader:
    """获取全局YAML配置加载器实例"""
    global _yaml_config_loader
    if _yaml_config_loader is None:
        _yaml_config_loader = YAMLConfigLoader()
    return _yaml_config_loader