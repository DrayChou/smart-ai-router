#!/bin/bash
# Smart AI Router - 自动重建并运行 Docker 容器
# Bash 脚本 (Linux/macOS)

echo "🔄 Smart AI Router - 自动重建并运行"
echo "================================="

# Function to detect docker-compose command
get_docker_compose_command() {
    # Try 'docker compose' first (newer syntax)
    if docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    else
        # Fall back to 'docker-compose' (legacy syntax)
        echo "docker-compose"
    fi
}

# 检查 Docker 是否运行
if ! docker version >/dev/null 2>&1; then
    echo "❌ Docker 未运行或未安装，请先启动 Docker"
    exit 1
fi
echo "✅ Docker 运行正常"

DOCKER_CMD=$(get_docker_compose_command)
echo "ℹ️  使用命令: $DOCKER_CMD"

# 停止并删除现有容器
echo "🛑 停止并删除现有容器..."
if $DOCKER_CMD down >/dev/null 2>&1; then
    echo "✅ 现有容器已停止"
else
    echo "ℹ️  没有运行中的容器"
fi

# 删除镜像（强制重建）
echo "🗑️  删除现有镜像..."
if docker rmi smart-ai-router-smart-ai-router >/dev/null 2>&1; then
    echo "✅ 现有镜像已删除"
else
    echo "ℹ️  没有找到现有镜像"
fi

# 清理 Docker 缓存
echo "🧹 清理 Docker 构建缓存..."
docker builder prune -f >/dev/null 2>&1
echo "✅ 构建缓存已清理"

# 重新构建镜像
echo "🔨 重新构建 Docker 镜像..."
if $DOCKER_CMD build --no-cache --progress=plain; then
    echo "✅ 镜像构建成功"
else
    echo "❌ 镜像构建失败"
    exit 1
fi

# 启动容器
echo "🚀 启动容器..."
if $DOCKER_CMD up -d; then
    echo "✅ 容器启动成功"
else
    echo "❌ 容器启动失败"
    exit 1
fi

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5

# 检查容器状态
echo "📊 检查容器状态..."
$DOCKER_CMD ps

# 显示日志（最近50行）
echo "📝 显示最近日志:"
$DOCKER_CMD logs --tail=50

echo ""
echo "🎉 完成！服务已在 http://localhost:7601 启动"
echo "📋 有用的命令:"
echo "   $DOCKER_CMD logs -f    # 查看实时日志"
echo "   $DOCKER_CMD down       # 停止服务"
echo "   $DOCKER_CMD ps         # 查看容器状态"
echo "   curl http://localhost:7601/health  # 健康检查"