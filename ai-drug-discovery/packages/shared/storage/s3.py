"""S3/MinIO file storage backend for production."""

import uuid
from datetime import datetime
from io import BytesIO
from typing import BinaryIO

from packages.shared.storage.base import FileStorageBackend, StoredFile

# Optional dependency - only required if using S3 storage
try:
    import aioboto3
    from botocore.exceptions import ClientError

    AIOBOTO3_AVAILABLE = True
except ImportError:
    AIOBOTO3_AVAILABLE = False
    aioboto3 = None  # type: ignore
    ClientError = Exception  # type: ignore


class S3FileStorage(FileStorageBackend):
    """
    S3/MinIO storage backend for production.

    Supports both AWS S3 and MinIO (via endpoint_url configuration).
    Files are organized by prefix and date: uploads/YYYY/MM/DD/<uuid>_<filename>
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        region: str = "us-east-1",
        prefix: str = "uploads",
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ):
        """
        Initialize S3 file storage.

        Args:
            bucket: S3 bucket name
            endpoint_url: Custom endpoint URL for MinIO (None for AWS S3)
            region: AWS region
            prefix: Key prefix for all uploads
            aws_access_key_id: AWS access key (optional, uses env/IAM if not set)
            aws_secret_access_key: AWS secret key (optional, uses env/IAM if not set)
        """
        if not AIOBOTO3_AVAILABLE:
            raise ImportError(
                "aioboto3 is required for S3 storage. "
                "Install with: pip install aioboto3"
            )

        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.region = region
        self.prefix = prefix.strip("/")
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self._session = aioboto3.Session()

    @property
    def backend_name(self) -> str:
        return "s3"

    def _get_client_kwargs(self) -> dict:
        """Build kwargs for S3 client."""
        kwargs = {
            "region_name": self.region,
        }
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        if self.aws_access_key_id and self.aws_secret_access_key:
            kwargs["aws_access_key_id"] = self.aws_access_key_id
            kwargs["aws_secret_access_key"] = self.aws_secret_access_key
        return kwargs

    def _get_storage_key(self, filename: str) -> str:
        """
        Generate a unique S3 key for a file.

        Returns:
            S3 key in format: prefix/YYYY/MM/DD/<uuid>_<filename>
        """
        date_path = datetime.utcnow().strftime("%Y/%m/%d")

        # Sanitize filename
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        if not safe_filename:
            safe_filename = "file"
        unique_name = f"{uuid.uuid4().hex[:12]}_{safe_filename}"

        return f"{self.prefix}/{date_path}/{unique_name}"

    async def save(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
    ) -> StoredFile:
        """
        Save a file to S3.

        Args:
            file: File-like object to save
            filename: Original filename
            content_type: MIME type for Content-Type header

        Returns:
            StoredFile with S3 key, hash, and size
        """
        # Compute hash and size first
        file_hash = self.compute_hash(file)
        file_size = self.get_file_size(file)

        # Get S3 key
        key = self._get_storage_key(filename)

        # Upload to S3
        file.seek(0)
        async with self._session.client("s3", **self._get_client_kwargs()) as s3:
            await s3.upload_fileobj(
                file,
                self.bucket,
                key,
                ExtraArgs={
                    "ContentType": content_type,
                    "Metadata": {
                        "sha256": file_hash,
                        "original_filename": filename,
                    },
                },
            )

        return StoredFile(
            storage_path=key,
            sha256_hash=file_hash,
            file_size_bytes=file_size,
        )

    async def get(self, path: str) -> BinaryIO:
        """
        Retrieve a file from S3.

        Args:
            path: S3 key

        Returns:
            BytesIO object with file contents

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        async with self._session.client("s3", **self._get_client_kwargs()) as s3:
            try:
                response = await s3.get_object(Bucket=self.bucket, Key=path)
                content = await response["Body"].read()
                return BytesIO(content)
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                    raise FileNotFoundError(f"File not found: {path}")
                raise

    async def delete(self, path: str) -> bool:
        """
        Delete a file from S3.

        Args:
            path: S3 key

        Returns:
            True if deleted (S3 always returns success for delete)
        """
        async with self._session.client("s3", **self._get_client_kwargs()) as s3:
            await s3.delete_object(Bucket=self.bucket, Key=path)
            return True

    async def exists(self, path: str) -> bool:
        """
        Check if a file exists in S3.

        Args:
            path: S3 key

        Returns:
            True if exists, False otherwise
        """
        async with self._session.client("s3", **self._get_client_kwargs()) as s3:
            try:
                await s3.head_object(Bucket=self.bucket, Key=path)
                return True
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") == "404":
                    return False
                raise

    async def generate_presigned_url(
        self,
        path: str,
        expires_in: int = 3600,
        method: str = "get_object",
    ) -> str:
        """
        Generate a presigned URL for direct file access.

        Args:
            path: S3 key
            expires_in: URL expiration time in seconds
            method: S3 operation (get_object or put_object)

        Returns:
            Presigned URL string
        """
        async with self._session.client("s3", **self._get_client_kwargs()) as s3:
            url = await s3.generate_presigned_url(
                ClientMethod=method,
                Params={"Bucket": self.bucket, "Key": path},
                ExpiresIn=expires_in,
            )
            return url
