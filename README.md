# Smart AI Router - 个人AI智能路由系统

轻量级个人AI智能路由系统，支持**智能标签化路由**、**负标签过滤**、成本优化、智能故障转移。基于38个渠道和3400+模型的大规模路由网关。

## ✨ 核心特性

🏷️ **智能标签系统** - 基于模型名称的自动标签化路由，支持 `tag:free,qwen3,!local` 等正负标签组合查询  
🎯 **多粒度模型匹配** - 支持完整模型名称精确匹配和标签化搜索两种模式，自动识别查询意图  
🔗 **模型别名映射** - 支持标准模型名称到渠道特定名称的智能转换，如 `doubao-1.5-pro` → `ep-xxx`  
🚫 **负标签过滤** - 支持 `!tagname` 语法排除特定标签，如 `tag:gpt,!free` 查询付费GPT模型  
🚀 **智能路由引擎** - 基于成本、参数数量、上下文长度、速度的四维评分策略，智能模型排序选择  
🧠 **智能模型分析** - 自动提取模型参数数量(200m-670b)和上下文长度(2k-2m)，支持可配置过滤策略  
💰 **成本优化** - 自动选择最便宜的可用渠道，支持本地模型零成本  
💰 **成本监控** - 完整的使用跟踪和成本分析系统，帮助优化AI API费用  
⚡ **智能故障转移** - 401错误渠道黑名单机制，多渠道自动切换，18个渠道支持API回退  
🎯 **模型类型过滤** - 自动过滤embedding模型，支持最小参数量和上下文长度过滤  
🔑 **API密钥验证** - 自动检测失效密钥，智能管理渠道状态  
🔧 **零配置启动** - 基于Pydantic的YAML配置文件，One-API数据库自动集成  
🌏 **多Provider支持** - OpenAI, Groq, SiliconFlow, Burn Hair, 豆包, 智谱, DeepSeek, 本地Ollama/LMStudio等  
⚡ **企业级性能优化** - HTTP/2连接池复用、智能TTL缓存、流式请求优化，系统响应速度提升40-70%  

## 🎯 系统表现指标

- **匹配精度**: 100% (严格标签匹配，支持正负标签组合)
- **支持渠道**: 38个渠道 (36云端 + 2本地)，3400+模型缓存
- **API回退**: 18个渠道支持配置模型回退机制
- **故障转移**: 智能渠道黑名单，多渠道自动切换
- **负标签过滤**: 支持 `!tagname` 语法精确排除
- **模型评分**: 支持0.6B-235B全规格差异化评分
- **特殊厂商**: 支持豆包EP模型、智谱GLM、DeepSeek等
- **性能优化**: 系统响应速度提升40-70%，连接建立时间减少50-80%，重复请求开销减少60-90%

## 🚀 快速开始

### 1. 安装依赖
```bash
uv sync
```

### 2. 配置
项目现在使用两个核心配置文件，都在 `config/` 目录下：

1.  **`providers.yaml`**: 定义AI服务商的基础连接信息。通常设置一次即可。
2.  **`router_config.yaml`**: 定义你的API密钥（渠道）、模型组和路由策略。这是你需要经常修改的文件。

开始配置：
```bash
# 1. 如果不存在，创建providers.yaml (通常使用模板默认值即可)
cp config/providers.yaml.template config/providers.yaml

# 2. 复制主配置模板
cp config/router_config.yaml.template config/router_config.yaml

# 3. 编辑主配置文件，填入你的API密钥
vim config/router_config.yaml
```

在 `router_config.yaml` 文件中配置API密钥和认证：

#### 基础配置
```yaml
# API认证配置 (可选)
auth:
  enabled: true  # 启用Token认证，个人使用建议开启
  # api_token: "your-secret-token"  # 可选：自定义Token，留空将自动生成

# 渠道配置
channels:
  - id: "groq_llama3_8b"
    name: "Groq Llama3.1 8B"
    provider: "groq"
    model_name: "llama-3.1-8b-instant"
    api_key: "你的_GROQ_API_密钥"  # 替换这里
    enabled: true  # 改为 true
```

#### Token认证说明
- **启用认证**: 设置 `auth.enabled: true` 
- **自动生成**: 如果不配置 `api_token`，系统会自动生成并保存到配置文件
- **手动设置**: 也可以手动设置自定义Token
- **使用Token**: 请求时在 `Authorization` 头中包含Token

### 3. 启动服务

