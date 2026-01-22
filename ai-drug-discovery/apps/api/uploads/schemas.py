"""Pydantic schemas for upload API request/response models."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from db.models.upload import DuplicateAction, FileType, UploadStatus


# =============================================================================
# Column Mapping Schema
# =============================================================================


class ColumnMapping(BaseModel):
    """
    Column mapping for CSV uploads.

    Maps source column names to expected fields.
    """

    smiles: str = Field(
        ...,
        description="Source column containing SMILES strings",
    )
    name: str | None = Field(
        default=None,
        description="Source column containing molecule names",
    )
    external_id: str | None = Field(
        default=None,
        description="Source column containing external IDs (e.g., CAS numbers)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "smiles": "SMILES",
                "name": "Compound_Name",
                "external_id": "CAS_Number",
            }
        }
    )


# =============================================================================
# Request Schemas
# =============================================================================


class UploadCreateRequest(BaseModel):
    """Request body for initiating an upload (metadata only, file is separate)."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="User-provided name for this upload",
    )
    file_type: FileType = Field(
        ...,
        description="Type of file being uploaded",
    )
    column_mapping: ColumnMapping | None = Field(
        default=None,
        description="Column mapping for CSV files (required for CSV)",
    )
    duplicate_action: DuplicateAction = Field(
        default=DuplicateAction.SKIP,
        description="How to handle duplicate molecules",
    )
    similarity_threshold: Decimal | None = Field(
        default=Decimal("0.85"),
        ge=Decimal("0.5"),
        le=Decimal("1.0"),
        description="Tanimoto threshold for similarity-based duplicate detection",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Q1 2026 Screening Hits",
                "file_type": "csv",
                "column_mapping": {
                    "smiles": "SMILES",
                    "name": "Name",
                    "external_id": "CAS",
                },
                "duplicate_action": "skip",
                "similarity_threshold": "0.85",
            }
        }
    )


class UploadConfirmRequest(BaseModel):
    """Request body for confirming an upload."""

    acknowledge_errors: bool = Field(
        default=False,
        description="Acknowledge that there are validation errors",
    )
    proceed_with_valid_only: bool = Field(
        default=True,
        description="Proceed with valid rows only (skip errors)",
    )
    # Optional column mapping for CSV/Excel that need mapping
    column_mapping: ColumnMapping | None = Field(
        default=None,
        description="Column mapping for CSV/Excel uploads (required if needs_column_mapping is true)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "acknowledge_errors": True,
                "proceed_with_valid_only": True,
                "column_mapping": {
                    "smiles": "SMILES",
                    "name": "Compound_Name",
                    "external_id": "CAS_Number",
                },
            }
        }
    )


# =============================================================================
# Response Schemas - Nested Objects
# =============================================================================


class UploadFileResponse(BaseModel):
    """File metadata in upload response."""

    original_filename: str
    file_size_bytes: int
    content_type: str

    model_config = ConfigDict(from_attributes=True)


class UploadProgressResponse(BaseModel):
    """Progress tracking in upload response."""

    phase: str
    total_rows: int
    processed_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_exact: int
    duplicate_similar: int
    percent_complete: float

    model_config = ConfigDict(from_attributes=True)


class ValidationSummaryResponse(BaseModel):
    """Summary of validation results for awaiting_confirm state."""

    ready_to_insert: int = Field(
        ...,
        description="Molecules ready to be inserted",
    )
    will_skip_duplicates: int = Field(
        ...,
        description="Duplicates that will be skipped",
    )
    errors_to_review: int = Field(
        ...,
        description="Rows with errors",
    )
    error_rate_percent: float = Field(
        ...,
        description="Percentage of rows with errors",
    )


class ColumnMappingInfo(BaseModel):
    """Information about column mapping for CSV/Excel uploads."""

    needs_mapping: bool = Field(
        ...,
        description="True if user needs to provide column mapping",
    )
    available_columns: list[str] = Field(
        default_factory=list,
        description="List of column names detected in the file",
    )
    inferred_mapping: dict[str, str | None] | None = Field(
        default=None,
        description="Auto-inferred column mapping suggestion (may be partial)",
    )
    current_mapping: dict[str, str | None] | None = Field(
        default=None,
        description="Currently configured column mapping",
    )


class ResultSummaryResponse(BaseModel):
    """Final processing results for completed uploads."""

    molecules_created: int
    molecules_updated: int
    molecules_skipped: int
    errors_count: int
    exact_duplicates_found: int
    similar_duplicates_found: int
    processing_duration_seconds: float | None

    model_config = ConfigDict(from_attributes=True)


class UploadLinksResponse(BaseModel):
    """HATEOAS links for upload resource."""

    status: str
    errors: str
    confirm: str | None = None


class UploadActionsResponse(BaseModel):
    """Available actions for the current state."""

    confirm: str | None = None
    cancel: str | None = None


# =============================================================================
# Response Schemas - Main Upload
# =============================================================================


class UploadResponse(BaseModel):
    """Response for upload creation."""

    id: UUID
    name: str
    status: UploadStatus
    file_type: FileType
    file: UploadFileResponse | None = None
    column_mapping: dict | None = None
    duplicate_action: DuplicateAction
    similarity_threshold: Decimal | None
    created_at: datetime
    links: UploadLinksResponse

    model_config = ConfigDict(from_attributes=True)


class UploadStatusResponse(BaseModel):
    """Response for upload status check."""

    id: UUID
    name: str
    status: UploadStatus
    file_type: FileType | None = None
    progress: UploadProgressResponse | None = None
    validation_summary: ValidationSummaryResponse | None = None
    column_mapping_info: ColumnMappingInfo | None = None
    summary: ResultSummaryResponse | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    validated_at: datetime | None = None
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    actions: UploadActionsResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class UploadConfirmResponse(BaseModel):
    """Response for upload confirmation."""

    id: UUID
    status: UploadStatus
    message: str
    estimated_completion_seconds: int | None = None
    links: UploadLinksResponse

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Response Schemas - Errors
# =============================================================================


class RowErrorResponse(BaseModel):
    """Individual row error in error list."""

    row_number: int
    error_code: str
    error_message: str
    field_name: str | None = None
    raw_data: dict | None = None
    duplicate_inchi_key: str | None = None
    duplicate_similarity: float | None = None

    model_config = ConfigDict(from_attributes=True)


class ErrorSummaryResponse(BaseModel):
    """Summary counts by error code."""

    # Dynamic dict of error_code -> count
    pass


class UploadErrorsResponse(BaseModel):
    """Response for upload errors list."""

    upload_id: UUID
    total_errors: int
    page: int
    limit: int
    errors: list[RowErrorResponse]
    error_summary: dict[str, int] = Field(
        default_factory=dict,
        description="Count of errors by error code",
    )

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Error Response Schemas
# =============================================================================


class UploadErrorResponse(BaseModel):
    """Error response for upload operations."""

    error: str
    message: str
    current_status: UploadStatus | None = None
    allowed_actions: list[str] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "invalid_state_transition",
                "message": "Upload is in 'validating' state and cannot be confirmed yet",
                "current_status": "validating",
                "allowed_actions": ["cancel"],
            }
        }
    )
