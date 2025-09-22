# Smart AI Router - TODO (2025-09-16 Review) / 智能 AI 路由器 - TODO（2025-09-16 审查）

## Completed and Verified / 已完成并确认

- Provider adapter system covers OpenAI/Anthropic/Groq/OpenRouter/SiliconFlow via `core/providers/adapters/*` and `core/utils/adapter_manager.py:167`. / 提供商适配器体系已覆盖 OpenAI、Anthropic、Groq、OpenRouter、SiliconFlow，对应 `core/providers/adapters/*` 及 `core/utils/adapter_manager.py:167`。
- Tag-based routing and performance helpers are in production (`core/utils/memory_index.py`, `core/services/tag_processor.py`, `core/utils/batch_scorer.py`). / 基于标签的路由与性能辅助模块已投入使用（`core/utils/memory_index.py`、`core/services/tag_processor.py`、`core/utils/batch_scorer.py`）。
- API key level discovery cache persists per key (`core/utils/api_key_cache_manager.py:18`, `core/scheduler/tasks/model_discovery.py:377`). / API Key 级模型发现缓存已按密钥持久化（`core/utils/api_key_cache_manager.py:18`、`core/scheduler/tasks/model_discovery.py:377`）。
- Cost usage reporting and status monitor are shipped (`api/usage_stats.py`, `api/status_monitor.py`, `templates/status_monitor.html`). / 成本统计与状态监控页面已上线（`api/usage_stats.py`、`api/status_monitor.py`、`templates/status_monitor.html`）。
- Pricing refactor including Doubao and tiered rules is present (`core/pricing`, `core/utils/tiered_pricing.py`). / 包含豆包及阶梯定价的定价重构已完成（`core/pricing`、`core/utils/tiered_pricing.py`）。
- Pytest suite covers routing, pricing, and compatibility scenarios (`tests/test_routing_logic.py`, `tests/test_new_architecture.py`). / Pytest 测试套件已覆盖路由、定价与兼容性场景（`tests/test_routing_logic.py`、`tests/test_new_architecture.py`）。

## P0 - High Priority / P0 - 高优先级

1. Core routing engine consolidation / 核心路由引擎整合
   - ✅ Split `core/json_router.py` into mixins and shared types under `core/router/*`. / ✅ 已拆分 `core/json_router.py`，核心逻辑迁移到 `core/router/*` 的 mixin 与类型模块。
   - ✅ Fully retired legacy modules under `core/routing/*` and updated imports to use new router structure. / ✅ 完全移除 `core/routing/*` 遗留模块并更新所有导入引用至新路由器结构。
   - Wire `main.py` and `api/*` to a single RoutingEngine with dependency injection (RouterService wrapper in place; update FastAPI routers and middleware next). / 通过依赖注入让 `main.py` 和 `api/*` 接入统一的 RoutingEngine（RouterService 已就绪，后续同步 FastAPI 路由与中间件）。
2. Complete API key aware routing path / 完成 API Key 感知的路由路径
   - Update call sites still using channel cache only (`api/status_monitor.py:95`) to rely on `_get_discovered_info` / `get_model_cache_by_channel_and_key`. / 修正仍仅读取渠道级缓存的调用（如 `api/status_monitor.py:95`），统一改用 `_get_discovered_info` / `get_model_cache_by_channel_and_key`。
   - Ensure chat handlers and scoring propagate the request API key for cost estimation and monitoring. / 确保聊天处理与评分链路向下传递请求的 API Key，用于成本估算与监控。
3. CI and quality gate / CI 与质量门禁
   - ✅ Added GitHub Actions for `ruff`, `black`, `isort`, `mypy`, and `pytest` with caching and coverage collection (70% threshold). / ✅ 新增 GitHub Actions，执行 `ruff`、`black`、`isort`、`mypy`、`pytest` 并启用缓存和覆盖率收集（70% 阈值）。
