# Smart AI Router - 自动重建并运行 Docker 容器
# PowerShell 脚本 (Windows)

Write-Host "🔄 Smart AI Router - 自动重建并运行" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Green

# 检查 Docker 是否运行
try {
    docker version | Out-Null
    Write-Host "✅ Docker 运行正常" -ForegroundColor Green
}
catch {
    Write-Host "❌ Docker 未运行或未安装，请先启动 Docker" -ForegroundColor Red
    exit 1
}

# 停止并删除现有容器
Write-Host "🛑 停止并删除现有容器..." -ForegroundColor Yellow
docker-compose down 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 现有容器已停止" -ForegroundColor Green
} else {
    Write-Host "ℹ️  没有运行中的容器" -ForegroundColor Blue
}

# 删除镜像（强制重建）
Write-Host "🗑️  删除现有镜像..." -ForegroundColor Yellow
docker rmi smart-ai-router-smart-ai-router 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 现有镜像已删除" -ForegroundColor Green
} else {
    Write-Host "ℹ️  没有找到现有镜像" -ForegroundColor Blue
}

# 清理 Docker 缓存
Write-Host "🧹 清理 Docker 构建缓存..." -ForegroundColor Yellow
docker builder prune -f
Write-Host "✅ 构建缓存已清理" -ForegroundColor Green

# 重新构建镜像
Write-Host "🔨 重新构建 Docker 镜像..." -ForegroundColor Yellow
docker-compose build --no-cache --progress=plain
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 镜像构建成功" -ForegroundColor Green
} else {
    Write-Host "❌ 镜像构建失败" -ForegroundColor Red
    exit 1
}

# 启动容器
Write-Host "🚀 启动容器..." -ForegroundColor Yellow
docker-compose up -d
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 容器启动成功" -ForegroundColor Green
} else {
    Write-Host "❌ 容器启动失败" -ForegroundColor Red
    exit 1
}

# 等待服务启动
Write-Host "⏳ 等待服务启动..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# 检查容器状态
Write-Host "📊 检查容器状态..." -ForegroundColor Yellow
docker-compose ps

# 显示日志（最近50行）
Write-Host "📝 显示最近日志:" -ForegroundColor Yellow
docker-compose logs --tail=50

Write-Host ""
Write-Host "🎉 完成！服务已在 http://localhost:7601 启动" -ForegroundColor Green
Write-Host "📋 有用的命令:" -ForegroundColor Cyan
Write-Host "   docker-compose logs -f    # 查看实时日志" -ForegroundColor White
Write-Host "   docker-compose down       # 停止服务" -ForegroundColor White
Write-Host "   docker-compose ps         # 查看容器状态" -ForegroundColor White
Write-Host "   curl http://localhost:7601/health  # 健康检查" -ForegroundColor White