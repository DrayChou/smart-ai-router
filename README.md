# 🚀 Smart AI Router

轻量化个人AI智能路由系统 - **成本优化** | **智能路由** | **故障转移**

## ✨ 特性

### 🧠 核心功能
- **🎯 Provider/Channel/Model Group架构** - 参考OpenRouter auto模型，支持Provider→Channel→Model Group三层架构
- **💰 智能成本优化** - 多层路由策略，自动选择成本最优渠道
- **⚡ 多策略路由** - 成本/速度/优先级/负载均衡等多层次智能路由
- **🔄 自动故障转移** - 智能错误分类，自动冷却恢复机制
- **📋 灵活配额管理** - 每渠道独立的每日限额与自动重置

### 🛡️ 高级特性
- **📊 实时成本监控** - 动态价格策略，成本分析和预算控制
- **🔍 健康状态检查** - 持续监控渠道健康度和性能指标
- **🎛️ 能力筛选路由** - 支持function_calling、vision、代码生成等能力过滤
- **📈 数据统计分析** - 请求量、成功率、成本趋势等详细统计
- **🌐 多厂商支持** - 支持官方/聚合/转售商等多种Provider类型
- **⚙️ 动态配置管理** - 数据库驱动，支持实时配置无需重启

## 🏗️ 项目结构

```
smart-ai-router/
├── core/                    # 核心功能模块
│   ├── models/             # SQLAlchemy数据模型
│   ├── router/             # 智能路由引擎
│   ├── manager/            # 渠道/密钥/模型组管理器
│   ├── providers/          # Provider适配器实现
│   └── scheduler/          # 定时任务和监控
├── api/                     # FastAPI路由接口
├── config/                  # 配置文件(YAML)
│   ├── providers.yaml      # Provider配置
│   ├── model_groups.yaml   # Model Group配置
│   ├── system.yaml         # 系统配置
│   └── pricing_policies.yaml # 动态价格策略
├── web/                     # Web管理界面(可选)
├── tests/                   # 测试文件
└── docs/                    # 文档
```

## 🚀 快速开始

### 环境要求
- Python 3.9+
- uv 包管理器

### 安装依赖
```bash
# 克隆仓库
git clone <your-repo-url>
cd smart-ai-router

# 使用 uv 安装依赖
uv sync

# 激活虚拟环境
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows
```

### 配置系统
```bash
# 复制配置模板
cp config/example.yaml config/config.yaml
cp .env.example .env

# 编辑环境变量文件，添加必要的API密钥
# vi .env

# 注意：具体的Channel和API密钥配置通过Web管理界面进行
# 无需手动编辑YAML配置文件
```

### 启动服务
```bash
# 开发模式
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 生产模式
python main.py
```

## ⚙️ 架构示例

### Model Group配置示例
```yaml
# config/model_groups.yaml
model_groups:
  auto:free:
    display_name: "免费模型组"
    description: "包含所有免费AI模型，按速度和可用性智能路由"
    
    # 多层排序策略
    routing_strategy:
      - field: "effective_cost"     # 考虑倍率后的实际成本
        order: "asc"
        weight: 1.0
      - field: "speed_score"        # 响应速度评分
        order: "desc"
        weight: 0.9
      - field: "quota_remaining"    # 剩余配额比例
        order: "desc"
        weight: 0.7
        
    # 筛选条件
    filters:
      max_cost_per_1k: 0.0         # 只要免费模型
      min_context_length: 4000     # 最小上下文长度
      
    # 渠道配置
    channels:
      - provider: "groq"
        model: "llama-3.1-8b-instant"
        priority: 1
        weight: 1.5
        daily_limit: 1000
        
      - provider: "openrouter"
        model: "meta-llama/llama-3.1-8b-instruct:free"
        priority: 2
        weight: 1.0
        daily_limit: 1000

# 具体Provider配置、API密钥管理通过数据库动态管理
# 支持实时添加/编辑，无需重启服务
```

## 💡 使用示例

### 基础API调用
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "auto:free",  # 使用免费模型组
    "messages": [{
      "role": "user", 
      "content": "Hello!"
    }]
  }'

# 其他预定义模型组示例
# auto:fast    - 速度优先(追求最快响应)
# auto:smart   - 质量优先(追求最佳效果)  
# auto:cheap   - 成本优先(追求最佳性价比)
# auto:tools   - 工具调用模型组(支持function calling)
# auto:vision  - 多模态模型组(支持图像处理)
# auto:code    - 代码助手模型组(专门用于代码生成)
# auto:chinese - 中文优化模型组(中文理解和生成)
```

### Python客户端
```python
import openai

# 使用模型组，系统自动从组内选择最优渠道
client = openai.Client(
    api_key="your-api-key",
    base_url="http://localhost:8000/v1"
)

# 使用免费模型组
response = client.chat.completions.create(
    model="auto:free",  # 免费模型组
    messages=[{"role": "user", "content": "Hello!"}]
)

# 使用快速模型组
response = client.chat.completions.create(
    model="auto:fast",  # 速度优先模型组
    messages=[{"role": "user", "content": "Hello!"}]
)
```

## 📊 核心优势

### 💰 成本优化
- **动态价格策略** - 支持时间段、配额使用率、需求等多种价格调整
- **多层预算控制** - Model Group、Channel、用户等多层次预算管理
- **成本透明化** - 详细的成本分解、趋势分析和预测

### 🧠 智能路由  
- **多层排序策略** - 支持成本、速度、质量、可靠性等多因子组合路由
- **能力筛选路由** - 基于function_calling、vision、code_generation等能力过滤
- **动态权重调整** - 基于实时性能数据和健康状态的动态权重

### 🛡️ 高可用性
- **智能错误分类** - 区分永久/临时错误，精确的冷却和恢复策略
- **熔断器模式** - 防止级联故障的Circuit Breaker实现
- **多Provider故障转移** - 跨Provider的无缝故障转移

## 🗺️ 开发路线图

- [x] **Phase 1** - 核心架构和基础功能
- [x] **Phase 2** - 智能路由引擎
- [ ] **Phase 3** - Web管理界面
- [ ] **Phase 4** - 高级监控和分析
- [ ] **Phase 5** - 部署和运维工具

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

---

**让AI API调用更智能、更经济、更可靠！** 🎯