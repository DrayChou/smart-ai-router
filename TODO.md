# Smart AI Router - TODO (2025-09-22 P0 Complete) / 智能 AI 路由器 - TODO（2025-09-22 P0完成）

## Completed and Verified / 已完成并确认

- Provider adapter system covers OpenAI/Anthropic/Groq/OpenRouter/SiliconFlow via `core/providers/adapters/*` and `core/utils/adapter_manager.py:167`. / 提供商适配器体系已覆盖 OpenAI、Anthropic、Groq、OpenRouter、SiliconFlow，对应 `core/providers/adapters/*` 及 `core/utils/adapter_manager.py:167`。
- Tag-based routing and performance helpers are in production (`core/utils/memory_index.py`, `core/services/tag_processor.py`, `core/utils/batch_scorer.py`). / 基于标签的路由与性能辅助模块已投入使用（`core/utils/memory_index.py`、`core/services/tag_processor.py`、`core/utils/batch_scorer.py`）。
- API key level discovery cache persists per key (`core/utils/api_key_cache_manager.py:18`, `core/scheduler/tasks/model_discovery.py:377`). / API Key 级模型发现缓存已按密钥持久化（`core/utils/api_key_cache_manager.py:18`、`core/scheduler/tasks/model_discovery.py:377`）。
- Cost usage reporting and status monitor are shipped (`api/usage_stats.py`, `api/status_monitor.py`, `templates/status_monitor.html`). / 成本统计与状态监控页面已上线（`api/usage_stats.py`、`api/status_monitor.py`、`templates/status_monitor.html`）。
- Pricing refactor including Doubao and tiered rules is present (`core/pricing`, `core/utils/tiered_pricing.py`). / 包含豆包及阶梯定价的定价重构已完成（`core/pricing`、`core/utils/tiered_pricing.py`）。
- Pytest suite covers routing, pricing, and compatibility scenarios (`tests/test_routing_logic.py`, `tests/test_new_architecture.py`). / Pytest 测试套件已覆盖路由、定价与兼容性场景（`tests/test_routing_logic.py`、`tests/test_new_architecture.py`）。

## ✅ P0 - COMPLETED (2025-09-22) / P0 - 已完成（2025-09-22）

**STATUS: ALL P0 TASKS COMPLETED** / **状态：所有P0任务已完成**

1. ✅ **Core routing engine consolidation** / 核心路由引擎整合
   - ✅ Split `core/json_router.py` into mixins and shared types under `core/router/*`. / ✅ 已拆分 `core/json_router.py`，核心逻辑迁移到 `core/router/*` 的 mixin 与类型模块。
   - ✅ **COMPLETE**: Fully retired legacy modules under `core/routing/*` and updated imports (commit fec6cac). / ✅ **已完成**：完全移除 `core/routing/*` 遗留模块并更新所有导入引用（提交 fec6cac）。
   - ✅ **COMPLETE**: FastAPI routers and middleware unified via dependency injection with modern lifespan management. / ✅ **已完成**：通过依赖注入和现代生命周期管理统一 FastAPI 路由与中间件。

2. ✅ **Complete API key aware routing path** / 完成 API Key 感知的路由路径
   - ✅ **COMPLETE**: Updated `api/status_monitor.py` to use API key-aware caching with fallback mechanisms. / ✅ **已完成**：更新 `api/status_monitor.py` 使用API密钥感知缓存及回退机制。
   - ✅ **COMPLETE**: Chat handlers and scoring propagate request API key for cost estimation and monitoring. / ✅ **已完成**：聊天处理与评分链路传递请求API密钥用于成本估算与监控。

3. ✅ **CI and quality gate** / CI 与质量门禁
   - ✅ **COMPLETE**: GitHub Actions pipeline with ruff, black, isort, mypy, pytest, security scanning (bandit, safety), 70% coverage threshold. / ✅ **已完成**：GitHub Actions管道包含代码质量检查、安全扫描、70%覆盖率要求。

4. ✅ **Unified error handling** / 统一错误处理
   - ✅ **COMPLETE**: `ExceptionHandlerMiddleware` with enterprise-grade error classification, request tracing, and structured logging. / ✅ **已完成**：企业级 `ExceptionHandlerMiddleware` 包含错误分类、请求追踪、结构化日志。

## P1 - Mid Term Focus (Updated 2025-09-22) / P1 - 中期重点（2025-09-22更新）

