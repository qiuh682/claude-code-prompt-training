"""
Redis client setup (sync redis-py).
"""

import os
from collections.abc import Generator
from typing import Any

import redis

# --- Configuration ---
REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6380/0",
)


# --- Dependency ---
def get_redis() -> Generator[Any, None, None]:
    """Yield a Redis client with 1s timeouts. Use as FastAPI dependency."""
    client = redis.from_url(
        REDIS_URL,
        socket_timeout=1,
        socket_connect_timeout=1,
    )
    try:
        yield client
    finally:
        client.close()