4. Unified error handling / 统一错误处理
   - ✅ Applied `core/utils/exception_handler.py` via `ExceptionHandlerMiddleware` to all API endpoints with unified response schema and severity/category tagging. / ✅ 通过 `ExceptionHandlerMiddleware` 在所有 API 端点应用 `core/utils/exception_handler.py`，实现统一返回结构与错误级别/类别标记。

## P1 - Mid Term Focus / P1 - 中期重点

- Configuration and legacy clean-up / 配置与遗留清理
  - Continue isolating `core/router/*` and `core/models/virtual_model.py` as optional; remove or guard managers that depend on them (`core/manager/channel_manager.py`). / 继续将 `core/router/*`、`core/models/virtual_model.py` 标记为可选模块，并清理或隔离依赖它们的管理器（如 `core/manager/channel_manager.py`）。
  - Keep docs centred on YAML + tags (follow up on `docs/LEGACY.md`) and drop remaining DB-first wording from README/docs. / 文档继续以 YAML + 标签为中心（参考 `docs/LEGACY.md`），清除 README/文档中残留的 DB 优先描述。
- Web management surface / Web 管理面增强
  - Extend `/status` with channel enable/disable, priority editing, key metadata, and live refresh. / 为 `/status` 页面新增渠道启停、优先级编辑、密钥元数据与实时刷新。
- Smart budget management / 智能预算管理
  - Use `core/utils/usage_tracker.py` data to enforce spend thresholds, send alerts, and auto switch strategies when limits reach. / 利用 `core/utils/usage_tracker.py` 数据设置支出阈值、发送告警并在触及阈值时自动切换策略。
- Observability upgrade / 可观测性升级
  - Export Prometheus metrics, standardise trace/log fields, and separate debug log channels. / 输出 Prometheus 指标，规范追踪/日志字段，并划分调试日志通道。
- Dependency upgrades / 依赖升级
  - Plan migration to SQLAlchemy 2.x, Pydantic 2.x, and python-json-logger new import path to remove deprecation warnings. / 规划升级 SQLAlchemy 2.x、Pydantic 2.x 以及 python-json-logger 新路径，消除弃用警告。

## P2+ - Longer Term / P2+ - 长期规划

- Dynamic and personalised routing based on historical outcomes and A/B evaluation. / 基于历史结果与 A/B 评估的动态个性化路由。
- Enterprise features: multi-tenant auth, RBAC, API key lifecycle, configuration audit. / 企业特性：多租户认证、RBAC、API Key 生命周期管理、配置审计。
- Advanced monitoring: distributed tracing, performance analytics, automated optimisation suggestions. / 高级监控：分布式追踪、性能分析、自动化优化建议。

## Archived / No Longer Needed / 已归档或无需继续

- "Testing missing" tasks: pytest coverage is already broad (`tests/test_routing_logic.py`, `tests/test_new_architecture.py`); focus shifts to CI enforcement. / “缺少测试” 相关任务已完成，Pytest 覆盖较广（`tests/test_routing_logic.py`、`tests/test_new_architecture.py`）；后续重点转向 CI 执行力。
- "Port alignment" is resolved; README documents 7602 for dev and 7601 for production (`README.md:90-113`). / “端口统一” 已解决；README 已明确开发使用 7602、生产使用 7601（`README.md:90-113`）。
- "Model Group + DB driver parity" is already labelled legacy (`docs/LEGACY.md`, `core/router/base.py:1-10`); future work tracked under P1 clean-up. / “Model Group 与数据库驱动一致” 已标记为遗留流程（`docs/LEGACY.md`、`core/router/base.py:1-10`），后续整理归入 P1 清理项。
- "API key level cache absent" is addressed via the discovery pipeline; remaining work is scoped in P0 item 2. / “缺少 API Key 级缓存” 已通过模型发现流程解决，剩余工作包含在 P0 第 2 条任务中。
