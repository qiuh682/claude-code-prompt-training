"""
Tests for GET /redis-check endpoint.
Uses dependency_overrides to simulate failures (no container restarts needed).
"""

import os

# Set DATABASE_URL before importing app (required for asyncpg driver)
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/drugdiscovery",
)

from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.redis_client import get_redis

# --- Mock Helpers ---


def mock_redis_ok() -> Generator[MagicMock, None, None]:
    """Mock healthy Redis client."""
    mock = MagicMock()
    mock.ping.return_value = True
    yield mock


def mock_redis_fail() -> Generator[MagicMock, None, None]:
    """Mock failing Redis client."""
    mock = MagicMock()
    mock.ping.side_effect = ConnectionError("Connection refused")
    yield mock


# --- Fixtures ---


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Test client with clean dependency state."""
    app.dependency_overrides.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- Tests ---


class TestRedisCheck:
    """Tests for GET /redis-check."""

    def test_healthy_returns_200(self, client: TestClient) -> None:
        """When Redis is healthy, return 200 with redis=ok."""
        app.dependency_overrides[get_redis] = mock_redis_ok

        response = client.get("/redis-check")

        assert response.status_code == 200
        data = response.json()
        assert data["redis"] == "ok"

    def test_failure_returns_503(self, client: TestClient) -> None:
        """When Redis fails, return 503 with redis=fail."""
        app.dependency_overrides[get_redis] = mock_redis_fail

        response = client.get("/redis-check")

        assert response.status_code == 503
        data = response.json()
        assert data["redis"] == "fail"
        assert "error" in data
