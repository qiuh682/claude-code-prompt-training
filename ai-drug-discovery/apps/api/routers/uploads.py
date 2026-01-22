"""
Upload API endpoints for molecule data ingestion.

Endpoints:
- POST /uploads: Initiate a new upload
- GET /uploads/{id}/status: Check upload status and progress
- GET /uploads/{id}/errors: List validation errors
- POST /uploads/{id}/confirm: Confirm and process upload
- DELETE /uploads/{id}: Cancel upload
"""

import uuid
from decimal import Decimal
from io import BytesIO
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile as FastAPIUploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.uploads.error_codes import UploadErrorCode
from apps.api.uploads.file_detection import detect_file_type
from apps.api.uploads.schemas import (
    ColumnMapping,
    ColumnMappingInfo,
    RowErrorResponse,
    UploadActionsResponse,
    UploadConfirmRequest,
    UploadConfirmResponse,
    UploadErrorResponse,
    UploadErrorsResponse,
    UploadFileResponse,
    UploadLinksResponse,
    UploadProgressResponse,
    UploadResponse,
    UploadStatusResponse,
    ResultSummaryResponse,
    ValidationSummaryResponse,
)
from apps.api.uploads.service import UploadService
from apps.api.uploads.tasks import run_insertion_task, run_validation_task
from db.models.upload import DuplicateAction, FileType, Upload, UploadStatus
from db.session import get_async_session
from packages.shared.storage import get_storage_backend

router = APIRouter()


# =============================================================================
# Dependencies
# =============================================================================


async def get_upload_service(
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> UploadService:
    """Get upload service with dependencies."""
    storage = get_storage_backend()
    return UploadService(db, storage)


# Placeholder for auth - in real app, this would be from JWT
async def get_current_user() -> dict:
    """Get current authenticated user (placeholder)."""
    return {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "organization_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
    }


# =============================================================================
# Helper Functions
# =============================================================================


def build_links(upload_id: uuid.UUID, include_confirm: bool = False) -> UploadLinksResponse:
    """Build HATEOAS links for upload."""
    base = f"/api/v1/uploads/{upload_id}"
    return UploadLinksResponse(
        status=f"{base}/status",
        errors=f"{base}/errors",
        confirm=f"{base}/confirm" if include_confirm else None,
    )


def build_actions(upload: Upload) -> UploadActionsResponse | None:
    """Build available actions based on upload state."""
    if upload.status == UploadStatus.AWAITING_CONFIRM:
        base = f"/api/v1/uploads/{upload.id}"
        return UploadActionsResponse(
            confirm=f"POST {base}/confirm",
            cancel=f"DELETE {base}",
        )
    return None


# =============================================================================
# POST /uploads - Initiate Upload
# =============================================================================


@router.post(
    "",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Initiate a new upload",
    description="Upload a file containing molecules (SDF, CSV, or SMILES list) for processing.",
)
async def create_upload(
    background_tasks: BackgroundTasks,
    service: Annotated[UploadService, Depends(get_upload_service)],
    user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    file: Annotated[FastAPIUploadFile, File(description="File to upload")],
    name: Annotated[str, Form(description="Name for this upload")],
    file_type: Annotated[
        FileType | None, Form(description="Type of file (auto-detected if not provided)")
    ] = None,
    duplicate_action: Annotated[
        DuplicateAction, Form(description="How to handle duplicates")
    ] = DuplicateAction.SKIP,
    similarity_threshold: Annotated[
        str | None, Form(description="Tanimoto threshold (0.5-1.0)")
    ] = "0.85",
    smiles_column: Annotated[
        str | None, Form(description="Column name for SMILES (CSV only)")
    ] = None,
    name_column: Annotated[
        str | None, Form(description="Column name for molecule names (CSV only)")
    ] = None,
    external_id_column: Annotated[
        str | None, Form(description="Column name for external IDs (CSV only)")
    ] = None,
) -> UploadResponse:
    """
    Initiate a new molecule upload.

    The file will be stored and validation will start in the background.
    Check the status endpoint to track progress.

    File type can be auto-detected from extension and content if not provided.
    """
    # Read file content
    content = await file.read()

    # Validate file size
    if len(content) > service.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum {service.MAX_FILE_SIZE // (1024*1024)}MB",
        )

    # Auto-detect file type if not provided
    detected_file_type = file_type
    if detected_file_type is None:
        detected_file_type = detect_file_type(file.filename, content)
        if detected_file_type is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not detect file type. Please specify file_type parameter.",
            )

    # Validate file type has column mapping for CSV
    column_mapping = None
    if detected_file_type == FileType.CSV:
        if not smiles_column:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="smiles_column is required for CSV uploads",
            )
        column_mapping = {
            "smiles": smiles_column,
            "name": name_column,
            "external_id": external_id_column,
        }

    # Parse similarity threshold
    threshold = None
    if similarity_threshold:
        try:
            threshold = Decimal(similarity_threshold)
            if not (Decimal("0.5") <= threshold <= Decimal("1.0")):
                raise ValueError("Threshold must be between 0.5 and 1.0")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="similarity_threshold must be a decimal between 0.5 and 1.0",
            )

    # Create upload
    file_obj = BytesIO(content)

    upload = await service.create_upload(
        organization_id=user["organization_id"],
        user_id=user["id"],
        name=name,
        file_type=detected_file_type,
        file=file_obj,
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        column_mapping=column_mapping,
        duplicate_action=duplicate_action,
        similarity_threshold=threshold,
    )

    # Enqueue validation job
    # Use ARQ in production, BackgroundTasks in development
    settings = get_settings()
    if settings.environment == "production":
        # Use ARQ job queue
        from apps.api.uploads.worker import enqueue_validation_job
        await enqueue_validation_job(upload.id, user["organization_id"])
    else:
        # Use FastAPI BackgroundTasks for development
        background_tasks.add_task(
            run_validation_task,
            db,
            service,
            upload.id,
            user["organization_id"],
        )

    # Build response
    return UploadResponse(
        id=upload.id,
        name=upload.name,
        status=upload.status,
        file_type=upload.file_type,
        file=UploadFileResponse(
            original_filename=upload.file.original_filename,
            file_size_bytes=upload.file.file_size_bytes,
            content_type=upload.file.content_type,
        ) if upload.file else None,
        column_mapping=upload.column_mapping,
        duplicate_action=upload.duplicate_action,
        similarity_threshold=upload.similarity_threshold,
        created_at=upload.created_at,
        links=build_links(upload.id, include_confirm=False),
    )


