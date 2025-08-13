# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Smart AI Router is a lightweight personal AI intelligent routing system based on Provider/Channel/Model Group architecture (similar to OpenRouter's auto model concept). The system provides cost optimization, intelligent routing, and fault tolerance for AI API requests through:

- **Provider**: AI service providers (OpenAI, Anthropic, Groq, etc.) with adapter classes
- **Channel**: Specific API endpoints under providers with API keys and daily quotas  
- **Model Group**: Unified model collections (like `auto:free`, `auto:fast`) that combine channels from different providers with multi-layer routing strategies

## Development Commands

### Environment Setup
```bash
# Install dependencies using uv package manager
uv sync

# Copy configuration files
copy .env.example .env
copy config\example.yaml config\config.yaml

# Activate virtual environment (if needed)
.venv\Scripts\activate  # Windows
```

### Development Server
```bash
# Development mode with auto-reload
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Direct run (production mode)
uv run python main.py

# Quick development run
python main.py
```

### Code Quality & Testing
```bash
# Code formatting
uv run black .
uv run isort .

# Code linting and type checking
uv run ruff check .
uv run mypy .

# Run tests
uv run pytest

# Run tests with specific markers
uv run pytest -m unit
uv run pytest -m integration
```

### Docker Development
```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Build standalone image
docker build -t smart-ai-router .
```

## Architecture Overview

### Core Design Philosophy
**Configuration vs Data Separation**: Static system settings in YAML, dynamic business data in database.

### Core Structure
- **Provider/Channel/Model Group三层架构**: 参考OpenRouter auto模型的设计理念
- **多层路由策略**: 支持成本、速度、质量、可靠性等多因子组合排序
- **能力筛选系统**: 支持function_calling、vision、code_generation等能力过滤
- **动态价格策略**: 时间段、配额使用率、需求等多维度价格调整
- **Provider适配器**: 支持官方/聚合/转售商等不同类型Provider
- **实时配置管理**: 数据库驱动，支持动态添加渠道和密钥
- **智能故障处理**: 错误分类、熔断器、自动冷却恢复

### Key Directories
- `core/models/` - SQLAlchemy数据模型 (providers, channels, model_groups等)
- `core/router/` - 智能路由引擎，支持多层排序策略和能力筛选
- `core/providers/` - Provider适配器 (OpenAI、Anthropic、Groq等)
- `core/manager/` - 渠道、密钥、模型组管理器
- `core/scheduler/` - 定时任务系统 (模型发现、价格更新、健康检查)
- `api/` - FastAPI路由接口
- `config/` - 配置文件目录 (providers.yaml, model_groups.yaml等)

### Data Storage Architecture
- **Database Tables**: providers, channels, api_keys, virtual_model_groups, model_group_channels, request_logs, channel_stats
- **Dynamic Configuration**: All channels and API keys managed in database
- **Scalability**: Support for hundreds of channels and thousands of API keys
- **Real-time Updates**: Configuration changes without service restart

### Configuration System
- **分层配置文件结构**:
  - `config/system.yaml` - 系统级配置 (服务器、数据库、监控、定时任务)
  - `config/providers.yaml` - Provider配置 (适配器、能力映射、定价)
  - `config/model_groups.yaml` - Model Group配置 (路由策略、筛选条件)
  - `config/pricing_policies.yaml` - 动态价格策略 (时间、配额、需求调整)
- **Environment Variables**: `.env` - 系统密钥 (JWT、数据库URL)
- **Dynamic Config**: 数据库管理的渠道、密钥、成本映射
- **Management Interface**: Web界面或API进行动态配置管理

### API Endpoints
- **Chat API**: `/v1/chat/completions` (OpenAI-compatible)
- **Models API**: `/v1/models` (list virtual models)
- **Health Check**: `/health`
- **Admin Interface**: `/admin/*`
- **Documentation**: `/docs` (FastAPI auto-generated)

## Development Patterns

### Model Group Configuration
Model groups are defined in `config/model_groups.yaml` with:
- **Multi-layer routing strategy**: 支持多因子组合排序 (effective_cost, speed_score, quality_score等)
- **Capability filtering**: 能力筛选 (function_calling, vision, code_generation等)
- **Budget controls**: 预算限制 (daily_budget, max_cost_per_request)
- **Time policies**: 时间策略 (高峰/非高峰时段的不同路由策略)
- **Channel configurations**: 渠道配置 (provider, model, priority, weight, daily_limit)

