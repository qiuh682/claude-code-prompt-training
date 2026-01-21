"""
ChEMBL HTTP client with caching and rate limiting.

Low-level API client that handles:
- HTTP requests with retries and exponential backoff
- Rate limiting (respects ChEMBL's 300 req/min limit)
- Caching (Redis preferred, in-memory fallback)
- Pagination handling

This client returns raw JSON responses. Use ChEMBLNormalizer to convert
to normalized schemas.
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

import httpx

from apps.api.connectors.settings import connector_settings

logger = logging.getLogger(__name__)


class ChEMBLClientError(Exception):
    """Base exception for ChEMBL client errors."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class RateLimitError(ChEMBLClientError):
    """Rate limit exceeded (HTTP 429)."""

    def __init__(self, retry_after: int | None = None):
        super().__init__("Rate limit exceeded", status_code=429)
        self.retry_after = retry_after


class NotFoundError(ChEMBLClientError):
    """Resource not found (HTTP 404)."""

    def __init__(self, resource: str):
        super().__init__(f"Resource not found: {resource}", status_code=404)
        self.resource = resource


class ChEMBLClient:
    """
    Low-level HTTP client for ChEMBL REST API.

    Example:
        client = ChEMBLClient()

        # Get single resource
        data = await client.get("/molecule/CHEMBL25.json")

        # Search with pagination
        async for page in client.paginate("/activity.json", {"target_chembl_id": "CHEMBL203"}):
            for activity in page["activities"]:
                print(activity["molecule_chembl_id"])

        await client.close()
    """

    BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"
    DEFAULT_TIMEOUT = 30
    MAX_RETRIES = 3
    RATE_LIMIT_RPM = 300  # ChEMBL allows ~300 requests/minute

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        cache_enabled: bool = True,
    ):
        self.base_url = base_url or connector_settings.chembl_base_url or self.BASE_URL
        self.timeout = timeout or connector_settings.connector_timeout or self.DEFAULT_TIMEOUT
        self.max_retries = max_retries or connector_settings.connector_max_retries or self.MAX_RETRIES
        self.cache_enabled = cache_enabled

        self._client: httpx.AsyncClient | None = None
        self._cache: dict[str, tuple[Any, float]] = {}  # In-memory cache
        self._redis_client = None
        self._request_times: list[float] = []
        self._rate_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy initialize HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AIdrugDiscovery/1.0",
                },
                follow_redirects=True,
            )
        return self._client

    async def _get_redis(self):
        """Lazy initialize Redis client."""
        if self._redis_client is None and connector_settings.connector_cache_backend == "redis":
            try:
                import redis.asyncio as redis

                self._redis_client = redis.from_url(
                    connector_settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis_client.ping()
                logger.info("ChEMBL client connected to Redis cache")
            except Exception as e:
                logger.warning(f"Redis unavailable, using in-memory cache: {e}")
                self._redis_client = False  # Mark as unavailable
        return self._redis_client if self._redis_client else None

    # =========================================================================
    # Caching
    # =========================================================================

    def _make_cache_key(self, endpoint: str, params: dict | None = None) -> str:
        """Generate cache key from endpoint and params."""
        key_data = f"{endpoint}|{json.dumps(params or {}, sort_keys=True)}"
        return f"chembl:{hashlib.md5(key_data.encode()).hexdigest()}"

    async def _cache_get(self, key: str) -> Any | None:
        """Get value from cache."""
        if not self.cache_enabled:
            return None

        # Try Redis first
        redis = await self._get_redis()
        if redis:
            try:
                value = await redis.get(key)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.warning(f"Redis GET error: {e}")

        # Fall back to in-memory
        if key in self._cache:
            value, expires_at = self._cache[key]
            if time.time() < expires_at:
                return value
            del self._cache[key]

        return None

    async def _cache_set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache."""
        if not self.cache_enabled:
            return

        # Try Redis
        redis = await self._get_redis()
        if redis:
            try:
                await redis.setex(key, ttl, json.dumps(value, default=str))
                return
            except Exception as e:
                logger.warning(f"Redis SET error: {e}")

        # Fall back to in-memory
        self._cache[key] = (value, time.time() + ttl)

        # Limit in-memory cache size
        if len(self._cache) > 10000:
            # Remove oldest 10%
            keys = sorted(self._cache.keys(), key=lambda k: self._cache[k][1])
            for k in keys[: len(keys) // 10]:
                del self._cache[k]

    # =========================================================================
    # Rate Limiting
    # =========================================================================

    async def _wait_for_rate_limit(self) -> None:
        """Wait if necessary to respect rate limits."""
        async with self._rate_lock:
            now = time.time()
            window_start = now - 60

            # Remove old timestamps
            self._request_times = [t for t in self._request_times if t > window_start]

            # Check if at limit
            if len(self._request_times) >= self.RATE_LIMIT_RPM:
                wait_time = self._request_times[0] - window_start + 0.1
                if wait_time > 0:
                    logger.debug(f"ChEMBL rate limit reached, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)

            self._request_times.append(now)

    def _backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        delay = 1.0 * (2**attempt)
        return min(delay, 60.0)

    # =========================================================================
    # HTTP Methods
    # =========================================================================

    async def get(
        self,
        endpoint: str,
        params: dict | None = None,
        cache_ttl: int | None = None,
    ) -> dict | list:
        """
        Make GET request with caching and retries.

        Args:
            endpoint: API endpoint (e.g., "/molecule/CHEMBL25.json")
            params: Query parameters
            cache_ttl: Cache TTL in seconds (default: 3600)

        Returns:
            Parsed JSON response

        Raises:
            NotFoundError: Resource not found (404)
            RateLimitError: Rate limit exceeded after retries
            ChEMBLClientError: Other API errors
        """
        cache_key = self._make_cache_key(endpoint, params)
        ttl = cache_ttl or connector_settings.connector_cache_ttl

        # Check cache
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        # Make request with retries
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                await self._wait_for_rate_limit()

                client = await self._get_client()
                response = await client.get(endpoint, params=params)

                # Handle status codes
                if response.status_code == 404:
                    raise NotFoundError(endpoint)

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    raise RateLimitError(int(retry_after) if retry_after else None)

                if response.status_code >= 500:
                    last_error = ChEMBLClientError(
                        f"Server error: {response.status_code}",
                        status_code=response.status_code,
                    )
                    if attempt < self.max_retries:
                        logger.warning(
                            f"ChEMBL server error {response.status_code}, "
                            f"retrying in {self._backoff_delay(attempt)}s"
                        )
                        await asyncio.sleep(self._backoff_delay(attempt))
                    continue

                response.raise_for_status()

                # Parse and cache response
                data = response.json()
                await self._cache_set(cache_key, data, ttl)
                return data

            except NotFoundError:
                raise

            except RateLimitError as e:
                last_error = e
                wait_time = e.retry_after or self._backoff_delay(attempt)
                if attempt < self.max_retries:
                    logger.warning(f"ChEMBL rate limited, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                continue

            except httpx.TimeoutException as e:
                last_error = ChEMBLClientError(f"Request timeout: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self._backoff_delay(attempt))
                continue

            except httpx.RequestError as e:
                last_error = ChEMBLClientError(f"Request error: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self._backoff_delay(attempt))
                continue

        raise last_error or ChEMBLClientError("Request failed after retries")

    async def paginate(
        self,
        endpoint: str,
        params: dict | None = None,
        page_size: int = 1000,
        max_pages: int | None = None,
        cache_ttl: int | None = None,
    ):
        """
        Iterate through paginated results.

        Args:
            endpoint: API endpoint
            params: Base query parameters
            page_size: Results per page (max 1000)
            max_pages: Maximum pages to fetch (None = all)
            cache_ttl: Cache TTL for each page

        Yields:
            dict: Each page of results
        """
        params = dict(params or {})
        params["limit"] = min(page_size, 1000)
        offset = 0
        pages_fetched = 0

        while True:
            params["offset"] = offset

            try:
                data = await self.get(endpoint, params, cache_ttl=cache_ttl)
            except NotFoundError:
                break

            yield data

            # Check for more pages
            page_meta = data.get("page_meta", {})
            total_count = page_meta.get("total_count", 0)
            next_url = page_meta.get("next")

            pages_fetched += 1
            offset += page_size

            if not next_url or offset >= total_count:
                break

            if max_pages and pages_fetched >= max_pages:
                break

    async def get_all(
        self,
        endpoint: str,
        params: dict | None = None,
        result_key: str = "molecules",
        max_results: int | None = None,
        cache_ttl: int | None = None,
    ) -> list[dict]:
        """
        Fetch all results across pages.

        Args:
            endpoint: API endpoint
            params: Query parameters
            result_key: Key containing results in response
            max_results: Maximum total results to fetch
            cache_ttl: Cache TTL for each page

        Returns:
            List of all results
        """
        results = []

        async for page in self.paginate(endpoint, params, cache_ttl=cache_ttl):
            page_results = page.get(result_key, [])
            results.extend(page_results)

            if max_results and len(results) >= max_results:
                results = results[:max_results]
                break

        return results

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def close(self) -> None:
        """Close HTTP client and cache connections."""
        if self._client:
            await self._client.aclose()
            self._client = None

        if self._redis_client and self._redis_client is not False:
            await self._redis_client.close()
            self._redis_client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
