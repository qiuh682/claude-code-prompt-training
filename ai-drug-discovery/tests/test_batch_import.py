"""
Unit tests for batch CSV/Excel import with column mapping.

Tests cover:
- CSV file reading and parsing
- Excel file reading
- Column mapping (explicit and auto-detection)
- Row-level validation and error handling
- SMILES validation integration
"""

import io
import tempfile
from pathlib import Path

import pytest

from packages.chemistry.batch_import import (
    BatchImporter,
    BatchImportResult,
    ColumnMapping,
    FileType,
    ImportedMolecule,
    ImportErrorCode,
    RowError,
    auto_detect_mapping,
    create_mapping,
    detect_file_type,
    import_molecules_from_csv,
    import_molecules_from_file,
    read_csv_file,
    validate_mapping,
)


# =============================================================================
# Test Data
# =============================================================================

SAMPLE_CSV = """SMILES,Name,ID
CCO,Ethanol,CHEM001
CC,Ethane,CHEM002
c1ccccc1,Benzene,CHEM003
"""

SAMPLE_CSV_WITH_ERRORS = """SMILES,Name,ID
CCO,Ethanol,CHEM001
invalid_smiles,Bad Molecule,CHEM002
CC,Ethane,CHEM003
,Empty,CHEM004
c1ccccc1,Benzene,CHEM005
"""

SAMPLE_CSV_ALTERNATE_NAMES = """structure,compound_name,external_id
CCO,Ethanol,CHEM001
CC,Ethane,CHEM002
"""

SAMPLE_CSV_CUSTOM_COLUMNS = """mol,title,cas_number,molecular_weight
CCO,Ethanol,64-17-5,46.07
CC,Ethane,74-84-0,30.07
"""

SAMPLE_TSV = """SMILES\tName\tID
CCO\tEthanol\tCHEM001
CC\tEthane\tCHEM002
"""


# =============================================================================
# Test: File Type Detection
# =============================================================================


class TestFileTypeDetection:
    """Tests for file type detection."""

    def test_detect_csv_by_extension(self):
        """Should detect CSV from file extension."""
        assert detect_file_type(filepath="test.csv") == FileType.CSV
        assert detect_file_type(filename="data.CSV") == FileType.CSV

    def test_detect_tsv_by_extension(self):
        """Should detect TSV from file extension."""
        assert detect_file_type(filepath="test.tsv") == FileType.TSV

    def test_detect_excel_by_extension(self):
        """Should detect Excel from file extension."""
        assert detect_file_type(filepath="test.xlsx") == FileType.EXCEL
        assert detect_file_type(filepath="test.xls") == FileType.EXCEL

    def test_detect_csv_from_content(self):
        """Should detect CSV from content."""
        content = b"col1,col2,col3\nval1,val2,val3"
        assert detect_file_type(content=content) == FileType.CSV

    def test_detect_tsv_from_content(self):
        """Should detect TSV from content with tabs."""
        content = b"col1\tcol2\tcol3\nval1\tval2\tval3"
        assert detect_file_type(content=content) == FileType.TSV

    def test_unknown_type(self):
        """Should return UNKNOWN for unrecognized formats."""
        assert detect_file_type() == FileType.UNKNOWN


# =============================================================================
# Test: CSV Reading
# =============================================================================


