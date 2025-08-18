# 项目目录结构说明

## 完整目录结构 (已重新组织)

```
smart-ai-router/
├── 📁 api/                          # FastAPI路由接口
│   ├── __init__.py
│   └── 📁 admin/                    # 管理员API接口
│       └── siliconflow.py           # SiliconFlow管理接口
│
├── 📁 cache/                        # 缓存目录
│   ├── 📁 channels/                 # 各渠道缓存文件
│   ├── discovered_models.json      # 已发现的模型缓存
│   ├── health_history.json         # 健康检查历史
│   ├── model_pricing.json          # 模型定价缓存
│   └── smart_cache.json            # 智能缓存
│
├── 📁 config/                       # 配置文件目录
│   ├── README.md                    # 配置文件说明
│   ├── providers.yaml               # Provider配置
│   ├── router_config.yaml           # 主配置文件
│   ├── router_config.yaml.template  # 配置模板
│   ├── synced_config.yaml           # 同步配置
│   ├── test_config.yaml             # 测试配置
│   └── working_config.yaml          # 工作配置
│
├── 📁 core/                         # 核心功能模块
│   ├── __init__.py
│   ├── auth.py                      # 认证模块
│   ├── config_loader.py             # 配置加载器
│   ├── config_models.py             # Pydantic配置模型
│   ├── database.py                  # 数据库配置
│   ├── exceptions.py                # 自定义异常
│   ├── json_router.py               # 核心路由引擎
│   ├── yaml_config.py               # YAML配置加载器
│   │
│   ├── 📁 handlers/                 # 请求处理器
│   │   ├── __init__.py
│   │   └── chat_handler.py          # 聊天请求处理器
│   │
│   ├── 📁 manager/                  # 业务管理器
│   │   ├── __init__.py
│   │   └── channel_manager.py       # 渠道管理器
│   │
│   ├── 📁 models/                   # SQLAlchemy数据模型
│   │   ├── __init__.py
│   │   ├── api_key.py               # API密钥模型
│   │   ├── base.py                  # 基础模型
│   │   ├── channel.py               # 渠道模型
│   │   ├── cost.py                  # 成本模型
│   │   ├── model_group.py           # 模型组模型
│   │   ├── provider.py              # Provider模型
│   │   ├── request_log.py           # 请求日志模型
│   │   ├── stats.py                 # 统计模型
│   │   └── virtual_model.py         # 虚拟模型
│   │
│   ├── 📁 providers/                # Provider适配器
│   │   ├── __init__.py
│   │   ├── base.py                  # 基础适配器接口
│   │   ├── registry.py              # 适配器注册器
│   │   └── 📁 adapters/             # 各Provider适配器实现
│   │       ├── __init__.py
│   │       ├── anthropic.py         # Anthropic适配器
│   │       ├── groq.py              # Groq适配器
│   │       ├── openai.py            # OpenAI适配器
│   │       └── siliconflow.py       # SiliconFlow适配器
│   │
│   ├── 📁 router/                   # 路由策略
│   │   ├── __init__.py
│   │   ├── base.py                  # 基础路由接口
│   │   └── 📁 strategies/           # 路由策略实现
│   │       ├── __init__.py
│   │       ├── cost_optimized.py    # 成本优化策略
│   │       ├── multi_layer.py       # 多层路由策略
│   │       └── speed_optimized.py   # 速度优化策略
│   │
│   ├── 📁 scheduler/                # 定时任务系统
│   │   ├── __init__.py
│   │   ├── scheduler.py             # 任务调度器
│   │   ├── task_manager.py          # 任务管理器
│   │   └── 📁 tasks/                # 各种定时任务
│   │       ├── __init__.py
│   │       ├── model_discovery.py   # 模型发现任务
│   │       ├── official_pricing.py  # 官方定价任务
│   │       ├── pricing_discovery.py # 定价发现任务
│   │       ├── pricing_extractor.py # 定价提取器
│   │       ├── service_health_check.py # 健康检查任务
│   │       └── siliconflow_pricing.py # SiliconFlow定价任务
│   │
│   └── 📁 utils/                    # 工具函数
│       ├── __init__.py
│       ├── api_key_validator.py     # API密钥验证器
│       ├── channel_cache_manager.py # 渠道缓存管理器
│       ├── config.py                # 配置工具
│       ├── http_client_pool.py      # HTTP客户端池
│       ├── logger.py                # 日志配置
│       ├── model_analyzer.py        # 模型分析器
│       ├── smart_cache.py           # 智能缓存
│       └── token_counter.py         # Token计数器
│
├── 📁 docs/                         # 项目文档 (已重新组织)
│   ├── DATABASE_SCHEMA.md           # 数据库架构
│   ├── PROJECT_STRUCTURE.md         # 项目结构说明
│   ├── api.md                       # API文档
│   ├── architecture.md              # 系统架构
│   ├── background_tasks.md          # 后台任务说明
│   ├── build.md                     # 构建说明
│   ├── channel_pricing_analysis.md  # 渠道定价分析
│   ├── code_quality_report.md       # 代码质量报告
│   ├── configuration.md             # 配置说明
│   ├── deployment.md                # 部署指南
│   ├── development.md               # 开发指南
│   ├── development_summary.md       # 开发总结
│   ├── gemini.md                    # Gemini集成说明
│   ├── performance_optimizations.md # 性能优化
│   ├── pricing_system.md            # 定价系统说明
│   └── project_review_and_fixes.md  # 项目回顾和修复
│
├── 📁 logs/                         # 日志文件目录
│   └── 📁 siliconflow_pricing/      # SiliconFlow定价相关文件
│       ├── 大模型 API 价格方案 - 硅基流动 SiliconFlow.html
│       └── 大模型 API 价格方案 - 硅基流动 SiliconFlow_files/
│
├── 📁 scripts/                      # 工具脚本 (已重新组织)
│   ├── analyze_routing_strategy.py  # 路由策略分析
│   ├── debug_routing.py             # 路由调试
│   ├── debug_tag_matching.py        # 标签匹配调试
│   ├── demo_tag_system.py           # 标签系统演示
│   ├── fix_config.py                # 配置修复工具
│   ├── import_oneapi_channels.py    # OneAPI渠道导入
│   ├── import_oneapi_data.py        # OneAPI数据导入
│   ├── migrate_cache.py             # 缓存迁移工具
│   ├── run_model_discovery.py       # 运行模型发现
│   ├── simple_test.py               # 简单测试
│   └── sync_oneapi_channels.py      # OneAPI渠道同步
│
├── 📁 tests/                        # 测试文件 (已重新组织)
│   ├── test_api_fix.py              # API修复测试
│   ├── test_api_key_validation.py   # API密钥验证测试
│   ├── test_background_tasks.py     # 后台任务测试
│   ├── test_cache_consistency.py    # 缓存一致性测试
│   ├── test_debug_headers.py        # 调试头测试
│   ├── test_detailed_logging.py     # 详细日志测试
│   ├── test_health_check.py         # 健康检查测试
│   ├── test_negative_local_only.json # 负面本地测试数据
│   ├── test_negative_tag_parsing.py # 负面标签解析测试
│   ├── test_negative_tags.json      # 负面标签测试数据
│   ├── test_official_pricing.py     # 官方定价测试
│   ├── test_optimizations.py        # 优化测试
│   ├── test_performance.py          # 性能测试
│   ├── test_phase1.py               # 第一阶段测试
│   ├── test_pricing_extraction.py   # 定价提取测试
│   ├── test_pricing_integration.py  # 定价集成测试
│   ├── test_routing_logic.py        # 路由逻辑测试
│   ├── test_simple_discovery.py     # 简单发现测试
│   ├── test_tag_error_handling.py   # 标签错误处理测试
│   ├── test_tag_fix.py              # 标签修复测试
│   └── test_tag_system.py           # 标签系统测试
│
├── 📁 web/                          # Web管理界面 (预留)
│   ├── 📁 static/                   # 静态资源
│   └── 📁 templates/                # 模板文件
│
├── 📄 main.py                       # 应用入口点
├── 📄 pyproject.toml                # Python项目配置
├── 📄 requirements.txt              # 依赖列表
├── 📄 uv.lock                       # UV锁定文件
├── 📄 Dockerfile                    # Docker配置
├── 📄 docker-compose.yml            # Docker Compose配置
├── 📄 CLAUDE.md                     # Claude开发指南
├── 📄 README.md                     # 项目说明
└── 📄 TODO.md                       # 任务列表
```

