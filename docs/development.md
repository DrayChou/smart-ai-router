# 开发指南

## 开发环境搭建

### 环境要求
- Python 3.9+
- uv 包管理器 (推荐)
- Git
- SQLite (开发环境)
- Redis (可选，用于缓存测试)

### 🏗️ 项目架构
基于Provider/Channel/Model Group三层架构：
- **Provider**: AI服务提供商 (OpenAI, Anthropic等)
- **Channel**: 具体API端点配置 (模型、密钥、限额等)  
- **Model Group**: 统一模型组合 (auto:free, auto:fast等)

## 🚀 快速开始

### 1. 进入项目目录
```bash
cd D:\Code\smart-ai-router
```

### 2. 激活虚拟环境
```bash
# 方式1: 使用 uv (推荐)
uv run python main.py

# 方式2: 激活虚拟环境
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac
```

### 3. 配置环境变量
```bash
# 复制环境变量模板
copy .env.example .env
# 编辑 .env 文件，填入真实的API密钥
```

### 4. 配置应用
```bash
# 复制配置模板
copy config\example.yaml config\config.yaml
# 编辑 config.yaml，配置虚拟模型和物理渠道
```

### 5. 启动应用
```bash
# 开发模式
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 或者直接运行
uv run python main.py
```

### 6. 访问应用
- 🏠 主页: http://localhost:8000
- 📚 API文档: http://localhost:8000/docs
- 🔍 健康检查: http://localhost:8000/health
- 💬 聊天接口: http://localhost:8000/v1/chat/completions
- 🎛️ 管理接口: http://localhost:8000/admin

## 📋 下一步开发任务

### Phase 1: 核心架构 (当前阶段)
- [ ] 实现数据模型 (VirtualModel, PhysicalModel, etc.)
- [ ] 实现配置加载和验证逻辑
- [ ] 实现基础的虚拟模型管理
- [ ] 实现简单的路由选择逻辑

### Phase 2: 智能路由引擎
- [ ] 实现成本计算器
- [ ] 实现成本优先路由算法
- [ ] 实现延迟优先路由算法
- [ ] 实现智能故障转移机制
- [ ] 实现错误分类和处理

### Phase 3: 提供商适配器
- [ ] 实现OpenAI适配器
- [ ] 实现Anthropic适配器  
- [ ] 实现Azure适配器
- [ ] 实现Gemini适配器
- [ ] 实现通用适配器框架

### Phase 4: Web管理界面
- [ ] 设计管理界面原型
- [ ] 实现虚拟模型管理页面
- [ ] 实现渠道监控页面
- [ ] 实现成本分析Dashboard
- [ ] 实现实时监控界面

## 🛠️ 开发工具

### 代码质量
```bash
# 格式化代码
uv run black .
uv run isort .

# 代码检查
uv run ruff check .
uv run mypy .

# 运行测试
uv run pytest
```

### 依赖管理
```bash
# 添加依赖
uv add package_name

# 添加开发依赖
uv add --dev package_name

# 同步依赖
uv sync

# 更新依赖
uv lock --upgrade
```

### Docker 部署
```bash
# 构建镜像
docker build -t smart-ai-router .

# 运行容器
docker-compose up -d

# 查看日志
docker-compose logs -f
```

## 🎯 开发重点

### 核心设计原则
1. **简洁性** - 避免过度设计，专注核心功能
2. **成本导向** - 一切设计围绕成本优化
3. **个人友好** - 配置简单，使用便捷
4. **高可靠** - 智能故障转移，服务稳定

### 关键功能优先级
1. 🔥 **虚拟模型系统** - 核心抽象概念
2. 🔥 **成本优化路由** - 主要价值主张
3. 🔥 **智能故障转移** - 可靠性保证  
4. 🟡 **性能监控** - 运维需求
5. 🟢 **Web界面** - 用户体验

## 🐛 调试技巧

### 启用调试模式
```bash
export DEBUG=true
export LOG_LEVEL=DEBUG
uv run python main.py
```

### 查看日志
```bash
# 实时查看日志
tail -f logs/smart-router.log

# Docker容器日志
docker-compose logs -f smart-ai-router
```

## 📚 参考文档

- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 文档](https://docs.sqlalchemy.org/)
- [Pydantic 文档](https://docs.pydantic.dev/)
- [structlog 文档](https://www.structlog.org/)

---

**准备好开始开发了！让我们构建这个智能的AI路由系统！** 🚀