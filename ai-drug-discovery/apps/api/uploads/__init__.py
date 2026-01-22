"""Upload system module for molecule data ingestion."""

from apps.api.uploads.duplicate_detection import (
    BatchDuplicateResult,
    DuplicateCheckResult,
    DuplicateSummary,
    ExactDuplicate,
    SimilarDuplicate,
    check_duplicates,
    check_duplicates_batch,
    find_duplicates_in_batch,
    find_exact_duplicates,
    find_similar_duplicates,
    find_similar_duplicates_batch,
    summarize_duplicates,
)
from apps.api.uploads.error_codes import UploadErrorCode, get_error_message
from apps.api.uploads.file_detection import detect_file_type
from apps.api.uploads.service import UploadService
from apps.api.uploads.tasks import UploadProcessor, run_insertion_task, run_validation_task

__all__ = [
    # Duplicate detection
    "BatchDuplicateResult",
    "DuplicateCheckResult",
    "DuplicateSummary",
    "ExactDuplicate",
    "SimilarDuplicate",
    "check_duplicates",
    "check_duplicates_batch",
    "find_duplicates_in_batch",
    "find_exact_duplicates",
    "find_similar_duplicates",
    "find_similar_duplicates_batch",
    "summarize_duplicates",
    # Error codes
    "UploadErrorCode",
    "get_error_message",
    # File detection
    "detect_file_type",
    # Service and processor
    "UploadProcessor",
    "UploadService",
    "run_insertion_task",
    "run_validation_task",
]
