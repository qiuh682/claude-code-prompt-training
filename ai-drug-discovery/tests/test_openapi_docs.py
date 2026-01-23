"""
Tests for OpenAPI documentation endpoints.
Verifies Swagger UI, ReDoc, and OpenAPI schema are properly configured.
"""

import os

# Set DATABASE_URL before importing app (required for asyncpg driver)
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/drugdiscovery",
)

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


# =============================================================================
# Tests: OpenAPI Schema (/openapi.json)
# =============================================================================

class TestOpenAPISchema:
    """Tests for GET /openapi.json."""

    def test_returns_200(self, client: TestClient) -> None:
        """OpenAPI schema endpoint returns HTTP 200."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

    def test_returns_valid_json(self, client: TestClient) -> None:
        """Response is valid JSON (no parse errors)."""
        response = client.get("/openapi.json")
        # .json() raises if invalid
        data = response.json()
        assert isinstance(data, dict)

    def test_contains_openapi_field(self, client: TestClient) -> None:
        """Schema contains 'openapi' version field."""
        response = client.get("/openapi.json")
        data = response.json()
        assert "openapi" in data
        assert data["openapi"].startswith("3.")  # OpenAPI 3.x

    def test_info_title_not_empty(self, client: TestClient) -> None:
        """Schema info.title is set (not empty)."""
        response = client.get("/openapi.json")
        data = response.json()
        assert "info" in data
        assert "title" in data["info"]
        assert data["info"]["title"]  # Not empty
        assert len(data["info"]["title"]) > 0

    def test_info_version_not_empty(self, client: TestClient) -> None:
        """Schema info.version is set (not empty)."""
        response = client.get("/openapi.json")
        data = response.json()
        assert "info" in data
        assert "version" in data["info"]
        assert data["info"]["version"]  # Not empty
        assert len(data["info"]["version"]) > 0

    def test_health_endpoint_in_paths(self, client: TestClient) -> None:
        """Schema paths contains /health endpoint."""
        response = client.get("/openapi.json")
        data = response.json()
        assert "paths" in data
        assert "/health" in data["paths"]

    def test_content_type_is_json(self, client: TestClient) -> None:
        """Response Content-Type is application/json."""
        response = client.get("/openapi.json")
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type


# =============================================================================
# Tests: Swagger UI (/docs)
# =============================================================================

class TestSwaggerUI:
    """Tests for GET /docs (Swagger UI)."""

    def test_returns_200(self, client: TestClient) -> None:
        """Swagger UI endpoint returns HTTP 200."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_returns_html(self, client: TestClient) -> None:
        """Response is HTML content."""
        response = client.get("/docs")
        content_type = response.headers.get("content-type", "")
        assert "text/html" in content_type

    def test_contains_swagger_ui_marker(self, client: TestClient) -> None:
        """HTML contains Swagger UI indicator."""
        response = client.get("/docs")
        text = response.text.lower()
        # Check for common Swagger UI markers (case-insensitive)
        has_swagger = "swagger" in text or "openapi" in text
        assert has_swagger, "Response should contain Swagger UI markers"


# =============================================================================
# Tests: ReDoc (/redoc)
# =============================================================================

class TestReDoc:
    """Tests for GET /redoc."""

    def test_returns_200_if_enabled(self, client: TestClient) -> None:
        """ReDoc endpoint returns HTTP 200 (if enabled)."""
        response = client.get("/redoc")
        # ReDoc might be disabled (404) - that's OK, but if enabled should be 200
        if response.status_code == 404:
            pytest.skip("ReDoc is disabled (redoc_url=None)")
        assert response.status_code == 200

    def test_returns_html_if_enabled(self, client: TestClient) -> None:
        """Response is HTML content (if enabled)."""
        response = client.get("/redoc")
        if response.status_code == 404:
            pytest.skip("ReDoc is disabled")
        content_type = response.headers.get("content-type", "")
        assert "text/html" in content_type

    def test_contains_redoc_marker_if_enabled(self, client: TestClient) -> None:
        """HTML contains ReDoc indicator (if enabled)."""
        response = client.get("/redoc")
        if response.status_code == 404:
            pytest.skip("ReDoc is disabled")
        text = response.text.lower()
        has_redoc = "redoc" in text or "openapi" in text
        assert has_redoc, "Response should contain ReDoc markers"


# =============================================================================
# Tests: Schema Content Validation
# =============================================================================

class TestSchemaContent:
    """Additional schema content validation."""

    def test_paths_is_not_empty(self, client: TestClient) -> None:
        """Schema has at least one path defined."""
        response = client.get("/openapi.json")
        data = response.json()
        assert len(data.get("paths", {})) > 0

    def test_health_has_get_method(self, client: TestClient) -> None:
        """/health endpoint has GET method defined."""
        response = client.get("/openapi.json")
        data = response.json()
        health_path = data.get("paths", {}).get("/health", {})
        assert "get" in health_path, "/health should have GET method"
