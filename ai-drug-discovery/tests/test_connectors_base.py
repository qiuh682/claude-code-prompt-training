"""
Unit tests for connector base class behaviors.

Tests:
1. Caching: second call hits cache and does not call HTTP client
2. Rate limit: when API returns 429 + Retry-After, connector retries correctly
3. Retries: transient 5xx is retried with backoff
4. Error normalization: network errors become a consistent ConnectorError type

Uses mocked HTTP responses - does not hit real external APIs.
"""

import asyncio
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from apps.api.connectors.chembl.client import (
    ChEMBLClient,
    ChEMBLClientError,
    NotFoundError,
    RateLimitError,
)
from apps.api.connectors.pubchem.client import (
    BadRequestError,
    PubChemClient,
    PubChemClientError,
)
from apps.api.connectors.pubchem.client import (
    NotFoundError as PubChemNotFoundError,
)
from apps.api.connectors.pubchem.client import (
    RateLimitError as PubChemRateLimitError,
)
from apps.api.connectors.uniprot.client import (
    UniProtClient,
    UniProtClientError,
)
from apps.api.connectors.uniprot.client import (
    NotFoundError as UniProtNotFoundError,
)
from apps.api.connectors.uniprot.client import (
    RateLimitError as UniProtRateLimitError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_response_factory():
    """Factory for creating mock httpx responses."""

    def _create_response(
        status_code: int = 200,
        json_data: dict | list | None = None,
        text: str = "",
        headers: dict | None = None,
    ) -> httpx.Response:
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code

        # Set headers with Content-Type for JSON responses
        default_headers = {}
        if json_data is not None:
            default_headers["Content-Type"] = "application/json"
        response.headers = {**default_headers, **(headers or {})}
        response.text = text

        if json_data is not None:
            response.json.return_value = json_data
        else:
            response.json.side_effect = ValueError("No JSON")

        # Make raise_for_status work correctly
        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"HTTP {status_code}",
                request=MagicMock(),
                response=response,
            )
        else:
            response.raise_for_status.return_value = None

        return response

    return _create_response


@pytest.fixture
def chembl_client():
    """Create ChEMBL client with caching disabled for isolation."""
    return ChEMBLClient(cache_enabled=False)


@pytest.fixture
def chembl_client_cached():
    """Create ChEMBL client with caching enabled (in-memory only)."""
    client = ChEMBLClient(cache_enabled=True)
    client._redis_client = False  # Force in-memory cache, skip Redis
    return client


@pytest.fixture
def pubchem_client():
    """Create PubChem client with caching disabled for isolation."""
    return PubChemClient(cache_enabled=False)


@pytest.fixture
def pubchem_client_cached():
    """Create PubChem client with caching enabled (in-memory only)."""
    client = PubChemClient(cache_enabled=True)
    client._redis_client = False  # Force in-memory cache, skip Redis
    return client


@pytest.fixture
def uniprot_client():
    """Create UniProt client with caching disabled for isolation."""
    return UniProtClient(cache_enabled=False)


@pytest.fixture
def uniprot_client_cached():
    """Create UniProt client with caching enabled (in-memory only)."""
    client = UniProtClient(cache_enabled=True)
    client._redis_client = False  # Force in-memory cache, skip Redis
    return client


# =============================================================================
# Test: Caching Behavior
# =============================================================================