### Error Handling Philosophy
- **Permanent errors**: Immediately disable channel (quota_exceeded, invalid_api_key)
- **Temporary errors**: Apply cooldown period (rate_limit_exceeded, timeout)
- **Smart recovery**: Automatic re-enabling after cooldown periods

### Cost Optimization Features
- **Dynamic pricing policies**: 动态价格策略 (时间段、配额使用率、需求调整)
- **Multi-layer budget controls**: 多层预算控制 (Model Group、Channel、User等)
- **Real-time cost calculation**: 实时成本计算 (考虑平台倍率和汇率)
- **Intelligent channel selection**: 智能渠道选择 (基于effective_cost和多因子评分)
- **Comprehensive cost tracking**: 详细成本追踪和趋势分析

## Database & Dependencies

### Core Dependencies
- **FastAPI**: Web framework and API
- **SQLAlchemy + aiosqlite**: Async database with SQLite default (PostgreSQL for production)
- **Pydantic**: Data validation and settings
- **httpx**: HTTP client for provider requests
- **structlog**: Structured logging
- **PyYAML**: System configuration parsing only

### Database Architecture (8 Core Tables)
1. **providers** - Provider definitions (OpenAI, Anthropic, etc.)
2. **channels** - Individual API endpoints with cost/priority settings
3. **api_keys** - Encrypted key storage with quotas and rotation
4. **virtual_model_groups** - Model group definitions and routing strategies
5. **model_group_channels** - Many-to-many mappings with priorities and speed scores
6. **request_logs** - Detailed request tracking with costs and performance
7. **channel_stats** - Daily aggregated statistics and health scores
8. **router_api_keys** - Client API keys with permissions and budgets

## Environment Variables

**System-only** environment variables (see `.env.example`):
- **Security**: `JWT_SECRET`, `WEB_SECRET_KEY` - system authentication
- **Database**: `DATABASE_URL` - optional PostgreSQL connection
- **Caching**: `REDIS_URL` - optional Redis for caching
- **System**: `LOG_LEVEL`, `DEBUG` - system behavior

**Important**: Provider API keys are now managed in the database, not environment variables. This enables:
- Multiple keys per provider with automatic rotation
- Dynamic key management without restarts
- Per-key quota and usage tracking
- Secure encrypted storage

## Development Status

Current implementation status:
- ✅ Project structure and FastAPI setup
- ✅ 完整的分层配置架构 (providers.yaml, model_groups.yaml, system.yaml, pricing_policies.yaml)
- ✅ 增强的数据库架构设计 (支持Model Group概念和多层路由)
- ✅ 预定义的Model Group示例 (auto:free, auto:fast, auto:smart等)
- ✅ Provider配置完善 (OpenAI、Anthropic、Groq、硅基流动、OpenRouter等)
- ✅ 动态价格策略系统设计
- ✅ Docker配置
- ⏳ Database models and migrations (priority)
- ⏳ Channel and API key management system (priority)
- ⏳ Multi-layer routing engine implementation
- ⏳ Provider adapters with capability detection
- ⏳ Dynamic pricing and cost calculation
- ⏳ Scheduled tasks and monitoring system
- ⏳ Web management interface for dynamic configuration

## Testing Philosophy

Use real API data and scenarios when possible:
- Integration tests with actual provider APIs (when keys available)
- Real configuration files and scenarios
- Performance testing with actual latency measurements
- Cost calculation validation with real token counts

## Important Notes

### Data Management Philosophy
- **Database-First**: All business data (channels, keys, costs) in database, not config files
- **Dynamic Configuration**: Changes take effect immediately without restart
- **Scalable Design**: Support hundreds of channels and thousands of API keys
- **Security Focus**: Encrypted API key storage with rotation and quotas

### Development Priorities
1. **Database Layer**: Implement SQLAlchemy models and migrations first
2. **Management APIs**: Channel and key management endpoints
3. **Routing Engine**: Database-integrated intelligent routing
4. **Web Interface**: For dynamic configuration management

### Key Features
- All API requests logged with detailed cost and performance metrics
- Multi-key rotation per channel for resilience
- Real-time cost tracking and budget enforcement
- Intelligent health monitoring and automatic recovery
- Chinese/English bilingual support throughout system