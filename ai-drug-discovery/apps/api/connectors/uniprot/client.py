"""
UniProt HTTP client with caching and rate limiting.

Low-level API client that handles:
- HTTP requests with retries and exponential backoff
- Rate limiting (UniProt is generous but we respect it)
- Caching (Redis preferred, in-memory fallback)
- Long TTLs for stable protein data

This client returns raw JSON responses. Use UniProtNormalizer to convert
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


class UniProtClientError(Exception):
    """Base exception for UniProt client errors."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class RateLimitError(UniProtClientError):
    """Rate limit exceeded (HTTP 429)."""

    def __init__(self, retry_after: int | None = None):
        super().__init__("Rate limit exceeded", status_code=429)
        self.retry_after = retry_after


class NotFoundError(UniProtClientError):
    """Resource not found (HTTP 404)."""

    def __init__(self, resource: str):
        super().__init__(f"Resource not found: {resource}", status_code=404)
        self.resource = resource


class BadRequestError(UniProtClientError):
    """Invalid request (HTTP 400)."""

    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class UniProtClient:
    """
    Low-level HTTP client for UniProt REST API.

    Example:
        client = UniProtClient()

        # Get protein by accession
        data = await client.get_entry("P00533")

        # Search proteins
        results = await client.search("kinase AND organism_id:9606", size=25)

        # Get FASTA sequence
        fasta = await client.get_fasta("P00533")

        await client.close()
    """

    BASE_URL = "https://rest.uniprot.org"
    DEFAULT_TIMEOUT = 30
    MAX_RETRIES = 3

    # UniProt is generous with rate limits, but we respect a reasonable limit
    RATE_LIMIT_RPS = 10  # 10 requests per second
    RATE_LIMIT_RPM = 600  # 600 requests per minute

    # Fields to request from UniProt (comprehensive for drug discovery)
    DEFAULT_FIELDS = [
        "accession",
        "id",
        "protein_name",
        "gene_names",
        "organism_name",
        "organism_id",
        "length",
        "mass",
        "sequence",
        "cc_function",
        "cc_catalytic_activity",
        "cc_pathway",
        "cc_subcellular_location",
        "cc_disease",
        "ft_domain",
        "ft_binding",
        "ft_act_site",
        "ft_site",
        "ft_metal",
        "ft_mod_res",
        "keyword",
        "go",
        "xref_pdb",
        "xref_chembl",
        "xref_drugbank",
        "xref_interpro",
        "xref_pfam",
        "xref_ensembl",
        "xref_refseq",
        "protein_existence",
        "reviewed",
        "date_created",
        "date_modified",
        "version",
    ]

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        cache_enabled: bool = True,
    ):
        self.base_url = (
            base_url or connector_settings.uniprot_base_url or self.BASE_URL
        )
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

        # Rate limiting
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
                logger.info("UniProt client connected to Redis cache")
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
        return f"uniprot:{hashlib.md5(key_data.encode()).hexdigest()}"

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

            # Per-second limit
            one_second_ago = now - 1.0
            recent_requests = [t for t in self._request_times if t > one_second_ago]

            if len(recent_requests) >= self.RATE_LIMIT_RPS:
                wait_time = recent_requests[0] - one_second_ago + 0.05
                if wait_time > 0:
                    logger.debug(
                        f"UniProt per-second rate limit, waiting {wait_time:.2f}s"
                    )
                    await asyncio.sleep(wait_time)

            # Per-minute limit
            one_minute_ago = now - 60
            self._request_times = [t for t in self._request_times if t > one_minute_ago]

            if len(self._request_times) >= self.RATE_LIMIT_RPM:
                wait_time = self._request_times[0] - one_minute_ago + 0.1
                if wait_time > 0:
                    logger.debug(
                        f"UniProt per-minute rate limit, waiting {wait_time:.2f}s"
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
    ) -> dict | list | str:
        """
        Make GET request with caching and retries.

        Args:
            endpoint: API endpoint path
            params: Query parameters
            cache_ttl: Cache TTL in seconds

        Returns:
            Parsed JSON response or text

        Raises:
            NotFoundError: Resource not found (404)
            RateLimitError: Rate limit exceeded after retries
            UniProtClientError: Other API errors
        """
        cache_key = self._make_cache_key(endpoint, params)
        # Long TTL for stable protein data
        ttl = cache_ttl or 86400  # 24 hours default

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

                if response.status_code == 400:
                    raise BadRequestError(response.text[:500])

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    raise RateLimitError(int(retry_after) if retry_after else None)

                if response.status_code >= 500:
                    last_error = UniProtClientError(
                        f"Server error: {response.status_code}",
                        status_code=response.status_code,
                    )
                    if attempt < self.max_retries:
                        logger.warning(
                            f"UniProt server error {response.status_code}, "
                            f"retrying in {self._backoff_delay(attempt)}s"
                        )
                        await asyncio.sleep(self._backoff_delay(attempt))
                    continue

                response.raise_for_status()

                # Parse response
                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    data = response.json()
                else:
                    data = response.text

                await self._cache_set(cache_key, data, ttl)
                return data

            except (NotFoundError, BadRequestError):
                raise

            except RateLimitError as e:
                last_error = e
                wait_time = e.retry_after or self._backoff_delay(attempt)
                if attempt < self.max_retries:
                    logger.warning(f"UniProt rate limited, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                continue

            except httpx.TimeoutException as e:
                last_error = UniProtClientError(f"Request timeout: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self._backoff_delay(attempt))
                continue

            except httpx.RequestError as e:
                last_error = UniProtClientError(f"Request error: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self._backoff_delay(attempt))
                continue

        raise last_error or UniProtClientError("Request failed after retries")

    # =========================================================================
    # UniProt-Specific Methods
    # =========================================================================

    async def get_entry(
        self,
        accession: str,
        cache_ttl: int = 86400,  # 24 hours - protein data is stable
    ) -> dict:
        """
        Get protein entry by UniProt accession.

        Args:
            accession: UniProt accession (e.g., P00533)
            cache_ttl: Cache TTL (long for stable data)

        Returns:
            Raw protein entry data
        """
        endpoint = f"/uniprotkb/{accession}"
        return await self.get(endpoint, cache_ttl=cache_ttl)

    async def get_fasta(
        self,
        accession: str,
        cache_ttl: int = 86400,
    ) -> str:
        """
        Get protein sequence in FASTA format.

        Args:
            accession: UniProt accession
            cache_ttl: Cache TTL

        Returns:
            FASTA formatted sequence
        """
        endpoint = f"/uniprotkb/{accession}.fasta"
        client = await self._get_client()
        await self._wait_for_rate_limit()

        response = await client.get(endpoint)
        if response.status_code == 404:
            raise NotFoundError(accession)
        response.raise_for_status()

        return response.text

    async def search(
        self,
        query: str,
        fields: list[str] | None = None,
        size: int = 25,
        cursor: str | None = None,
        reviewed_only: bool = False,
        cache_ttl: int = 3600,  # 1 hour for searches
    ) -> dict:
        """
        Search UniProtKB.

        Args:
            query: UniProt query string (supports field:value syntax)
            fields: Fields to return (default: essential fields)
            size: Results per page (max 500)
            cursor: Pagination cursor
            reviewed_only: Only return Swiss-Prot (reviewed) entries
            cache_ttl: Cache TTL

        Returns:
            Search results with results list and pagination info
        """
        # Build query
        if reviewed_only and "reviewed:" not in query:
            query = f"({query}) AND reviewed:true"

        params = {
            "query": query,
            "format": "json",
            "size": min(size, 500),
        }

        if fields:
            params["fields"] = ",".join(fields)
        else:
            # Use a smaller set for search results
            params["fields"] = ",".join([
                "accession",
                "id",
                "protein_name",
                "gene_names",
                "organism_name",
                "organism_id",
                "length",
                "reviewed",
            ])

        if cursor:
            params["cursor"] = cursor

        endpoint = "/uniprotkb/search"
        return await self.get(endpoint, params=params, cache_ttl=cache_ttl)

    async def search_by_gene(
        self,
        gene_name: str,
        organism_id: int | None = None,
        reviewed_only: bool = True,
        size: int = 25,
        cache_ttl: int = 3600,
    ) -> dict:
        """
        Search proteins by gene name.

        Args:
            gene_name: Gene symbol or name
            organism_id: NCBI taxonomy ID (e.g., 9606 for human)
            reviewed_only: Only Swiss-Prot entries
            size: Results per page
            cache_ttl: Cache TTL

        Returns:
            Search results
        """
        query = f'gene:"{gene_name}"'
        if organism_id:
            query += f" AND organism_id:{organism_id}"

        return await self.search(
            query,
            reviewed_only=reviewed_only,
            size=size,
            cache_ttl=cache_ttl,
        )

    async def search_by_protein_name(
        self,
        name: str,
        organism_id: int | None = None,
        reviewed_only: bool = True,
        size: int = 25,
        cache_ttl: int = 3600,
    ) -> dict:
        """
        Search proteins by protein name.

        Args:
            name: Protein name or keyword
            organism_id: NCBI taxonomy ID
            reviewed_only: Only Swiss-Prot entries
            size: Results per page
            cache_ttl: Cache TTL

        Returns:
            Search results
        """
        query = f'protein_name:"{name}"'
        if organism_id:
            query += f" AND organism_id:{organism_id}"

        return await self.search(
            query,
            reviewed_only=reviewed_only,
            size=size,
            cache_ttl=cache_ttl,
        )

    async def search_human_kinases(
        self,
        size: int = 100,
        cache_ttl: int = 7200,
    ) -> dict:
        """
        Get human protein kinases (common drug discovery targets).

        Returns:
            Search results for human kinases
        """
        query = 'keyword:"Kinase" AND organism_id:9606 AND reviewed:true'
        return await self.search(query, size=size, cache_ttl=cache_ttl)

    async def search_by_ec_number(
        self,
        ec_number: str,
        organism_id: int | None = None,
        reviewed_only: bool = True,
        size: int = 25,
        cache_ttl: int = 3600,
    ) -> dict:
        """
        Search enzymes by EC number.

        Args:
            ec_number: EC number (e.g., "2.7.10.1" for receptor tyrosine kinases)
            organism_id: NCBI taxonomy ID
            reviewed_only: Only Swiss-Prot entries
            size: Results per page
            cache_ttl: Cache TTL

        Returns:
            Search results
        """
        query = f'ec:{ec_number}'
        if organism_id:
            query += f" AND organism_id:{organism_id}"

        return await self.search(
            query,
            reviewed_only=reviewed_only,
            size=size,
            cache_ttl=cache_ttl,
        )

    async def get_entry_batch(
        self,
        accessions: list[str],
        fields: list[str] | None = None,
        cache_ttl: int = 86400,
    ) -> list[dict]:
        """
        Get multiple entries by accession.

        Args:
            accessions: List of UniProt accessions
            fields: Fields to return
            cache_ttl: Cache TTL

        Returns:
            List of entry data
        """
        if not accessions:
            return []

        # Use search with accession list
        query = " OR ".join(f"accession:{acc}" for acc in accessions)
        result = await self.search(
            query,
            fields=fields,
            size=len(accessions),
            cache_ttl=cache_ttl,
        )
        return result.get("results", [])

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