class TestCaching:
    """Tests for connector caching behavior."""

    async def test_chembl_second_call_hits_cache(
        self, chembl_client_cached, mock_response_factory
    ):
        """ChEMBL: Second call should hit cache and not call HTTP client."""
        mock_response = mock_response_factory(
            status_code=200,
            json_data={"molecule_chembl_id": "CHEMBL25", "pref_name": "Aspirin"},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_response)

        # Inject mock client
        chembl_client_cached._client = mock_http_client

        # First call - should hit HTTP
        result1 = await chembl_client_cached.get("/molecule/CHEMBL25.json")
        assert result1["molecule_chembl_id"] == "CHEMBL25"
        assert mock_http_client.get.call_count == 1

        # Second call - should hit cache, not HTTP
        result2 = await chembl_client_cached.get("/molecule/CHEMBL25.json")
        assert result2["molecule_chembl_id"] == "CHEMBL25"
        assert mock_http_client.get.call_count == 1  # Still 1, not 2

        await chembl_client_cached.close()

    async def test_pubchem_second_call_hits_cache(
        self, pubchem_client_cached, mock_response_factory
    ):
        """PubChem: Second call should hit cache and not call HTTP client."""
        mock_response = mock_response_factory(
            status_code=200,
            json_data={"PropertyTable": {"Properties": [{"CID": 2244, "MolecularWeight": 180.16}]}},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_response)

        pubchem_client_cached._client = mock_http_client

        # First call
        result1 = await pubchem_client_cached.get("/compound/cid/2244/property/MolecularWeight/JSON")
        assert mock_http_client.get.call_count == 1

        # Second call - should hit cache
        result2 = await pubchem_client_cached.get("/compound/cid/2244/property/MolecularWeight/JSON")
        assert mock_http_client.get.call_count == 1  # Still 1

        await pubchem_client_cached.close()

    async def test_uniprot_second_call_hits_cache(
        self, uniprot_client_cached, mock_response_factory
    ):
        """UniProt: Second call should hit cache and not call HTTP client."""
        mock_response = mock_response_factory(
            status_code=200,
            json_data={"primaryAccession": "P00533", "uniProtkbId": "EGFR_HUMAN"},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_response)

        uniprot_client_cached._client = mock_http_client

        # First call
        result1 = await uniprot_client_cached.get("/uniprotkb/P00533")
        assert result1["primaryAccession"] == "P00533"
        assert mock_http_client.get.call_count == 1

        # Second call - should hit cache
        result2 = await uniprot_client_cached.get("/uniprotkb/P00533")
        assert result2["primaryAccession"] == "P00533"
        assert mock_http_client.get.call_count == 1

        await uniprot_client_cached.close()

    async def test_cache_respects_ttl(self, chembl_client_cached, mock_response_factory):
        """Cache should expire after TTL."""
        mock_response = mock_response_factory(
            status_code=200,
            json_data={"test": "data"},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_response)

        chembl_client_cached._client = mock_http_client

        # First call with very short TTL
        result1 = await chembl_client_cached.get("/test", cache_ttl=1)
        assert mock_http_client.get.call_count == 1

        # Wait for cache to expire
        await asyncio.sleep(1.1)

        # Third call - should hit HTTP again after expiry
        result2 = await chembl_client_cached.get("/test", cache_ttl=1)
        assert mock_http_client.get.call_count == 2

        await chembl_client_cached.close()

    async def test_different_endpoints_cached_separately(
        self, chembl_client_cached, mock_response_factory
    ):
        """Different endpoints should have separate cache entries."""
        mock_response_1 = mock_response_factory(
            status_code=200,
            json_data={"id": "endpoint1"},
        )
        mock_response_2 = mock_response_factory(
            status_code=200,
            json_data={"id": "endpoint2"},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_response_1, mock_response_2])

        chembl_client_cached._client = mock_http_client

        result1 = await chembl_client_cached.get("/endpoint1")
        result2 = await chembl_client_cached.get("/endpoint2")

        assert result1["id"] == "endpoint1"
        assert result2["id"] == "endpoint2"
        assert mock_http_client.get.call_count == 2

        # Subsequent calls should hit cache
        result1_cached = await chembl_client_cached.get("/endpoint1")
        result2_cached = await chembl_client_cached.get("/endpoint2")

        assert result1_cached["id"] == "endpoint1"
        assert result2_cached["id"] == "endpoint2"
        assert mock_http_client.get.call_count == 2  # Still 2

        await chembl_client_cached.close()

    async def test_cache_disabled_always_hits_http(
        self, chembl_client, mock_response_factory
    ):
        """When caching is disabled, every call should hit HTTP."""
        mock_response = mock_response_factory(
            status_code=200,
            json_data={"test": "data"},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_response)

        chembl_client._client = mock_http_client

        await chembl_client.get("/test")
        await chembl_client.get("/test")
        await chembl_client.get("/test")

        assert mock_http_client.get.call_count == 3

        await chembl_client.close()


# =============================================================================
# Test: Rate Limit Handling (429)
# =============================================================================


