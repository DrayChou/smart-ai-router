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
uv run uvicorn main:app --host 0.0.0.0 --port 7602 --reload

# Direct run (production mode) - use ports 7602-7610 for local dev
uv run python main.py --port 7602

# Quick development run
python main.py --port 7602
```

**IMPORTANT**: 
- Port 7601 is reserved for Docker production environment
- Use ports 7602-7610 for local development and testing
- Never attempt to kill processes on port 7601 (Docker services)

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

# Performance and diagnostic testing
python scripts/performance_test.py --comprehensive
python scripts/realistic_benchmark.py
python scripts/diagnostic_tool.py
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
**KISS + Performance First**: 
- **Configuration vs Data Separation**: Static system settings in YAML, dynamic business data in database
- **API Performance Priority**: 后台任务处理复杂计算，API专注于快速响应
- **Function over Class**: 简单接口优先使用函数，复杂状态管理才使用类
- **Simplicity First**: 选择最简单有效的解决方案，避免过度设计

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

### API服务影响评估 (Phase 8 更新)

#### ✅ **非破坏性变更**
- **完全向后兼容**: 所有现有API端点保持不变
- **透明优化**: 客户端将体验到更快的响应时间，无需修改代码
- **优雅降级**: 小批量请求(<5个渠道)自动回退到原有评分逻辑

#### 🚀 **性能改进**
- **路由速度**: 从70-80ms/渠道提升至<0.1ms/渠道 (800+倍提升)
- **缓存命中**: 重复查询响应时间从秒级降至亚毫秒级
- **并发处理**: 20个并发查询仅需0.6ms总时间
- **内存优化**: 使用数据类和线程池复用减少内存分配

#### ⚠️ **潜在影响**
- **响应时间方差**: 缓存命中vs未命中可能产生不同的延迟模式
- **内存使用**: 大批量请求可能暂时增加内存消耗
- **错误处理**: 新的异步边界可能改变错误传播行为
- **日志模式**: 审计中间件增加了请求日志的详细程度

#### 🔧 **监控建议**
- 监控响应时间分布和缓存命中率
- 观察内存使用模式，特别是大批量请求时
- 验证错误处理和故障转移机制正常工作

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

### Cost Optimization Features (Phase 7 - ✅ Completed)
- **智能模型分析**: 自动提取模型参数数量(270m-670b)和上下文长度(2k-2m)，基于三层优先级智能评分
- **多层路由策略**: 支持 `cost_first`, `free_first`, `local_first`, `balanced`, `speed_optimized`, `quality_optimized` 六种策略
- **免费优先路由**: ✅ 严格的免费模型验证，优先使用真正免费的渠道，支持 `tag:free` 精确匹配
- **本地优先模式**: ✅ 智能识别本地模型，优先使用 Ollama/LMStudio，减少云端API调用
- **实时成本追踪**: ✅ 会话级别成本统计，每次请求显示实际成本和累计消费
- **成本感知路由**: ✅ 动态策略切换API，一键切换不同成本优化策略
- **管理接口增强**: ✅ 独立admin token认证，成本优化建议，策略管理接口
- **标签匹配优化**: ✅ Case-insensitive标签匹配，支持SiliconFlow等大写模型名
- **渠道分离缓存**: 每个渠道独立缓存模型分析结果，便于调试和管理

### Recently Discovered Issues (Phase 8 Planning)
- **🚨 渠道级别定价问题**: 不同API Key用户级别可能有不同定价，当前按渠道缓存存在风险
- **🔧 SiliconFlow定价集成**: 完成基础适配器，需进一步优化HTML解析准确性
- **🛡️ 认证系统优化**: 已实现基础独立认证，可扩展权限分级和审计功能

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

### 🚀 Core System Status (Phase 1-9 完成):
- ✅ **基础架构**: FastAPI + Pydantic配置系统 + Docker部署
- ✅ **智能标签化路由系统** (Tag-Based Routing，自动标签提取)
- ✅ **多层路由引擎** (成本、速度、质量、可靠性等多因子评分)
- ✅ **Provider适配器架构** (OpenAI、Anthropic、Groq、SiliconFlow等)
- ✅ **渠道分离缓存架构** (独立缓存、模型分析、定价数据)
- ✅ **API密钥验证系统** (自动失效检测、轮换机制)
- ✅ **定时任务系统** (模型发现、健康检查、价格更新)
- ✅ **实时健康监控** (故障转移、熔断器、自动恢复)

✅ **Phase 7 已完成** (个人使用成本优化):
- ✅ **免费资源最大化**: 免费优先路由策略、严格免费验证、tag:free精确匹配
- ✅ **本地模型优先**: 本地优先模式、智能本地识别、Ollama/LMStudio支持  
- ✅ **智能成本控制**: 实时成本追踪、成本感知路由、动态策略切换API
- ✅ **使用体验优化**: 成本透明化、admin接口增强、完善启动信息
- ✅ **标签匹配优化**: Case-insensitive匹配、SiliconFlow大写模型支持
- ✅ **SiliconFlow集成**: 定价适配器、HTML解析、真实定价数据
- ✅ **认证系统增强**: 独立admin token、API token可选、安全分层

### 🚀 **Performance Optimization Status (Phase 8-11 完成)**:

✅ **Phase 8** (极致性能优化):
- ✅ **批量评分系统**: 渠道评分时间从70-80ms降至<0.1ms，性能提升800+倍
- ✅ **智能缓存机制**: 请求级缓存TTL 60秒，热缓存响应达到亚毫秒级
- ✅ **异步批处理**: ThreadPoolExecutor + asyncio并行评分计算
- ✅ **企业级日志**: 结构化JSON日志、异步文件操作、自动轮换

✅ **Phase 9** (关键错误修复):
- ✅ **JSON序列化修复**: 解决datetime序列化错误，恢复缓存持久化
- ✅ **API重试优化**: 指数退避策略，智能渠道拉黑，消除429错误循环
- ✅ **健康检查修复**: 解决NoneType错误，base_url空值检查
- ✅ **Token计算优化**: 智能tiktoken回退，支持中英文混合计算

✅ **Phase 10** (性能监控与预加载):
- ✅ **性能监控系统**: 慢查询检测、性能指标统计、优化建议生成
- ✅ **内存索引优化**: 智能重建控制、增量更新、重建间隔限制
- ✅ **分层缓存策略**: L1-L4四层缓存、LRU驱逐、大小限制管理
- ✅ **热点查询预加载**: 查询模式识别、批量预加载、响应时间优化

✅ **Phase 11** (UI监控优化与问题修复):
- ✅ **搜索功能增强**: 修复隐式标签查询，支持"kimi,0905"等逗号分隔查询
- ✅ **状态监控优化**: 修复渠道信息显示，从"unknown"改为显示实际渠道名称
- ✅ **UI交互改进**: 弹窗支持点击外部区域关闭，提升用户体验
- ✅ **日志系统修复**: 解决重复日志记录问题，消除协程未等待警告

🛡️ **API服务影响评估总结**:
- **✅ 零破坏性变更**: 所有现有API端点完全向后兼容
- **✅ 透明性能提升**: 客户端无感知获得800+倍速度提升  
- **✅ 生产就绪**: 完整错误处理、资源管理、安全审计
- **✅ UI监控完善**: 状态监控界面功能齐全，支持实时日志和渠道管理
- **✅ 问题修复完成**: 解决搜索、日志、交互等关键问题，系统稳定性提升

### 🎯 **KISS原则实践成果**:
- **函数优先设计**: 预加载器使用函数而非复杂类，代码简洁易维护
- **后台任务分离**: 模型发现、健康检查、定价更新全部后台处理
- **API极简化**: 路由请求仅做数据组装，复杂计算预先完成
- **缓存即用策略**: API调用直接使用预处理数据，响应时间最小化
- **单点责任制**: 状态监控、日志记录、UI交互各司其职，避免重复逻辑
- **异步优化**: 协程正确处理，避免阻塞和资源泄露，系统响应更稳定

### 🚀 **Future Considerations**:
- 📱 **Web管理界面**: 动态配置管理、实时监控仪表板
- 🗃️ **数据库扩展**: PostgreSQL支持，企业级数据持久化
- 🔧 **微服务架构**: 路由服务、监控服务、管理服务独立部署
- 📊 **高级分析**: 用户行为分析、成本优化建议、性能趋势预测

## Testing Philosophy

Use real API data and scenarios when possible:
- Integration tests with actual provider APIs (when keys available)
- Real configuration files and scenarios
- Performance testing with actual latency measurements
- Cost calculation validation with real token counts

## Important Notes

### Project Positioning & Security Philosophy
**🏠 Personal Local Use Focus**: This project is designed for individual users running locally, not enterprise production environments.

**Security Approach**:
- **Key Protection**: Primary concern is preventing API keys from being committed to version control
- **Local-First**: Security measures optimized for single-user local deployment
- **Practical Security**: Focus on preventing accidental key exposure rather than enterprise-grade threat models
- **Development Safety**: `.env` and `.gitignore` patterns ensure keys stay local

### Data Management Philosophy
- **Database-First**: All business data (channels, keys, costs) in database, not config files
- **Dynamic Configuration**: Changes take effect immediately without restart
- **Scalable Design**: Support hundreds of channels and thousands of API keys
- **Practical Security**: API keys managed securely for local use, with focus on preventing version control exposure

### Local Use Optimization Priorities
1. **Performance First**: Route optimization and caching for responsive local usage
2. **Cost Control**: Free resource prioritization and cost tracking for personal budgets
3. **Ease of Use**: Simple configuration and management for individual users
4. **Reliability**: Stable operation without complex enterprise infrastructure

### Personal Use Optimization Recommendations

#### 🎯 **High Priority (Individual User Benefits)**
1. **Code Quality Improvements**:
   - [ ] Split large `core/json_router.py` file for better maintainability
   - [ ] Improve exception handling consistency for better debugging
   - [ ] Add comprehensive type annotations for development experience

2. **User Experience Enhancements**:
   - [ ] Improve startup time and initial configuration experience
   - [ ] Better error messages and debugging information
   - [ ] Enhanced logging for troubleshooting personal setups

3. **Performance Optimizations** (已基本完成):
   - ✅ 800x routing performance improvement
   - ✅ Multi-layer caching system
   - ✅ Async processing optimization

#### 🔧 **Medium Priority (Nice to Have)**
1. **Configuration Management**:
   - [ ] Web-based configuration interface for easier management
   - [ ] Configuration validation and error prevention
   - [ ] Backup/restore configuration features

2. **Monitoring & Analytics**:
   - [ ] Personal usage analytics and cost optimization suggestions
   - [ ] Simple health monitoring dashboard
   - [ ] Request/response debugging tools

#### 🌟 **Low Priority (Future Enhancements)**
1. **Advanced Features**:
   - [ ] Model performance benchmarking for personal use cases
   - [ ] Custom routing strategy creation
   - [ ] Integration with personal productivity tools

### Development Priorities (Personal Use Focused)
1. **Code Maintainability**: Improve codebase structure for easier personal modifications
2. **User Experience**: Simplify configuration and management for individual users
3. **Performance**: Maintain current high-performance routing capabilities
4. **Reliability**: Ensure stable operation in personal computing environments

### Key Features (Personal Use Optimized)
- **Local-First Design**: All processing happens locally, no external dependencies for core functionality
- **Personal Cost Tracking**: Detailed cost analysis for individual API usage patterns
- **Flexible Configuration**: Easy setup and modification for personal preferences
- **Intelligent Routing**: Automatic optimization for personal use cases and cost savings
- **Multi-Language Support**: Chinese/English bilingual interface for global users