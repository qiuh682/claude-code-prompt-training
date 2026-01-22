"""
SQLAlchemy models for the Custom Data Upload System.

Tables:
- Upload: Main upload job record with settings and state
- UploadFile: File storage reference and metadata
- UploadProgress: Real-time progress tracking
- UploadRowError: Per-row validation errors
- UploadResultSummary: Final processing statistics
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base_model import BaseModel, TimestampMixin


class UploadStatus(str, Enum):
    """Upload job states."""

    INITIATED = "initiated"
    VALIDATING = "validating"
    VALIDATION_FAILED = "validation_failed"
    AWAITING_CONFIRM = "awaiting_confirm"
    CANCELLED = "cancelled"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FileType(str, Enum):
    """Supported upload file types."""

    SDF = "sdf"
    CSV = "csv"
    EXCEL = "excel"
    SMILES_LIST = "smiles_list"


class DuplicateAction(str, Enum):
    """How to handle duplicate molecules."""

    SKIP = "skip"  # Skip duplicates silently
    UPDATE = "update"  # Update existing records
    ERROR = "error"  # Treat duplicates as errors


# Valid state transitions
VALID_TRANSITIONS: dict[UploadStatus, list[UploadStatus]] = {
    UploadStatus.INITIATED: [UploadStatus.VALIDATING],
    UploadStatus.VALIDATING: [
        UploadStatus.AWAITING_CONFIRM,
        UploadStatus.VALIDATION_FAILED,
        UploadStatus.FAILED,
    ],
    UploadStatus.VALIDATION_FAILED: [],  # Terminal
    UploadStatus.AWAITING_CONFIRM: [
        UploadStatus.PROCESSING,
        UploadStatus.CANCELLED,
    ],
    UploadStatus.CANCELLED: [],  # Terminal
    UploadStatus.PROCESSING: [
        UploadStatus.COMPLETED,
        UploadStatus.FAILED,
    ],
    UploadStatus.COMPLETED: [],  # Terminal
    UploadStatus.FAILED: [],  # Terminal
}


def can_transition(current: UploadStatus, target: UploadStatus) -> bool:
    """Check if a state transition is valid."""
    return target in VALID_TRANSITIONS.get(current, [])


class Upload(BaseModel, TimestampMixin):
    """
    Main upload job record.

    Tracks the full lifecycle of a molecule upload from initiation through
    validation, confirmation, and processing to completion.
    """

    __tablename__ = "uploads"

    # --- Tenant Isolation ---
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )

    # --- Upload Metadata ---
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="User-provided upload name",
    )
    file_type: Mapped[FileType] = mapped_column(
        nullable=False,
        comment="sdf, csv, or smiles_list",
    )
    status: Mapped[UploadStatus] = mapped_column(
        default=UploadStatus.INITIATED,
        nullable=False,
        index=True,
    )

    # --- Duplicate Handling Settings ---
    duplicate_action: Mapped[DuplicateAction] = mapped_column(
        default=DuplicateAction.SKIP,
        nullable=False,
    )
    similarity_threshold: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3),
        default=Decimal("0.850"),
        nullable=True,
        comment="Tanimoto threshold for similarity-based duplicate detection",
    )

    # --- CSV/Excel Column Mapping (null for SDF/SMILES) ---
    column_mapping: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment='{"smiles": "SMILES_COL", "name": "Compound_Name", ...}',
    )
    needs_column_mapping: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="True if CSV/Excel upload requires user to provide column mapping",
    )
    available_columns: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="List of column names detected in CSV/Excel file",
    )
    inferred_mapping: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Auto-inferred column mapping suggestion",
    )

    # --- Error Information ---
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="High-level error message if failed",
    )

    # --- Lifecycle Timestamps ---
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Auto-cancel unconfirmed uploads after this time",
    )

    # --- Relationships ---
    file: Mapped["UploadFile | None"] = relationship(
        "UploadFile",
        back_populates="upload",
        uselist=False,
        cascade="all, delete-orphan",
    )
    progress: Mapped["UploadProgress | None"] = relationship(
        "UploadProgress",
        back_populates="upload",
        uselist=False,
        cascade="all, delete-orphan",
    )
    summary: Mapped["UploadResultSummary | None"] = relationship(
        "UploadResultSummary",
        back_populates="upload",
        uselist=False,
        cascade="all, delete-orphan",
    )
    row_errors: Mapped[list["UploadRowError"]] = relationship(
        "UploadRowError",
        back_populates="upload",
        cascade="all, delete-orphan",
        order_by="UploadRowError.row_number",
    )

    # --- Table Configuration ---
    __table_args__ = (
        Index("ix_uploads_org_status", "organization_id", "status"),
        Index("ix_uploads_org_created", "organization_id", "created_at"),
        Index("ix_uploads_created_by", "created_by"),
        {"comment": "Molecule upload job records"},
    )

    def __repr__(self) -> str:
        return f"<Upload {self.name} ({self.status.value})>"

    def can_transition_to(self, target: UploadStatus) -> bool:
        """Check if this upload can transition to the target state."""
        return can_transition(self.status, target)

    def transition_to(self, target: UploadStatus) -> None:
        """
        Transition to a new state.

        Raises:
            ValueError: If the transition is not allowed.
        """
        if not self.can_transition_to(target):
            raise ValueError(
                f"Cannot transition from {self.status.value} to {target.value}"
            )
        self.status = target


class UploadFile(BaseModel, TimestampMixin):
    """
    Uploaded file storage reference.

    Stores metadata about the uploaded file and its storage location,
    supporting both local disk and S3/MinIO backends.
    """

    __tablename__ = "upload_files"

    # --- Foreign Key ---
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("uploads.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # --- File Metadata ---
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # --- Storage Location ---
    storage_backend: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="local or s3",
    )
    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Relative path (local) or S3 key",
    )

    # --- Integrity ---
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash for integrity verification",
    )

    # --- Relationship ---
    upload: Mapped["Upload"] = relationship("Upload", back_populates="file")

    # --- Table Configuration ---
    __table_args__ = (
        Index("ix_upload_files_hash", "sha256_hash"),
        {"comment": "Uploaded file storage references"},
    )

    def __repr__(self) -> str:
        return f"<UploadFile {self.original_filename} ({self.file_size_bytes} bytes)>"


class UploadProgress(BaseModel):
    """
    Real-time progress tracking for upload processing.

    Updated frequently during validation and processing phases
    to provide live feedback to users.
    """

    __tablename__ = "upload_progress"

    # --- Foreign Key ---
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("uploads.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # --- Progress Counters ---
    total_rows: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    processed_rows: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    valid_rows: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    invalid_rows: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    duplicate_exact: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="InChIKey exact matches",
    )
    duplicate_similar: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Tanimoto similarity matches",
    )

    # --- Current Phase ---
    phase: Mapped[str] = mapped_column(
        String(50),
        default="initializing",
        nullable=False,
        comment="parsing, validating, checking_duplicates, inserting",
    )

    # --- Timing ---
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --- Relationship ---
    upload: Mapped["Upload"] = relationship("Upload", back_populates="progress")

    # --- Table Configuration ---
    __table_args__ = ({"comment": "Real-time upload progress tracking"},)

    def __repr__(self) -> str:
        return f"<UploadProgress {self.processed_rows}/{self.total_rows} ({self.phase})>"

    @property
    def percent_complete(self) -> float:
        """Calculate completion percentage."""
        if self.total_rows == 0:
            return 0.0
        return round((self.processed_rows / self.total_rows) * 100, 1)


class UploadRowError(BaseModel):
    """
    Individual row-level validation errors.

    Stores detailed error information for each failed row,
    including the raw data for debugging and user review.
    """

    __tablename__ = "upload_row_errors"

    # --- Foreign Key ---
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Error Details ---
    row_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="1-based row number in source file",
    )
    error_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Structured error code",
    )
    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable error message",
    )

    # --- Context ---
    raw_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Truncated row data for debugging",
    )
    field_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Which field caused the error",
    )

    # --- Duplicate Reference ---
    duplicate_inchi_key: Mapped[str | None] = mapped_column(
        String(27),
        nullable=True,
        comment="InChIKey of existing duplicate molecule",
    )
    duplicate_similarity: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3),
        nullable=True,
        comment="Tanimoto similarity score for similar duplicates",
    )

    # --- Relationship ---
    upload: Mapped["Upload"] = relationship("Upload", back_populates="row_errors")

    # --- Table Configuration ---
    __table_args__ = (
        UniqueConstraint("upload_id", "row_number", name="uq_upload_row_error"),
        Index("ix_upload_row_errors_code", "upload_id", "error_code"),
        {"comment": "Per-row validation errors"},
    )

    def __repr__(self) -> str:
        return f"<UploadRowError row={self.row_number} code={self.error_code}>"


class UploadResultSummary(BaseModel):
    """
    Final results after upload processing completes.

    Created once processing finishes, providing a summary of
    what was created, updated, skipped, and failed.
    """

    __tablename__ = "upload_result_summaries"

    # --- Foreign Key ---
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("uploads.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # --- Final Counts ---
    molecules_created: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    molecules_updated: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    molecules_skipped: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    errors_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # --- Duplicate Breakdown ---
    exact_duplicates_found: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    similar_duplicates_found: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # --- Processing Time ---
    processing_duration_seconds: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    # --- Timestamp ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- Relationship ---
    upload: Mapped["Upload"] = relationship("Upload", back_populates="summary")

    # --- Table Configuration ---
    __table_args__ = ({"comment": "Final upload processing statistics"},)

    def __repr__(self) -> str:
        return (
            f"<UploadResultSummary created={self.molecules_created} "
            f"errors={self.errors_count}>"
        )