class TestCsvReading:
    """Tests for CSV file reading."""

    def test_read_csv_string(self):
        """Should read CSV from string IO."""
        result = read_csv_file(io.StringIO(SAMPLE_CSV))

        assert result.error is None
        assert result.headers == ["SMILES", "Name", "ID"]
        assert result.total_rows == 3
        assert len(result.rows) == 3

    def test_read_csv_file(self):
        """Should read CSV from file path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(SAMPLE_CSV)
            f.flush()

            result = read_csv_file(f.name)

            assert result.error is None
            assert result.total_rows == 3

        Path(f.name).unlink()

    def test_read_csv_row_values(self):
        """Should correctly parse row values."""
        result = read_csv_file(io.StringIO(SAMPLE_CSV))

        assert result.rows[0]["SMILES"] == "CCO"
        assert result.rows[0]["Name"] == "Ethanol"
        assert result.rows[0]["ID"] == "CHEM001"

    def test_read_tsv(self):
        """Should read TSV with tab delimiter."""
        result = read_csv_file(io.StringIO(SAMPLE_TSV), delimiter="\t")

        assert result.error is None
        assert result.headers == ["SMILES", "Name", "ID"]
        assert result.total_rows == 2


# =============================================================================
# Test: Column Mapping
# =============================================================================


class TestColumnMapping:
    """Tests for column mapping."""

    def test_auto_detect_standard_columns(self):
        """Should auto-detect standard column names."""
        columns = ["SMILES", "Name", "ID", "MW"]
        mapping = auto_detect_mapping(columns)

        assert mapping is not None
        assert mapping.smiles_col == "SMILES"
        assert mapping.name_col == "Name"
        assert mapping.id_col == "ID"

    def test_auto_detect_alternate_names(self):
        """Should detect alternate column names."""
        columns = ["structure", "compound_name", "external_id"]
        mapping = auto_detect_mapping(columns)

        assert mapping is not None
        assert mapping.smiles_col == "structure"
        assert mapping.name_col == "compound_name"
        assert mapping.id_col == "external_id"

    def test_auto_detect_case_insensitive(self):
        """Should match columns case-insensitively."""
        columns = ["smiles", "NAME", "Id"]
        mapping = auto_detect_mapping(columns)

        assert mapping is not None
        assert mapping.smiles_col == "smiles"
        assert mapping.name_col == "NAME"
        assert mapping.id_col == "Id"

    def test_auto_detect_no_smiles_column(self):
        """Should return None if no SMILES column found."""
        columns = ["Name", "ID", "MW"]
        mapping = auto_detect_mapping(columns)

        assert mapping is None

    def test_create_mapping_from_dict(self):
        """Should create mapping from dict."""
        mapping_dict = {
            "smiles_col": "mol",
            "name_col": "title",
            "id_col": "cas_number",
        }
        columns = ["mol", "title", "cas_number", "mw"]

        mapping, errors = create_mapping(mapping_dict, columns)

        assert mapping is not None
        assert len(errors) == 0
        assert mapping.smiles_col == "mol"
        assert mapping.name_col == "title"
        assert mapping.id_col == "cas_number"

    def test_create_mapping_with_extra_cols(self):
        """Should support extra column mapping."""
        mapping_dict = {
            "smiles_col": "SMILES",
            "mw": "molecular_weight",
            "logp": "LogP",
        }
        columns = ["SMILES", "molecular_weight", "LogP"]

        mapping, errors = create_mapping(mapping_dict, columns)

        assert mapping is not None
        assert mapping.extra_cols == {"mw": "molecular_weight", "logp": "LogP"}

    def test_create_mapping_missing_required(self):
        """Should error if SMILES column missing."""
        mapping_dict = {"name_col": "Name"}
        columns = ["Name", "ID"]

        mapping, errors = create_mapping(mapping_dict, columns)

        assert mapping is None
        assert len(errors) > 0
        assert "smiles_col" in errors[0]

    def test_create_mapping_invalid_column(self):
        """Should error if mapped column doesn't exist."""
        mapping_dict = {"smiles_col": "nonexistent"}
        columns = ["SMILES", "Name"]

        mapping, errors = create_mapping(mapping_dict, columns)

        assert mapping is None
        assert len(errors) > 0
        assert "not found" in errors[0]

    def test_validate_mapping_helper(self):
        """Should validate mapping against columns."""
        is_valid, errors = validate_mapping(
            {"smiles_col": "SMILES", "name_col": "Title"},
            ["SMILES", "Name", "ID"]
        )

        assert is_valid is False
        assert any("Title" in e for e in errors)


# =============================================================================
# Test: Batch Import - CSV
# =============================================================================


class TestBatchImportCsv:
    """Tests for batch import from CSV."""

    def test_import_basic_csv(self):
        """Should import molecules from basic CSV."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV),
            file_type=FileType.CSV,
        )

        assert result.success_count == 3
        assert result.error_count == 0
        assert len(result.molecules) == 3

    def test_import_with_explicit_mapping(self):
        """Should use explicit column mapping."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV_CUSTOM_COLUMNS),
            mapping={"smiles_col": "mol", "name_col": "title", "id_col": "cas_number"},
            file_type=FileType.CSV,
        )

        assert result.success_count == 2
        assert result.molecules[0].smiles == "CCO"
        assert result.molecules[0].name == "Ethanol"
        assert result.molecules[0].external_id == "64-17-5"

    def test_import_extracts_molecule_data(self):
        """Should extract all molecule fields."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV),
            file_type=FileType.CSV,
        )

        mol = result.molecules[0]
        assert mol.row_number == 2  # 1-based, after header
        assert mol.smiles == "CCO"
        assert mol.name == "Ethanol"
        assert mol.external_id == "CHEM001"

    def test_import_with_extra_columns(self):
        """Should extract extra mapped columns."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV_CUSTOM_COLUMNS),
            mapping={
                "smiles_col": "mol",
                "name_col": "title",
                "mw": "molecular_weight",  # Extra column
            },
            file_type=FileType.CSV,
        )

        assert result.success_count == 2
        assert result.molecules[0].extra_data.get("mw") == "46.07"


