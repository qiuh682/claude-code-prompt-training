#!/usr/bin/env python3
"""
Wait for dependent services to be ready before starting the application.
等待依赖服务就绪后再启动应用程序。

This script provides application-level readiness checks as defense-in-depth,
complementing Docker's healthcheck mechanism.
此脚本提供应用级就绪检查作为纵深防御，补充 Docker 的健康检查机制。

Why is this needed? / 为什么需要这个？
----------------------------------
1. depends_on: service_healthy waits for container health, but:
   - Healthcheck passes ≠ service accepts YOUR connections
   - Network routing may not be ready
   - Service may be in "warm-up" phase
   依赖服务健康不等于服务接受你的连接，网络路由可能未就绪，服务可能在预热阶段

2. This script verifies actual connectivity from YOUR container
   此脚本验证从你的容器到服务的实际连接性

3. Provides clear logs for debugging startup issues
   提供清晰的日志用于调试启动问题
"""

import os
import socket
import sys
import time
from urllib.parse import urlparse


def log(message: str, level: str = "INFO") -> None:
    """Print timestamped log message. / 打印带时间戳的日志消息"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)


def check_tcp_connection(host: str, port: int, timeout: float = 5.0) -> bool:
    """
    Check if TCP connection can be established.
    检查是否可以建立 TCP 连接。
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except socket.error as e:
        log(f"Socket error connecting to {host}:{port} - {e}", "DEBUG")
        return False


def check_postgres(url: str, timeout: float = 5.0) -> bool:
    """
    Check PostgreSQL connectivity using asyncpg or psycopg2.
    使用 asyncpg 或 psycopg2 检查 PostgreSQL 连接性。

    Falls back to TCP check if drivers not available.
    如果驱动不可用则回退到 TCP 检查。
    """
    parsed = urlparse(url.replace("+asyncpg", "").replace("+psycopg2", ""))
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432

    # First check TCP connectivity / 首先检查 TCP 连接性
    if not check_tcp_connection(host, port, timeout):
        return False

    # Try actual database connection / 尝试实际数据库连接
    try:
        import psycopg2

        conn_str = url.replace("+asyncpg", "").replace("postgresql", "postgres")
        conn = psycopg2.connect(conn_str, connect_timeout=int(timeout))
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return True
    except ImportError:
        # psycopg2 not available, TCP check passed
        # psycopg2 不可用，TCP 检查已通过
        log("psycopg2 not available, using TCP check only", "DEBUG")
        return True
    except Exception as e:
        log(f"PostgreSQL connection failed: {e}", "DEBUG")
        return False


def check_redis(url: str, timeout: float = 5.0) -> bool:
    """
    Check Redis connectivity using redis-py or TCP.
    使用 redis-py 或 TCP 检查 Redis 连接性。
    """
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379

    # First check TCP connectivity / 首先检查 TCP 连接性
    if not check_tcp_connection(host, port, timeout):
        return False

    # Try actual Redis PING / 尝试实际 Redis PING
    try:
        import redis

        client = redis.from_url(url, socket_timeout=timeout)
        client.ping()
        client.close()
        return True
    except ImportError:
        # redis-py not available, TCP check passed
        log("redis-py not available, using TCP check only", "DEBUG")
        return True
    except Exception as e:
        log(f"Redis connection failed: {e}", "DEBUG")
        return False


def wait_for_service(
    name: str,
    check_func,
    url: str,
    max_retries: int = 30,
    retry_interval: float = 2.0,
) -> bool:
    """
    Wait for a service to become available with retries.
    等待服务可用，带重试机制。
    """
    log(f"Waiting for {name}... / 等待 {name}...")

    for attempt in range(1, max_retries + 1):
        if check_func(url):
            log(f"✓ {name} is ready! (attempt {attempt}/{max_retries})")
            log(f"✓ {name} 已就绪！（第 {attempt}/{max_retries} 次尝试）")
            return True

        if attempt < max_retries:
            log(
                f"✗ {name} not ready, retrying in {retry_interval}s... "
                f"(attempt {attempt}/{max_retries})"
            )
            time.sleep(retry_interval)

    log(f"✗ {name} failed to become ready after {max_retries} attempts", "ERROR")
    log(f"✗ {name} 在 {max_retries} 次尝试后仍未就绪", "ERROR")
    return False


def main() -> int:
    """
    Main entry point. Checks all required services.
    主入口点。检查所有必需的服务。
    """
    log("=" * 60)
    log("Starting service readiness checks / 开始服务就绪检查")
    log("=" * 60)

    # Configuration from environment / 从环境变量获取配置
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@postgres:5432/drugdiscovery",
    )
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")

    max_retries = int(os.environ.get("WAIT_MAX_RETRIES", "30"))
    retry_interval = float(os.environ.get("WAIT_RETRY_INTERVAL", "2.0"))

    log(f"DATABASE_URL: {database_url.split('@')[0]}@***")  # Hide credentials
    log(f"REDIS_URL: {redis_url}")
    log(f"Max retries: {max_retries}, Interval: {retry_interval}s")
    log("-" * 60)

    # Check all services / 检查所有服务
    services = [
        ("PostgreSQL", check_postgres, database_url),
        ("Redis", check_redis, redis_url),
    ]

    all_ready = True
    for name, check_func, url in services:
        if not wait_for_service(name, check_func, url, max_retries, retry_interval):
            all_ready = False
            break  # Fail fast / 快速失败

    log("-" * 60)
    if all_ready:
        log("✓ All services are ready! Starting application...")
        log("✓ 所有服务已就绪！正在启动应用程序...")
        log("=" * 60)
        return 0
    else:
        log("✗ Service readiness check failed!", "ERROR")
        log("✗ 服务就绪检查失败！", "ERROR")
        log("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
