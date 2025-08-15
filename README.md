# Smart AI Router - 个人AI智能路由系统

轻量级个人AI智能路由系统，支持多Provider智能选择、成本优化、故障转移。

## ✨ 特性

🚀 **智能路由** - 基于成本、速度、质量的多层路由策略  
💰 **成本优化** - 自动选择最便宜的可用渠道  
⚡ **故障转移** - 智能重试和自动故障恢复  
🎯 **虚拟模型组** - auto:free, auto:fast, auto:balanced, auto:premium  
🔧 **零配置启动** - 单一YAML配置文件  
🌏 **多Provider支持** - OpenAI, Groq, SiliconFlow, Burn Hair等  

## 🚀 快速开始

### 1. 安装依赖
```bash
uv sync
```

### 2. 配置API密钥
```bash
# 复制配置模板
cp config/router_config.yaml.template config/router_config.yaml

# 编辑配置文件
vim config/router_config.yaml
```

在配置文件中替换API密钥并启用渠道：
```yaml
channels:
  - id: "groq_llama3_8b"
    name: "Groq Llama3.1 8B"
    provider: "groq"
    model_name: "llama-3.1-8b-instant"
    api_key: "你的_GROQ_API_密钥"  # 替换这里
    enabled: true  # 改为 true
```

### 3. 启动服务
```bash
# 默认启动 (YAML模式)
python main.py

# 指定端口
python main.py --port 8080

# 调试模式
python main.py --debug
```

### 4. 测试API
```bash
# 健康检查
curl http://127.0.0.1:8000/health

# 聊天测试
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto:fast",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## 🎯 推荐Provider

### 💰 性价比之王
- **[Groq](https://groq.com/)** - 免费，超快推理速度
- **[Burn Hair](https://burn.hair/)** - 便宜的GPT-4o代理
- **[SiliconFlow](https://siliconflow.cn/)** - 国内访问友好

### ⚡ 速度为王
1. **Groq Llama3.1 8B** - 极快免费
2. **Groq Llama3.1 70B** - 平衡速度质量
3. **Burn Hair GPT-4o Mini** - 速度不错且便宜

### 🎓 质量为王
1. **Burn Hair GPT-4o** - 高质量便宜
2. **OpenAI GPT-4o Mini** - 官方保证
3. **SiliconFlow Qwen2.5** - 国产之光

## 🤖 虚拟模型组

| 模型组 | 策略 | 适用场景 | 预算 |
|--------|------|----------|------|
| `auto:free` | 成本优先 | 大量基础任务 | $5/天 |
| `auto:fast` | 速度优先 | 快速响应需求 | $10/天 |
| `auto:balanced` | 平衡策略 | 日常使用 | $20/天 |
| `auto:premium` | 质量优先 | 重要任务 | $50/天 |

## 📋 配置模式

| 特性 | YAML模式 | SQLite模式 |
|------|----------|------------|
| 配置文件 | router_config.yaml | 数据库 |
| 易读性 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| 注释支持 | ✅ | ❌ |
| 性能 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 适用场景 | 个人使用(推荐) | 企业级 |

## 📊 API兼容性

✅ **OpenAI API 完全兼容**  
✅ **支持流式响应**  
✅ **支持Function Calling**  
✅ **支持Vision模型**  

```bash
# 直接替换OpenAI API端点即可使用
export OPENAI_API_BASE=http://127.0.0.1:8000/v1
export OPENAI_API_KEY=任意值
```

## 🔧 高级配置

### 自定义路由策略
```yaml
model_groups:
  my_custom:
    routing_strategy: "multi_layer"
    routing_weights:
      cost: 0.4      # 成本权重
      speed: 0.3     # 速度权重  
      quality: 0.2   # 质量权重
      reliability: 0.1 # 可靠性权重
```

### 预算控制
```yaml
cost_control:
  global_daily_budget: 100.0
  alert_threshold: 0.8
  auto_disable_on_budget_exceeded: true
```

### 错误处理
```yaml
routing:
  max_retry_attempts: 3
  error_cooldown_period: 60
  enable_fallback: true
```

## 📂 项目结构

```
smart-ai-router/
├── config/
│   ├── router_config.yaml.template  # 配置模板
│   └── README.md                    # 配置说明
├── core/                            # 核心代码
│   ├── models/                      # 数据模型
│   ├── providers/                   # Provider适配器
│   ├── router/                      # 路由引擎
│   └── yaml_config.py              # YAML配置加载器
├── api/                             # API路由
├── main.py                          # 统一入口
└── README.md                        # 项目说明
```

## 🔗 相关文档

- **[配置指南](config/README.md)** - 详细配置说明
- **[API文档](http://127.0.0.1:8000/docs)** - 启动服务后访问
- **[TODO列表](TODO.md)** - 开发进度
- **[架构文档](docs/architecture.md)** - 系统架构

## 🎉 开始使用

1. **获取API密钥**: 注册 [Groq](https://groq.com/) 获取免费API密钥
2. **配置系统**: 复制模板并填入密钥
3. **启动服务**: `python main.py`
4. **开始聊天**: 访问 http://127.0.0.1:8000/docs 体验

---

**⭐ 如果觉得有用，请给个Star！**