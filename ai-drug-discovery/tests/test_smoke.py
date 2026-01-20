"""
Smoke tests for FastAPI application.
Verifies the app starts and basic endpoints respond.
"""

from fastapi.testclient import TestClient


class TestAppSmoke:
    """Basic smoke tests to verify app is working."""

    def test_app_starts(self, client: TestClient) -> None:
        """App starts without errors and responds to requests."""
        # Any endpoint will do - we just want to verify the app boots
        response = client.get("/health")
        assert response.status_code in (200, 503)  # Either is valid

    def test_openapi_available(self, client: TestClient) -> None:
        """OpenAPI schema is accessible."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert "openapi" in response.json()

    def test_docs_available(self, client: TestClient) -> None:
        """Swagger UI is accessible."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
