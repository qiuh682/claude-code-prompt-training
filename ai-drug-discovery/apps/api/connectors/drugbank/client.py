"""
DrugBank API HTTP client with authentication, caching, and rate limiting.

Low-level API client for DrugBank's commercial API.
Requires API credentials (key or token) from DrugBank subscription.

Note: DrugBank API access requires a commercial license.
See https://go.drugbank.com/public_users/sign_up for access.

This client returns raw JSON responses. Use DrugBankNormalizer to convert
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


class DrugBankClientError(Exception):
    """Base exception for DrugBank client errors."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotConfiguredError(DrugBankClientError):
    """DrugBank API credentials not configured."""

    def __init__(self):
        super().__init__(
            "DrugBank API credentials not configured. "
            "Set DRUGBANK_API_KEY environment variable or use local data mode.",
            status_code=None,
        )


class AuthenticationError(DrugBankClientError):
    """Authentication failed (HTTP 401/403)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)


class RateLimitError(DrugBankClientError):
    """Rate limit exceeded (HTTP 429)."""

    def __init__(self, retry_after: int | None = None):
        super().__init__("Rate limit exceeded", status_code=429)
        self.retry_after = retry_after


class NotFoundError(DrugBankClientError):
    """Resource not found (HTTP 404)."""

    def __init__(self, resource: str):
        super().__init__(f"Resource not found: {resource}", status_code=404)
        self.resource = resource


class DrugBankClient:
    """
    Low-level HTTP client for DrugBank API.

    Requires DRUGBANK_API_KEY to be set in environment.

    Example:
        client = DrugBankClient()

        if not client.is_configured:
            raise NotConfiguredError()

        # Get drug by DrugBank ID
        data = await client.get_drug("DB00945")

        # Search drugs
        results = await client.search_drugs("aspirin")

        await client.close()
    """

    BASE_URL = "https://api.drugbank.com/v1"
    DEFAULT_TIMEOUT = 30
    MAX_RETRIES = 3

    # DrugBank API rate limit (varies by subscription)
    RATE_LIMIT_RPM = 60  # Conservative default

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        cache_enabled: bool = True,
    ):
        self.api_key = api_key or connector_settings.drugbank_api_key
        self.base_url = (
            base_url or connector_settings.drugbank_base_url or self.BASE_URL
        )
        self.timeout = (
            timeout or connector_settings.connector_timeout or self.DEFAULT_TIMEOUT
        )
        self.max_retries = (
            max_retries or connector_settings.connector_max_retries or self.MAX_RETRIES
        )
        self.cache_enabled = cache_enabled

        self._client: httpx.AsyncClient | None = None
        self._cache: dict[str, tuple[Any, float]] = {}
        self._redis_client = None

        # Rate limiting
        self._request_times: list[float] = []
        self._rate_lock = asyncio.Lock()

    @property
    def is_configured(self) -> bool:
        """Check if API credentials are configured."""
        return bool(self.api_key)

    def _check_configured(self) -> None:
        """Raise error if not configured."""
        if not self.is_configured:
            raise NotConfiguredError()

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy initialize HTTP client."""
        self._check_configured()

        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "AIdrugDiscovery/1.0",
                },
                follow_redirects=True,
            )
        return self._client

    async def _get_redis(self):
        """Lazy initialize Redis client."""
        if (
            self._redis_client is None
            and connector_settings.connector_cache_backend == "redis"
        ):
            try:
                import redis.asyncio as redis

                self._redis_client = redis.from_url(
                    connector_settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis_client.ping()
                logger.info("DrugBank client connected to Redis cache")
            except Exception as e:
                logger.warning(f"Redis unavailable, using in-memory cache: {e}")
                self._redis_client = False
        return self._redis_client if self._redis_client else None

    # =========================================================================
    # Caching
    # =========================================================================

    def _make_cache_key(self, endpoint: str, params: dict | None = None) -> str:
        """Generate cache key from endpoint and params."""
        key_data = f"{endpoint}|{json.dumps(params or {}, sort_keys=True)}"
        return f"drugbank:{hashlib.md5(key_data.encode()).hexdigest()}"

    async def _cache_get(self, key: str) -> Any | None:
        """Get value from cache."""
        if not self.cache_enabled:
            return None

        redis = await self._get_redis()
        if redis:
            try:
                value = await redis.get(key)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.warning(f"Redis GET error: {e}")

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

        redis = await self._get_redis()
        if redis:
            try:
                await redis.setex(key, ttl, json.dumps(value, default=str))
                return
            except Exception as e:
                logger.warning(f"Redis SET error: {e}")

        self._cache[key] = (value, time.time() + ttl)

        if len(self._cache) > 10000:
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
            one_minute_ago = now - 60

            self._request_times = [t for t in self._request_times if t > one_minute_ago]

            if len(self._request_times) >= self.RATE_LIMIT_RPM:
                wait_time = self._request_times[0] - one_minute_ago + 0.1
                if wait_time > 0:
                    logger.debug(
                        f"DrugBank rate limit reached, waiting {wait_time:.2f}s"
                    )
                    await asyncio.sleep(wait_time)

            self._request_times.append(time.time())

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
            endpoint: API endpoint path
            params: Query parameters
            cache_ttl: Cache TTL in seconds

        Returns:
            Parsed JSON response

        Raises:
            NotConfiguredError: API key not set
            AuthenticationError: Invalid credentials
            NotFoundError: Resource not found
            RateLimitError: Rate limit exceeded
            DrugBankClientError: Other API errors
        """
        self._check_configured()

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
                if response.status_code == 401:
                    raise AuthenticationError("Invalid API key")

                if response.status_code == 403:
                    raise AuthenticationError(
                        "Access forbidden - check API subscription level"
                    )

                if response.status_code == 404:
                    raise NotFoundError(endpoint)

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    raise RateLimitError(int(retry_after) if retry_after else None)

                if response.status_code >= 500:
                    raise DrugBankClientError(
                        f"Server error: {response.status_code}",
                        status_code=response.status_code,
                    )

                response.raise_for_status()

                data = response.json()
                await self._cache_set(cache_key, data, ttl)
                return data

            except (NotConfiguredError, AuthenticationError, NotFoundError):
                raise

            except RateLimitError as e:
                last_error = e
                wait_time = e.retry_after or self._backoff_delay(attempt)
                if attempt < self.max_retries:
                    logger.warning(f"DrugBank rate limited, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                continue

            except httpx.TimeoutException as e:
                last_error = DrugBankClientError(f"Request timeout: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self._backoff_delay(attempt))
                continue

            except httpx.RequestError as e:
                last_error = DrugBankClientError(f"Request error: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self._backoff_delay(attempt))
                continue

        raise last_error or DrugBankClientError("Request failed after retries")

    # =========================================================================
    # DrugBank API Methods
    # =========================================================================

    async def get_drug(
        self,
        drugbank_id: str,
        cache_ttl: int = 86400,  # 24 hours
    ) -> dict:
        """
        Get drug by DrugBank ID.

        Args:
            drugbank_id: DrugBank ID (e.g., DB00945)
            cache_ttl: Cache TTL

        Returns:
            Raw drug data
        """
        endpoint = f"/drugs/{drugbank_id}"
        return await self.get(endpoint, cache_ttl=cache_ttl)

    async def get_drug_targets(
        self,
        drugbank_id: str,
        cache_ttl: int = 86400,
    ) -> list[dict]:
        """
        Get targets for a drug.

        Args:
            drugbank_id: DrugBank ID
            cache_ttl: Cache TTL

        Returns:
            List of target records
        """
        endpoint = f"/drugs/{drugbank_id}/targets"
        return await self.get(endpoint, cache_ttl=cache_ttl)

    async def get_drug_enzymes(
        self,
        drugbank_id: str,
        cache_ttl: int = 86400,
    ) -> list[dict]:
        """
        Get enzymes for a drug (metabolizing enzymes).

        Args:
            drugbank_id: DrugBank ID
            cache_ttl: Cache TTL

        Returns:
            List of enzyme records
        """
        endpoint = f"/drugs/{drugbank_id}/enzymes"
        return await self.get(endpoint, cache_ttl=cache_ttl)

    async def get_drug_carriers(
        self,
        drugbank_id: str,
        cache_ttl: int = 86400,
    ) -> list[dict]:
        """
        Get carriers for a drug.

        Args:
            drugbank_id: DrugBank ID
            cache_ttl: Cache TTL

        Returns:
            List of carrier records
        """
        endpoint = f"/drugs/{drugbank_id}/carriers"
        return await self.get(endpoint, cache_ttl=cache_ttl)

    async def get_drug_transporters(
        self,
        drugbank_id: str,
        cache_ttl: int = 86400,
    ) -> list[dict]:
        """
        Get transporters for a drug.

        Args:
            drugbank_id: DrugBank ID
            cache_ttl: Cache TTL

        Returns:
            List of transporter records
        """
        endpoint = f"/drugs/{drugbank_id}/transporters"
        return await self.get(endpoint, cache_ttl=cache_ttl)

    async def get_drug_interactions(
        self,
        drugbank_id: str,
        cache_ttl: int = 43200,  # 12 hours
    ) -> list[dict]:
        """
        Get drug-drug interactions.

        Args:
            drugbank_id: DrugBank ID
            cache_ttl: Cache TTL

        Returns:
            List of interaction records
        """
        endpoint = f"/drugs/{drugbank_id}/drug_interactions"
        return await self.get(endpoint, cache_ttl=cache_ttl)

    async def search_drugs(
        self,
        query: str,
        page: int = 1,
        per_page: int = 25,
        cache_ttl: int = 3600,  # 1 hour
    ) -> dict:
        """
        Search drugs by name, identifier, or other fields.

        Args:
            query: Search query
            page: Page number
            per_page: Results per page
            cache_ttl: Cache TTL

        Returns:
            Search results with pagination
        """
        endpoint = "/drugs"
        params = {
            "q": query,
            "page": page,
            "per_page": per_page,
        }
        return await self.get(endpoint, params=params, cache_ttl=cache_ttl)

    async def get_target(
        self,
        target_id: str,
        cache_ttl: int = 86400,
    ) -> dict:
        """
        Get target by DrugBank target ID.

        Args:
            target_id: DrugBank target ID
            cache_ttl: Cache TTL

        Returns:
            Raw target data
        """
        endpoint = f"/targets/{target_id}"
        return await self.get(endpoint, cache_ttl=cache_ttl)

    async def search_targets(
        self,
        query: str,
        page: int = 1,
        per_page: int = 25,
        cache_ttl: int = 3600,
    ) -> dict:
        """
        Search targets.

        Args:
            query: Search query
            page: Page number
            per_page: Results per page
            cache_ttl: Cache TTL

        Returns:
            Search results
        """
        endpoint = "/targets"
        params = {
            "q": query,
            "page": page,
            "per_page": per_page,
        }
        return await self.get(endpoint, params=params, cache_ttl=cache_ttl)

    async def get_drugs_by_target(
        self,
        uniprot_id: str,
        cache_ttl: int = 43200,
    ) -> list[dict]:
        """
        Get drugs that interact with a target (by UniProt ID).

        Args:
            uniprot_id: UniProt accession
            cache_ttl: Cache TTL

        Returns:
            List of drug records
        """
        endpoint = "/targets/search"
        params = {"uniprot_id": uniprot_id}
        result = await self.get(endpoint, params=params, cache_ttl=cache_ttl)
        return result.get("drugs", [])

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