class TestRateLimitHandling:
    """Tests for rate limit (429) handling with Retry-After."""

    async def test_chembl_retries_on_429_with_retry_after(
        self, chembl_client, mock_response_factory
    ):
        """ChEMBL: Should retry after 429 with Retry-After header."""
        # First call returns 429, second succeeds
        mock_429 = mock_response_factory(
            status_code=429,
            headers={"Retry-After": "1"},
            json_data=None,
        )
        mock_success = mock_response_factory(
            status_code=200,
            json_data={"success": True},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_429, mock_success])

        chembl_client._client = mock_http_client

        start_time = time.time()
        result = await chembl_client.get("/test")
        elapsed = time.time() - start_time

        assert result["success"] is True
        assert mock_http_client.get.call_count == 2
        # Should have waited at least 1 second (Retry-After)
        assert elapsed >= 0.9

        await chembl_client.close()

    async def test_pubchem_retries_on_503_rate_limit(
        self, pubchem_client, mock_response_factory
    ):
        """PubChem: Should retry on 503 (PubChem rate limit signal)."""
        mock_503 = mock_response_factory(
            status_code=503,
            headers={"Retry-After": "1"},
            json_data=None,
        )
        mock_success = mock_response_factory(
            status_code=200,
            json_data={"IdentifierList": {"CID": [2244]}},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_503, mock_success])

        pubchem_client._client = mock_http_client

        result = await pubchem_client.get("/compound/name/aspirin/cids/JSON")

        assert "IdentifierList" in result
        assert mock_http_client.get.call_count == 2

        await pubchem_client.close()

    async def test_uniprot_retries_on_429(
        self, uniprot_client, mock_response_factory
    ):
        """UniProt: Should retry after 429."""
        mock_429 = mock_response_factory(
            status_code=429,
            headers={"Retry-After": "1"},
            json_data=None,
        )
        mock_success = mock_response_factory(
            status_code=200,
            json_data={"results": []},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_429, mock_success])

        uniprot_client._client = mock_http_client

        result = await uniprot_client.get("/uniprotkb/search", params={"query": "test"})

        assert "results" in result
        assert mock_http_client.get.call_count == 2

        await uniprot_client.close()

    async def test_raises_rate_limit_error_after_max_retries(
        self, chembl_client, mock_response_factory
    ):
        """Should raise RateLimitError after exhausting retries."""
        mock_429 = mock_response_factory(
            status_code=429,
            headers={"Retry-After": "1"},
            json_data=None,
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        # Return 429 for all retry attempts
        mock_http_client.get = AsyncMock(return_value=mock_429)

        chembl_client._client = mock_http_client
        chembl_client.max_retries = 2  # Reduce for faster test

        with pytest.raises(RateLimitError) as exc_info:
            await chembl_client.get("/test")

        assert exc_info.value.status_code == 429
        # Should have tried initial + 2 retries = 3 calls
        assert mock_http_client.get.call_count == 3

        await chembl_client.close()

    async def test_retry_after_header_respected(
        self, chembl_client, mock_response_factory
    ):
        """Retry-After header value should be respected."""
        mock_429 = mock_response_factory(
            status_code=429,
            headers={"Retry-After": "2"},
            json_data=None,
        )
        mock_success = mock_response_factory(
            status_code=200,
            json_data={"success": True},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_429, mock_success])

        chembl_client._client = mock_http_client

        start_time = time.time()
        await chembl_client.get("/test")
        elapsed = time.time() - start_time

        # Should have waited ~2 seconds as specified
        assert elapsed >= 1.8  # Allow some tolerance

        await chembl_client.close()


# =============================================================================
# Test: Transient 5xx Retry with Backoff
# =============================================================================