# =============================================================================
# GET /uploads/{id}/status - Check Status
# =============================================================================


@router.get(
    "/{upload_id}/status",
    response_model=UploadStatusResponse,
    summary="Get upload status",
    description="Check the current status and progress of an upload.",
)
async def get_upload_status(
    upload_id: uuid.UUID,
    service: Annotated[UploadService, Depends(get_upload_service)],
    user: Annotated[dict, Depends(get_current_user)],
) -> UploadStatusResponse:
    """Get upload status and progress."""
    upload = await service.get_upload_with_relations(
        upload_id, user["organization_id"]
    )
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found",
        )

    # Build progress response
    progress = None
    if upload.progress:
        progress = UploadProgressResponse(
            phase=upload.progress.phase,
            total_rows=upload.progress.total_rows,
            processed_rows=upload.progress.processed_rows,
            valid_rows=upload.progress.valid_rows,
            invalid_rows=upload.progress.invalid_rows,
            duplicate_exact=upload.progress.duplicate_exact,
            duplicate_similar=upload.progress.duplicate_similar,
            percent_complete=upload.progress.percent_complete,
        )

    # Build validation summary for awaiting_confirm
    validation_summary = None
    if upload.status == UploadStatus.AWAITING_CONFIRM and upload.progress:
        ready_to_insert = upload.progress.valid_rows - (
            upload.progress.duplicate_exact + upload.progress.duplicate_similar
            if upload.duplicate_action == DuplicateAction.SKIP
            else 0
        )
        error_rate = (
            upload.progress.invalid_rows / upload.progress.total_rows * 100
            if upload.progress.total_rows > 0
            else 0
        )
        validation_summary = ValidationSummaryResponse(
            ready_to_insert=ready_to_insert,
            will_skip_duplicates=(
                upload.progress.duplicate_exact + upload.progress.duplicate_similar
                if upload.duplicate_action == DuplicateAction.SKIP
                else 0
            ),
            errors_to_review=upload.progress.invalid_rows,
            error_rate_percent=round(error_rate, 1),
        )

    # Build summary for completed
    summary = None
    if upload.summary:
        summary = ResultSummaryResponse(
            molecules_created=upload.summary.molecules_created,
            molecules_updated=upload.summary.molecules_updated,
            molecules_skipped=upload.summary.molecules_skipped,
            errors_count=upload.summary.errors_count,
            exact_duplicates_found=upload.summary.exact_duplicates_found,
            similar_duplicates_found=upload.summary.similar_duplicates_found,
            processing_duration_seconds=(
                float(upload.summary.processing_duration_seconds)
                if upload.summary.processing_duration_seconds
                else None
            ),
        )

    # Build column mapping info for CSV/Excel
    column_mapping_info = None
    if upload.file_type in (FileType.CSV, FileType.EXCEL):
        column_mapping_info = ColumnMappingInfo(
            needs_mapping=upload.needs_column_mapping,
            available_columns=upload.available_columns or [],
            inferred_mapping=upload.inferred_mapping,
            current_mapping=upload.column_mapping,
        )

    return UploadStatusResponse(
        id=upload.id,
        name=upload.name,
        status=upload.status,
        file_type=upload.file_type,
        progress=progress,
        validation_summary=validation_summary,
        column_mapping_info=column_mapping_info,
        summary=summary,
        error_message=upload.error_message,
        created_at=upload.created_at,
        updated_at=upload.updated_at,
        validated_at=upload.validated_at,
        confirmed_at=upload.confirmed_at,
        completed_at=upload.completed_at,
        expires_at=upload.expires_at,
        actions=build_actions(upload),
    )


