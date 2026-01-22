"""
Simplified file storage interface for the API layer.

Re-exports storage backends from packages/shared/storage with
convenience functions for common operations.

Usage:
    from apps.api.storage import save_upload_file, get_upload_file

    # Save a file
    stored = await save_upload_file(file_content, "compounds.sdf", "chemical/x-mdl-sdfile")

    # Retrieve a file
    content = await get_upload_file(stored.storage_path)
"""

from typing import BinaryIO

from packages.shared.storage import (
    FileStorageBackend,
    LocalFileStorage,
    S3FileStorage,
    get_storage_backend,
)
from packages.shared.storage.base import StoredFile

__all__ = [
    # Classes
    "FileStorageBackend",
    "LocalFileStorage",
    "S3FileStorage",
    "StoredFile",
    # Factory
    "get_storage_backend",
    # Convenience functions
    "save_upload_file",
    "get_upload_file",
    "delete_upload_file",
    "upload_file_exists",
]


# =============================================================================
# Convenience Functions
# =============================================================================


async def save_upload_file(
    file: BinaryIO,
    filename: str,
    content_type: str,
) -> StoredFile:
    """
    Save an uploaded file to storage.

    Args:
        file: File-like object to save
        filename: Original filename
        content_type: MIME type

    Returns:
        StoredFile with path, hash, and size
    """
    storage = get_storage_backend()
    return await storage.save(file, filename, content_type)


async def get_upload_file(path: str) -> BinaryIO:
    """
    Retrieve an uploaded file from storage.

    Args:
        path: Storage path returned from save_upload_file

    Returns:
        File-like object for reading

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    storage = get_storage_backend()
    return await storage.get(path)


async def delete_upload_file(path: str) -> bool:
    """
    Delete an uploaded file from storage.

    Args:
        path: Storage path

    Returns:
        True if deleted, False if not found
    """
    storage = get_storage_backend()
    return await storage.delete(path)


async def upload_file_exists(path: str) -> bool:
    """
    Check if an uploaded file exists.

    Args:
        path: Storage path

    Returns:
        True if exists
    """
    storage = get_storage_backend()
    return await storage.exists(path)
