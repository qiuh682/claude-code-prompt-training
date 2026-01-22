"""Local disk file storage backend for development."""

import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import aiofiles
import aiofiles.os

from packages.shared.storage.base import FileStorageBackend, StoredFile


class LocalFileStorage(FileStorageBackend):
    """
    Local disk storage backend for development.

    Files are organized by date: uploads/YYYY/MM/DD/<uuid>_<filename>
    """

    def __init__(self, base_path: str = "./uploads"):
        """
        Initialize local file storage.

        Args:
            base_path: Base directory for file storage
        """
        self.base_path = Path(base_path)
        # Create base directory synchronously on init
        self.base_path.mkdir(parents=True, exist_ok=True)

    @property
    def backend_name(self) -> str:
        return "local"

    def _get_storage_path(self, filename: str) -> tuple[Path, str]:
        """
        Generate a unique storage path for a file.

        Returns:
            Tuple of (full_path, relative_path)
        """
        # Organize by date: uploads/2026/01/22/<uuid>_<filename>
        date_path = datetime.utcnow().strftime("%Y/%m/%d")
        dir_path = self.base_path / date_path

        # Sanitize filename and make unique
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        if not safe_filename:
            safe_filename = "file"
        unique_name = f"{uuid.uuid4().hex[:12]}_{safe_filename}"

        full_path = dir_path / unique_name
        relative_path = f"{date_path}/{unique_name}"

        return full_path, relative_path

    async def save(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
    ) -> StoredFile:
        """
        Save a file to local disk.

        Args:
            file: File-like object to save
            filename: Original filename
            content_type: MIME type (stored for reference, not used)

        Returns:
            StoredFile with path, hash, and size
        """
        # Compute hash and size first
        file_hash = self.compute_hash(file)
        file_size = self.get_file_size(file)

        # Get storage path
        full_path, relative_path = self._get_storage_path(filename)

        # Create directory if needed
        await aiofiles.os.makedirs(full_path.parent, exist_ok=True)

        # Write file
        file.seek(0)
        content = file.read()
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)

        return StoredFile(
            storage_path=relative_path,
            sha256_hash=file_hash,
            file_size_bytes=file_size,
        )

    async def get(self, path: str) -> BinaryIO:
        """
        Retrieve a file from local disk.

        Args:
            path: Relative storage path

        Returns:
            BytesIO object with file contents

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        full_path = self.base_path / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        async with aiofiles.open(full_path, "rb") as f:
            content = await f.read()

        return BytesIO(content)

    async def delete(self, path: str) -> bool:
        """
        Delete a file from local disk.

        Args:
            path: Relative storage path

        Returns:
            True if deleted, False if not found
        """
        full_path = self.base_path / path
        if full_path.exists():
            await aiofiles.os.remove(full_path)
            return True
        return False

    async def exists(self, path: str) -> bool:
        """
        Check if a file exists on local disk.

        Args:
            path: Relative storage path

        Returns:
            True if exists, False otherwise
        """
        full_path = self.base_path / path
        return full_path.exists()
