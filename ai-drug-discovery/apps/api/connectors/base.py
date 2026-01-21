"""
Base connector class with common functionality.

Features:
- HTTP client with retries and exponential backoff
- Rate limit handling (429 + Retry-After)
- Caching layer (Redis preferred, in-memory fallback)
- Consistent error handling and logging
- Abstract methods for normalization
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, TypeVar

import httpx

from apps.api.connectors.cache import CacheBackend, get_cache, make_cache_key
from apps.api.connectors.exceptions import (
    AuthenticationError,
    ConnectorError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
    TimeoutError,
)
from apps.api.connectors.schemas import (
    AssaySearchResult,
    CompoundSearchResult,
    DataSource,
    ExternalAssay,
    ExternalCompound,
    ExternalDTI,
    ExternalTarget,
    TargetSearchResult,
)
from apps.api.connectors.settings import connector_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseConnector(ABC):
    """
    Abstract base class for external database connectors.

    Subclasses must implement:
    - source: DataSource enum value
    - base_url: API base URL
    - Normalization methods for each entity type
    - Specific API methods (search_compounds, get_compound, etc.)
    """

    # ==========================================================================
    # Class Attributes (override in subclasses)
    # ==========================================================================

    source: DataSource  # Must be set by subclass
    base_url: str  # Must be set by subclass
    rate_limit_rpm: int = 60  # Requests per minute

    # ==========================================================================
    # Initialization
    # ==========================================================================

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        cache: CacheBackend | None = None,
    ):
        """
        Initialize connector.

        Args:
            base_url: Override default base URL
            timeout: Request timeout in seconds
            max_retries: Max retry attempts
            cache: Cache backend (will use default if not provided)
        """
        self._base_url = base_url or self.base_url
        self._timeout = timeout or connector_settings.connector_timeout
        self._max_retries = max_retries or connector_settings.connector_max_retries
        self._cache = cache
        self._client: httpx.AsyncClient | None = None

        # Rate limiting state
        self._request_times: list[float] = []
        self._rate_limit_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
                headers=self._get_default_headers(),
                follow_redirects=True,
            )
        return self._client

    async def _get_cache(self) -> CacheBackend:
        """Get cache backend."""
        if self._cache is None:
            self._cache = await get_cache()
        return self._cache

    def _get_default_headers(self) -> dict[str, str]:
        """Get default HTTP headers. Override in subclasses for auth."""
        return {
            "Accept": "application/json",
            "User-Agent": "AIdrugDiscovery/1.0 (research platform)",
        }

    # ==========================================================================
    # HTTP Request with Retries and Rate Limiting
    # ==========================================================================

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict | None = None,
        json_data: dict | None = None,
        headers: dict | None = None,
        cache_key: str | None = None,
        cache_ttl: int | None = None,
    ) -> dict | list | str:
        """
        Make HTTP request with retries, rate limiting, and caching.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (relative to base_url)
            params: Query parameters
            json_data: JSON body for POST/PUT
            headers: Additional headers
            cache_key: Cache key (if provided, will cache response)
            cache_ttl: Cache TTL in seconds

        Returns:
            Parsed JSON response

        Raises:
            ConnectorError: On request failure after retries
            RateLimitError: When rate limited and retries exhausted
            NotFoundError: When resource not found (404)
        """
        # Check cache first (for GET requests)
        if method.upper() == "GET" and cache_key:
            cached = await self.cache_get(cache_key)
            if cached is not None:
                if connector_settings.connector_log_cache_hits:
                    logger.debug(f"[{self.source.value}] Cache hit: {cache_key}")
                return cached

        # Rate limiting
        await self._wait_for_rate_limit()

        # Request with retries
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._do_request(
                    method, endpoint, params, json_data, headers
                )

                # Cache successful GET responses
                if method.upper() == "GET" and cache_key:
                    ttl = cache_ttl or connector_settings.connector_cache_ttl
                    await self.cache_set(cache_key, response, ttl)

                return response

            except RateLimitError as e:
                last_error = e
                if attempt < self._max_retries:
                    wait_time = e.retry_after or self._calculate_backoff(attempt)
                    logger.warning(
                        f"[{self.source.value}] Rate limited, waiting {wait_time}s "
                        f"(attempt {attempt + 1}/{self._max_retries + 1})"
                    )
                    await asyncio.sleep(wait_time)
                continue

            except (ServiceUnavailableError, TimeoutError) as e:
                last_error = e
                if attempt < self._max_retries:
                    wait_time = self._calculate_backoff(attempt)
                    logger.warning(
                        f"[{self.source.value}] {type(e).__name__}, retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{self._max_retries + 1})"
                    )
                    await asyncio.sleep(wait_time)
                continue

            except (NotFoundError, AuthenticationError):
                # Don't retry these
                raise

        # All retries exhausted
        raise last_error or ConnectorError("Request failed", connector=self.source.value)

    async def _do_request(
        self,
        method: str,
        endpoint: str,
        params: dict | None,
        json_data: dict | None,
        headers: dict | None,
    ) -> dict | list | str:
        """Execute single HTTP request."""
        client = await self._get_client()

        if connector_settings.connector_log_requests:
            logger.info(f"[{self.source.value}] {method} {endpoint}")

        try:
            response = await client.request(
                method,
                endpoint,
                params=params,
                json=json_data,
                headers=headers,
            )
        except httpx.TimeoutException as e:
            raise TimeoutError(
                f"Request timed out after {self._timeout}s",
                connector=self.source.value,
                timeout=self._timeout,
            ) from e
        except httpx.RequestError as e:
            raise ConnectorError(
                f"Request failed: {e}",
                connector=self.source.value,
            ) from e

        # Handle response status
        self._record_request_time()

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                connector=self.source.value,
                retry_after=int(retry_after) if retry_after else None,
            )

        if response.status_code == 404:
            raise NotFoundError(
                resource_type="resource",
                resource_id=endpoint,
                connector=self.source.value,
            )

        if response.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed: {response.text[:200]}",
                connector=self.source.value,
            )

        if response.status_code >= 500:
            raise ServiceUnavailableError(
                f"Server error: {response.status_code}",
                connector=self.source.value,
                status_code=response.status_code,
            )

        if not response.is_success:
            raise ConnectorError(
                f"Request failed: {response.text[:500]}",
                connector=self.source.value,
                status_code=response.status_code,
            )

        # Parse response
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    # ==========================================================================
    # Rate Limiting
    # ==========================================================================

    async def _wait_for_rate_limit(self) -> None:
        """Wait if necessary to respect rate limits."""
        async with self._rate_limit_lock:
            now = time.time()
            window_start = now - 60  # 1 minute window

            # Remove old request times
            self._request_times = [t for t in self._request_times if t > window_start]

            # Check if at limit
            if len(self._request_times) >= self.rate_limit_rpm:
                # Wait until oldest request falls out of window
                oldest = self._request_times[0]
                wait_time = oldest - window_start + 0.1
                if wait_time > 0:
                    logger.debug(
                        f"[{self.source.value}] Rate limit reached, waiting {wait_time:.2f}s"
                    )
                    await asyncio.sleep(wait_time)

    def _record_request_time(self) -> None:
        """Record a request for rate limiting."""
        self._request_times.append(time.time())

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        delay = connector_settings.connector_retry_backoff_base * (2**attempt)
        return min(delay, connector_settings.connector_retry_backoff_max)

    # ==========================================================================
    # Caching
    # ==========================================================================

    async def cache_get(self, key: str) -> Any | None:
        """Get value from cache."""
        cache = await self._get_cache()
        return await cache.get(key)

    async def cache_set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in cache."""
        cache = await self._get_cache()
        await cache.set(key, value, ttl)

    async def cache_delete(self, key: str) -> None:
        """Delete value from cache."""
        cache = await self._get_cache()
        await cache.delete(key)

    def make_cache_key(self, method: str, *args, **kwargs) -> str:
        """Generate cache key for this connector."""
        return make_cache_key(self.source.value, method, *args, **kwargs)

    # ==========================================================================
    # Abstract Methods: Normalization
    # ==========================================================================

    @abstractmethod
    def normalize_compound(self, raw_data: dict) -> ExternalCompound:
        """
        Normalize raw compound data to ExternalCompound schema.

        Args:
            raw_data: Raw API response for a compound

        Returns:
            Normalized ExternalCompound
        """
        pass

    @abstractmethod
    def normalize_target(self, raw_data: dict) -> ExternalTarget:
        """
        Normalize raw target data to ExternalTarget schema.

        Args:
            raw_data: Raw API response for a target

        Returns:
            Normalized ExternalTarget
        """
        pass

    @abstractmethod
    def normalize_assay(self, raw_data: dict) -> ExternalAssay:
        """
        Normalize raw assay/bioactivity data to ExternalAssay schema.

        Args:
            raw_data: Raw API response for an assay

        Returns:
            Normalized ExternalAssay
        """
        pass

    # ==========================================================================
    # Abstract Methods: Connector Contract
    # ==========================================================================

    @abstractmethod
    async def search_compounds(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> CompoundSearchResult:
        """
        Search for compounds by name, SMILES, or other identifier.

        Args:
            query: Search query (name, SMILES, InChIKey, etc.)
            page: Page number (1-indexed)
            page_size: Results per page

        Returns:
            CompoundSearchResult with matching compounds
        """
        pass

    @abstractmethod
    async def get_compound(self, compound_id: str) -> ExternalCompound:
        """
        Get a specific compound by its source ID.

        Args:
            compound_id: ID in the source database (e.g., CHEMBL25)

        Returns:
            ExternalCompound

        Raises:
            NotFoundError: If compound not found
        """
        pass

    @abstractmethod
    async def get_target(self, target_id: str) -> ExternalTarget:
        """
        Get a specific target by its source ID or UniProt ID.

        Args:
            target_id: Target ID or UniProt accession

        Returns:
            ExternalTarget

        Raises:
            NotFoundError: If target not found
        """
        pass

    @abstractmethod
    async def get_assays_by_target(
        self,
        target_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> AssaySearchResult:
        """
        Get assays/bioactivity data for a target.

        Args:
            target_id: Target ID or UniProt accession
            page: Page number
            page_size: Results per page

        Returns:
            AssaySearchResult with assays for the target
        """
        pass

    @abstractmethod
    async def get_bioactivity(
        self,
        compound_id: str,
        *,
        target_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AssaySearchResult:
        """
        Get bioactivity data for a compound.

        Args:
            compound_id: Compound ID
            target_id: Optional target filter
            page: Page number
            page_size: Results per page

        Returns:
            AssaySearchResult with bioactivity data
        """
        pass

    # ==========================================================================
    # Cleanup
    # ==========================================================================

    async def close(self) -> None:
        """Close HTTP client and release resources."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Re-export exceptions for convenience
__all__ = [
    "BaseConnector",
    "ConnectorError",
    "RateLimitError",
    "NotFoundError",
    "AuthenticationError",
    "ServiceUnavailableError",
    "TimeoutError",
]
