# =============================================================================
# AI Drug Discovery Platform - Dockerfile
# AI 药物发现平台 - Docker 镜像构建文件
# =============================================================================

# -----------------------------------------------------------------------------
# Base Stage: Common dependencies / 基础阶段：通用依赖
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
# 防止 Python 写入 .pyc 文件并启用非缓冲输出
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies required for asyncpg and psycopg
# 安装 asyncpg 和 psycopg 所需的系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# Development Stage / 开发阶段
# -----------------------------------------------------------------------------
FROM base AS development

# Copy only dependency file first (for better caching)
# 首先只复制依赖文件（以便更好地利用缓存）
COPY pyproject.toml ./

# Create empty package directories for editable install
# 创建空的包目录用于可编辑安装
RUN mkdir -p apps/api/routers packages/ml packages/chemistry packages/shared db/models alembic tests scripts

# Copy package init files for editable install
# 复制包初始化文件用于可编辑安装
COPY apps/__init__.py ./apps/
COPY apps/api/__init__.py ./apps/api/
COPY apps/api/routers/__init__.py ./apps/api/routers/
COPY packages/__init__.py ./packages/
COPY packages/ml/__init__.py ./packages/ml/
COPY packages/chemistry/__init__.py ./packages/chemistry/
COPY packages/shared/__init__.py ./packages/shared/
COPY db/__init__.py ./db/
COPY db/models/__init__.py ./db/models/

# Install all dependencies including dev tools + psycopg2 for wait script
# 安装所有依赖，包括开发工具 + psycopg2 用于等待脚本
RUN pip install -e ".[dev]" psycopg2-binary

# Copy entrypoint and wait scripts / 复制入口和等待脚本
COPY scripts/docker-entrypoint.sh /app/scripts/docker-entrypoint.sh
COPY scripts/wait-for-services.py /app/scripts/wait-for-services.py
RUN chmod +x /app/scripts/docker-entrypoint.sh

# Copy remaining source code (will be overridden by volume mount in dev)
# 复制剩余源代码（在开发中会被卷挂载覆盖）
COPY . .

EXPOSE 8000

# Health check for the API / API 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use entrypoint script to wait for services / 使用入口脚本等待服务
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]

# Run with hot reload for development / 开发模式下启用热重载
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# -----------------------------------------------------------------------------
# Production Stage / 生产阶段
# -----------------------------------------------------------------------------
FROM base AS production

# Copy project files
COPY pyproject.toml ./
COPY apps ./apps
COPY packages ./packages
COPY db ./db
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

# Install production dependencies + psycopg2 for wait script
# 安装生产依赖 + psycopg2 用于等待脚本
RUN pip install -e . psycopg2-binary && \
    chmod +x /app/scripts/docker-entrypoint.sh

# Create non-root user for security / 创建非 root 用户以提高安全性
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Health check for the API / API 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use entrypoint script to wait for services / 使用入口脚本等待服务
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]

# Run with multiple workers for production / 生产环境使用多 worker
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
