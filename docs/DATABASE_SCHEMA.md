# 数据库架构设计

## 设计原则
- **配置与数据分离**：静态系统配置在YAML，动态业务数据在数据库
- **支持大规模**：可管理数百个渠道和API key
- **动态管理**：支持实时添加/编辑/禁用，无需重启
- **监控友好**：内置统计和健康状态追踪

## 核心数据表

### 1. providers (提供商表)
```sql
CREATE TABLE providers (
    id INTEGER PRIMARY KEY,
    name VARCHAR(50) NOT NULL,           -- openai, anthropic, azure 等
    type VARCHAR(20) NOT NULL,           -- 提供商类型
    base_endpoint VARCHAR(200),          -- 基础API端点
    default_headers JSON,                -- 默认请求头
    status VARCHAR(20) DEFAULT 'active', -- active, disabled
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. channels (渠道表) 
```sql
CREATE TABLE channels (
    id INTEGER PRIMARY KEY,
    provider_id INTEGER REFERENCES providers(id),
    name VARCHAR(100) NOT NULL,          -- 渠道友好名称
    model_name VARCHAR(50) NOT NULL,     -- gpt-4o, claude-3-5-sonnet 等
    endpoint VARCHAR(300),               -- 完整API端点
    priority INTEGER DEFAULT 1,         -- 优先级 (1=最高)
    weight INTEGER DEFAULT 1,           -- 负载均衡权重
    
    -- 成本配置 (可动态更新)
    input_cost_per_1k DECIMAL(10,4),   -- 输入成本 $/1K tokens
    output_cost_per_1k DECIMAL(10,4),  -- 输出成本 $/1K tokens
    
    -- 每日限额管理
    daily_request_limit INTEGER DEFAULT 1000,  -- 每日请求限额
    daily_request_count INTEGER DEFAULT 0,     -- 当日已使用数量
    quota_reset_date DATE,                     -- 配额重置日期
    
    -- 运行状态
    status VARCHAR(20) DEFAULT 'active', -- active, disabled, cooling, quota_exceeded
    health_score DECIMAL(3,2) DEFAULT 1.0, -- 0.0-1.0 健康度
    last_success_at TIMESTAMP,
    last_error_at TIMESTAMP,
    cooldown_until TIMESTAMP,           -- 冷却结束时间
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3. api_keys (API密钥表)
```sql
CREATE TABLE api_keys (
    id INTEGER PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    key_name VARCHAR(100),               -- 密钥友好名称
    key_value VARCHAR(500) NOT NULL,     -- 加密存储的API key
    
    -- 使用状态
    status VARCHAR(20) DEFAULT 'active', -- active, disabled, exhausted
    last_used_at TIMESTAMP,
    usage_count INTEGER DEFAULT 0,
    
    -- 配额管理
    daily_quota DECIMAL(10,2),          -- 每日配额 ($)
    monthly_quota DECIMAL(10,2),        -- 月度配额 ($)
    remaining_quota DECIMAL(10,2),      -- 剩余配额
    quota_reset_at TIMESTAMP,           -- 配额重置时间
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4. virtual_model_groups (模型组表)
```sql
CREATE TABLE virtual_model_groups (
    id INTEGER PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,   -- auto:free, auto:fast, auto:smart, auto:cheap
    display_name VARCHAR(100),          -- 免费模型组, 快速模型组
    description TEXT,                   -- 模型组描述
    
    -- 多层路由策略配置 (JSON字段)
    routing_strategy JSON,              -- 多层路由策略数组
    filters JSON,                       -- 模型筛选条件
    budget_limits JSON,                 -- 预算限制配置
    time_policies JSON,                 -- 时间策略配置
    load_balancing JSON,                -- 负载均衡配置
    
    -- 模型组状态
    status VARCHAR(20) DEFAULT 'active', -- active, disabled, maintenance
    priority INTEGER DEFAULT 100,      -- 优先级 (数字越小优先级越高)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### JSON字段说明

**routing_strategy (路由策略)**
```json
[
  {
    "field": "effective_cost",
    "order": "asc", 
    "weight": 1.0
  },
  {
    "field": "speed_score",
    "order": "desc",
    "weight": 0.9
  }
]
```

**filters (筛选条件)**
```json
{
  "max_cost_per_1k": 5.0,
  "min_quality_score": 0.7,
  "required_capabilities": ["function_calling", "vision"],
  "optional_capabilities": ["code_generation"],
  "exclude_models": ["gpt-3.5-turbo"],
  "min_context_length": 4000,
  "max_latency_ms": 3000,
  "supports_streaming": true
}
```

**budget_limits (预算限制)**
```json
{
  "daily_budget": 20.0,
  "max_cost_per_request": 2.0
}
```

### 5. model_group_channels (模型组-渠道映射表)
```sql
CREATE TABLE model_group_channels (
    model_group_id INTEGER REFERENCES virtual_model_groups(id),
    channel_id INTEGER REFERENCES channels(id),
    priority INTEGER DEFAULT 1,         -- 在该模型组中的优先级
    weight DECIMAL(3,2) DEFAULT 1.0,    -- 负载均衡权重
    daily_limit INTEGER DEFAULT 1000,   -- 在此模型组中的每日限额
    
    -- 性能评分和能力配置
    speed_score DECIMAL(3,2) DEFAULT 1.0,      -- 速度评分 (0.0-1.0)
    quality_score DECIMAL(3,2) DEFAULT 1.0,    -- 质量评分 (0.0-1.0)
    reliability_score DECIMAL(3,2) DEFAULT 1.0, -- 可靠性评分 (0.0-1.0)
    capabilities JSON,                          -- 渠道特定能力覆盖
    overrides JSON,                            -- 模型组特定配置覆盖
    
    enabled BOOLEAN DEFAULT true,       -- 是否在此模型组中启用
    
    PRIMARY KEY (model_group_id, channel_id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### JSON字段说明

**capabilities (能力覆盖)**
```json
{
  "function_calling": true,
  "vision": false,
  "code_generation": true,
  "chinese_optimized": true,
  "max_context_length": 32000,
  "supports_streaming": true
}
```

**overrides (配置覆盖)**
```json
{
  "speed_score": 0.95,
  "quality_score": 0.9,
  "effective_cost_multiplier": 0.8,
  "custom_endpoint": "/v1/chat/completions",
  "timeout_ms": 5000
}
```

### 6. request_logs (请求日志表)
```sql
CREATE TABLE request_logs (
    id INTEGER PRIMARY KEY,
    request_id VARCHAR(50),              -- 请求唯一ID
    model_group_name VARCHAR(50),        -- 使用的模型组名称
    channel_id INTEGER REFERENCES channels(id),
    api_key_id INTEGER REFERENCES api_keys(id),
    client_api_key_id INTEGER REFERENCES router_api_keys(id),
    
    -- 请求详情
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    request_size INTEGER,               -- 请求体大小
    response_size INTEGER,              -- 响应体大小
    
    -- 成本和性能
    estimated_cost DECIMAL(10,4),       -- 预估成本
    actual_cost DECIMAL(10,4),          -- 实际成本
    effective_cost DECIMAL(10,4),       -- 考虑倍率后的有效成本
    latency_ms INTEGER,                 -- 响应延迟(毫秒)
    ttft_ms INTEGER,                    -- Time to First Token (毫秒)
    throughput_tps DECIMAL(6,2),        -- 吞吐量 tokens/second
    
    -- 路由决策信息
    routing_strategy_used JSON,         -- 使用的路由策略
    routing_scores JSON,                -- 各渠道的评分
    fallback_attempts INTEGER DEFAULT 0, -- 故障转移尝试次数
    
    -- 结果状态
    status VARCHAR(20),                 -- success, error, timeout
    error_code VARCHAR(50),             -- 错误代码
    error_message TEXT,                 -- 错误信息
    error_type VARCHAR(20),             -- 错误类型: permanent, temporary, rate_limit
    
    -- 请求特征
    has_function_calls BOOLEAN DEFAULT false, -- 是否包含工具调用
    has_images BOOLEAN DEFAULT false,         -- 是否包含图片
    stream_enabled BOOLEAN DEFAULT false,     -- 是否启用流式
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### JSON字段说明

**routing_strategy_used (使用的路由策略)**
```json
{
  "strategy_name": "auto:fast",
  "primary_factors": ["speed_score", "effective_cost"],
  "weights": {
    "speed_score": 1.0,
    "effective_cost": 0.3
  }
}
```

**routing_scores (各渠道评分)**
```json
{
  "channel_123": {
    "total_score": 0.85,
    "speed_score": 0.9,
    "cost_score": 0.8,
    "health_score": 0.9,
    "selected": true
  },
  "channel_124": {
    "total_score": 0.78,
    "selected": false
  }
}
```

### 7. channel_stats (渠道统计表)
```sql
CREATE TABLE channel_stats (
    id INTEGER PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    date DATE NOT NULL,                 -- 统计日期
    hour INTEGER,                       -- 小时(0-23, NULL表示全天统计)
    
    -- 请求统计
    request_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    timeout_count INTEGER DEFAULT 0,
    rate_limit_count INTEGER DEFAULT 0,
    
    -- 性能统计  
    total_tokens INTEGER DEFAULT 0,
    total_cost DECIMAL(10,4) DEFAULT 0,
    avg_latency_ms INTEGER DEFAULT 0,
    min_latency_ms INTEGER DEFAULT 0,
    max_latency_ms INTEGER DEFAULT 0,
    avg_ttft_ms INTEGER DEFAULT 0,      -- 平均首字延迟
    avg_throughput_tps DECIMAL(6,2) DEFAULT 0, -- 平均吞吐量
    
    -- 质量统计
    success_rate DECIMAL(5,4) DEFAULT 0.0,     -- 成功率 (0.0-1.0)
    error_rate DECIMAL(5,4) DEFAULT 0.0,       -- 错误率
    timeout_rate DECIMAL(5,4) DEFAULT 0.0,     -- 超时率
    
    -- 评分计算 (0.0-1.0)
    speed_score DECIMAL(3,2) DEFAULT 1.0,      -- 速度评分
    reliability_score DECIMAL(3,2) DEFAULT 1.0, -- 可靠性评分
    cost_efficiency DECIMAL(3,2) DEFAULT 1.0,   -- 性价比评分
    overall_health_score DECIMAL(3,2) DEFAULT 1.0, -- 综合健康评分
    
    -- 详细错误统计
    error_breakdown JSON,               -- 错误类型分解统计
    
    UNIQUE(channel_id, date, hour),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### JSON字段说明

**error_breakdown (错误分解统计)**
```json
{
  "quota_exceeded": 15,
  "rate_limit": 8,
  "timeout": 5,
  "invalid_api_key": 2,
  "server_error": 3,
  "network_error": 1
}
```

### 8. router_api_keys (路由器API密钥表)
```sql
CREATE TABLE router_api_keys (
    id INTEGER PRIMARY KEY,
    key_hash VARCHAR(64) NOT NULL UNIQUE,  -- API key 哈希
    key_name VARCHAR(100),                 -- 密钥名称
    
    -- 权限配置
    allowed_model_groups JSON,             -- 允许访问的模型组
    daily_budget DECIMAL(10,2),           -- 每日预算限制
    monthly_budget DECIMAL(10,2),         -- 月度预算限制
    rate_limit VARCHAR(20),               -- 速率限制 "100/hour"
    role VARCHAR(20) DEFAULT 'user',      -- admin, user
    
    -- 使用统计
    last_used_at TIMESTAMP,
    request_count INTEGER DEFAULT 0,
    total_cost DECIMAL(10,4) DEFAULT 0,
    
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 数据管理优势

### 1. 可扩展性
- 支持数百个渠道和数千个API key
- 每个渠道可以有多个API key进行轮换
- 模型组可以包含任意数量的不同厂商渠道
- 支持每个渠道的每日请求限额独立配置

### 2. 动态配置
- 通过管理界面实时添加/编辑渠道和模型组
- 动态调整权重、优先级、成本、限额配置
- 实时修改模型组的渠道组合和路由策略
- 无需重启服务即可生效

### 3. 智能管理
- API key自动轮换和故障转移
- 基于每日限额的渠道管理和自动切换
- 渠道健康状态实时监控和评分
- 模型组内智能路由选择（成本/速度/优先级）

### 4. 成本控制
- 多层次预算控制(模型组、用户、全局)
- 实时成本追踪和告警
- 详细的成本分析报告
- 自动成本优化路由选择

### 5. 监控与运维
- 详细的请求日志和统计
- 渠道性能监控和评分
- 错误分析和自动恢复