# =============================================================================
# GET /uploads/{id}/errors - List Errors
# =============================================================================


@router.get(
    "/{upload_id}/errors",
    response_model=UploadErrorsResponse,
    summary="List validation errors",
    description="Get paginated list of validation errors for an upload.",
)
async def get_upload_errors(
    upload_id: uuid.UUID,
    service: Annotated[UploadService, Depends(get_upload_service)],
    user: Annotated[dict, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> UploadErrorsResponse:
    """Get validation errors for an upload."""
    upload = await service.get_upload(upload_id, user["organization_id"])
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found",
        )

    # Get errors
    errors, total = await service.get_errors(upload, page=page, limit=limit)
    error_summary = await service.get_error_summary(upload)

    return UploadErrorsResponse(
        upload_id=upload.id,
        total_errors=total,
        page=page,
        limit=limit,
        errors=[
            RowErrorResponse(
                row_number=e.row_number,
                error_code=e.error_code,
                error_message=e.error_message,
                field_name=e.field_name,
                raw_data=e.raw_data,
                duplicate_inchi_key=e.duplicate_inchi_key,
                duplicate_similarity=(
                    float(e.duplicate_similarity) if e.duplicate_similarity else None
                ),
            )
            for e in errors
        ],
        error_summary=error_summary,
    )


# =============================================================================
# PATCH /uploads/{id}/mapping - Update Column Mapping
# =============================================================================


from pydantic import BaseModel as PydanticBaseModel, Field


class UpdateColumnMappingRequest(PydanticBaseModel):
    """Request to update column mapping for CSV/Excel uploads."""

    smiles_column: str = Field(..., description="Column containing SMILES")
    name_column: str | None = Field(None, description="Column containing molecule names")
    external_id_column: str | None = Field(None, description="Column containing external IDs")


@router.patch(
    "/{upload_id}/mapping",
    response_model=UploadStatusResponse,
    summary="Update column mapping",
    description="Update column mapping for CSV/Excel uploads that need mapping.",
)
async def update_column_mapping(
    upload_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    service: Annotated[UploadService, Depends(get_upload_service)],
    user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    request: UpdateColumnMappingRequest,
) -> UploadStatusResponse:
    """Update column mapping and restart validation."""
    upload = await service.get_upload_with_relations(
        upload_id, user["organization_id"]
    )
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found",
        )

    # Only allow for CSV/Excel that need mapping
    if upload.file_type not in (FileType.CSV, FileType.EXCEL):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Column mapping is only applicable to CSV/Excel uploads",
        )

    if upload.status != UploadStatus.AWAITING_CONFIRM:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot update mapping in '{upload.status.value}' state",
        )

    # Validate that smiles_column exists in available columns
    if upload.available_columns and request.smiles_column not in upload.available_columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Column '{request.smiles_column}' not found. Available: {upload.available_columns}",
        )

    # Update mapping
    upload.column_mapping = {
        "smiles": request.smiles_column,
        "name": request.name_column,
        "external_id": request.external_id_column,
    }
    upload.needs_column_mapping = False

    # Reset to INITIATED and restart validation
    upload.status = UploadStatus.INITIATED
    if upload.progress:
        upload.progress.phase = "revalidating"
        upload.progress.processed_rows = 0
        upload.progress.valid_rows = 0
        upload.progress.invalid_rows = 0

    await db.commit()

    # Restart validation in background
    settings = get_settings()
    if settings.environment == "production":
        from apps.api.uploads.worker import enqueue_validation_job
        await enqueue_validation_job(upload.id, user["organization_id"])
    else:
        background_tasks.add_task(
            run_validation_task,
            db,
            service,
            upload.id,
            user["organization_id"],
        )

    # Return updated status
    return await get_upload_status(upload_id, service, user)