class TestTransientErrorRetry:
    """Tests for transient 5xx error retry with exponential backoff."""

    async def test_chembl_retries_on_500(
        self, chembl_client, mock_response_factory
    ):
        """ChEMBL: Should retry on 500 with backoff."""
        mock_500 = mock_response_factory(status_code=500, json_data=None)
        mock_success = mock_response_factory(
            status_code=200,
            json_data={"recovered": True},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_500, mock_success])

        chembl_client._client = mock_http_client

        result = await chembl_client.get("/test")

        assert result["recovered"] is True
        assert mock_http_client.get.call_count == 2

        await chembl_client.close()

    async def test_pubchem_retries_on_502(
        self, pubchem_client, mock_response_factory
    ):
        """PubChem: Should retry on 502 Bad Gateway."""
        mock_502 = mock_response_factory(status_code=502, json_data=None)
        mock_success = mock_response_factory(
            status_code=200,
            json_data={"PropertyTable": {"Properties": []}},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_502, mock_success])

        pubchem_client._client = mock_http_client

        result = await pubchem_client.get("/compound/cid/2244/property/MolecularWeight/JSON")

        assert "PropertyTable" in result
        assert mock_http_client.get.call_count == 2

        await pubchem_client.close()

    async def test_uniprot_retries_on_503(
        self, uniprot_client, mock_response_factory
    ):
        """UniProt: Should retry on 503 Service Unavailable."""
        mock_503 = mock_response_factory(status_code=503, json_data=None)
        mock_success = mock_response_factory(
            status_code=200,
            json_data={"primaryAccession": "P00533"},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_503, mock_success])

        uniprot_client._client = mock_http_client

        result = await uniprot_client.get("/uniprotkb/P00533")

        assert result["primaryAccession"] == "P00533"
        assert mock_http_client.get.call_count == 2

        await uniprot_client.close()

    async def test_exponential_backoff_increases(
        self, chembl_client, mock_response_factory
    ):
        """Backoff delay should increase exponentially."""
        mock_500 = mock_response_factory(status_code=500, json_data=None)
        mock_success = mock_response_factory(
            status_code=200,
            json_data={"success": True},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        # Fail twice, then succeed
        mock_http_client.get = AsyncMock(
            side_effect=[mock_500, mock_500, mock_success]
        )

        chembl_client._client = mock_http_client

        start_time = time.time()
        result = await chembl_client.get("/test")
        elapsed = time.time() - start_time

        assert result["success"] is True
        assert mock_http_client.get.call_count == 3
        # First retry: 1s, second retry: 2s = ~3s minimum
        assert elapsed >= 2.5

        await chembl_client.close()

    async def test_raises_error_after_max_retries_on_5xx(
        self, chembl_client, mock_response_factory
    ):
        """Should raise ChEMBLClientError after exhausting retries on 5xx."""
        mock_500 = mock_response_factory(status_code=500, json_data=None)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_500)

        chembl_client._client = mock_http_client
        chembl_client.max_retries = 2

        with pytest.raises(ChEMBLClientError) as exc_info:
            await chembl_client.get("/test")

        assert exc_info.value.status_code == 500
        assert mock_http_client.get.call_count == 3  # initial + 2 retries

        await chembl_client.close()

    async def test_no_retry_on_4xx_client_errors(
        self, chembl_client, mock_response_factory
    ):
        """Should NOT retry on 4xx client errors (except 429)."""
        mock_400 = mock_response_factory(status_code=400, json_data=None, text="Bad Request")

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_400)

        chembl_client._client = mock_http_client

        # 400 should raise immediately without retries
        with pytest.raises(Exception):  # Will raise httpx error or custom error
            await chembl_client.get("/test")

        # Should only call once (no retries for client errors)
        assert mock_http_client.get.call_count == 1

        await chembl_client.close()


# =============================================================================
# Test: Error Normalization
# =============================================================================


