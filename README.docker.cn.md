# Smart AI Router - 国内 Docker 部署指南

## 国内镜像优化版本

为了解决国内用户在构建 Docker 镜像时遇到的网络问题，我们提供了专门针对国内网络环境优化的 Docker 配置文件。

## 优化特性

### 🚀 镜像源优化

- **Docker 基础镜像**: 使用道云镜像 `docker.m.daocloud.io/library/python:3.11-slim`
- **APT 镜像源**: 使用阿里云 Debian 镜像源
- **PyPI 镜像源**: 使用清华大学 PyPI 镜像源
- **智能源切换**: HTTP→HTTPS 升级策略，避免证书验证问题

### 🛡️ 安全优化

- **HTTP→HTTPS 升级策略**: 先用 HTTP 源安装 ca-certificates，再升级为 HTTPS 源
- **最小权限原则**: 创建非 root 用户运行应用
- **依赖层缓存**: 优化构建缓存，减少重复下载

## 快速部署

### 1. 使用 Docker Compose（推荐）

```bash
# 克隆项目
git clone <your-repo>
cd smart-ai-router

# 复制配置文件
copy .env.example .env
copy config\example.yaml config\config.yaml

# 使用国内优化版启动
docker-compose -f docker-compose.cn.yml up -d

# 查看日志
docker-compose -f docker-compose.cn.yml logs -f
```

### 2. 直接使用 Docker

```bash
# 构建国内优化镜像
docker build -f Dockerfile.cn -t smart-ai-router:cn-latest .

# 运行容器
docker run -d \
  --name smart-ai-router-cn \
  -p 7601:7601 \
  -v ./config:/app/config:ro \
  -v ./logs:/app/logs \
  -v ./cache:/app/cache \
  -v ./.env:/app/.env:ro \
  smart-ai-router:cn-latest
```

## 镜像源说明

### Docker Hub 镜像源

- **原版**: `python:3.11-slim`
- **国内版**: `docker.m.daocloud.io/library/python:3.11-slim`

### APT 镜像源（阿里云）

```
deb https://mirrors.aliyun.com/debian/ bookworm main contrib non-free non-free-firmware
deb https://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free non-free-firmware
deb https://mirrors.aliyun.com/debian-security bookworm-security main contrib non-free non-free-firmware
```

### PyPI 镜像源（清华大学）

```
https://pypi.tuna.tsinghua.edu.cn/simple
```

## 构建性能对比

| 镜像版本 | 基础镜像下载 | 系统包安装 | Python 包安装 | 总构建时间 |
| -------- | ------------ | ---------- | ------------- | ---------- |
| 原版     | ~2-5 分钟    | ~1-3 分钟  | ~2-5 分钟     | ~5-13 分钟 |
| 国内版   | ~30-60 秒    | ~20-40 秒  | ~30-60 秒     | ~1-3 分钟  |

## 故障排除

### 镜像拉取失败

```bash
# 手动配置 Docker 镜像加速器
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<-'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://hub-mirror.c.163.com",
    "https://mirror.baidubce.com"
  ]
}
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
```

### APT 源访问问题

如果构建过程中出现 APT 源访问问题，可以尝试其他国内镜像源：

- 清华大学：`mirrors.tuna.tsinghua.edu.cn`
- 中科大：`mirrors.ustc.edu.cn`
- 网易：`mirrors.163.com`

### PyPI 源访问问题

如果 PyPI 源访问有问题，可以尝试其他镜像：

- 阿里云：`mirrors.aliyun.com/pypi/simple/`
- 豆瓣：`pypi.douban.com/simple/`
- 中科大：`pypi.mirrors.ustc.edu.cn/simple/`

## 与原版的差异

| 配置项   | 原版               | 国内优化版                                      |
| -------- | ------------------ | ----------------------------------------------- |
| 基础镜像 | `python:3.11-slim` | `docker.m.daocloud.io/library/python:3.11-slim` |
| APT 源   | 官方源             | 阿里云镜像源                                    |
| PyPI 源  | 官方源             | 清华大学镜像源                                  |
| 构建策略 | 标准构建           | HTTP→HTTPS 升级策略                             |
| 容器名称 | `smart-ai-router`  | `smart-ai-router-cn`                            |

## 生产环境建议

1. **镜像版本管理**: 建议为国内版本打上专门的标签
2. **镜像仓库**: 考虑推送到阿里云、腾讯云等国内容器镜像仓库
3. **网络优化**: 生产环境可配置企业级镜像代理
4. **监控告警**: 添加构建时间和成功率监控

## 技术支持

如果在使用国内优化版本时遇到问题，请提供以下信息：

- 操作系统版本
- Docker 版本
- 网络环境（是否使用代理）
- 完整的错误日志

祝使用愉快！🚀
