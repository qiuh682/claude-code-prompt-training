"""
File type detection for uploads.

Detects file type by:
1. File extension
2. Content inspection (magic bytes / patterns)
"""

from enum import Enum
from io import BytesIO
from typing import BinaryIO

from db.models.upload import FileType


# Magic bytes / patterns for file detection
SDF_MARKERS = [
    b"$$$$",  # SDF record separator
    b"M  END",  # MOL block end marker
    b"V2000",  # MOL V2000 format
    b"V3000",  # MOL V3000 format
]

CSV_MARKERS = [
    b"smiles",
    b"SMILES",
    b"Smiles",
    b",",  # CSV delimiter
]


def detect_file_type_by_extension(filename: str) -> FileType | None:
    """
    Detect file type by extension.

    Args:
        filename: Original filename

    Returns:
        FileType or None if unknown
    """
    if not filename:
        return None

    lower = filename.lower()

    if lower.endswith(".sdf") or lower.endswith(".sd"):
        return FileType.SDF
    elif lower.endswith(".mol"):
        return FileType.SDF  # MOL is single-molecule SDF
    elif lower.endswith(".csv"):
        return FileType.CSV
    elif lower.endswith(".tsv"):
        return FileType.CSV
    elif lower.endswith(".txt"):
        return FileType.SMILES_LIST
    elif lower.endswith(".smi") or lower.endswith(".smiles"):
        return FileType.SMILES_LIST

    return None


def detect_file_type_by_content(content: bytes, sample_size: int = 4096) -> FileType | None:
    """
    Detect file type by inspecting content.

    Args:
        content: File content bytes
        sample_size: How many bytes to inspect

    Returns:
        FileType or None if unknown
    """
    sample = content[:sample_size]

    # Check for SDF markers
    for marker in SDF_MARKERS:
        if marker in sample:
            return FileType.SDF

    # Check for CSV (look for header with SMILES column and commas)
    try:
        text_sample = sample.decode("utf-8", errors="ignore")
        lines = text_sample.split("\n")

        if lines:
            first_line = lines[0].lower()

            # Check for CSV with SMILES column
            if "," in first_line and "smiles" in first_line:
                return FileType.CSV

            # Check for TSV with SMILES column
            if "\t" in first_line and "smiles" in first_line:
                return FileType.CSV

            # Check if it looks like a SMILES list (each line is a valid-looking SMILES)
            valid_smiles_lines = 0
            for line in lines[:10]:  # Check first 10 lines
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Simple heuristic: SMILES typically have C, c, N, n, O, o, etc.
                if any(c in line for c in "CcNnOoSsFfClBrI[]()=#"):
                    valid_smiles_lines += 1

            if valid_smiles_lines >= 3:
                return FileType.SMILES_LIST

    except Exception:
        pass

    return None


def detect_file_type(
    filename: str | None,
    content: bytes | BinaryIO | None = None,
) -> FileType | None:
    """
    Detect file type using extension and/or content.

    Priority:
    1. Extension (if recognized)
    2. Content inspection (fallback)

    Args:
        filename: Original filename
        content: File content (bytes or file-like object)

    Returns:
        FileType or None if unknown
    """
    # Try extension first
    if filename:
        file_type = detect_file_type_by_extension(filename)
        if file_type:
            return file_type

    # Try content inspection
    if content:
        if isinstance(content, bytes):
            content_bytes = content
        else:
            pos = content.tell()
            content_bytes = content.read(4096)
            content.seek(pos)  # Reset position

        file_type = detect_file_type_by_content(content_bytes)
        if file_type:
            return file_type

    return None


def get_content_type_for_file_type(file_type: FileType) -> str:
    """Get MIME content type for a file type."""
    mapping = {
        FileType.SDF: "chemical/x-mdl-sdfile",
        FileType.CSV: "text/csv",
        FileType.SMILES_LIST: "text/plain",
    }
    return mapping.get(file_type, "application/octet-stream")
