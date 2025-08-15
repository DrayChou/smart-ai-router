# Smart AI Router 配置目录

## 📁 文件说明

### 📋 配置模板
- **`router_config.yaml.template`** - 主配置文件模板，包含完整的系统配置
  - 复制为 `router_config.yaml` 并填入真实API密钥使用
  - 包含推荐的Provider和渠道配置
  - 预设了4个虚拟模型组：auto:free, auto:fast, auto:balanced, auto:premium

## 🚀 快速开始

### 1. 复制配置模板
```bash
cp config/router_config.yaml.template config/router_config.yaml
```

### 2. 编辑配置文件
打开 `config/router_config.yaml`，替换以下占位符：
- `YOUR_BURN_HAIR_API_KEY_HERE` - Burn Hair API密钥
- `YOUR_GROQ_API_KEY_HERE` - Groq API密钥  
- `YOUR_SILICONFLOW_API_KEY_HERE` - SiliconFlow API密钥
- `YOUR_OPENAI_API_KEY_HERE` - OpenAI API密钥

### 3. 启用渠道
将需要使用的渠道的 `enabled` 字段改为 `true`：
```yaml
channels:
  - id: "groq_llama3_8b"
    enabled: true  # 改为 true
```

### 4. 启动服务
```bash
python main.py
```

## 🎯 推荐配置

### 💰 性价比推荐
1. **Groq** - 免费且超快的推理速度
2. **Burn Hair** - 便宜的GPT-4o代理
3. **SiliconFlow** - 国内访问友好

### ⚡ 速度优先
1. **Groq Llama3.1 8B** - 极快的推理速度
2. **Groq Llama3.1 70B** - 平衡速度和质量
3. **Burn Hair GPT-4o Mini** - 不错的速度

### 🎓 质量优先
1. **Burn Hair GPT-4o** - 高质量且便宜
2. **OpenAI GPT-4o Mini** - 官方质量保证
3. **Groq Llama3.1 70B** - 开源模型中的佼佼者

## 🤖 虚拟模型组说明

### `auto:free` - 最便宜
优先选择成本最低的可用渠道，适合大量基础任务。

### `auto:fast` - 最快速  
优先选择推理速度最快的渠道，适合需要快速响应的场景。

### `auto:balanced` - 平衡
平衡成本、速度、质量三个因素，适合日常使用。

### `auto:premium` - 高质量
优先选择质量最高的模型，适合重要任务。

## 🔧 配置示例

### 基础配置（只启用Groq）
```yaml
channels:
  - id: "groq_llama3_8b"
    name: "Groq Llama3.1 8B"
    provider: "groq"
    model_name: "llama-3.1-8b-instant"
    api_key: "你的_GROQ_API_密钥"
    enabled: true  # 启用
```

### 多渠道配置
```yaml
channels:
  # 启用Groq (免费快速)
  - id: "groq_llama3_8b"
    enabled: true
    api_key: "你的_GROQ_API_密钥"
    
  # 启用Burn Hair (便宜好用)  
  - id: "burn_hair_gpt4o_mini"
    enabled: true
    api_key: "你的_BURN_HAIR_API_密钥"
    
  # 启用SiliconFlow (国内友好)
  - id: "siliconflow_qwen"
    enabled: true
    api_key: "你的_SILICONFLOW_API_密钥"
```

## 📊 测试配置

启动服务后可以通过以下方式测试：

### 健康检查
```bash
curl http://127.0.0.1:8000/health
```

### 聊天测试
```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto:fast",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### 可用模型列表
```bash
curl http://127.0.0.1:8000/v1/models
```

## ⚠️ 注意事项

1. **API密钥安全**: 配置文件包含敏感信息，已被gitignore忽略
2. **渠道启用**: 至少启用一个渠道才能正常工作
3. **预算控制**: 可以设置每日预算和单次请求成本限制
4. **错误处理**: 系统会自动重试和故障转移

## 🔗 相关链接

- **API文档**: http://127.0.0.1:8000/docs (启动服务后访问)
- **项目文档**: ../README.md
- **配置指南**: ../CONFIGURATION.md
- **开发进度**: ../TODO.md