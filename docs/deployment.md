# 部署指南

## 部署方式概览

Smart AI Router 支持多种部署方式，从简单的本地开发到生产环境的容器化部署。

## 开发环境部署

### 环境要求
- Python 3.9+
- uv 包管理器
- SQLite (默认数据库)

### 快速开始
```bash
# 1. 克隆项目
git clone <your-repo-url>
cd smart-ai-router

# 2. 安装依赖
uv sync

# 3. 配置环境
cp .env.example .env
cp config/example.yaml config/config.yaml

# 4. 编辑环境变量
# vi .env  # 添加 JWT_SECRET 等必要配置

# 5. 启动开发服务器
uv run uvicorn main:app --host 0.0.0.0 --port 7601 --reload
```

## Docker 部署

### 单容器部署
```bash
# 构建镜像
docker build -t smart-ai-router .

# 运行容器
docker run -d \
  --name smart-ai-router \
  -p 7601:7601 \
  -e JWT_SECRET=your-secret-here \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  smart-ai-router
```

### Docker Compose 部署
```bash
# 使用 docker-compose
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## 生产环境部署

### 系统要求
- Linux 服务器 (Ubuntu 20.04+ / CentOS 8+)
- Python 3.9+
- PostgreSQL 13+ (推荐)
- Redis 6+ (可选，用于缓存)
- Nginx (反向代理)

### 数据库配置
```bash
# PostgreSQL 安装和配置
sudo apt update
sudo apt install postgresql postgresql-contrib

# 创建数据库和用户
sudo -u postgres createdb smart_router
sudo -u postgres createuser --interactive smart_router_user
```

### 环境变量配置
```bash
# 生产环境 .env
JWT_SECRET=your-production-secret-key
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/smart_router
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
DEBUG=false
```

### 服务配置 (systemd)
```ini
# /etc/systemd/system/smart-ai-router.service
[Unit]
Description=Smart AI Router Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/smart-ai-router
ExecStart=/opt/smart-ai-router/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 7601
Restart=always

[Install]
WantedBy=multi-user.target
```

### Nginx 反向代理
```nginx
# /etc/nginx/sites-available/smart-ai-router
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:7601;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 支持流式响应
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

## Kubernetes 部署

### 基本部署清单
```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: smart-ai-router
spec:
  replicas: 3
  selector:
    matchLabels:
      app: smart-ai-router
  template:
    metadata:
      labels:
        app: smart-ai-router
    spec:
      containers:
      - name: smart-ai-router
        image: smart-ai-router:latest
        ports:
        - containerPort: 7601
        env:
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: smart-ai-router-secrets
              key: jwt-secret
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: smart-ai-router-secrets
              key: database-url
```

### 服务暴露
```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: smart-ai-router-service
spec:
  selector:
    app: smart-ai-router
  ports:
  - protocol: TCP
    port: 80
    targetPort: 7601
  type: LoadBalancer
```

## 监控和维护

### 日志管理
```bash
# 查看应用日志
tail -f logs/smart-router.log

# 使用 journalctl (systemd)
journalctl -u smart-ai-router.service -f
```

### 性能监控
- CPU 和内存使用率
- API 响应时间
- 数据库连接池状态
- 渠道健康状态

### 备份策略
```bash
# 数据库备份
pg_dump smart_router > backup_$(date +%Y%m%d).sql

# 配置文件备份
tar -czf config_backup_$(date +%Y%m%d).tar.gz config/
```

## 安全配置

### 防火墙设置
```bash
# 仅开放必要端口
ufw allow 22    # SSH
ufw allow 80    # HTTP
ufw allow 443   # HTTPS
ufw enable
```

### SSL/TLS 配置
```bash
# 使用 Let's Encrypt
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## 故障排除

### 常见问题

1. **数据库连接失败**
   - 检查 DATABASE_URL 配置
   - 确认数据库服务状态
   - 验证网络连通性

2. **API 请求超时**
   - 检查Provider API密钥有效性
   - 调整超时配置
   - 查看渠道健康状态

3. **内存不足**
   - 增加服务器内存
   - 调整数据库连接池大小
   - 启用Redis缓存

### 日志分析
```bash
# 错误日志分析
grep "ERROR" logs/smart-router.log | tail -20

# 性能分析
grep "latency" logs/smart-router.log | awk '{print $NF}' | sort -n
```