"""
Connector exception types.

Provides consistent error handling across all connectors.
"""

from typing import Any


class ConnectorError(Exception):
    """Base exception for all connector errors."""

    def __init__(
        self,
        message: str,
        connector: str | None = None,
        status_code: int | None = None,
        response_body: Any = None,
    ):
        self.message = message
        self.connector = connector
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(self.message)

    def __str__(self) -> str:
        parts = [self.message]
        if self.connector:
            parts.insert(0, f"[{self.connector}]")
        if self.status_code:
            parts.append(f"(HTTP {self.status_code})")
        return " ".join(parts)


class RateLimitError(ConnectorError):
    """Raised when rate limit is exceeded (HTTP 429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        connector: str | None = None,
        retry_after: int | None = None,
    ):
        super().__init__(message, connector, status_code=429)
        self.retry_after = retry_after

    def __str__(self) -> str:
        base = super().__str__()
        if self.retry_after:
            return f"{base} - retry after {self.retry_after}s"
        return base


class NotFoundError(ConnectorError):
    """Raised when requested resource is not found (HTTP 404)."""

    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        connector: str | None = None,
    ):
        message = f"{resource_type} '{resource_id}' not found"
        super().__init__(message, connector, status_code=404)
        self.resource_type = resource_type
        self.resource_id = resource_id


class ValidationError(ConnectorError):
    """Raised when API response doesn't match expected schema."""

    def __init__(
        self,
        message: str,
        connector: str | None = None,
        field: str | None = None,
    ):
        super().__init__(message, connector)
        self.field = field


class AuthenticationError(ConnectorError):
    """Raised when API authentication fails (HTTP 401/403)."""

    def __init__(
        self,
        message: str = "Authentication failed",
        connector: str | None = None,
    ):
        super().__init__(message, connector, status_code=401)


class ServiceUnavailableError(ConnectorError):
    """Raised when external service is unavailable (HTTP 5xx)."""

    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        connector: str | None = None,
        status_code: int = 503,
    ):
        super().__init__(message, connector, status_code=status_code)


class TimeoutError(ConnectorError):
    """Raised when request times out."""

    def __init__(
        self,
        message: str = "Request timed out",
        connector: str | None = None,
        timeout: float | None = None,
    ):
        super().__init__(message, connector)
        self.timeout = timeout