# =============================================================================
# POST /uploads/{id}/confirm - Confirm Upload
# =============================================================================


@router.post(
    "/{upload_id}/confirm",
    response_model=UploadConfirmResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Confirm and process upload",
    description="""
Confirm the upload and begin processing molecules into the database.

**Idempotency:**
- If upload is already PROCESSING, returns current status (no duplicate job)
- If upload is already COMPLETED, returns final summary
- Safe to call multiple times

**Column Mapping:**
- For CSV/Excel uploads with needs_column_mapping=true, column_mapping must be provided
- Column mapping can also be provided for validated uploads to override inferred mapping
    """,
    responses={
        409: {
            "model": UploadErrorResponse,
            "description": "Upload is not in a confirmable state",
        }
    },
)
async def confirm_upload(
    upload_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    service: Annotated[UploadService, Depends(get_upload_service)],
    user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    request: UploadConfirmRequest,
) -> UploadConfirmResponse:
    """
    Confirm an upload and start processing.

    Idempotency Rules:
    - AWAITING_CONFIRM: Start processing, transition to PROCESSING
    - PROCESSING: Return current status (job already running)
    - COMPLETED: Return final summary (already done)
    - Other states: Return 409 Conflict
    """
    upload = await service.get_upload_with_relations(
        upload_id, user["organization_id"]
    )
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found",
        )

    # ==========================================================================
    # Idempotency: Handle already processing or completed uploads
    # ==========================================================================

    if upload.status == UploadStatus.PROCESSING:
        # Already processing - return current status (idempotent)
        return UploadConfirmResponse(
            id=upload.id,
            status=upload.status,
            message="Upload is already being processed.",
            estimated_completion_seconds=_estimate_remaining_time(upload),
            links=build_links(upload.id),
        )

    if upload.status == UploadStatus.COMPLETED:
        # Already completed - return success (idempotent)
        return UploadConfirmResponse(
            id=upload.id,
            status=upload.status,
            message="Upload has already been processed successfully.",
            estimated_completion_seconds=0,
            links=build_links(upload.id),
        )

    # ==========================================================================
    # State validation
    # ==========================================================================

    if upload.status != UploadStatus.AWAITING_CONFIRM:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=UploadErrorResponse(
                error="invalid_state_transition",
                message=f"Upload is in '{upload.status.value}' state and cannot be confirmed",
                current_status=upload.status,
                allowed_actions=_get_allowed_actions(upload.status),
            ).model_dump(),
        )

    # ==========================================================================
    # Column mapping validation for CSV/Excel
    # ==========================================================================

    if upload.needs_column_mapping:
        if not request.column_mapping:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "column_mapping_required",
                    "message": "This upload requires column mapping. Provide column_mapping in the request.",
                    "available_columns": upload.available_columns or [],
                    "inferred_mapping": upload.inferred_mapping,
                },
            )
        # Update column mapping from request
        upload.column_mapping = {
            "smiles": request.column_mapping.smiles,
            "name": request.column_mapping.name,
            "external_id": request.column_mapping.external_id,
        }
        upload.needs_column_mapping = False
        await db.commit()

        # Need to run validation first with new mapping
        upload.status = UploadStatus.INITIATED
        if upload.progress:
            upload.progress.phase = "revalidating"
            upload.progress.processed_rows = 0
        await db.commit()

        # Start validation (not processing)
        settings = get_settings()
        if settings.environment == "production":
            from apps.api.uploads.worker import enqueue_validation_job
            await enqueue_validation_job(upload.id, user["organization_id"])
        else:
            background_tasks.add_task(
                run_validation_task,
                db,
                service,
                upload.id,
                user["organization_id"],
            )

        return UploadConfirmResponse(
            id=upload.id,
            status=upload.status,
            message="Column mapping accepted. Validation started. Check status for progress.",
            estimated_completion_seconds=None,
            links=build_links(upload.id),
        )

    # ==========================================================================
    # Error acknowledgment
    # ==========================================================================

    if upload.progress and upload.progress.invalid_rows > 0:
        if not request.acknowledge_errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "errors_not_acknowledged",
                    "message": f"Upload has {upload.progress.invalid_rows} validation errors. Set acknowledge_errors=true to proceed with valid rows only.",
                    "invalid_rows": upload.progress.invalid_rows,
                    "valid_rows": upload.progress.valid_rows,
                },
            )

    # ==========================================================================
    # Confirm and start processing
    # ==========================================================================

    await service.confirm_upload(upload)

    # Start insertion job
    settings = get_settings()
    if settings.environment == "production":
        from apps.api.uploads.worker import enqueue_processing_job
        job_id = await enqueue_processing_job(upload.id, user["organization_id"])
        if not job_id:
            # Failed to enqueue - fall back to background task
            background_tasks.add_task(
                run_insertion_task,
                db,
                service,
                upload.id,
                user["organization_id"],
            )
    else:
        background_tasks.add_task(
            run_insertion_task,
            db,
            service,
            upload.id,
            user["organization_id"],
        )

    # Estimate completion time
    estimated_seconds = _estimate_remaining_time(upload)

    return UploadConfirmResponse(
        id=upload.id,
        status=upload.status,
        message=f"Upload confirmed. Processing {upload.progress.valid_rows if upload.progress else 0} molecules.",
        estimated_completion_seconds=estimated_seconds,
        links=build_links(upload.id),
    )


