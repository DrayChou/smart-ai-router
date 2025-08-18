# 🐳 Smart AI Router - Docker部署说明

## 🎯 简单部署

本项目提供了一个简单实用的Docker部署方案，适合个人使用。

## 🚀 快速开始

### 1. 准备配置文件

```bash
# 复制配置模板
cp config/router_config.yaml.template config/router_config.yaml
cp .env.example .env

# 编辑配置文件，填入你的API密钥
nano config/router_config.yaml
```

### 2. 启动服务

```bash
# 使用Docker Compose启动（推荐）
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 3. 验证部署

```bash
# 健康检查
curl http://localhost:7601/health

# 查看可用模型
curl http://localhost:7601/v1/models

# 测试聊天功能
curl -X POST http://localhost:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tag:free",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## 📁 目录结构

Docker部署会创建以下目录结构：

```
smart-ai-router/
├── config/           # 配置文件（只读挂载）
├── logs/            # 日志文件
├── cache/           # 缓存文件
├── .env             # 环境变量（只读挂载）
├── Dockerfile       # Docker镜像构建文件
├── docker-compose.yml # Docker编排配置
└── .dockerignore    # 构建上下文排除文件
```

## 🔧 配置说明

### 环境变量

通过 `.env` 文件配置系统环境变量：

```bash
# .env
JWT_SECRET=your-super-secret-jwt-key-here
LOG_LEVEL=INFO
DEBUG=false
```

### 主配置文件

通过 `config/router_config.yaml` 配置API密钥和路由策略：

```yaml
channels:
  - name: "groq-free"
    provider: "groq"
    api_key: "your-groq-api-key"
    enabled: true
```

## 🛠️ 自定义构建

### 手动构建镜像

```bash
# 构建镜像
docker build -t smart-ai-router .

# 运行容器
docker run -d \
  --name smart-ai-router \
  --restart unless-stopped \
  -p 7601:7601 \
  -v $(pwd)/config:/app/config:ro \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/cache:/app/cache \
  -v $(pwd)/.env:/app/.env:ro \
  smart-ai-router
```

## 🔍 故障排除

### 常见问题

**1. 配置文件未找到**
```bash
# 确保配置文件存在
ls -la config/router_config.yaml
ls -la .env
```

**2. 端口冲突**
```bash
# 检查端口占用
netstat -an | grep 7601

# 修改端口
docker run -p 8601:7601 ...
```

**3. 健康检查失败**
```bash
# 查看容器日志
docker logs smart-ai-router

# 手动检查服务
docker exec smart-ai-router curl localhost:7601/health
```

### 调试模式

```bash
# 交互式调试
docker exec -it smart-ai-router /bin/bash

# 查看实时日志
docker logs -f smart-ai-router
```

## 📊 性能特点

- **镜像大小**: ~200-300MB
- **启动时间**: ~10-30秒
- **内存使用**: ~50-100MB
- **安全性**: 非root用户运行
- **健康检查**: 自动监控服务状态

---

**💡 提示**: 个人使用建议直接使用 `docker-compose up -d` 启动，简单方便！