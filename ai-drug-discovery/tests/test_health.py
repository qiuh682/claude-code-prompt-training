"""
Tests for GET /health endpoint.
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
from sqlalchemy.exc import OperationalError

from apps.api.dependencies import get_db, get_redis
from apps.api.main import app


# --- Mock Helpers ---

def mock_db_ok() -> Generator[MagicMock, None, None]:
    """Mock healthy DB session."""
    mock = MagicMock()
    mock.execute.return_value = None
    yield mock


def mock_db_fail() -> Generator[MagicMock, None, None]:
    """Mock failing DB session."""
    mock = MagicMock()
    mock.execute.side_effect = OperationalError("SELECT 1", {}, Exception("Connection refused"))
    yield mock


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

class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_healthy_returns_200(self, client: TestClient) -> None:
        """When DB and Redis are healthy, return 200 with status=ok."""
        app.dependency_overrides[get_db] = mock_db_ok
        app.dependency_overrides[get_redis] = mock_redis_ok

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["api"] == "ok"
        assert data["db"] == "ok"
        assert data["redis"] == "ok"

    def test_healthy_includes_latency(self, client: TestClient) -> None:
        """When healthy, response includes latency_ms fields."""
        app.dependency_overrides[get_db] = mock_db_ok
        app.dependency_overrides[get_redis] = mock_redis_ok

        response = client.get("/health")
        data = response.json()

        assert "db_latency_ms" in data
        assert "redis_latency_ms" in data
        assert isinstance(data["db_latency_ms"], (int, float))
        assert isinstance(data["redis_latency_ms"], (int, float))

    def test_db_failure_returns_503(self, client: TestClient) -> None:
        """When DB fails, return 503 with db=fail."""
        app.dependency_overrides[get_db] = mock_db_fail
        app.dependency_overrides[get_redis] = mock_redis_ok

        response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["db"] == "fail"
        assert data["redis"] == "ok"

    def test_redis_failure_returns_503(self, client: TestClient) -> None:
        """When Redis fails, return 503 with redis=fail."""
        app.dependency_overrides[get_db] = mock_db_ok
        app.dependency_overrides[get_redis] = mock_redis_fail

        response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["db"] == "ok"
        assert data["redis"] == "fail"

    def test_both_fail_returns_503(self, client: TestClient) -> None:
        """When both fail, return 503 with both=fail."""
        app.dependency_overrides[get_db] = mock_db_fail
        app.dependency_overrides[get_redis] = mock_redis_fail

        response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["db"] == "fail"
        assert data["redis"] == "fail"

    def test_response_has_required_fields(self, client: TestClient) -> None:
        """Response always includes required fields."""
        app.dependency_overrides[get_db] = mock_db_ok
        app.dependency_overrides[get_redis] = mock_redis_ok

        response = client.get("/health")
        data = response.json()

        required = ["status", "api", "db", "redis"]
        for field in required:
            assert field in data, f"Missing required field: {field}"
