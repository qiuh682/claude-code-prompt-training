"""
File type detection for uploads.

Detects file type by:
1. File extension
2. Content inspection (magic bytes / patterns)
"""

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

# Excel XLSX magic bytes (ZIP file format: PK..)
XLSX_MAGIC = b"PK\x03\x04"

# Old Excel XLS magic bytes
XLS_MAGIC = b"\xd0\xcf\x11\xe0"


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
    elif lower.endswith(".xlsx"):
        return FileType.EXCEL
    elif lower.endswith(".xls"):
        return FileType.EXCEL
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

    # Check for Excel magic bytes first (binary format)
    if sample.startswith(XLSX_MAGIC):
        return FileType.EXCEL
    if sample.startswith(XLS_MAGIC):
        return FileType.EXCEL

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
        FileType.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        FileType.SMILES_LIST: "text/plain",
    }
    return mapping.get(file_type, "application/octet-stream")


# =============================================================================
# Column Inference for CSV/Excel
# =============================================================================

# Common SMILES column names (case-insensitive matching)
SMILES_COLUMN_NAMES = [
    "smiles",
    "canonical_smiles",
    "smi",
    "structure",
    "mol",
    "molecule",
    "compound",
    "compound_smiles",
]

# Common name column names
NAME_COLUMN_NAMES = [
    "name",
    "compound_name",
    "molecule_name",
    "mol_name",
    "title",
    "id",
    "compound_id",
]

# Common external ID column names
EXTERNAL_ID_COLUMN_NAMES = [
    "external_id",
    "cas",
    "cas_number",
    "registry",
    "registry_number",
    "chembl_id",
    "pubchem_cid",
]


def infer_column_mapping(columns: list[str]) -> dict[str, str | None]:
    """
    Infer column mapping from available column names.

    Args:
        columns: List of column names from CSV/Excel header

    Returns:
        Dict with 'smiles', 'name', 'external_id' keys (values may be None)
    """
    lower_columns = {col.lower().strip(): col for col in columns}

    mapping: dict[str, str | None] = {
        "smiles": None,
        "name": None,
        "external_id": None,
    }

    # Find SMILES column
    for name in SMILES_COLUMN_NAMES:
        if name in lower_columns:
            mapping["smiles"] = lower_columns[name]
            break

    # Find name column
    for name in NAME_COLUMN_NAMES:
        if name in lower_columns:
            mapping["name"] = lower_columns[name]
            break

    # Find external ID column
    for name in EXTERNAL_ID_COLUMN_NAMES:
        if name in lower_columns:
            mapping["external_id"] = lower_columns[name]
            break

    return mapping


def detect_csv_columns(content: bytes) -> list[str]:
    """
    Detect column names from CSV content.

    Args:
        content: CSV file content

    Returns:
        List of column names from header row
    """
    try:
        text = content.decode("utf-8", errors="ignore")
        lines = text.split("\n")
        if lines:
            header = lines[0].strip()
            # Detect delimiter
            if "\t" in header:
                return [col.strip() for col in header.split("\t")]
            else:
                return [col.strip() for col in header.split(",")]
    except Exception:
        pass
    return []


def detect_excel_columns(content: bytes) -> list[str]:
    """
    Detect column names from Excel content.

    Args:
        content: Excel file content

    Returns:
        List of column names from header row
    """
    try:
        import openpyxl
        from io import BytesIO

        wb = openpyxl.load_workbook(BytesIO(content), read_only=True)
        ws = wb.active
        if ws:
            # Get first row as headers
            first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
            if first_row:
                return [str(cell) if cell else "" for cell in first_row]
    except ImportError:
        # openpyxl not installed
        pass
    except Exception:
        pass
    return []
