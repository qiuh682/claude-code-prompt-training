"""Health endpoint tests."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient) -> None:
    """Test basic health check endpoint."""
    response = await async_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_health_ready_all_connected(async_client: AsyncClient) -> None:
    """Test readiness check when all services are connected."""
    # Mock Redis
    with patch("apps.api.routers.health.redis") as mock_redis:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.close = AsyncMock()
        mock_redis.from_url.return_value = mock_client

        response = await async_client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"
        assert data["redis"] == "connected"


@pytest.mark.asyncio
async def test_health_ready_redis_disconnected(async_client: AsyncClient) -> None:
    """Test readiness check when Redis is disconnected."""
    # Mock Redis to raise an exception
    with patch("apps.api.routers.health.redis") as mock_redis:
        mock_redis.from_url.side_effect = Exception("Connection refused")

        response = await async_client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "connected"
        assert data["redis"] == "disconnected"


@pytest.mark.asyncio
async def test_openapi_docs_accessible(async_client: AsyncClient) -> None:
    """Test that OpenAPI documentation is accessible."""
    response = await async_client.get("/openapi.json")

    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert data["info"]["title"] == "AI Drug Discovery Platform"