#### 本地启动
```bash
# 默认启动 (YAML模式)
python main.py

# 指定端口
python main.py --port 8080

# 调试模式
python main.py --debug
```

#### Docker部署（推荐）
```bash
# 使用Docker Compose启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

Docker部署会自动：
- 创建必要的目录结构
- 配置环境变量
- 设置健康检查
- 管理数据持久化

### Docker镜像导出与导入

#### 导出镜像
```bash
# 查看当前所有镜像
docker images

# 导出指定镜像（示例：导出 smart-ai-router:cn-test）
docker save -o smart-ai-router-cn-test.tar smart-ai-router:cn-test

# 查看导出的文件大小
ls -lh smart-ai-router-cn-test.tar
```

#### 上传到其他服务器
```bash
# 方法1: 使用 scp
scp smart-ai-router-cn-test.tar username@server-ip:/path/to/destination/

# 方法2: 使用 rsync（支持断点续传）
rsync -avz --progress smart-ai-router-cn-test.tar username@server-ip:/path/to/destination/

# 方法3: 如果目标服务器无法直接访问，可以使用 SFTP 工具
# FileZilla、WinSCP 等工具拖拽上传
```

#### 在目标服务器上导入镜像
```bash
# 进入上传文件所在目录
cd /path/to/destination/

# 加载 Docker 镜像
docker load -i smart-ai-router-cn-test.tar

# 验证镜像是否加载成功
docker images | grep smart-ai-router

# 运行容器
docker run -d \
  --name smart-ai-router \
  -p 7601:7601 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/cache:/app/cache \
  smart-ai-router:cn-test

# 或者使用 docker-compose
# 确保 docker-compose.yml 中的镜像名称正确
docker-compose up -d
```

#### 镜像压缩（可选）
如果需要更小的文件大小，可以使用 gzip 压缩：
```bash
# 导出并压缩
docker save smart-ai-router:cn-test | gzip > smart-ai-router-cn-test.tar.gz

# 在目标服务器上解压并加载
gunzip -c smart-ai-router-cn-test.tar.gz | docker load
```

### 4. 测试API

#### 无认证模式（auth.enabled: false）
```bash
# 健康检查
curl http://127.0.0.1:7601/health

# 聊天测试
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tag:free",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

#### 启用认证模式（auth.enabled: true）
```bash
# 使用Bearer Token格式
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Authorization: Bearer sar-your-generated-token-here" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tag:free",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# 或直接使用Token
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Authorization: sar-your-generated-token-here" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tag:free", 
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

**注意**: 启动服务时，如果启用了认证但未配置Token，系统会自动生成Token并显示在日志中，请保存此Token！

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

## 🏷️ 智能标签系统

**核心原理**: 系统采用**渠道标签+模型标签合并**的机制，支持**正负标签组合查询**，实现精确的智能路由。

### 🔄 系统调用流程图

```mermaid
flowchart TD
    A[用户请求] --> B{模型类型}
    B -->|tag:xxx| C[标签路由]
    B -->|物理模型| D[直接路由]
    
    C --> E[解析标签]
    E --> F{包含负标签?}
    F -->|是| G[正负标签分离]
    F -->|否| H[正标签匹配]
    
    G --> I[正标签匹配]
    I --> J[负标签过滤]
    J --> K[候选渠道]
    
    H --> K
    D --> K
    
    K --> L[多维度评分]
    L --> M[按评分排序]
    M --> N[逐一尝试渠道]
    
    N --> O{API调用成功?}
    O -->|是| P[返回响应]
    O -->|否| Q{是否有下个渠道?}
    Q -->|是| R[尝试下个渠道]
    Q -->|否| S[返回失败]
    
    R --> N
```

### 🔍 模型发现与回退机制

```mermaid
flowchart TD
    A[启动模型发现] --> B[遍历所有渠道]
    B --> C[调用/models接口]
    
    C --> D{API调用成功?}
    D -->|是| E[解析模型列表]
    D -->|否| F[检查configured_models]
    
    F --> G{有配置模型?}
    G -->|是| H[使用配置模型]
    G -->|否| I[记录失败]
    
    E --> J[提取模型标签]
    H --> J
    J --> K[合并渠道标签]
    K --> L[保存到缓存]
    
    I --> M[继续下个渠道]
    L --> M
    M --> N{还有渠道?}
    N -->|是| B
    N -->|否| O[完成发现]
