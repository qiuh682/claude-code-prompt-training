#!/bin/bash
# =============================================================================
# Docker Entrypoint Script / Docker 入口脚本
# =============================================================================
# This script:
# 1. Waits for dependent services (Postgres, Redis) to be ready
# 2. Runs database migrations (optional)
# 3. Starts the FastAPI application
#
# 此脚本：
# 1. 等待依赖服务（Postgres、Redis）就绪
# 2. 运行数据库迁移（可选）
# 3. 启动 FastAPI 应用程序
# =============================================================================

set -e  # Exit on error / 出错时退出

echo "========================================"
echo "Docker Entrypoint Starting..."
echo "Docker 入口脚本启动中..."
echo "========================================"

# -----------------------------------------------------------------------------
# Step 1: Wait for services / 第一步：等待服务就绪
# -----------------------------------------------------------------------------
echo "[1/3] Checking service readiness..."
echo "[1/3] 检查服务就绪状态..."

python /app/scripts/wait-for-services.py
WAIT_RESULT=$?

if [ $WAIT_RESULT -ne 0 ]; then
    echo "ERROR: Services not ready, exiting..."
    echo "错误：服务未就绪，退出中..."
    exit 1
fi

# -----------------------------------------------------------------------------
# Step 2: Run migrations (if enabled) / 第二步：运行迁移（如果启用）
# -----------------------------------------------------------------------------
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "[2/3] Running database migrations..."
    echo "[2/3] 运行数据库迁移..."
    alembic upgrade head
else
    echo "[2/3] Skipping migrations (RUN_MIGRATIONS != true)"
    echo "[2/3] 跳过迁移（RUN_MIGRATIONS != true）"
fi

# -----------------------------------------------------------------------------
# Step 3: Start application / 第三步：启动应用程序
# -----------------------------------------------------------------------------
echo "[3/3] Starting FastAPI application..."
echo "[3/3] 启动 FastAPI 应用程序..."
echo "========================================"

# Execute the CMD passed to docker run (or from Dockerfile)
# 执行传递给 docker run 的 CMD（或来自 Dockerfile）
exec "$@"