def _estimate_remaining_time(upload: Upload) -> int | None:
    """Estimate remaining processing time in seconds."""
    if not upload.progress:
        return None
    if upload.progress.total_rows == 0:
        return None

    # Estimate based on progress and typical rate (10 rows/sec)
    rows_remaining = upload.progress.total_rows - upload.progress.processed_rows
    if rows_remaining <= 0:
        return 0
    return max(1, rows_remaining // 10)


def _get_allowed_actions(status: UploadStatus) -> list[str]:
    """Get allowed actions for a given upload status."""
    if status == UploadStatus.VALIDATING:
        return ["wait", "cancel"]
    elif status == UploadStatus.AWAITING_CONFIRM:
        return ["confirm", "cancel"]
    elif status == UploadStatus.PROCESSING:
        return ["wait"]
    elif status == UploadStatus.VALIDATION_FAILED:
        return ["delete"]
    elif status == UploadStatus.FAILED:
        return ["delete", "retry"]
    return []


# =============================================================================
# DELETE /uploads/{id} - Cancel Upload
# =============================================================================


@router.delete(
    "/{upload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel upload",
    description="Cancel an upload that is awaiting confirmation.",
    responses={
        409: {
            "model": UploadErrorResponse,
            "description": "Upload cannot be cancelled in current state",
        }
    },
)
async def cancel_upload(
    upload_id: uuid.UUID,
    service: Annotated[UploadService, Depends(get_upload_service)],
    user: Annotated[dict, Depends(get_current_user)],
) -> None:
    """Cancel an upload."""
    upload = await service.get_upload(upload_id, user["organization_id"])
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found",
        )

    # Check state
    if upload.status != UploadStatus.AWAITING_CONFIRM:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=UploadErrorResponse(
                error="invalid_state_transition",
                message=f"Upload in '{upload.status.value}' state cannot be cancelled",
                current_status=upload.status,
                allowed_actions=[],
            ).model_dump(),
        )

    await service.cancel_upload(upload)


# =============================================================================
# GET /uploads - List Uploads (Optional)
# =============================================================================


@router.get(
    "",
    summary="List uploads",
    description="List all uploads for the current organization.",
)
async def list_uploads(
    service: Annotated[UploadService, Depends(get_upload_service)],
    user: Annotated[dict, Depends(get_current_user)],
    status_filter: Annotated[
        UploadStatus | None, Query(alias="status", description="Filter by status")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    """List uploads for the organization."""
    # This is a simplified implementation
    # In production, add proper filtering and pagination
    return {
        "message": "List uploads endpoint",
        "filters": {"status": status_filter},
        "page": page,
        "limit": limit,
    }
