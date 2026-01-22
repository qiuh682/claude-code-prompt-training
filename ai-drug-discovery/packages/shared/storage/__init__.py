"""
File storage backends for upload system.

Provides abstract interface and implementations for:
- Local disk storage (development)
- S3/MinIO storage (production)
"""

from packages.shared.storage.base import FileStorageBackend
from packages.shared.storage.local import LocalFileStorage
from packages.shared.storage.s3 import S3FileStorage
from packages.shared.storage.factory import get_storage_backend

__all__ = [
    "FileStorageBackend",
    "LocalFileStorage",
    "S3FileStorage",
    "get_storage_backend",
]
