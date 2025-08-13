# 项目目录结构说明

## 完整目录结构

```
smart-ai-router/
├── 📁 api/                          # FastAPI路由接口
│   ├── __init__.py
│   ├── admin.py                     # 管理员接口
│   ├── chat.py                      # OpenAI兼容聊天接口
│   ├── health.py                    # 健康检查接口
│   └── management.py                # 动态配置管理接口
│
├── 📁 config/                       # 分层配置文件
│   ├── example.yaml                 # 主配置文件模板
│   ├── providers.yaml               # Provider配置 (OpenAI、Anthropic等)
│   ├── model_groups.yaml           # Model Group配置 (auto:free等)
│   ├── system.yaml                 # 系统配置 (监控、定时任务等)
│   └── pricing_policies.yaml       # 动态价格策略
│
├── 📁 core/                         # 核心功能模块
│   ├── __init__.py
│   │
│   ├── 📁 models/                   # SQLAlchemy数据模型
│   │   ├── __init__.py              # 导出所有模型
│   │   ├── base.py                  # 基础配置和会话管理
│   │   ├── provider.py              # Provider表模型
│   │   ├── channel.py               # Channel表模型
│   │   ├── model_group.py           # Model Group相关表模型
│   │   ├── api_key.py               # API密钥相关表模型
│   │   └── stats.py                 # 统计和日志表模型
│   │
│   ├── 📁 router/                   # 智能路由引擎
│   │   ├── __init__.py
│   │   └── 📁 strategies/           # 路由策略实现
│   │       ├── __init__.py          # 导出所有策略
│   │       ├── base.py              # 基础策略接口
│   │       ├── multi_layer.py       # 多层路由策略
│   │       ├── cost_strategy.py     # 成本优化策略
│   │       ├── speed_strategy.py    # 速度优化策略
│   │       ├── quality_strategy.py  # 质量优化策略
│   │       ├── load_balance_strategy.py # 负载均衡策略
│   │       └── capability_filter.py # 能力筛选器
│   │
│   ├── 📁 providers/                # Provider适配器
│   │   ├── __init__.py
│   │   └── 📁 adapters/             # 各Provider适配器实现
│   │       ├── __init__.py          # 导出所有适配器
│   │       ├── base.py              # 基础适配器接口
│   │       ├── openai_adapter.py    # OpenAI适配器
│   │       ├── anthropic_adapter.py # Anthropic适配器
│   │       ├── groq_adapter.py      # Groq适配器
│   │       ├── openrouter_adapter.py # OpenRouter适配器
│   │       ├── siliconflow_adapter.py # 硅基流动适配器
│   │       └── tuzi_adapter.py      # 兔子API适配器
│   │
│   ├── 📁 manager/                  # 业务管理器
│   │   ├── __init__.py
│   │   ├── channel_manager.py       # 渠道管理器
│   │   ├── model_group_manager.py   # 模型组管理器
│   │   ├── api_key_manager.py       # API密钥管理器
│   │   └── cost_manager.py          # 成本管理器
│   │
│   ├── 📁 scheduler/                # 定时任务系统
│   │   ├── __init__.py              # 导出任务和调度器
│   │   ├── scheduler.py             # 任务调度器
│   │   └── jobs.py                  # 各种定时任务实现
│   │
│   └── 📁 utils/                    # 工具函数
│       ├── __init__.py
│       ├── config.py                # 配置加载器
│       ├── logger.py                # 日志配置
│       ├── security.py              # 安全工具
│       └── validation.py            # 数据验证
│
├── 📁 web/                          # Web管理界面 (可选)
│   ├── 📁 static/                   # 静态资源
│   └── 📁 templates/                # 模板文件
│
├── 📁 tests/                        # 测试文件
│   ├── test_api/                    # API测试
│   ├── test_core/                   # 核心功能测试
│   ├── test_integration/            # 集成测试
│   └── conftest.py                  # 测试配置
│
├── 📁 migrations/                   # 数据库迁移
│   └── versions/                    # 迁移版本文件
│
├── 📁 logs/                         # 日志文件目录
│
├── 📁 docs/                         # 项目文档
│   ├── api.md                       # API文档
│   ├── deployment.md                # 部署指南
│   └── development.md               # 开发指南
│
├── 📄 main.py                       # 应用入口点
├── 📄 pyproject.toml                # Python项目配置
├── 📄 requirements.txt              # 依赖列表
├── 📄 uv.lock                       # UV锁定文件
├── 📄 Dockerfile                    # Docker配置
├── 📄 docker-compose.yml            # Docker Compose配置
├── 📄 .env.example                  # 环境变量模板
├── 📄 .gitignore                    # Git忽略文件
├── 📄 README.md                     # 项目说明
├── 📄 CLAUDE.md                     # Claude开发指南
├── 📄 DATABASE_SCHEMA.md            # 数据库架构文档
└── 📄 DEVELOPMENT.md                # 开发文档
```

## 核心架构说明

### 🏗️ Provider/Channel/Model Group 三层架构

1. **Provider层**: AI服务提供商 (OpenAI、Anthropic等)
2. **Channel层**: 具体的API端点配置 (模型、密钥、限额等)  
3. **Model Group层**: 统一的模型组合 (auto:free、auto:fast等)

### 📊 数据模型关系

- **providers** ← **channels** ← **api_keys**
- **virtual_model_groups** ←→ **model_group_channels** ←→ **channels**
- **request_logs** → **channels**, **api_keys**, **router_api_keys**
- **channel_stats** → **channels**

### 🎯 配置管理策略

- **静态配置**: YAML文件 (系统设置、Provider定义、Model Group模板)
- **动态配置**: 数据库 (渠道、API密钥、实时统计)
- **环境变量**: 系统密钥和连接信息

### 🚀 核心特性实现

1. **多层路由策略**: `core/router/strategies/`
2. **Provider适配器**: `core/providers/adapters/`  
3. **定时任务系统**: `core/scheduler/`
4. **动态配置管理**: `api/management.py`
5. **智能故障处理**: 集成在路由引擎中

## 开发工作流程

1. **配置**: 编辑 `config/*.yaml` 定义Provider和Model Group
2. **适配器**: 实现 `core/providers/adapters/` 中的Provider适配器
3. **路由策略**: 扩展 `core/router/strategies/` 中的路由算法
4. **管理接口**: 完善 `api/management.py` 的动态配置功能
5. **监控**: 实现 `core/scheduler/` 中的定时任务

## 部署架构

- **开发环境**: SQLite + 内存缓存
- **生产环境**: PostgreSQL + Redis + 负载均衡
- **容器化**: Docker + Docker Compose
- **监控**: 内置健康检查 + 外部监控集成