"""Pytest configuration and fixtures."""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_db
from apps.api.main import app


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Create a mock database session."""
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def override_get_db(mock_db_session: MagicMock) -> Any:
    """Override the get_db dependency with mock session."""

    async def _override() -> AsyncGenerator[MagicMock, None]:
        yield mock_db_session

    return _override


@pytest.fixture
async def async_client(
    override_get_db: Any,
) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing."""
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
