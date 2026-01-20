"""
Pytest configuration and fixtures.

Provides reusable fixtures for FastAPI testing:
- app: The FastAPI application instance
- client: Sync TestClient for HTTP requests
- override_env: Set DATABASE_URL and REDIS_URL for tests
"""

import os
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# =============================================================================
# Environment Fixture
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def override_env() -> Generator[None, None, None]:
    """
    Set test environment variables before any imports that read them.

    Scope: session (runs once for entire test session)
    Autouse: True (automatically used by all tests)
    """
    original_env = os.environ.copy()

    # Set test database and redis URLs
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5433/drugdiscovery_test",
    )
    os.environ.setdefault(
        "REDIS_URL",
        "redis://localhost:6380/0",
    )

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


# =============================================================================
# App Fixture
# =============================================================================


@pytest.fixture(scope="module")
def app() -> FastAPI:
    """
    Import and return the FastAPI application.

    Scope: module (one app instance per test module)
    """
    from apps.api.main import app as fastapi_app

    return fastapi_app


# =============================================================================
# Client Fixture
# =============================================================================


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    """
    Create a TestClient for the FastAPI app.

    Scope: function (fresh client per test)
    Clears dependency_overrides before and after each test.
    """
    app.dependency_overrides.clear()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