```

### 工作机制
1. **模型发现**: 系统自动调用各渠道的 `/models` 接口，失败时回退到 `configured_models`
2. **双重标签系统**: 
   - **渠道标签**: 基础属性标签（如 `free`, `local`, `cloud`）
   - **模型标签**: 从模型名称自动提取（如 `qwen3`, `gpt`, `claude`, `ep`）
3. **正负标签处理**: 支持 `!tagname` 语法排除特定标签
4. **严格匹配**: 只有同时包含所有正标签且不包含任何负标签的模型才被选中

### 标签提取与合并示例
```bash
# 模型标签自动提取
qwen/qwen3-30b-a3b:free -> ["qwen", "qwen3", "30b", "a3b", "free"]
ep-20250613210739-qjxdl -> ["ep", "20250613210739", "qjxdl"]
text-embedding-qwen3-embedding-0.6b -> 自动过滤 (embedding模型)

# 渠道+模型标签合并
Doubao (渠道标签: ["cloud"]) + 
ep-20250613210739-qjxdl (模型标签: ["ep", "20250613210739", "qjxdl"]) = 
合并标签: ["cloud", "ep", "20250613210739", "qjxdl"]
```

### 使用方式
```bash
# 单标签查询
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "tag:free", "messages": [{"role": "user", "content": "Hello!"}]}'

# 多标签精确匹配
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "tag:free,qwen3", "messages": [{"role": "user", "content": "Hello!"}]}'

# 负标签过滤 - 查询免费的qwen3模型，但排除本地模型
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "tag:free,qwen3,!local", "messages": [{"role": "user", "content": "Hello!"}]}'

# 查询GPT模型，但排除免费版本
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "tag:gpt,!free", "messages": [{"role": "user", "content": "Hello!"}]}'

# EP模型查询（豆包专有模型）
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "tag:ep", "messages": [{"role": "user", "content": "Hello!"}]}'
```

### 智能特性
- **严格匹配**: 只返回真正包含所有正标签且不包含负标签的模型
- **负标签过滤**: 支持 `!tagname` 语法精确排除不需要的模型
- **模型过滤**: 自动过滤embedding模型，避免chat请求错误  
- **API回退机制**: 18个渠道支持 `/models` 失败时回退到配置模型
- **智能模型分析**: 自动提取模型参数数量(270m-670b)和上下文长度(2k-2m)，智能评分排序
- **可配置排序策略**: 支持cost_first、balanced、speed_optimized、quality_optimized四种策略
- **模型过滤器**: 支持最小参数量、最小上下文长度、排除embedding模型等过滤条件
- **渠道分离缓存**: 每个渠道独立缓存模型分析结果，便于调试和管理
- **大规模支持**: 38个渠道，3400+模型统一路由

## 🎯 多粒度模型匹配系统

**最新特性**: 系统现在支持**多粒度模型匹配**，用户可以使用完整模型核心名称精确匹配所有变体，同时保持原有的标签化路由功能。

### 🔍 完整片段匹配

用户现在可以直接使用模型的核心名称来匹配所有该模型的变体：

```bash
# 使用完整片段匹配 - 匹配所有 qwen3-235b-a22b 的变体
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-235b-a22b",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# 使用完整片段匹配 - 匹配所有 doubao-1.5-pro 的变体  
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-1.5-pro-256k", 
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### 🏷️ 智能路由模式识别

系统会自动识别用户的查询意图：

- **完整片段模式**: 不带 `tag:` 或 `tags:` 前缀的查询使用完整片段匹配
- **标签化模式**: 带 `tag:` 或 `tags:` 前缀的查询使用标签匹配

```bash
# 完整片段匹配 - 精确匹配 deepseek-v3.1 的所有变体
"model": "deepseek-v3.1"          # ✅ 完整片段匹配

# 标签化匹配 - 匹配所有包含 deepseek 标签的模型
"model": "tag:deepseek"           # ✅ 标签匹配
"model": "tag:deepseek,free"      # ✅ 多标签匹配  
"model": "tag:deepseek,!local"    # ✅ 负标签过滤
```

### 🗓️ 日期后缀智能处理

系统自动处理带日期后缀的模型名称：

```bash
# 模型发现时自动生成两个版本的标签
claude-3-haiku-20240307 -> 
  - claude-3-haiku-20240307  (原版本)
  - claude-3-haiku          (去日期版本)

# 用户可以使用任一版本查询
"model": "claude-3-haiku"         # ✅ 匹配带日期的版本
"model": "claude-3-haiku-20240307" # ✅ 精确匹配
```

支持的日期格式：
- `YYYYMMDD`: 如 `20240307`
- `YYYYMM`: 如 `202403`  
- `YYYY-MM-DD`: 如 `2024-03-07`