class TestBatchImportValidation:
    """Tests for SMILES validation during import."""

    def test_validates_smiles_by_default(self):
        """Should validate SMILES by default."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV_WITH_ERRORS),
            file_type=FileType.CSV,
            validate=True,
        )

        # 3 valid (CCO, CC, benzene), 1 invalid, 1 empty (skipped by default)
        assert result.success_count == 3
        assert result.error_count == 1

    def test_invalid_smiles_creates_error(self):
        """Should create error record for invalid SMILES."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV_WITH_ERRORS),
            file_type=FileType.CSV,
        )

        errors = [e for e in result.errors if e.error_code == ImportErrorCode.INVALID_SMILES]
        assert len(errors) == 1
        assert errors[0].row_number == 3  # Row with "invalid_smiles"
        assert "invalid_smiles" in errors[0].smiles_value

    def test_empty_smiles_skipped_by_default(self):
        """Should skip rows with empty SMILES by default."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV_WITH_ERRORS),
            file_type=FileType.CSV,
        )

        # Empty SMILES row should be skipped, not errored
        assert result.success_count == 3
        assert result.error_count == 1  # Only invalid_smiles

    def test_canonicalize_generates_inchikey(self):
        """Should generate InChIKey when canonicalize=True."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV),
            file_type=FileType.CSV,
            canonicalize=True,
        )

        mol = result.molecules[0]
        assert mol.canonical_smiles == "CCO"
        assert mol.inchikey is not None
        assert len(mol.inchikey) == 27

    def test_error_row_number_correct(self):
        """Error should have correct row number."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV_WITH_ERRORS),
            file_type=FileType.CSV,
        )

        # invalid_smiles is on line 3 of CSV (row 2 after header, 1-based = 3)
        error = result.errors[0]
        assert error.row_number == 3


class TestBatchImportErrors:
    """Tests for error handling during import."""

    def test_file_not_found(self):
        """Should handle file not found."""
        result = import_molecules_from_file(
            "/nonexistent/path/file.csv",
            file_type=FileType.CSV,
        )

        assert result.error_count >= 1
        assert result.errors[0].error_code == ImportErrorCode.FILE_READ_ERROR

    def test_missing_smiles_column_auto_detect(self):
        """Should error if SMILES column not found."""
        csv_no_smiles = "Name,ID,MW\nEthanol,001,46\n"
        result = import_molecules_from_file(
            io.StringIO(csv_no_smiles),
            file_type=FileType.CSV,
        )

        assert result.error_count == 1
        assert result.errors[0].error_code == ImportErrorCode.MISSING_SMILES_COLUMN

    def test_invalid_column_mapping(self):
        """Should error for invalid column mapping."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV),
            mapping={"smiles_col": "nonexistent_column"},
            file_type=FileType.CSV,
        )

        assert result.error_count == 1
        assert result.errors[0].error_code == ImportErrorCode.INVALID_COLUMN_MAPPING


# =============================================================================
# Test: BatchImportResult
# =============================================================================


