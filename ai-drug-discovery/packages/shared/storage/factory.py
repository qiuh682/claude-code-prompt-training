"""Factory for creating storage backends based on configuration."""

from functools import lru_cache
from typing import TYPE_CHECKING

from packages.shared.storage.base import FileStorageBackend
from packages.shared.storage.local import LocalFileStorage

if TYPE_CHECKING:
    from apps.api.config import Settings


@lru_cache(maxsize=1)
def get_storage_backend(
    backend: str | None = None,
    local_path: str | None = None,
    s3_bucket: str | None = None,
    s3_endpoint_url: str | None = None,
    s3_region: str | None = None,
    s3_access_key: str | None = None,
    s3_secret_key: str | None = None,
) -> FileStorageBackend:
    """
    Factory function to create the appropriate storage backend.

    Can be called directly with parameters or will use settings from config.

    Args:
        backend: "local" or "s3" (defaults to settings.storage_backend)
        local_path: Path for local storage
        s3_bucket: S3 bucket name
        s3_endpoint_url: Custom endpoint for MinIO
        s3_region: AWS region
        s3_access_key: AWS access key
        s3_secret_key: AWS secret key

    Returns:
        Configured FileStorageBackend instance
    """
    # Import settings lazily to avoid circular imports
    from apps.api.config import get_settings

    settings = get_settings()

    # Use provided values or fall back to settings
    storage_backend = backend or settings.storage_backend

    if storage_backend == "s3":
        from packages.shared.storage.s3 import S3FileStorage

        return S3FileStorage(
            bucket=s3_bucket or settings.s3_bucket,
            endpoint_url=s3_endpoint_url or settings.s3_endpoint_url,
            region=s3_region or settings.s3_region,
            aws_access_key_id=s3_access_key or settings.s3_access_key_id,
            aws_secret_access_key=s3_secret_key or settings.s3_secret_access_key,
        )
    else:
        # Default to local storage
        return LocalFileStorage(
            base_path=local_path or settings.local_upload_path,
        )


def get_storage_backend_from_settings(settings: "Settings") -> FileStorageBackend:
    """
    Create storage backend directly from a Settings object.

    Useful for dependency injection in tests.

    Args:
        settings: Application settings

    Returns:
        Configured FileStorageBackend instance
    """
    if settings.storage_backend == "s3":
        from packages.shared.storage.s3 import S3FileStorage

        return S3FileStorage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
        )
    else:
        return LocalFileStorage(base_path=settings.local_upload_path)
