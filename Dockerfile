# Smart AI Router - 简单Docker配置
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 安装系统依赖和uv
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# 创建非root用户(在安装依赖前)
RUN useradd --create-home app && chown -R app:app /app
USER app

# 复制必要文件
COPY --chown=app:app pyproject.toml README.md ./

# 安装依赖（使用--no-dev跳过开发依赖）
RUN uv sync --no-dev

# 复制应用代码
COPY --chown=app:app . .

# 创建必要目录
RUN mkdir -p logs cache

EXPOSE 7601

# 健康检查
HEALTHCHECK --interval=30s --timeout=30s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:7601/health || exit 1

# 启动命令（使用虚拟环境中的Python）
CMD [".venv/bin/python", "main.py"]