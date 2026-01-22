"""Abstract base class for file storage backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
from typing import BinaryIO


@dataclass
class StoredFile:
    """Information about a stored file."""

    storage_path: str
    sha256_hash: str
    file_size_bytes: int


class FileStorageBackend(ABC):
    """
    Abstract base for file storage backends.

    Provides a common interface for storing and retrieving files,
    supporting both local disk and cloud storage (S3/MinIO).
    """

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Return the name of this backend (e.g., 'local', 's3')."""
        pass

    @abstractmethod
    async def save(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
    ) -> StoredFile:
        """
        Save a file and return storage information.

        Args:
            file: File-like object to save
            filename: Original filename
            content_type: MIME type of the file

        Returns:
            StoredFile with path, hash, and size
        """
        pass

    @abstractmethod
    async def get(self, path: str) -> BinaryIO:
        """
        Retrieve a file by its storage path.

        Args:
            path: Storage path/key returned from save()

        Returns:
            File-like object for reading

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """
        Delete a file by its storage path.

        Args:
            path: Storage path/key returned from save()

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """
        Check if a file exists at the given path.

        Args:
            path: Storage path/key to check

        Returns:
            True if file exists, False otherwise
        """
        pass

    @staticmethod
    def compute_hash(file: BinaryIO) -> str:
        """
        Compute SHA-256 hash of a file.

        Args:
            file: File-like object (will be seeked to start)

        Returns:
            Hex-encoded SHA-256 hash
        """
        sha256 = hashlib.sha256()
        file.seek(0)
        for chunk in iter(lambda: file.read(8192), b""):
            sha256.update(chunk)
        file.seek(0)
        return sha256.hexdigest()

    @staticmethod
    def get_file_size(file: BinaryIO) -> int:
        """
        Get the size of a file in bytes.

        Args:
            file: File-like object (will be seeked to start)

        Returns:
            File size in bytes
        """
        file.seek(0, 2)  # Seek to end
        size = file.tell()
        file.seek(0)  # Seek back to start
        return size
