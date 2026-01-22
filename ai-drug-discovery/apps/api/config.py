"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "AI Drug Discovery Platform"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: Literal["development", "staging", "production"] = "development"

    # API
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/drugdiscovery"
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Rate Limiting (requests per minute)
    rate_limit_user_rpm: int = 60  # Per authenticated user
    rate_limit_org_rpm: int = 300  # Per organization (shared across users)
    rate_limit_ip_rpm: int = 30  # Fallback for unauthenticated requests
    rate_limit_auth_rpm: int = 10  # Auth endpoints (login, register)
    rate_limit_expensive_rpm: int = 10  # Expensive operations (ML predictions)
    rate_limit_window_seconds: int = 60  # Sliding window size

    # File Storage
    storage_backend: Literal["local", "s3"] = "local"
    local_upload_path: str = "./uploads"

    # S3/MinIO (production)
    s3_bucket: str = ""
    s3_endpoint_url: str | None = None  # Set for MinIO, None for AWS S3
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    # Upload Limits
    max_upload_size_mb: int = 100
    max_rows_per_upload: int = 100000
    upload_expiry_hours: int = 24  # Auto-cancel unconfirmed uploads


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