## 核心架构说明

### 🏗️ 智能标签化路由系统

Smart AI Router 采用**基于模型名称的自动标签化系统**，完全替代了传统的 Model Groups 概念：

1. **自动标签提取**: 从模型名称中自动提取标签
2. **智能匹配**: 支持多标签组合查询 (如 `tag:gpt,free`)
3. **实时路由**: 基于标签进行智能路由选择

### 📊 多层路由策略

支持六种路由策略，可动态切换：
- `cost_first`: 成本优先
- `free_first`: 免费资源优先  
- `local_first`: 本地模型优先
- `balanced`: 平衡策略
- `speed_optimized`: 速度优化
- `quality_optimized`: 质量优化

### 🔧 数据模型关系

```
Provider (OpenAI, Anthropic, etc.)
    ↓
Channel (具体API端点配置)
    ↓
Model (物理模型)
    ↓
Tag-based Routing (标签化路由)
```

### 🚀 主要特性

- **Phase 7 成本优化**: 免费资源最大化、本地模型优先
- **实时成本追踪**: 透明的成本计算和显示
- **智能故障转移**: 自动错误检测和渠道切换
- **定时任务系统**: 模型发现、定价更新、健康检查
- **管理API**: 动态配置管理和监控

## 文件组织变更

### ✅ 已完成的重新组织

1. **文档集中化**: 所有 `*.md` 文件移动到 `docs/` 目录
2. **测试集中化**: 所有 `test_*.py` 和 `test_*.json` 文件移动到 `tests/` 目录  
3. **脚本集中化**: 所有工具脚本移动到 `scripts/` 目录
4. **日志结构化**: `logs/` 目录下创建分类子目录
5. **清理根目录**: 删除备份文件和临时文件

### 📈 架构优势

- **模块化设计**: 清晰的功能分离和依赖关系
- **可扩展性**: 易于添加新的Provider和路由策略
- **可维护性**: 良好的代码组织和文档结构
- **Docker友好**: 完整的容器化支持
- **开发友好**: 完善的开发工具和测试套件