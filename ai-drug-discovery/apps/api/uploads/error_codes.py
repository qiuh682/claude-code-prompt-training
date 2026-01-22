"""Structured error codes for upload validation and processing."""

from enum import Enum


class UploadErrorCode(str, Enum):
    """
    Error codes for upload row-level validation failures.

    Categories:
    - PARSE_*: File parsing errors
    - VALIDATION_*: Chemical structure validation errors
    - DUPLICATE_*: Duplicate detection errors
    - PROCESS_*: Processing/computation errors
    """

    # --- Parsing Errors ---
    INVALID_SMILES = "invalid_smiles"
    INVALID_MOLBLOCK = "invalid_molblock"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    MALFORMED_ROW = "malformed_row"
    EMPTY_ROW = "empty_row"
    ENCODING_ERROR = "encoding_error"

    # --- Validation Errors ---
    SMILES_TOO_LONG = "smiles_too_long"
    MOLECULE_TOO_LARGE = "molecule_too_large"  # >1000 heavy atoms
    INVALID_STRUCTURE = "invalid_structure"
    KEKULIZATION_FAILED = "kekulization_failed"
    SANITIZATION_FAILED = "sanitization_failed"
    NO_ATOMS = "no_atoms"

    # --- Duplicate Errors ---
    EXACT_DUPLICATE = "exact_duplicate"
    SIMILAR_DUPLICATE = "similar_duplicate"
    DUPLICATE_IN_BATCH = "duplicate_in_batch"  # Duplicate within same upload

    # --- Processing Errors ---
    DESCRIPTOR_CALCULATION_FAILED = "descriptor_calculation_failed"
    FINGERPRINT_CALCULATION_FAILED = "fingerprint_calculation_failed"
    INCHI_GENERATION_FAILED = "inchi_generation_failed"
    CANONICALIZATION_FAILED = "canonicalization_failed"

    # --- Database Errors ---
    DB_CONSTRAINT_VIOLATION = "db_constraint_violation"
    DB_INSERT_FAILED = "db_insert_failed"


# Human-readable error messages
ERROR_MESSAGES: dict[UploadErrorCode, str] = {
    # Parsing
    UploadErrorCode.INVALID_SMILES: "Cannot parse SMILES string",
    UploadErrorCode.INVALID_MOLBLOCK: "Cannot parse MOL/SDF block",
    UploadErrorCode.MISSING_REQUIRED_FIELD: "Required field is missing or empty",
    UploadErrorCode.MALFORMED_ROW: "Row structure is malformed",
    UploadErrorCode.EMPTY_ROW: "Row is empty",
    UploadErrorCode.ENCODING_ERROR: "Character encoding error",
    # Validation
    UploadErrorCode.SMILES_TOO_LONG: "SMILES string exceeds maximum length (2000 chars)",
    UploadErrorCode.MOLECULE_TOO_LARGE: "Molecule exceeds maximum size (1000 heavy atoms)",
    UploadErrorCode.INVALID_STRUCTURE: "Invalid chemical structure",
    UploadErrorCode.KEKULIZATION_FAILED: "Failed to kekulize molecule",
    UploadErrorCode.SANITIZATION_FAILED: "Failed to sanitize molecule",
    UploadErrorCode.NO_ATOMS: "Molecule has no atoms",
    # Duplicates
    UploadErrorCode.EXACT_DUPLICATE: "Molecule with same InChIKey already exists",
    UploadErrorCode.SIMILAR_DUPLICATE: "Similar molecule found above threshold",
    UploadErrorCode.DUPLICATE_IN_BATCH: "Duplicate molecule within this upload",
    # Processing
    UploadErrorCode.DESCRIPTOR_CALCULATION_FAILED: "Failed to calculate molecular descriptors",
    UploadErrorCode.FINGERPRINT_CALCULATION_FAILED: "Failed to calculate molecular fingerprint",
    UploadErrorCode.INCHI_GENERATION_FAILED: "Failed to generate InChI/InChIKey",
    UploadErrorCode.CANONICALIZATION_FAILED: "Failed to canonicalize SMILES",
    # Database
    UploadErrorCode.DB_CONSTRAINT_VIOLATION: "Database constraint violation",
    UploadErrorCode.DB_INSERT_FAILED: "Failed to insert into database",
}


def get_error_message(code: UploadErrorCode, detail: str | None = None) -> str:
    """
    Get human-readable error message for an error code.

    Args:
        code: The error code
        detail: Optional additional detail to append

    Returns:
        Human-readable error message
    """
    base_message = ERROR_MESSAGES.get(code, f"Unknown error: {code}")
    if detail:
        return f"{base_message}: {detail}"
    return base_message