class TestBatchImportResult:
    """Tests for BatchImportResult data class."""

    def test_result_statistics(self):
        """Should calculate correct statistics."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV_WITH_ERRORS),
            file_type=FileType.CSV,
        )

        assert result.total_rows == 5
        assert result.success_count == 3
        assert result.error_count == 1
        # Note: empty row is skipped, not counted as error

    def test_success_rate(self):
        """Should calculate success rate correctly."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV),
            file_type=FileType.CSV,
        )

        assert result.success_rate == 100.0

    def test_has_errors_property(self):
        """Should indicate if errors occurred."""
        result_clean = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV),
            file_type=FileType.CSV,
        )
        assert result_clean.has_errors is False

        result_errors = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV_WITH_ERRORS),
            file_type=FileType.CSV,
        )
        assert result_errors.has_errors is True

    def test_detected_columns(self):
        """Should record detected columns."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV),
            file_type=FileType.CSV,
        )

        assert "SMILES" in result.detected_columns
        assert "Name" in result.detected_columns
        assert "ID" in result.detected_columns

    def test_used_mapping(self):
        """Should record used mapping."""
        result = import_molecules_from_file(
            io.StringIO(SAMPLE_CSV),
            file_type=FileType.CSV,
        )

        assert result.used_mapping is not None
        assert result.used_mapping.smiles_col == "SMILES"


# =============================================================================
# Test: BatchImporter Class
# =============================================================================


class TestBatchImporter:
    """Tests for BatchImporter class."""

    def test_importer_options_validate(self):
        """Should respect validate_smiles option."""
        importer = BatchImporter(validate_smiles=True)
        result = importer.import_from_file(
            io.StringIO(SAMPLE_CSV_WITH_ERRORS),
            file_type=FileType.CSV,
        )

        assert result.error_count == 1  # Invalid SMILES detected

    def test_importer_options_no_validate(self):
        """Should skip validation when disabled."""
        importer = BatchImporter(validate_smiles=False)
        result = importer.import_from_file(
            io.StringIO(SAMPLE_CSV_WITH_ERRORS),
            file_type=FileType.CSV,
        )

        # All rows pass without validation (except empty which is skipped)
        assert result.success_count == 4
        assert result.error_count == 0

    def test_importer_options_canonicalize(self):
        """Should canonicalize when enabled."""
        importer = BatchImporter(canonicalize=True)
        result = importer.import_from_file(
            io.StringIO(SAMPLE_CSV),
            file_type=FileType.CSV,
        )

        for mol in result.molecules:
            assert mol.canonical_smiles is not None
            assert mol.inchikey is not None

    def test_importer_options_strip_whitespace(self):
        """Should strip whitespace when enabled."""
        csv_whitespace = "SMILES,Name\n  CCO  ,  Ethanol  \n"
        importer = BatchImporter(strip_whitespace=True)
        result = importer.import_from_file(
            io.StringIO(csv_whitespace),
            file_type=FileType.CSV,
        )

        assert result.molecules[0].smiles == "CCO"
        assert result.molecules[0].name == "Ethanol"


# =============================================================================
# Test: Convenience Functions
# =============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_import_molecules_from_csv(self):
        """Should import from CSV file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(SAMPLE_CSV)
            f.flush()

            result = import_molecules_from_csv(f.name)

            assert result.success_count == 3
            assert result.file_type == FileType.CSV

        Path(f.name).unlink()

    def test_validate_mapping_valid(self):
        """Should validate correct mapping."""
        is_valid, errors = validate_mapping(
            {"smiles_col": "SMILES", "name_col": "Name"},
            ["SMILES", "Name", "ID"]
        )

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_mapping_invalid(self):
        """Should reject incorrect mapping."""
        is_valid, errors = validate_mapping(
            {"smiles_col": "Structure"},
            ["SMILES", "Name"]
        )

        assert is_valid is False
        assert len(errors) > 0


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_file(self):
        """Should handle empty file."""
        result = import_molecules_from_file(
            io.StringIO(""),
            file_type=FileType.CSV,
        )

        assert result.error_count >= 1

    def test_header_only_file(self):
        """Should handle file with only header."""
        result = import_molecules_from_file(
            io.StringIO("SMILES,Name,ID\n"),
            file_type=FileType.CSV,
        )

        assert result.success_count == 0
        assert result.total_rows == 0

    def test_unicode_values(self):
        """Should handle unicode in values."""
        csv_unicode = "SMILES,Name\nCCO,Éthanol\nCC,メタン\n"
        result = import_molecules_from_file(
            io.StringIO(csv_unicode),
            file_type=FileType.CSV,
        )

        assert result.success_count == 2
        assert result.molecules[0].name == "Éthanol"
        assert result.molecules[1].name == "メタン"

    def test_quoted_values(self):
        """Should handle quoted CSV values."""
        csv_quoted = 'SMILES,Name,Description\nCCO,"Ethanol, alcohol","A ""simple"" alcohol"\n'
        result = import_molecules_from_file(
            io.StringIO(csv_quoted),
            file_type=FileType.CSV,
        )

        assert result.success_count == 1
        assert result.molecules[0].name == "Ethanol, alcohol"

    def test_null_name_and_id(self):
        """Should handle missing optional columns."""
        csv_minimal = "smiles\nCCO\nCC\n"
        result = import_molecules_from_file(
            io.StringIO(csv_minimal),
            file_type=FileType.CSV,
        )

        assert result.success_count == 2
        assert result.molecules[0].name is None
        assert result.molecules[0].external_id is None
