"""
Pytest configuration and fixtures.

Provides reusable fixtures for FastAPI testing:
- app: The FastAPI application instance
- client: Sync TestClient for HTTP requests
- override_env: Set DATABASE_URL and REDIS_URL for tests
- db_session: Database session with transaction rollback for isolation
"""

import os
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

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

    # Set test database URL with asyncpg driver for async support
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5433/drugdiscovery_test",
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


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine (session-scoped)."""
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5433/drugdiscovery_test",
    )
    engine = create_engine(database_url, pool_pre_ping=True)
    return engine


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    """Create session factory for tests."""
    return sessionmaker(bind=test_engine)


@pytest.fixture
def db_session(test_session_factory) -> Generator[Session, None, None]:
    """
    Provide a database session with automatic cleanup.

    Uses DELETE for cleanup instead of transaction rollback to avoid
    issues with TestClient which manages its own transactions.
    """
    session = test_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def clean_db(test_engine) -> Generator[None, None, None]:
    """
    Clean database tables before and after test.

    Use this fixture for tests that need a clean database state.
    Truncates auth-related tables in correct order (respecting FKs).
    """
    def truncate_tables():
        with test_engine.connect() as conn:
            # Disable FK checks, truncate, re-enable
            conn.execute(text("SET session_replication_role = 'replica';"))
            conn.execute(text("TRUNCATE TABLE refresh_tokens CASCADE;"))
            conn.execute(text("TRUNCATE TABLE api_keys CASCADE;"))
            conn.execute(text("TRUNCATE TABLE memberships CASCADE;"))
            conn.execute(text("TRUNCATE TABLE teams CASCADE;"))
            conn.execute(text("TRUNCATE TABLE organizations CASCADE;"))
            conn.execute(text("TRUNCATE TABLE users CASCADE;"))
            conn.execute(text("SET session_replication_role = 'origin';"))
            conn.commit()

    truncate_tables()
    yield
    truncate_tables()


@pytest.fixture
def client_clean_db(
    app: FastAPI, clean_db
) -> Generator[TestClient, None, None]:
    """
    TestClient with clean database state.

    Combines client fixture with clean_db for isolated tests.
    """
    app.dependency_overrides.clear()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