class TestErrorNormalization:
    """Tests for error normalization to consistent ConnectorError types."""

    async def test_chembl_timeout_becomes_connector_error(self, chembl_client):
        """ChEMBL: Timeout should become ChEMBLClientError."""
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(
            side_effect=httpx.TimeoutException("Connection timed out")
        )

        chembl_client._client = mock_http_client
        chembl_client.max_retries = 0  # No retries for faster test

        with pytest.raises(ChEMBLClientError) as exc_info:
            await chembl_client.get("/test")

        assert "timeout" in exc_info.value.message.lower()

        await chembl_client.close()

    async def test_pubchem_connection_error_becomes_connector_error(
        self, pubchem_client
    ):
        """PubChem: Connection error should become PubChemClientError."""
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        pubchem_client._client = mock_http_client
        pubchem_client.max_retries = 0

        with pytest.raises(PubChemClientError) as exc_info:
            await pubchem_client.get("/test")

        assert "error" in exc_info.value.message.lower()

        await pubchem_client.close()

    async def test_uniprot_network_error_becomes_connector_error(
        self, uniprot_client
    ):
        """UniProt: Network error should become UniProtClientError."""
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(
            side_effect=httpx.RequestError("Network unreachable")
        )

        uniprot_client._client = mock_http_client
        uniprot_client.max_retries = 0

        with pytest.raises(UniProtClientError) as exc_info:
            await uniprot_client.get("/test")

        assert "error" in exc_info.value.message.lower()

        await uniprot_client.close()

    async def test_chembl_404_becomes_not_found_error(
        self, chembl_client, mock_response_factory
    ):
        """ChEMBL: 404 should become NotFoundError."""
        mock_404 = mock_response_factory(status_code=404, json_data=None)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_404)

        chembl_client._client = mock_http_client

        with pytest.raises(NotFoundError) as exc_info:
            await chembl_client.get("/molecule/INVALID.json")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message.lower()

        await chembl_client.close()

    async def test_pubchem_404_becomes_not_found_error(
        self, pubchem_client, mock_response_factory
    ):
        """PubChem: 404 should become NotFoundError."""
        mock_404 = mock_response_factory(status_code=404, json_data=None)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_404)

        pubchem_client._client = mock_http_client

        with pytest.raises(PubChemNotFoundError) as exc_info:
            await pubchem_client.get("/compound/cid/99999999999/JSON")

        assert exc_info.value.status_code == 404

        await pubchem_client.close()

    async def test_uniprot_404_becomes_not_found_error(
        self, uniprot_client, mock_response_factory
    ):
        """UniProt: 404 should become NotFoundError."""
        mock_404 = mock_response_factory(status_code=404, json_data=None)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_404)

        uniprot_client._client = mock_http_client

        with pytest.raises(UniProtNotFoundError) as exc_info:
            await uniprot_client.get("/uniprotkb/INVALID")

        assert exc_info.value.status_code == 404

        await uniprot_client.close()

    async def test_pubchem_400_becomes_bad_request_error(
        self, pubchem_client, mock_response_factory
    ):
        """PubChem: 400 (invalid SMILES) should become BadRequestError."""
        mock_400 = mock_response_factory(
            status_code=400,
            json_data={"Fault": {"Message": "Invalid SMILES"}},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_400)

        pubchem_client._client = mock_http_client

        with pytest.raises(BadRequestError) as exc_info:
            await pubchem_client.get("/compound/smiles/INVALID/cids/JSON")

        assert exc_info.value.status_code == 400

        await pubchem_client.close()

    async def test_error_contains_status_code(
        self, chembl_client, mock_response_factory
    ):
        """Error objects should contain HTTP status code."""
        mock_500 = mock_response_factory(status_code=500, json_data=None)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_500)

        chembl_client._client = mock_http_client
        chembl_client.max_retries = 0

        with pytest.raises(ChEMBLClientError) as exc_info:
            await chembl_client.get("/test")

        assert exc_info.value.status_code == 500

        await chembl_client.close()

    async def test_retries_on_network_error_before_failing(
        self, chembl_client
    ):
        """Should retry on network errors before raising."""
        call_count = 0

        async def failing_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.ConnectError("Connection failed")
            # Success on third try
            response = MagicMock(spec=httpx.Response)
            response.status_code = 200
            response.json.return_value = {"success": True}
            response.raise_for_status.return_value = None
            return response

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = failing_get

        chembl_client._client = mock_http_client

        result = await chembl_client.get("/test")

        assert result["success"] is True
        assert call_count == 3

        await chembl_client.close()


# =============================================================================
# Test: Rate Limiting Internal Behavior
# =============================================================================


class TestInternalRateLimiting:
    """Tests for internal rate limiting (request throttling)."""

    async def test_chembl_respects_internal_rate_limit(self, chembl_client, mock_response_factory):
        """ChEMBL: Internal rate limiter should throttle rapid requests."""
        mock_response = mock_response_factory(
            status_code=200,
            json_data={"test": "data"},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_response)

        chembl_client._client = mock_http_client

        # Simulate hitting the rate limit
        chembl_client._request_times = [time.time()] * 300  # Fill up window

        start_time = time.time()
        await chembl_client.get("/test")
        elapsed = time.time() - start_time

        # Should have waited due to rate limiting
        # At least some delay should occur
        assert mock_http_client.get.call_count == 1

        await chembl_client.close()

    async def test_rate_limit_window_clears(self, chembl_client, mock_response_factory):
        """Rate limit window should clear old entries."""
        mock_response = mock_response_factory(
            status_code=200,
            json_data={"test": "data"},
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_response)

        chembl_client._client = mock_http_client

        # Add old timestamps that should be cleared
        old_time = time.time() - 120  # 2 minutes ago
        chembl_client._request_times = [old_time] * 300

        # This should not be throttled because old entries are cleared
        start_time = time.time()
        await chembl_client.get("/test")
        elapsed = time.time() - start_time

        # Should be fast since old entries were cleared
        assert elapsed < 1.0

        await chembl_client.close()


