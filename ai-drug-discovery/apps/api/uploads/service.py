"""
Upload service for molecule data ingestion.

Handles:
- Upload creation and file storage
- Validation orchestration
- Duplicate detection (exact and similarity-based)
- State management
- Progress tracking
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.uploads.error_codes import UploadErrorCode, get_error_message
from db.models.discovery import Molecule
from db.models.upload import (
    DuplicateAction,
    FileType,
    Upload,
    UploadFile,
    UploadProgress,
    UploadResultSummary,
    UploadRowError,
    UploadStatus,
)
from packages.shared.storage import FileStorageBackend


class UploadService:
    """
    Service for managing molecule uploads.

    Coordinates file storage, validation, duplicate detection,
    and database operations for the upload workflow.
    """

    # Maximum rows per upload
    MAX_ROWS = 100_000

    # Maximum file size (100 MB)
    MAX_FILE_SIZE = 100 * 1024 * 1024

    # Upload expiry time (24 hours)
    UPLOAD_EXPIRY_HOURS = 24

    # Batch size for duplicate checks
    DUPLICATE_CHECK_BATCH_SIZE = 100

    def __init__(
        self,
        db: AsyncSession,
        storage: FileStorageBackend,
    ):
        """
        Initialize upload service.

        Args:
            db: Async database session
            storage: File storage backend
        """
        self.db = db
        self.storage = storage

    # =========================================================================
    # Upload Creation
    # =========================================================================

    async def create_upload(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        file_type: FileType,
        file: BinaryIO,
        filename: str,
        content_type: str,
        column_mapping: dict | None = None,
        duplicate_action: DuplicateAction = DuplicateAction.SKIP,
        similarity_threshold: Decimal | None = Decimal("0.85"),
    ) -> Upload:
        """
        Create a new upload and store the file.

        Args:
            organization_id: Organization ID
            user_id: User ID
            name: Upload name
            file_type: Type of file (sdf, csv, smiles_list)
            file: File-like object
            filename: Original filename
            content_type: MIME type
            column_mapping: Column mapping for CSV
            duplicate_action: How to handle duplicates
            similarity_threshold: Tanimoto threshold for similarity

        Returns:
            Created Upload object

        Raises:
            ValueError: If validation fails
        """
        # Validate file size
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)

        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(
                f"File size {file_size} exceeds maximum {self.MAX_FILE_SIZE} bytes"
            )

        # Validate CSV has column mapping
        if file_type == FileType.CSV and not column_mapping:
            raise ValueError("column_mapping is required for CSV uploads")

        # Store the file
        stored_file = await self.storage.save(file, filename, content_type)

        # Create upload record
        upload = Upload(
            organization_id=organization_id,
            created_by=user_id,
            name=name,
            file_type=file_type,
            status=UploadStatus.INITIATED,
            column_mapping=column_mapping,
            duplicate_action=duplicate_action,
            similarity_threshold=similarity_threshold,
            expires_at=datetime.now(UTC) + timedelta(hours=self.UPLOAD_EXPIRY_HOURS),
        )
        self.db.add(upload)
        await self.db.flush()

        # Create file record
        upload_file = UploadFile(
            upload_id=upload.id,
            original_filename=filename,
            content_type=content_type,
            file_size_bytes=stored_file.file_size_bytes,
            storage_backend=self.storage.backend_name,
            storage_path=stored_file.storage_path,
            sha256_hash=stored_file.sha256_hash,
        )
        self.db.add(upload_file)

        # Create progress record
        progress = UploadProgress(
            upload_id=upload.id,
            phase="initializing",
        )
        self.db.add(progress)

        await self.db.commit()
        await self.db.refresh(upload)

        return upload

    # =========================================================================
    # Upload Retrieval
    # =========================================================================

    async def get_upload(
        self,
        upload_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> Upload | None:
        """
        Get an upload by ID, scoped to organization.

        Args:
            upload_id: Upload ID
            organization_id: Organization ID for access control

        Returns:
            Upload if found and accessible, None otherwise
        """
        stmt = select(Upload).where(
            Upload.id == upload_id,
            Upload.organization_id == organization_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_upload_with_relations(
        self,
        upload_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> Upload | None:
        """
        Get an upload with all related data loaded.

        Args:
            upload_id: Upload ID
            organization_id: Organization ID

        Returns:
            Upload with file, progress, summary loaded
        """
        upload = await self.get_upload(upload_id, organization_id)
        if upload:
            # Eager load relationships
            await self.db.refresh(upload, ["file", "progress", "summary"])
        return upload

    # =========================================================================
    # State Transitions
    # =========================================================================

    async def start_validation(self, upload: Upload) -> None:
        """
        Transition upload to VALIDATING state.

        Args:
            upload: Upload to transition

        Raises:
            ValueError: If transition not allowed
        """
        upload.transition_to(UploadStatus.VALIDATING)
        if upload.progress:
            upload.progress.phase = "parsing"
            upload.progress.started_at = datetime.now(UTC)
        await self.db.commit()

    async def complete_validation(
        self,
        upload: Upload,
        total_rows: int,
        valid_rows: int,
        invalid_rows: int,
        duplicate_exact: int,
        duplicate_similar: int,
    ) -> None:
        """
        Complete validation and transition to appropriate state.

        Args:
            upload: Upload to transition
            total_rows: Total rows in file
            valid_rows: Valid rows
            invalid_rows: Invalid rows
            duplicate_exact: Exact duplicates found
            duplicate_similar: Similar duplicates found
        """
        # Update progress
        if upload.progress:
            upload.progress.total_rows = total_rows
            upload.progress.processed_rows = total_rows
            upload.progress.valid_rows = valid_rows
            upload.progress.invalid_rows = invalid_rows
            upload.progress.duplicate_exact = duplicate_exact
            upload.progress.duplicate_similar = duplicate_similar
            upload.progress.phase = "validation_complete"

        # Determine next state based on error rate
        error_rate = invalid_rows / total_rows if total_rows > 0 else 0

        if error_rate > 0.5:
            # More than 50% errors - fail validation
            upload.status = UploadStatus.VALIDATION_FAILED
            upload.error_message = f"Validation failed: {error_rate:.1%} of rows had errors"
        else:
            upload.status = UploadStatus.AWAITING_CONFIRM

        upload.validated_at = datetime.now(UTC)
        await self.db.commit()

    async def confirm_upload(self, upload: Upload) -> None:
        """
        Confirm upload and transition to PROCESSING state.

        Args:
            upload: Upload to confirm

        Raises:
            ValueError: If not in AWAITING_CONFIRM state
        """
        upload.transition_to(UploadStatus.PROCESSING)
        upload.confirmed_at = datetime.now(UTC)
        if upload.progress:
            upload.progress.phase = "inserting"
            upload.progress.processed_rows = 0  # Reset for insertion phase
        await self.db.commit()

    async def cancel_upload(self, upload: Upload) -> None:
        """
        Cancel an upload awaiting confirmation.

        Args:
            upload: Upload to cancel

        Raises:
            ValueError: If not in AWAITING_CONFIRM state
        """
        upload.transition_to(UploadStatus.CANCELLED)
        await self.db.commit()

        # Optionally clean up stored file
        if upload.file:
            await self.storage.delete(upload.file.storage_path)

    async def complete_processing(
        self,
        upload: Upload,
        molecules_created: int,
        molecules_updated: int,
        molecules_skipped: int,
        errors_count: int,
        exact_duplicates: int,
        similar_duplicates: int,
        duration_seconds: float,
    ) -> None:
        """
        Complete processing and create result summary.

        Args:
            upload: Upload to complete
            molecules_created: New molecules created
            molecules_updated: Existing molecules updated
            molecules_skipped: Molecules skipped (duplicates)
            errors_count: Processing errors
            exact_duplicates: Exact duplicates found
            similar_duplicates: Similar duplicates found
            duration_seconds: Processing time
        """
        upload.transition_to(UploadStatus.COMPLETED)
        upload.completed_at = datetime.now(UTC)

        if upload.progress:
            upload.progress.phase = "completed"

        # Create summary
        summary = UploadResultSummary(
            upload_id=upload.id,
            molecules_created=molecules_created,
            molecules_updated=molecules_updated,
            molecules_skipped=molecules_skipped,
            errors_count=errors_count,
            exact_duplicates_found=exact_duplicates,
            similar_duplicates_found=similar_duplicates,
            processing_duration_seconds=Decimal(str(duration_seconds)),
        )
        self.db.add(summary)
        await self.db.commit()

    async def fail_upload(self, upload: Upload, error_message: str) -> None:
        """
        Mark upload as failed.

        Args:
            upload: Upload to fail
            error_message: Error description
        """
        if upload.can_transition_to(UploadStatus.FAILED):
            upload.status = UploadStatus.FAILED
        upload.error_message = error_message
        await self.db.commit()

    # =========================================================================
    # Progress Tracking
    # =========================================================================

    async def update_progress(
        self,
        upload: Upload,
        processed_rows: int | None = None,
        valid_rows: int | None = None,
        invalid_rows: int | None = None,
        duplicate_exact: int | None = None,
        duplicate_similar: int | None = None,
        phase: str | None = None,
    ) -> None:
        """
        Update upload progress.

        Args:
            upload: Upload to update
            processed_rows: Rows processed so far
            valid_rows: Valid rows so far
            invalid_rows: Invalid rows so far
            duplicate_exact: Exact duplicates found
            duplicate_similar: Similar duplicates found
            phase: Current phase name
        """
        if not upload.progress:
            return

        if processed_rows is not None:
            upload.progress.processed_rows = processed_rows
        if valid_rows is not None:
            upload.progress.valid_rows = valid_rows
        if invalid_rows is not None:
            upload.progress.invalid_rows = invalid_rows
        if duplicate_exact is not None:
            upload.progress.duplicate_exact = duplicate_exact
        if duplicate_similar is not None:
            upload.progress.duplicate_similar = duplicate_similar
        if phase is not None:
            upload.progress.phase = phase

        await self.db.commit()

    # =========================================================================
    # Error Recording
    # =========================================================================

    async def add_row_error(
        self,
        upload: Upload,
        row_number: int,
        error_code: UploadErrorCode,
        detail: str | None = None,
        field_name: str | None = None,
        raw_data: dict | None = None,
        duplicate_inchi_key: str | None = None,
        duplicate_similarity: Decimal | None = None,
    ) -> UploadRowError:
        """
        Record a row-level error.

        Args:
            upload: Upload record
            row_number: 1-based row number
            error_code: Structured error code
            detail: Additional error detail
            field_name: Field that caused error
            raw_data: Row data for debugging (truncated)
            duplicate_inchi_key: InChIKey of duplicate
            duplicate_similarity: Similarity score

        Returns:
            Created UploadRowError
        """
        # Truncate raw_data to prevent huge storage
        if raw_data:
            truncated_data = {
                k: (v[:100] + "..." if isinstance(v, str) and len(v) > 100 else v)
                for k, v in raw_data.items()
            }
        else:
            truncated_data = None

        error = UploadRowError(
            upload_id=upload.id,
            row_number=row_number,
            error_code=error_code.value,
            error_message=get_error_message(error_code, detail),
            field_name=field_name,
            raw_data=truncated_data,
            duplicate_inchi_key=duplicate_inchi_key,
            duplicate_similarity=duplicate_similarity,
        )
        self.db.add(error)
        return error

    async def add_row_errors_batch(
        self,
        errors: list[UploadRowError],
    ) -> None:
        """
        Add multiple row errors in batch.

        Args:
            errors: List of error objects to add
        """
        self.db.add_all(errors)
        await self.db.flush()

    async def get_errors(
        self,
        upload: Upload,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[UploadRowError], int]:
        """
        Get paginated errors for an upload.

        Args:
            upload: Upload record
            page: Page number (1-based)
            limit: Items per page

        Returns:
            Tuple of (errors, total_count)
        """
        # Count total
        count_stmt = select(func.count()).where(UploadRowError.upload_id == upload.id)
        total = (await self.db.execute(count_stmt)).scalar() or 0

        # Get page
        offset = (page - 1) * limit
        stmt = (
            select(UploadRowError)
            .where(UploadRowError.upload_id == upload.id)
            .order_by(UploadRowError.row_number)
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        errors = list(result.scalars().all())

        return errors, total

    async def get_error_summary(self, upload: Upload) -> dict[str, int]:
        """
        Get error counts grouped by error code.

        Args:
            upload: Upload record

        Returns:
            Dict of error_code -> count
        """
        stmt = (
            select(
                UploadRowError.error_code,
                func.count().label("count"),
            )
            .where(UploadRowError.upload_id == upload.id)
            .group_by(UploadRowError.error_code)
        )
        result = await self.db.execute(stmt)
        return {row.error_code: row.count for row in result}

    # =========================================================================
    # Duplicate Detection
    # =========================================================================

    async def check_exact_duplicate(
        self,
        organization_id: uuid.UUID,
        inchi_key: str,
    ) -> Molecule | None:
        """
        Check for exact duplicate by InChIKey.

        Args:
            organization_id: Organization ID
            inchi_key: InChIKey to check

        Returns:
            Existing Molecule if found, None otherwise
        """
        stmt = select(Molecule).where(
            Molecule.organization_id == organization_id,
            Molecule.inchi_key == inchi_key,
            Molecule.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def check_exact_duplicates_batch(
        self,
        organization_id: uuid.UUID,
        inchi_keys: list[str],
    ) -> dict[str, Molecule]:
        """
        Check for exact duplicates in batch.

        Args:
            organization_id: Organization ID
            inchi_keys: List of InChIKeys to check

        Returns:
            Dict of inchi_key -> Molecule for existing molecules
        """
        if not inchi_keys:
            return {}

        stmt = select(Molecule).where(
            Molecule.organization_id == organization_id,
            Molecule.inchi_key.in_(inchi_keys),
            Molecule.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        molecules = result.scalars().all()

        return {m.inchi_key: m for m in molecules}

    async def find_similar_molecules(
        self,
        organization_id: uuid.UUID,
        fingerprint_bytes: bytes,
        threshold: Decimal,
        limit: int = 10,
    ) -> list[tuple[Molecule, float]]:
        """
        Find molecules similar to the given fingerprint.

        This is a placeholder implementation using brute-force comparison.
        For production, use a vector index (pgvector, Pinecone, etc.).

        Args:
            organization_id: Organization ID
            fingerprint_bytes: Morgan fingerprint bytes
            threshold: Tanimoto similarity threshold
            limit: Maximum results

        Returns:
            List of (Molecule, similarity_score) tuples
        """
        # For MVP, we'll do a simple in-database comparison
        # In production, this would use a vector index
        from packages.chemistry import tanimoto_similarity_bytes

        # Get molecules with fingerprints
        stmt = select(Molecule).where(
            Molecule.organization_id == organization_id,
            Molecule.fingerprint_morgan.isnot(None),
            Molecule.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        molecules = result.scalars().all()

        # Calculate similarities
        similar = []
        for mol in molecules:
            if mol.fingerprint_morgan:
                similarity = tanimoto_similarity_bytes(
                    fingerprint_bytes,
                    mol.fingerprint_morgan,
                )
                if similarity >= float(threshold):
                    similar.append((mol, similarity))

        # Sort by similarity and limit
        similar.sort(key=lambda x: x[1], reverse=True)
        return similar[:limit]

    # =========================================================================
    # File Access
    # =========================================================================

    async def get_upload_file_content(self, upload: Upload) -> BytesIO:
        """
        Get the content of an upload's file.

        Args:
            upload: Upload record

        Returns:
            BytesIO with file content

        Raises:
            ValueError: If upload has no file
            FileNotFoundError: If file not in storage
        """
        if not upload.file:
            raise ValueError("Upload has no associated file")

        return await self.storage.get(upload.file.storage_path)

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def cleanup_expired_uploads(self) -> int:
        """
        Cancel and clean up expired unconfirmed uploads.

        Returns:
            Number of uploads cleaned up
        """
        now = datetime.now(UTC)
        stmt = select(Upload).where(
            Upload.status == UploadStatus.AWAITING_CONFIRM,
            Upload.expires_at < now,
        )
        result = await self.db.execute(stmt)
        uploads = result.scalars().all()

        count = 0
        for upload in uploads:
            await self.cancel_upload(upload)
            count += 1

        return count