**PRIORITY ORDER BASED ON VALUE & IMPACT** / **基于价值和影响的优先级排序**

1. **🚀 Web management surface** / Web 管理面增强 **[HIGH VALUE]**
   - Extend `/status` with channel enable/disable, priority editing, key metadata, and live refresh. / 为 `/status` 页面新增渠道启停、优先级编辑、密钥元数据与实时刷新。
   - **Rationale**: Direct user experience improvement, builds on existing status monitor. / **理由**：直接提升用户体验，基于现有状态监控扩展。

2. **💰 Smart budget management** / 智能预算管理 **[CORE NEED]**
   - Use `core/utils/usage_tracker.py` data to enforce spend thresholds, send alerts, and auto switch strategies when limits reach. / 利用 `core/utils/usage_tracker.py` 数据设置支出阈值、发送告警并在触及阈值时自动切换策略。
   - **Rationale**: Essential for personal cost control, existing tracker infrastructure ready. / **理由**：个人成本控制核心需求，现有追踪基础设施就绪。

3. **🔧 Configuration and legacy clean-up** / 配置与遗留清理 **[MAINTENANCE]**
   - **UPDATED**: Clean up remaining optional modules (`core/models/virtual_model.py`) and unused managers (`core/manager/channel_manager.py`). / **已更新**：清理剩余可选模块（`core/models/virtual_model.py`）和未使用的管理器（`core/manager/channel_manager.py`）。
   - Keep docs centred on YAML + tags (follow up on `docs/LEGACY.md`) and drop remaining DB-first wording from README/docs. / 文档继续以 YAML + 标签为中心（参考 `docs/LEGACY.md`），清除 README/文档中残留的 DB 优先描述。

4. **🛠️ Dependency upgrades** / 依赖升级 **[UPDATED - PARTIAL COMPLETE]**
   - ✅ **COMPLETE**: Pydantic 2.x compatibility achieved (commit fec6cac). / ✅ **已完成**：Pydantic 2.x 兼容性已实现（提交 fec6cac）。
   - **REMAINING**: Migrate to SQLAlchemy 2.x to remove deprecation warnings from `declarative_base()`. / **剩余**：迁移到 SQLAlchemy 2.x 消除 `declarative_base()` 弃用警告。

5. **📊 Observability upgrade** / 可观测性升级 **[ADVANCED]**
   - Export Prometheus metrics, standardise trace/log fields, and separate debug log channels. / 输出 Prometheus 指标，规范追踪/日志字段，并划分调试日志通道。
   - **Rationale**: Lower priority as basic monitoring exists, suitable for enterprise scaling. / **理由**：基础监控已存在，优先级较低，适合企业级扩展。

## P2+ - Longer Term / P2+ - 长期规划

- Dynamic and personalised routing based on historical outcomes and A/B evaluation. / 基于历史结果与 A/B 评估的动态个性化路由。
- Enterprise features: multi-tenant auth, RBAC, API key lifecycle, configuration audit. / 企业特性：多租户认证、RBAC、API Key 生命周期管理、配置审计。
- Advanced monitoring: distributed tracing, performance analytics, automated optimisation suggestions. / 高级监控：分布式追踪、性能分析、自动化优化建议。

## Archived / No Longer Needed / 已归档或无需继续

- "Testing missing" tasks: pytest coverage is already broad (`tests/test_routing_logic.py`, `tests/test_new_architecture.py`); focus shifts to CI enforcement. / “缺少测试” 相关任务已完成，Pytest 覆盖较广（`tests/test_routing_logic.py`、`tests/test_new_architecture.py`）；后续重点转向 CI 执行力。
- "Port alignment" is resolved; README documents 7602 for dev and 7601 for production (`README.md:90-113`). / “端口统一” 已解决；README 已明确开发使用 7602、生产使用 7601（`README.md:90-113`）。
- "Model Group + DB driver parity" is already labelled legacy (`docs/LEGACY.md`, `core/router/base.py:1-10`); future work tracked under P1 clean-up. / “Model Group 与数据库驱动一致” 已标记为遗留流程（`docs/LEGACY.md`、`core/router/base.py:1-10`），后续整理归入 P1 清理项。
- "API key level cache absent" is addressed via the discovery pipeline; remaining work is scoped in P0 item 2. / “缺少 API Key 级缓存” 已通过模型发现流程解决，剩余工作包含在 P0 第 2 条任务中。