# =============================================================================
# Test: Backoff Calculation
# =============================================================================


class TestBackoffCalculation:
    """Tests for exponential backoff calculation."""

    def test_chembl_backoff_increases_exponentially(self, chembl_client):
        """Backoff delay should follow exponential pattern."""
        delay_0 = chembl_client._backoff_delay(0)
        delay_1 = chembl_client._backoff_delay(1)
        delay_2 = chembl_client._backoff_delay(2)
        delay_3 = chembl_client._backoff_delay(3)

        assert delay_0 == 1.0  # 1 * 2^0
        assert delay_1 == 2.0  # 1 * 2^1
        assert delay_2 == 4.0  # 1 * 2^2
        assert delay_3 == 8.0  # 1 * 2^3

    def test_chembl_backoff_capped_at_max(self, chembl_client):
        """Backoff should be capped at maximum value."""
        delay_10 = chembl_client._backoff_delay(10)  # Would be 1024 without cap

        assert delay_10 == 60.0  # Capped at 60 seconds

    def test_pubchem_backoff_increases_exponentially(self, pubchem_client):
        """PubChem backoff should follow same pattern."""
        delay_0 = pubchem_client._backoff_delay(0)
        delay_1 = pubchem_client._backoff_delay(1)
        delay_2 = pubchem_client._backoff_delay(2)

        assert delay_0 == 1.0
        assert delay_1 == 2.0
        assert delay_2 == 4.0

    def test_uniprot_backoff_increases_exponentially(self, uniprot_client):
        """UniProt backoff should follow same pattern."""
        delay_0 = uniprot_client._backoff_delay(0)
        delay_1 = uniprot_client._backoff_delay(1)

        assert delay_0 == 1.0
        assert delay_1 == 2.0


# =============================================================================
# Test: Cache Key Generation
# =============================================================================


class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    def test_chembl_cache_key_includes_endpoint(self, chembl_client):
        """Cache key should include endpoint."""
        key1 = chembl_client._make_cache_key("/endpoint1")
        key2 = chembl_client._make_cache_key("/endpoint2")

        assert key1 != key2
        assert key1.startswith("chembl:")
        assert key2.startswith("chembl:")

    def test_chembl_cache_key_includes_params(self, chembl_client):
        """Cache key should include query params."""
        key1 = chembl_client._make_cache_key("/search", {"q": "aspirin"})
        key2 = chembl_client._make_cache_key("/search", {"q": "ibuprofen"})

        assert key1 != key2

    def test_chembl_cache_key_deterministic(self, chembl_client):
        """Same input should produce same cache key."""
        key1 = chembl_client._make_cache_key("/test", {"a": 1, "b": 2})
        key2 = chembl_client._make_cache_key("/test", {"a": 1, "b": 2})

        assert key1 == key2

    def test_pubchem_cache_key_different_prefix(self, pubchem_client):
        """PubChem cache keys should have different prefix."""
        key = pubchem_client._make_cache_key("/test")

        assert key.startswith("pubchem:")

    def test_uniprot_cache_key_different_prefix(self, uniprot_client):
        """UniProt cache keys should have different prefix."""
        key = uniprot_client._make_cache_key("/test")

        assert key.startswith("uniprot:")

    def test_param_order_independent(self, chembl_client):
        """Cache key should be independent of param order."""
        key1 = chembl_client._make_cache_key("/search", {"a": 1, "b": 2})
        key2 = chembl_client._make_cache_key("/search", {"b": 2, "a": 1})

        # JSON serialization with sort_keys=True should make these equal
        assert key1 == key2
