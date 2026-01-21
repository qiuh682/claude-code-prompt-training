"""
Caching layer for connectors.

Provides Redis-based caching with in-memory fallback.
"""

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

from apps.api.connectors.settings import connector_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Abstract Cache Interface
# =============================================================================


class CacheBackend(ABC):
    """Abstract cache backend interface."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get value from cache. Returns None if not found or expired."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in cache with optional TTL (seconds)."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        pass

    @abstractmethod
    async def clear_prefix(self, prefix: str) -> int:
        """Clear all keys with given prefix. Returns count of deleted keys."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close cache connection."""
        pass


# =============================================================================
# Redis Cache Backend
# =============================================================================


class RedisCache(CacheBackend):
    """Redis-based cache backend."""

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or connector_settings.redis_url
        self._client = None

    async def _get_client(self):
        """Lazy initialize Redis client."""
        if self._client is None:
            try:
                import redis.asyncio as redis
                self._client = redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                # Test connection
                await self._client.ping()
                logger.info(f"Redis cache connected: {self.redis_url}")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Falling back to memory cache.")
                raise
        return self._client

    async def get(self, key: str) -> Any | None:
        try:
            client = await self._get_client()
            value = await client.get(key)
            if value is None:
                return None
            return json.loads(value)
        except Exception as e:
            logger.warning(f"Redis GET error for {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        try:
            client = await self._get_client()
            serialized = json.dumps(value, default=str)
            if ttl:
                await client.setex(key, ttl, serialized)
            else:
                await client.set(key, serialized)
        except Exception as e:
            logger.warning(f"Redis SET error for {key}: {e}")

    async def delete(self, key: str) -> None:
        try:
            client = await self._get_client()
            await client.delete(key)
        except Exception as e:
            logger.warning(f"Redis DELETE error for {key}: {e}")

    async def clear_prefix(self, prefix: str) -> int:
        try:
            client = await self._get_client()
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await client.scan(cursor, match=f"{prefix}*", count=100)
                if keys:
                    await client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            return deleted
        except Exception as e:
            logger.warning(f"Redis CLEAR_PREFIX error for {prefix}: {e}")
            return 0

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None


# =============================================================================
# In-Memory Cache Backend
# =============================================================================


class MemoryCache(CacheBackend):
    """
    Simple in-memory cache with TTL support.

    Note: Not suitable for production with multiple workers.
    Use only as fallback when Redis is unavailable.
    """

    def __init__(self, max_size: int = 10000):
        self._cache: dict[str, tuple[Any, datetime | None]] = {}
        self._max_size = max_size
        logger.info("Using in-memory cache (not shared across workers)")

    async def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None

        value, expires_at = self._cache[key]
        if expires_at and datetime.utcnow() > expires_at:
            del self._cache[key]
            return None

        return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        # Simple LRU-like eviction if at capacity
        if len(self._cache) >= self._max_size:
            # Remove oldest 10%
            to_remove = list(self._cache.keys())[: self._max_size // 10]
            for k in to_remove:
                del self._cache[k]

        expires_at = datetime.utcnow() + timedelta(seconds=ttl) if ttl else None
        self._cache[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._cache.pop(key, None)

    async def clear_prefix(self, prefix: str) -> int:
        keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
        for key in keys_to_delete:
            del self._cache[key]
        return len(keys_to_delete)

    async def close(self) -> None:
        self._cache.clear()


# =============================================================================
# Cache Factory
# =============================================================================


_cache_instance: CacheBackend | None = None


async def get_cache() -> CacheBackend:
    """
    Get or create cache instance based on settings.

    Returns Redis cache if configured and available, otherwise memory cache.
    """
    global _cache_instance

    if _cache_instance is not None:
        return _cache_instance

    if connector_settings.connector_cache_backend == "redis":
        try:
            redis_cache = RedisCache()
            # Test connection
            await redis_cache._get_client()
            _cache_instance = redis_cache
            return _cache_instance
        except Exception as e:
            logger.warning(f"Redis unavailable, falling back to memory cache: {e}")

    _cache_instance = MemoryCache()
    return _cache_instance


async def close_cache() -> None:
    """Close cache connection."""
    global _cache_instance
    if _cache_instance:
        await _cache_instance.close()
        _cache_instance = None


# =============================================================================
# Cache Key Utilities
# =============================================================================


def make_cache_key(connector: str, method: str, *args, **kwargs) -> str:
    """
    Generate a cache key from connector, method, and arguments.

    Format: connector:method:hash(args)
    """
    # Serialize args and kwargs for hashing
    key_parts = [str(arg) for arg in args]
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    key_data = "|".join(key_parts)

    # Hash if too long
    if len(key_data) > 100:
        key_hash = hashlib.md5(key_data.encode()).hexdigest()[:16]
    else:
        key_hash = key_data.replace(" ", "_").replace(":", "-")

    return f"{connector}:{method}:{key_hash}"