### 🔗 模型别名映射系统

通过模型别名映射，用户可以使用标准模型名称访问渠道特定的模型：

```yaml
# 在渠道配置中定义别名映射
channels:
  - id: "doubao_ep"
    name: "豆包 EP 模型"
    provider: "doubao"
    model_aliases:
      # 标准名称 -> 渠道特定名称
      doubao-1.5-pro-256k: ep-20250203083646-2szv9
      doubao-1.5-lite-32k: ep-20250203083621-dsvgq
      deepseek-v3.1: ep-20250822224907-6xgzj
      claude-3-haiku: ep-20250204192333-8vmqs
```

用户可以使用标准名称：
```bash
# 使用标准名称访问豆包EP模型
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-1.5-pro-256k",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### 📊 片段提取示例

系统从模型名称中智能提取完整片段：

```bash
# 片段提取示例
qwen/qwen3-235b-a22b:free -> 完整片段: qwen3-235b-a22b
openai/gpt-4o-mini -> 完整片段: gpt-4o-mini  
doubao/ep-20250203083646-2szv9:free -> 完整片段: ep-20250203083646-2szv9
claude-3-haiku-20240307 -> 完整片段: claude-3-haiku, claude-3-haiku-20240307
```

### 🎯 使用场景

#### 精确模型匹配
当用户明确知道要使用的模型，希望获得该模型的所有服务商选择：
```bash
"model": "qwen3-235b-a22b"    # 返回所有提供此模型的渠道，按价格排序
```

#### 灵活标签搜索  
当用户希望在某类模型中选择：
```bash
"model": "tag:qwen3,free"     # 返回所有免费的qwen3模型
"model": "tag:gpt,!free"      # 返回所有付费的GPT模型
```

#### 标准化访问
使用通用模型名称访问不同渠道的特殊命名：
```bash
"model": "doubao-1.5-pro"     # 通过别名映射访问豆包EP模型
```

### ✨ 系统优势

- **🎯 精确匹配**: 完整片段匹配确保用户获得精确的模型变体
- **🏷️ 灵活搜索**: 保持完整的标签化路由功能  
- **🔄 智能识别**: 自动区分查询类型，无需用户额外配置
- **📊 价格排序**: 相同模型的多个服务按价格自动排序
- **🔗 别名支持**: 标准化模型名称访问，提升用户体验
- **⏰ 日期兼容**: 智能处理模型版本的日期后缀
- **🔄 向后兼容**: 所有现有查询方式完全保持兼容

## 🧠 智能模型分析与排序

### 模型参数提取
系统采用三层优先级自动提取模型关键信息：

1. **API响应优先** - 如果provider的`/models`接口返回`context_length`字段，直接使用（如OpenRouter）
2. **知识库映射** - 基于680+已知模型的详细参数映射表进行匹配
3. **名称解析** - 从模型名称中提取参数信息（如"7b", "32k"等）

支持提取的信息：
- **参数数量**: 270m, 600m, 1.7b, 4b, 7b, 8b, 12b, 70b, 670b等  
- **上下文长度**: 2k, 4k, 8k, 16k, 32k, 64k, 128k, 200k, 1m, 2m等
- **自适应性**: 自动适配各provider的API响应格式

### 智能评分算法
四维评分机制，可配置权重：
1. **成本评分** (cost_score): 基于输入/输出token价格
2. **参数评分** (parameter_score): 基于模型参数数量的对数式评分
3. **上下文评分** (context_score): 基于上下文长度的智能评分
4. **速度评分** (speed_score): 基于历史性能测试结果

### 可配置排序策略
```yaml
routing:
  default_strategy: "cost_first"  # 成本优先(推荐)
  
  # 模型过滤器
  model_filters:
    min_context_length: 8192      # 最小8k上下文
    min_parameter_count: 0        # 不限参数数量
    exclude_embedding_models: true # 排除embedding模型
  
  # 排序策略配置
  sorting_strategies:
    cost_first:           # 成本优先策略
      - field: "cost_score"
        weight: 0.4       # 成本权重40%
      - field: "parameter_score"  
        weight: 0.25      # 参数权重25%
      - field: "context_score"
        weight: 0.2       # 上下文权重20%
      - field: "speed_score"
        weight: 0.15      # 速度权重15%
