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
uv run uvicorn main:app --host 0.0.0.0 --port 7601 --reload

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
# Build and run with Docker Compose (推荐)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop service
docker-compose down

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
- `core/config_models.py` - Pydantic数据模型 (providers, channels等)
- `core/json_router.py` - 智能路由引擎，支持标签化和多层排序策略
- `core/yaml_config.py` - 基于Pydantic的YAML配置加载器
- `core/scheduler/` - 定时任务系统 (模型发现、价格更新、健康检查、API密钥验证)
- `core/utils/` - 工具模块 (API密钥验证、日志等)
- `api/` - FastAPI路由接口
- `config/` - 配置文件目录
- `cache/` - 缓存目录 (模型发现、API密钥验证结果等)

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

## 🏷️ 智能标签系统 (Tag-Based Routing)

### 核心概念
Smart AI Router 现在使用**基于模型名称的自动标签化系统**，完全替代了传统的 Model Groups 概念。

### 标签提取机制
系统会自动从模型名称中提取标签，使用多种分隔符进行拆分：`:`, `/`, `@`, `-`, `_`, `,`

**示例**:
```
qwen/qwen3-30b-a3b:free -> ["qwen", "qwen3", "30b", "a3b", "free"]
openai/gpt-4o-mini -> ["openai", "gpt", "4o", "mini"]  
anthropic/claude-3-haiku:free -> ["anthropic", "claude", "3", "haiku", "free"]
moonshot-v1-128k -> ["moonshot", "v1", "128k"]
free,gemma,270m -> ["free", "gemma", "270m"]
```

### 标签查询方式

#### 1. 单标签查询
```bash
curl -X POST http://localhost:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tag:gpt",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

#### 2. 多标签组合查询
```bash
curl -X POST http://localhost:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tag:qwen,free",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### 标签优势
- **自动化**: 无需手动配置标签，从模型名称自动提取
- **灵活性**: 支持任意标签组合查询
- **可扩展**: 新模型自动获得相应标签
- **智能匹配**: 系统自动找到包含所有指定标签的模型

### 常见标签示例
- **提供商标签**: `gpt`, `claude`, `qwen`, `gemini`, `llama`
- **模型规格**: `mini`, `turbo`, `pro`, `max`, `4o`, `3.5`
- **定价标签**: `free`, `pro`, `premium`
- **功能标签**: `chat`, `instruct`, `vision`, `code`

### API Endpoints
- **Chat API**: `/v1/chat/completions` (OpenAI-compatible)
- **Models API**: `/v1/models` (list all available models and tags)
- **Health Check**: `/health`
- **Admin Interface**: `/admin/*`
- **Documentation**: `/docs` (FastAPI auto-generated)

## Development Patterns

### 标签化路由配置
标签系统无需额外配置文件，完全基于模型发现的结果：
- **自动标签提取**: 从已发现的模型名称中自动提取标签
- **多层路由策略**: 支持多因子组合排序 (cost_score, speed_score, quality_score, reliability_score)
- **智能匹配**: 根据标签组合自动找到合适的渠道
- **实时更新**: 新发现的模型会自动更新可用标签列表

### Error Handling Philosophy
- **Permanent errors**: Immediately disable channel (quota_exceeded, invalid_api_key)
- **Temporary errors**: Apply cooldown period (rate_limit_exceeded, timeout)
- **Smart recovery**: Automatic re-enabling after cooldown periods

### Cost Optimization Features
- **智能模型分析**: 自动提取模型参数数量(270m-670b)和上下文长度(2k-2m)，基于三层优先级智能评分
- **可配置排序策略**: 支持cost_first、balanced、speed_optimized、quality_optimized四种路由策略
- **模型过滤器**: 支持最小参数量、最小上下文长度、排除embedding模型等过滤条件
- **渠道分离缓存**: 每个渠道独立缓存模型分析结果，便于调试和管理

### Planned Cost Optimization (Phase 7)
- **免费资源最大化**: 免费优先路由策略、配额监控、API密钥轮换机制
- **本地模型优先**: 本地优先模式、能力检测、集群负载均衡
- **智能成本控制**: 实时成本追踪、Token预估、成本感知路由
- **使用体验优化**: 成本透明化、使用建议、个性化配置助手
- **预期收益**: 预计可节省70-90%的API费用，最大化利用免费额度和本地资源

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

Current implementation status (Phase 1-6 完成):
- ✅ Project structure and FastAPI setup
- ✅ 基于Pydantic的配置系统架构
- ✅ **智能标签化路由系统** (Tag-Based Routing)
- ✅ **智能模型分析与排序系统** (智能参数提取、可配置策略、模型过滤器)
- ✅ **渠道分离缓存架构** (每个渠道独立缓存，包含模型分析结果)
- ✅ 模型发现和缓存系统
- ✅ **API密钥验证和自动失效检测系统**
- ✅ 定时任务系统 (模型发现、API密钥验证、健康检查等)
- ✅ 多层路由引擎 (成本、参数数量、上下文长度、速度评分)
- ✅ Provider适配器架构
- ✅ 实时健康监控和统计
- ✅ Docker配置和部署支持
- ✅ 完整的错误处理和故障转移机制

Planned for Phase 7 (个人使用成本优化):
- 🎯 **免费资源最大化**: 免费优先路由策略、配额监控、API密钥轮换
- 🎯 **本地模型优先**: 本地优先模式、能力检测、集群负载均衡
- 🎯 **智能成本控制**: 实时成本追踪、Token预估、成本感知路由
- 🎯 **使用体验优化**: 成本透明化、使用建议、个性化配置

Future considerations:
- 📱 Web管理界面 (用于动态配置管理)
- 🗃️ 数据库集成 (当前使用高效的YAML+文件系统)

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