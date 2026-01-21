"""
Chemistry pipeline exceptions.

Provides structured error handling with row-level context for batch processing.
"""

from dataclasses import dataclass, field
from enum import Enum


class ChemistryErrorCode(str, Enum):
    """Error codes for chemistry pipeline."""

    # Parsing errors
    INVALID_SMILES = "INVALID_SMILES"
    INVALID_MOLFILE = "INVALID_MOLFILE"
    INVALID_SDF = "INVALID_SDF"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    EMPTY_INPUT = "EMPTY_INPUT"

    # Normalization errors
    CANONICALIZATION_FAILED = "CANONICALIZATION_FAILED"
    KEKULIZATION_FAILED = "KEKULIZATION_FAILED"

    # Computation errors
    DESCRIPTOR_CALCULATION_FAILED = "DESCRIPTOR_CALCULATION_FAILED"
    FINGERPRINT_CALCULATION_FAILED = "FINGERPRINT_CALCULATION_FAILED"
    RENDERING_FAILED = "RENDERING_FAILED"

    # Storage errors
    DUPLICATE_MOLECULE = "DUPLICATE_MOLECULE"
    STORAGE_FAILED = "STORAGE_FAILED"

    # General
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class ChemistryError(Exception):
    """Base exception for chemistry pipeline."""

    def __init__(
        self,
        message: str,
        code: ChemistryErrorCode = ChemistryErrorCode.UNKNOWN_ERROR,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class ParsingError(ChemistryError):
    """Raised when parsing molecular input fails."""

    pass


class NormalizationError(ChemistryError):
    """Raised when normalization/canonicalization fails."""

    pass


class ComputationError(ChemistryError):
    """Raised when descriptor/fingerprint computation fails."""

    pass


class StorageError(ChemistryError):
    """Raised when database storage fails."""

    pass


@dataclass
class RowError:
    """Error information for a single row in batch processing."""

    row_index: int
    input_value: str
    error_code: ChemistryErrorCode
    error_message: str
    details: dict = field(default_factory=dict)


@dataclass
class BatchResult:
    """Result of batch processing with per-row errors."""

    successful_count: int
    failed_count: int
    errors: list[RowError]
    total_count: int

    @property
    def success_rate(self) -> float:
        """Calculate success rate as a percentage."""
        if self.total_count == 0:
            return 0.0
        return (self.successful_count / self.total_count) * 100.0

    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return self.failed_count > 0