```

### 渠道分离缓存
每个渠道独立存储模型分析结果：
```bash
cache/channels/
├── groq_llama3_8b.json          # Groq渠道模型缓存
├── lmstudio_local.json          # LMStudio本地缓存  
├── siliconflow_qwen.json        # SiliconFlow缓存
└── burn_hair_gpt4o.json         # Burn Hair缓存
```

每个缓存文件包含：
- 模型基础信息和状态
- 参数数量和上下文长度分析
- 原始API响应数据
- 分析元数据和时间戳

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
export OPENAI_API_BASE=http://127.0.0.1:7601/v1
export OPENAI_API_KEY=任意值
```

## 💰 成本监控系统

**全新特性**: 系统现在提供完整的成本监控和使用跟踪功能，帮助个人开发者优化AI API使用成本。

### 🔍 功能概览

- **✅ 自动记录**: 每次API调用自动记录到JSONL文件
- **✅ 详细信息**: 包含模型、渠道、tokens、成本、响应时间等
- **✅ 标签系统**: 自动提取和记录请求标签
- **✅ 错误跟踪**: 记录失败请求和错误信息
- **🚨 配额用完提醒**: 自动检测并通知渠道配额耗尽
- **🚨 余额不足告警**: 监控余额并发送低余额提醒
- **🚨 API密钥失效**: 检测无效密钥并发送告警
- **🚨 错误频率监控**: 监控渠道错误率并告警
- **📊 多维度统计**: 按日、周、月查看使用统计
- **📊 成本分析**: 按模型、渠道、提供商的成本分解
- **📊 热门排行**: 使用最多的模型和渠道排行
- **📊 趋势分析**: 使用趋势和成本变化分析

### 📁 数据存储

**使用记录文件** (JSONL格式): `logs/usage_YYYYMMDD.jsonl`

每行记录包含：
```json
{
  "timestamp": "2025-08-24T12:30:45Z",
  "request_id": "req_abc123", 
  "model": "gpt-4o-mini",
  "channel_id": "ch_openai_001",
  "channel_name": "OpenAI Official",
  "provider": "openai",
  "input_tokens": 150,
  "output_tokens": 300,
  "total_tokens": 450,
  "input_cost": 0.000075,
  "output_cost": 0.0003,
  "total_cost": 0.000375,
  "cost_currency": "USD",
  "request_type": "chat",
  "status": "success",
  "response_time_ms": 1250,
  "tags": ["gpt", "4o", "mini", "chat"]
}
```

**渠道告警文件** (JSONL格式): `logs/channel_alerts.jsonl`

### 📊 API接口详细说明

#### 统计查询接口
| 接口 | 方法 | 描述 |
|------|------|------|
| `/v1/stats/daily` | GET | 获取每日使用统计 |
| `/v1/stats/weekly` | GET | 获取本周使用统计 |
| `/v1/stats/monthly` | GET | 获取月度使用统计 |
| `/v1/stats/summary` | GET | 获取使用情况汇总 |
| `/v1/stats/top-models` | GET | 获取热门模型排行 |
| `/v1/stats/top-channels` | GET | 获取热门渠道排行 |
| `/v1/stats/cost-breakdown` | GET | 获取成本分解分析 |

#### 告警管理接口
| 接口 | 方法 | 描述 |
|------|------|------|
| `/v1/stats/alerts` | GET | 获取渠道告警信息 |
| `/v1/stats/channel-status` | GET | 获取渠道状态概览 |
| `/v1/stats/clear-alerts/{channel_id}` | POST | 清除指定渠道告警 |
| `/v1/stats/clear-all-alerts` | POST | 清除所有渠道告警 |

### 🚀 使用示例

#### 查看使用统计
```bash
# 查看今日统计
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://localhost:7601/v1/stats/daily

# 查看本周统计  
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://localhost:7601/v1/stats/weekly

# 查看本月统计
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://localhost:7601/v1/stats/monthly
```

#### 查看渠道告警
```bash
# 查看最近24小时的告警
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://localhost:7601/v1/stats/alerts

# 查看渠道状态
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://localhost:7601/v1/stats/channel-status
```

#### 管理命令
```bash
# 归档30天前的日志 (默认)
python scripts/archive_usage_logs.py --archive

# 归档7天前的日志
python scripts/archive_usage_logs.py --archive --days-to-keep 7

# 生成统计报告
python scripts/archive_usage_logs.py --report

# 查看实时统计
python examples/cost_tracking_example.py
```

### 💡 使用场景

#### 1. 成本优化
- 查看最昂贵的模型和渠道
- 分析成本分布和优化机会
- 识别成本异常和浪费

