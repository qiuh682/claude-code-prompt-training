"""
PubChem HTTP client with caching and rate limiting.

Low-level API client that handles:
- HTTP requests with retries and exponential backoff
- Rate limiting (respects PubChem's 5 req/sec, 400 req/min limit)
- Caching (Redis preferred, in-memory fallback)
- Different cache TTLs for search vs compound data

This client returns raw JSON responses. Use PubChemNormalizer to convert
to normalized schemas.
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any
from urllib.parse import quote

import httpx

from apps.api.connectors.settings import connector_settings

logger = logging.getLogger(__name__)


class PubChemClientError(Exception):
    """Base exception for PubChem client errors."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class RateLimitError(PubChemClientError):
    """Rate limit exceeded (HTTP 503 from PubChem)."""

    def __init__(self, retry_after: int | None = None):
        super().__init__("Rate limit exceeded", status_code=503)
        self.retry_after = retry_after


class NotFoundError(PubChemClientError):
    """Resource not found (HTTP 404) or no results."""

    def __init__(self, resource: str):
        super().__init__(f"Resource not found: {resource}", status_code=404)
        self.resource = resource


class BadRequestError(PubChemClientError):
    """Invalid request (HTTP 400) - often invalid SMILES or query."""

    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class PubChemClient:
    """
    Low-level HTTP client for PubChem PUG REST API.

    Example:
        client = PubChemClient()

        # Search by name
        data = await client.search_cids("name", "aspirin")

        # Get compound properties
        props = await client.get_properties(2244, ["MolecularWeight", "XLogP"])

        # Get full compound record
        compound = await client.get_compound(2244)

        await client.close()
    """

    BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    DEFAULT_TIMEOUT = 30
    MAX_RETRIES = 3

    # PubChem rate limits: 5 requests/second, 400 requests/minute
    RATE_LIMIT_RPS = 5
    RATE_LIMIT_RPM = 400

    # Standard property names for PUG REST
    STANDARD_PROPERTIES = [
        "MolecularFormula",
        "MolecularWeight",
        "CanonicalSMILES",
        "IsomericSMILES",
        "InChI",
        "InChIKey",
        "IUPACName",
        "XLogP",
        "ExactMass",
        "MonoisotopicMass",
        "TPSA",
        "Complexity",
        "Charge",
        "HBondDonorCount",
        "HBondAcceptorCount",
        "RotatableBondCount",
        "HeavyAtomCount",
        "AtomStereoCount",
        "DefinedAtomStereoCount",
        "UndefinedAtomStereoCount",
        "BondStereoCount",
        "CovalentUnitCount",
    ]

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        cache_enabled: bool = True,
    ):
        self.base_url = base_url or connector_settings.pubchem_base_url or self.BASE_URL
        self.timeout = (
            timeout or connector_settings.connector_timeout or self.DEFAULT_TIMEOUT
        )
        self.max_retries = (
            max_retries or connector_settings.connector_max_retries or self.MAX_RETRIES
        )
        self.cache_enabled = cache_enabled

        self._client: httpx.AsyncClient | None = None
        self._cache: dict[str, tuple[Any, float]] = {}  # In-memory cache
        self._redis_client = None

        # Rate limiting with per-second tracking
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
                logger.info("PubChem client connected to Redis cache")
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
        return f"pubchem:{hashlib.md5(key_data.encode()).hexdigest()}"

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

            # Per-second limit (5 req/sec)
            one_second_ago = now - 1.0
            recent_requests = [t for t in self._request_times if t > one_second_ago]

            if len(recent_requests) >= self.RATE_LIMIT_RPS:
                wait_time = recent_requests[0] - one_second_ago + 0.05
                if wait_time > 0:
                    logger.debug(
                        f"PubChem per-second rate limit, waiting {wait_time:.2f}s"
                    )
                    await asyncio.sleep(wait_time)

            # Per-minute limit (400 req/min)
            one_minute_ago = now - 60
            self._request_times = [t for t in self._request_times if t > one_minute_ago]

            if len(self._request_times) >= self.RATE_LIMIT_RPM:
                wait_time = self._request_times[0] - one_minute_ago + 0.1
                if wait_time > 0:
                    logger.debug(
                        f"PubChem per-minute rate limit, waiting {wait_time:.2f}s"
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
        cache_ttl: int | None = None,
    ) -> dict | list:
        """
        Make GET request with caching and retries.

        Args:
            endpoint: API endpoint path
            cache_ttl: Cache TTL in seconds (default varies by endpoint type)

        Returns:
            Parsed JSON response

        Raises:
            NotFoundError: Resource not found (404)
            RateLimitError: Rate limit exceeded after retries
            BadRequestError: Invalid query (400)
            PubChemClientError: Other API errors
        """
        cache_key = self._make_cache_key(endpoint)
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
                response = await client.get(endpoint)

                # Handle status codes
                if response.status_code == 404:
                    raise NotFoundError(endpoint)

                if response.status_code == 400:
                    # PubChem returns 400 for invalid SMILES, etc.
                    try:
                        error_data = response.json()
                        message = error_data.get("Fault", {}).get(
                            "Message", "Invalid request"
                        )
                    except Exception:
                        message = response.text[:200]
                    raise BadRequestError(message)

                if response.status_code in (503, 429):
                    # PubChem uses 503 for rate limiting
                    retry_after = response.headers.get("Retry-After")
                    raise RateLimitError(int(retry_after) if retry_after else None)

                if response.status_code >= 500:
                    last_error = PubChemClientError(
                        f"Server error: {response.status_code}",
                        status_code=response.status_code,
                    )
                    if attempt < self.max_retries:
                        logger.warning(
                            f"PubChem server error {response.status_code}, "
                            f"retrying in {self._backoff_delay(attempt)}s"
                        )
                        await asyncio.sleep(self._backoff_delay(attempt))
                    continue

                response.raise_for_status()

                # Parse and cache response
                data = response.json()
                await self._cache_set(cache_key, data, ttl)
                return data

            except (NotFoundError, BadRequestError):
                raise

            except RateLimitError as e:
                last_error = e
                wait_time = e.retry_after or self._backoff_delay(attempt)
                if attempt < self.max_retries:
                    logger.warning(f"PubChem rate limited, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                continue

            except httpx.TimeoutException as e:
                last_error = PubChemClientError(f"Request timeout: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self._backoff_delay(attempt))
                continue

            except httpx.RequestError as e:
                last_error = PubChemClientError(f"Request error: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self._backoff_delay(attempt))
                continue

        raise last_error or PubChemClientError("Request failed after retries")

    # =========================================================================
    # PubChem-Specific Methods
    # =========================================================================

    async def search_cids(
        self,
        search_type: str,
        query: str,
        cache_ttl: int = 300,  # 5 min for searches
    ) -> list[int]:
        """
        Search for compound CIDs.

        Args:
            search_type: One of "name", "smiles", "inchi", "inchikey", "formula"
            query: Search query
            cache_ttl: Cache TTL (shorter for searches)

        Returns:
            List of CIDs
        """
        # URL-encode the query for SMILES, InChI, etc.
        encoded_query = quote(query, safe="")
        endpoint = f"/compound/{search_type}/{encoded_query}/cids/JSON"

        try:
            data = await self.get(endpoint, cache_ttl=cache_ttl)
            return data.get("IdentifierList", {}).get("CID", [])
        except NotFoundError:
            return []

    async def get_compound(
        self,
        cid: int,
        cache_ttl: int = 3600,  # 1 hour for compound data
    ) -> dict:
        """
        Get full compound record.

        Args:
            cid: PubChem Compound ID
            cache_ttl: Cache TTL (longer for stable compound data)

        Returns:
            Raw compound data
        """
        endpoint = f"/compound/cid/{cid}/JSON"
        data = await self.get(endpoint, cache_ttl=cache_ttl)
        return data.get("PC_Compounds", [{}])[0]

    async def get_properties(
        self,
        cid: int,
        properties: list[str] | None = None,
        cache_ttl: int = 3600,
    ) -> dict:
        """
        Get computed properties for a compound.

        Args:
            cid: PubChem Compound ID
            properties: List of property names (default: all standard)
            cache_ttl: Cache TTL

        Returns:
            Dict of property name -> value
        """
        props = properties or self.STANDARD_PROPERTIES
        props_str = ",".join(props)
        endpoint = f"/compound/cid/{cid}/property/{props_str}/JSON"

        data = await self.get(endpoint, cache_ttl=cache_ttl)
        prop_list = data.get("PropertyTable", {}).get("Properties", [])
        return prop_list[0] if prop_list else {}

    async def get_properties_batch(
        self,
        cids: list[int],
        properties: list[str] | None = None,
        cache_ttl: int = 3600,
    ) -> list[dict]:
        """
        Get properties for multiple compounds (max 100).

        Args:
            cids: List of CIDs (max 100)
            properties: Property names
            cache_ttl: Cache TTL

        Returns:
            List of property dicts
        """
        if len(cids) > 100:
            raise ValueError("Maximum 100 CIDs per batch request")

        props = properties or self.STANDARD_PROPERTIES
        props_str = ",".join(props)
        cids_str = ",".join(str(c) for c in cids)
        endpoint = f"/compound/cid/{cids_str}/property/{props_str}/JSON"

        data = await self.get(endpoint, cache_ttl=cache_ttl)
        return data.get("PropertyTable", {}).get("Properties", [])

    async def get_synonyms(
        self,
        cid: int,
        cache_ttl: int = 3600,
    ) -> list[str]:
        """
        Get synonyms/names for a compound.

        Args:
            cid: PubChem Compound ID
            cache_ttl: Cache TTL

        Returns:
            List of synonyms
        """
        endpoint = f"/compound/cid/{cid}/synonyms/JSON"

        try:
            data = await self.get(endpoint, cache_ttl=cache_ttl)
            info_list = data.get("InformationList", {}).get("Information", [])
            if info_list:
                return info_list[0].get("Synonym", [])
            return []
        except NotFoundError:
            return []

    async def get_xrefs(
        self,
        cid: int,
        xref_type: str = "RegistryID",
        cache_ttl: int = 3600,
    ) -> list[str]:
        """
        Get cross-references for a compound.

        Args:
            cid: PubChem Compound ID
            xref_type: Type of xref (RegistryID, RN, etc.)
            cache_ttl: Cache TTL

        Returns:
            List of cross-reference IDs
        """
        endpoint = f"/compound/cid/{cid}/xrefs/{xref_type}/JSON"

        try:
            data = await self.get(endpoint, cache_ttl=cache_ttl)
            info_list = data.get("InformationList", {}).get("Information", [])
            if info_list:
                return info_list[0].get(xref_type, [])
            return []
        except NotFoundError:
            return []

    async def get_assays_for_cid(
        self,
        cid: int,
        cache_ttl: int = 1800,  # 30 min for assay data
    ) -> list[dict]:
        """
        Get bioassay AIDs for a compound.

        Args:
            cid: PubChem Compound ID
            cache_ttl: Cache TTL

        Returns:
            List of assay IDs
        """
        endpoint = f"/compound/cid/{cid}/assaysummary/JSON"

        try:
            data = await self.get(endpoint, cache_ttl=cache_ttl)
            return data.get("Table", {}).get("Row", [])
        except NotFoundError:
            return []

    async def get_assay(
        self,
        aid: int,
        cache_ttl: int = 3600,
    ) -> dict:
        """
        Get assay metadata.

        Args:
            aid: PubChem Assay ID
            cache_ttl: Cache TTL

        Returns:
            Assay metadata dict
        """
        endpoint = f"/assay/aid/{aid}/description/JSON"
        data = await self.get(endpoint, cache_ttl=cache_ttl)
        return data.get("PC_AssayContainer", [{}])[0]

    async def get_bioactivity(
        self,
        aid: int,
        cid: int,
        cache_ttl: int = 1800,
    ) -> list[dict]:
        """
        Get bioactivity data for a specific compound in an assay.

        Args:
            aid: PubChem Assay ID
            cid: PubChem Compound ID
            cache_ttl: Cache TTL

        Returns:
            List of activity records
        """
        endpoint = f"/assay/aid/{aid}/cid/{cid}/JSON"

        try:
            data = await self.get(endpoint, cache_ttl=cache_ttl)
            return data.get("PC_AssaySubmit", [])
        except NotFoundError:
            return []

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
