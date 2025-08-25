# -*- coding: utf-8 -*-
"""
Pydantic models for configuration validation.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

class Provider(BaseModel):
    name: str
    display_name: str = ""
    adapter_class: str
    base_url: str
    auth_type: str = "bearer"
    rate_limit: int = 60
    capabilities: List[str] = []

class Channel(BaseModel):
    id: str
    name: str
    provider: str
    model_name: str
    api_key: str
    base_url: Optional[str] = None
    enabled: bool = True
    priority: int = 1
    weight: float = 1.0
    daily_limit: int = 1000
    capabilities: List[str] = []
    
    # Channel-level tags that apply to all models in this channel
    tags: List[str] = Field(default_factory=list)
    
    # Configured models list for fallback when /models API fails
    configured_models: Optional[List[str]] = Field(default=None)
    
    # Cost per token
    cost_per_token: Optional[Dict[str, float]] = Field(default_factory=dict)
    
    # Model name aliases mapping: standard_name -> channel_specific_name
    # Example: {"deepseek-v3.1": "deepseek-chat", "doubao-1.5-pro-256k": "ep-20250203083646-2szv9"}
    model_aliases: Optional[Dict[str, str]] = Field(default=None)
    
    # performance and pricing are optional dictionaries  
    performance: Dict[str, float] = Field(default_factory=dict)
    pricing: Dict[str, Any] = Field(default_factory=dict)
    
    # Currency exchange configuration for special pricing providers
    # Example: {"currency_exchange": {"from": "USD", "to": "CNY", "rate": 0.7, "description": "充值0.7人民币获得1美元"}}
    currency_exchange: Optional[Dict[str, Any]] = Field(default=None)
    
    # Rate limiting configuration
    min_request_interval: int = Field(default=0, description="Minimum seconds between requests (0 = no limit)")  # 最小请求间隔(秒)

class Routing(BaseModel):
    default_strategy: str = "balanced"
    enable_fallback: bool = True
    max_retry_attempts: int = 3
    health_check_interval: int = 300
    error_cooldown_period: int = 60

class TaskConfig(BaseModel):
    enabled: bool = True
    interval_hours: Optional[int] = None
    interval_minutes: Optional[int] = None
    run_on_startup: bool = False
    max_concurrent_validations: Optional[int] = None
    max_concurrent_checks: Optional[int] = None

class Tasks(BaseModel):
    model_discovery: TaskConfig = Field(default_factory=TaskConfig)
    pricing_discovery: TaskConfig = Field(default_factory=TaskConfig)
    health_check: TaskConfig = Field(default_factory=TaskConfig)
    api_key_validation: TaskConfig = Field(default_factory=TaskConfig)

class Server(BaseModel):
    host: str = "0.0.0.0"
    port: int = 7601
    debug: bool = False
    cors_origins: List[str] = ["*"]
    request_timeout: int = 300
    max_request_size: int = 10485760

class AdminAuth(BaseModel):
    """管理API独立认证配置"""
    enabled: bool = True
    admin_token: Optional[str] = None

class Auth(BaseModel):
    enabled: bool = False
    api_token: Optional[str] = None
    admin: AdminAuth = Field(default_factory=AdminAuth)

class System(BaseModel):
    name: str = "Smart AI Router"
    version: str = "0.3.0" # Bump version for this change
    storage_mode: str = "yaml"

class Config(BaseModel):
    system: System = Field(default_factory=System)
    server: Server = Field(default_factory=Server)
    auth: Auth = Field(default_factory=Auth)
    providers: Dict[str, Provider]
    channels: List[Channel]
    routing: Routing = Field(default_factory=Routing)
    tasks: Tasks = Field(default_factory=Tasks)

    # Allow extra fields for things like cost_control, monitoring etc.
    class Config:
        extra = "allow"