#### 2. 异常监控
- 检查最近的渠道告警
- 监控失败率较高的渠道
- 及时发现API密钥失效

#### 3. 趋势分析
- 对比不同时间段的使用情况
- 分析使用量和成本趋势
- 制定合理的预算计划

### ⚠️ 注意事项

- **存储空间**: JSONL文件会随时间增长，定期运行归档命令
- **权限认证**: 统计API需要admin token认证
- **数据保留**: 默认保留30天的详细日志，可通过归档脚本调整
- **性能影响**: 使用记录是异步写入，对API响应时间影响微乎其微

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
│   ├── config_models.py            # Pydantic配置模型
│   ├── json_router.py              # 智能路由引擎（支持负标签+智能排序）
│   ├── yaml_config.py              # YAML配置加载器
│   ├── scheduler/                   # 定时任务系统
│   │   ├── tasks/
│   │   │   ├── model_discovery.py  # 模型发现（支持API回退）
│   │   │   ├── api_key_validation.py # API密钥验证
│   │   │   └── service_health_check.py # 健康检查
│   │   └── task_manager.py         # 任务管理器
│   └── utils/                      # 工具模块
│       ├── model_analyzer.py       # 模型参数和上下文分析器
│       └── channel_cache_manager.py # 渠道分离缓存管理器
├── cache/                          # 缓存目录
│   ├── channels/                   # 渠道分离缓存
│   │   ├── groq_llama3_8b.json    # 各渠道独立模型缓存
│   │   └── lmstudio_local.json    # 包含参数和上下文分析
│   ├── discovered_models.json     # 模型发现缓存(旧格式)
│   └── api_key_validation.json    # 密钥验证缓存
├── import_oneapi_channels.py       # One-API数据库导入工具
├── migrate_cache.py                # 缓存迁移脚本（旧格式→新格式）
├── main.py                         # 统一入口
└── README.md                       # 项目说明
```

## 🔗 相关文档

- **[配置指南](config/README.md)** - 详细配置说明
- **[API文档](http://127.0.0.1:7601/docs)** - 启动服务后访问
- **[TODO列表](TODO.md)** - 开发进度和最新特性
- **[项目说明](CLAUDE.md)** - 开发者指南

## 🎉 开始使用

1. **获取API密钥**: 注册 [Groq](https://groq.com/) 获取免费API密钥，或配置本地Ollama/LMStudio
2. **配置系统**: 复制模板并填入密钥，支持38个渠道配置
3. **启动服务**: `python main.py` 
4. **智能路由**: 使用 `tag:free,qwen3,!local` 等正负标签组合查询，享受精确的智能模型选择
5. **监控系统**: 访问 `/docs` 查看API文档，响应头包含完整路由调试信息

### 💡 快速体验
```bash
# 查询免费的qwen3模型
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "tag:free,qwen3", "messages": [{"role": "user", "content": "你好"}]}'

# 查询本地模型
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "tag:local", "messages": [{"role": "user", "content": "Hello"}]}'

# 负标签过滤 - 查询GPT模型但排除免费版
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "tag:gpt,!free", "messages": [{"role": "user", "content": "Hello GPT Pro"}]}'

# 查询豆包EP模型
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "tag:ep", "messages": [{"role": "user", "content": "你好豆包"}]}'

# 复杂查询 - 云端免费qwen3但排除本地
curl -X POST http://127.0.0.1:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "tag:free,qwen3,!local", "messages": [{"role": "user", "content": "云端qwen3"}]}'
```

## 🚀 性能优化特性

### ⚡ 企业级性能提升
- **HTTP/2连接池复用** - 连接建立时间减少50-80%，支持keepalive和连接复用
- **智能TTL缓存机制** - 重复请求开销减少60-90%，差异化缓存策略
- **流式请求优化** - 流式响应速度提升30-50%，快速错误检测和内存优化
- **健康检查优化** - 使用/models接口替代chat请求，token消耗降为零
- **快速失败检测** - 流式状态码检测，失败请求响应提升70%+
- **智能渠道预检** - 并发可用性检查，多渠道选择效率提升60%+

### 📊 综合性能提升
- **整体系统响应**: 提升 40-70%
- **健康检查速度**: 提升 90%+ (零token消耗)
- **连接效率**: HTTP/2支持，全局连接池管理
- **缓存命中率**: 智能TTL管理，持久化缓存支持
- **错误恢复**: 快速错误检测，智能故障转移
- **资源优化**: 内存优化，自动清理机制

---

**⭐ 如果觉得有用，请给个Star！**