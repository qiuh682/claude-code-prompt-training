"""
Unit tests for SDF/MOL file parsing.

Tests cover:
- parse_sdf_string: Parse SDF content from string
- parse_sdf_file: Parse SDF from file
- parse_mol_block: Parse single MOL block
- Error tolerance: Continue on bad records
- Identifier extraction: Name, SMILES, external IDs
- Iterator interface: Memory-efficient parsing
"""

import tempfile
from pathlib import Path

import pytest

from packages.chemistry.sdf_parser import (
    MoleculeIdentifiers,
    ParsedMolecule,
    ParseError,
    SDFErrorCode,
    SDFParseError,
    SDFParseResult,
    SDFParser,
    iter_sdf_file,
    parse_mol_block,
    parse_sdf_bytes,
    parse_sdf_file,
    parse_sdf_string,
)


# =============================================================================
# Test Data
# =============================================================================

# Valid ethanol MOL block
ETHANOL_MOL = """ethanol
     RDKit          2D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2990    0.7500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.5981    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
M  END
"""

# Valid aspirin MOL block with properties
ASPIRIN_MOL_WITH_PROPS = """aspirin
     RDKit          2D

 13 13  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2990    0.7500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2990    2.2500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    3.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2990    2.2500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2990    0.7500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.5981    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.5981   -1.5000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    3.8971    0.7500    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
   -2.5981    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.8971    0.7500    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
   -2.5981   -1.5000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
   -3.8971   -2.2500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  2  0
  2  3  1  0
  3  4  2  0
  4  5  1  0
  5  6  2  0
  6  1  1  0
  2  7  1  0
  7  8  2  0
  7  9  1  0
  6 10  1  0
 10 11  2  0
 10 12  1  0
 12 13  1  0
M  END
> <COMPOUND_NAME>
Aspirin

> <SMILES>
CC(=O)OC1=CC=CC=C1C(=O)O

> <CAS>
50-78-2

> <CHEMBL_ID>
CHEMBL25

"""

# Invalid MOL block (0 atoms - will be treated as empty molecule error)
INVALID_MOL = """invalid
     RDKit          2D

  0  0  0  0  0  0  0  0  0  0999 V2000
M  END
"""

# Completely malformed
MALFORMED_MOL = """this is not
a valid mol block
at all
"""


def make_sdf(*mol_blocks: str) -> str:
    """Create SDF content from MOL blocks."""
    return "$$$$\n".join(mol_blocks) + "$$$$\n"


# =============================================================================
# Test: parse_sdf_string
# =============================================================================


class TestParseSdfString:
    """Tests for parse_sdf_string function."""

    def test_parse_single_molecule(self):
        """Should parse single molecule from SDF."""
        sdf = make_sdf(ETHANOL_MOL)
        result = parse_sdf_string(sdf)

        assert result.total_records == 1
        assert result.success_count == 1
        assert result.error_count == 0
        assert len(result.molecules) == 1

    def test_parse_multiple_molecules(self):
        """Should parse multiple molecules from SDF."""
        sdf = make_sdf(ETHANOL_MOL, ASPIRIN_MOL_WITH_PROPS)
        result = parse_sdf_string(sdf)

        assert result.total_records == 2
        assert result.success_count == 2
        assert len(result.molecules) == 2

    def test_molecule_has_canonical_smiles(self):
        """Parsed molecule should have canonical SMILES."""
        sdf = make_sdf(ETHANOL_MOL)
        result = parse_sdf_string(sdf)
        mol = result.molecules[0]

        assert mol.canonical_smiles == "CCO"

    def test_molecule_has_inchikey(self):
        """Parsed molecule should have InChIKey."""
        sdf = make_sdf(ETHANOL_MOL)
        result = parse_sdf_string(sdf)
        mol = result.molecules[0]

        assert mol.inchikey is not None
        assert len(mol.inchikey) == 27

    def test_molecule_has_atom_count(self):
        """Parsed molecule should have atom count."""
        sdf = make_sdf(ETHANOL_MOL)
        result = parse_sdf_string(sdf)
        mol = result.molecules[0]

        assert mol.atom_count == 3
        assert mol.bond_count == 2

    def test_extracts_name_from_mol_block(self):
        """Should extract name from first line of MOL block."""
        sdf = make_sdf(ETHANOL_MOL)
        result = parse_sdf_string(sdf)
        mol = result.molecules[0]

        assert mol.name == "ethanol"

    def test_extracts_properties(self):
        """Should extract SDF properties."""
        sdf = make_sdf(ASPIRIN_MOL_WITH_PROPS)
        result = parse_sdf_string(sdf)
        mol = result.molecules[0]

        assert "COMPOUND_NAME" in mol.properties
        assert mol.properties["COMPOUND_NAME"] == "Aspirin"
        assert "SMILES" in mol.properties
        assert "CAS" in mol.properties

    def test_extracts_identifiers(self):
        """Should extract best-available identifiers."""
        sdf = make_sdf(ASPIRIN_MOL_WITH_PROPS)
        result = parse_sdf_string(sdf)
        mol = result.molecules[0]

        assert mol.identifiers.name == "Aspirin"
        assert mol.identifiers.smiles_from_sdf == "CC(=O)OC1=CC=CC=C1C(=O)O"
        # CAS has priority over CHEMBL_ID in ID_PROPERTIES
        assert mol.identifiers.external_id == "50-78-2"
        assert mol.identifiers.external_id_type == "CAS"

    def test_empty_sdf_returns_error(self):
        """Empty SDF should return error result."""
        result = parse_sdf_string("")

        assert result.success_count == 0
        assert result.error_count == 1
        assert result.errors[0].error_code == SDFErrorCode.EMPTY_FILE

    def test_result_has_statistics(self):
        """Result should have correct statistics."""
        sdf = make_sdf(ETHANOL_MOL, ASPIRIN_MOL_WITH_PROPS)
        result = parse_sdf_string(sdf)

        assert result.success_rate == 100.0
        assert result.has_errors is False
        assert result.source_type == "string"


class TestParseSdfStringErrorTolerance:
    """Tests for error tolerance in SDF parsing."""

    def test_continues_after_invalid_record(self):
        """Should continue parsing after invalid record."""
        sdf = make_sdf(ETHANOL_MOL, INVALID_MOL, ASPIRIN_MOL_WITH_PROPS)
        result = parse_sdf_string(sdf)

        # Should have 2 successful, 1 error
        assert result.success_count == 2
        assert result.error_count == 1
        assert len(result.molecules) == 2
        assert len(result.errors) == 1

    def test_error_has_record_index(self):
        """Error should have correct record index."""
        sdf = make_sdf(ETHANOL_MOL, INVALID_MOL, ASPIRIN_MOL_WITH_PROPS)
        result = parse_sdf_string(sdf)

        error = result.errors[0]
        assert error.record_index == 1  # Second record (0-indexed)

    def test_strict_mode_raises_on_error(self):
        """Strict mode should raise on first error."""
        sdf = make_sdf(ETHANOL_MOL, INVALID_MOL)

        with pytest.raises(SDFParseError):
            parse_sdf_string(sdf, strict=True)

    def test_malformed_records_are_errors(self):
        """Malformed records should be counted as errors."""
        sdf = make_sdf(MALFORMED_MOL)
        result = parse_sdf_string(sdf)

        assert result.success_count == 0
        assert result.error_count == 1

    def test_success_rate_calculation(self):
        """Success rate should be calculated correctly."""
        sdf = make_sdf(ETHANOL_MOL, INVALID_MOL, ASPIRIN_MOL_WITH_PROPS, MALFORMED_MOL)
        result = parse_sdf_string(sdf)

        # 2 valid molecules (ethanol, aspirin)
        # 2 errors (INVALID_MOL with 0 atoms, MALFORMED_MOL)
        assert result.success_count == 2
        assert result.error_count == 2
        assert result.success_rate == 50.0


# =============================================================================
# Test: parse_sdf_file
# =============================================================================


class TestParseSdfFile:
    """Tests for parse_sdf_file function."""

    def test_parse_file(self):
        """Should parse SDF from file."""
        sdf = make_sdf(ETHANOL_MOL, ASPIRIN_MOL_WITH_PROPS)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sdf", delete=False) as f:
            f.write(sdf)
            f.flush()

            result = parse_sdf_file(f.name)

            assert result.success_count == 2
            assert result.source_type == "file"
            assert result.source_path == f.name

        # Cleanup
        Path(f.name).unlink()

    def test_file_not_found(self):
        """Missing file should return error result."""
        result = parse_sdf_file("/nonexistent/path/file.sdf")

        assert result.success_count == 0
        assert result.error_count == 1
        assert result.errors[0].error_code == SDFErrorCode.FILE_NOT_FOUND

    def test_file_not_found_strict_raises(self):
        """Missing file in strict mode should raise."""
        with pytest.raises(SDFParseError) as exc_info:
            parse_sdf_file("/nonexistent/file.sdf", strict=True)

        assert exc_info.value.code == SDFErrorCode.FILE_NOT_FOUND


# =============================================================================
# Test: parse_sdf_bytes
# =============================================================================


class TestParseSdfBytes:
    """Tests for parse_sdf_bytes function."""

    def test_parse_bytes_utf8(self):
        """Should parse UTF-8 encoded SDF bytes."""
        sdf = make_sdf(ETHANOL_MOL)
        sdf_bytes = sdf.encode("utf-8")

        result = parse_sdf_bytes(sdf_bytes)

        assert result.success_count == 1
        assert result.source_type == "bytes"

    def test_parse_bytes_latin1(self):
        """Should parse Latin-1 encoded SDF bytes."""
        sdf = make_sdf(ETHANOL_MOL)
        sdf_bytes = sdf.encode("latin-1")

        result = parse_sdf_bytes(sdf_bytes)

        assert result.success_count == 1


# =============================================================================
# Test: parse_mol_block
# =============================================================================


class TestParseMolBlock:
    """Tests for parse_mol_block function."""

    def test_parse_valid_mol_block(self):
        """Should parse valid MOL block."""
        parsed = parse_mol_block(ETHANOL_MOL)

        assert parsed.canonical_smiles == "CCO"
        assert parsed.atom_count == 3
        assert parsed.name == "ethanol"

    def test_parse_invalid_mol_block_raises(self):
        """Invalid MOL block should raise SDFParseError."""
        with pytest.raises(SDFParseError) as exc_info:
            parse_mol_block(MALFORMED_MOL)

        assert exc_info.value.code == SDFErrorCode.INVALID_MOL_BLOCK

    def test_parse_empty_mol_block_raises(self):
        """Empty MOL block should raise SDFParseError."""
        with pytest.raises(SDFParseError) as exc_info:
            parse_mol_block("")

        assert exc_info.value.code == SDFErrorCode.INVALID_MOL_BLOCK

    def test_parsed_molecule_has_mol_object(self):
        """ParsedMolecule should have RDKit Mol object."""
        parsed = parse_mol_block(ETHANOL_MOL)

        assert parsed.mol is not None
        assert parsed.mol.GetNumAtoms() == 3


# =============================================================================
# Test: iter_sdf_file
# =============================================================================


class TestIterSdfFile:
    """Tests for iter_sdf_file function."""

    def test_iterate_molecules(self):
        """Should yield ParsedMolecule for valid records."""
        sdf = make_sdf(ETHANOL_MOL, ASPIRIN_MOL_WITH_PROPS)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sdf", delete=False) as f:
            f.write(sdf)
            f.flush()

            molecules = []
            for item in iter_sdf_file(f.name):
                if isinstance(item, ParsedMolecule):
                    molecules.append(item)

            assert len(molecules) == 2

        Path(f.name).unlink()

    def test_iterate_with_errors(self):
        """Should yield ParseError for invalid records."""
        sdf = make_sdf(ETHANOL_MOL, INVALID_MOL, ASPIRIN_MOL_WITH_PROPS)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sdf", delete=False) as f:
            f.write(sdf)
            f.flush()

            molecules = []
            errors = []
            for item in iter_sdf_file(f.name):
                if isinstance(item, ParsedMolecule):
                    molecules.append(item)
                elif isinstance(item, ParseError):
                    errors.append(item)

            assert len(molecules) == 2
            assert len(errors) == 1
            assert errors[0].record_index == 1

        Path(f.name).unlink()

    def test_file_not_found_yields_error(self):
        """Missing file should yield ParseError."""
        items = list(iter_sdf_file("/nonexistent/file.sdf"))

        assert len(items) == 1
        assert isinstance(items[0], ParseError)
        assert items[0].error_code == SDFErrorCode.FILE_NOT_FOUND


# =============================================================================
# Test: SDFParser class
# =============================================================================


class TestSDFParser:
    """Tests for SDFParser class."""

    def test_parser_options_sanitize(self):
        """Parser should respect sanitize option."""
        parser = SDFParser(sanitize=True)
        sdf = make_sdf(ETHANOL_MOL)
        result = parser.parse_string(sdf)

        assert result.success_count == 1

    def test_parser_options_compute_identifiers(self):
        """Parser should respect compute_identifiers option."""
        parser = SDFParser(compute_identifiers=False)
        sdf = make_sdf(ETHANOL_MOL)
        result = parser.parse_string(sdf)

        mol = result.molecules[0]
        assert mol.canonical_smiles == ""  # Not computed

    def test_parser_options_strict(self):
        """Parser should respect strict_parsing option."""
        parser = SDFParser(strict_parsing=True)
        sdf = make_sdf(ETHANOL_MOL, INVALID_MOL)

        with pytest.raises(SDFParseError):
            parser.parse_string(sdf)


# =============================================================================
# Test: Data Classes
# =============================================================================


class TestDataClasses:
    """Tests for data classes."""

    def test_parsed_molecule_fields(self):
        """ParsedMolecule should have all expected fields."""
        sdf = make_sdf(ASPIRIN_MOL_WITH_PROPS)
        result = parse_sdf_string(sdf)
        mol = result.molecules[0]

        # Check all fields are populated
        assert mol.record_index == 0
        assert mol.mol is not None
        assert mol.canonical_smiles is not None
        assert mol.inchikey is not None
        assert mol.properties is not None
        assert mol.identifiers is not None

    def test_parse_result_fields(self):
        """SDFParseResult should have all expected fields."""
        sdf = make_sdf(ETHANOL_MOL)
        result = parse_sdf_string(sdf)

        assert hasattr(result, "molecules")
        assert hasattr(result, "errors")
        assert hasattr(result, "total_records")
        assert hasattr(result, "success_count")
        assert hasattr(result, "error_count")
        assert hasattr(result, "success_rate")
        assert hasattr(result, "has_errors")

    def test_parse_error_fields(self):
        """ParseError should have all expected fields."""
        sdf = make_sdf(INVALID_MOL)
        result = parse_sdf_string(sdf)
        error = result.errors[0]

        assert hasattr(error, "record_index")
        assert hasattr(error, "error_code")
        assert hasattr(error, "error_message")

    def test_molecule_identifiers_fields(self):
        """MoleculeIdentifiers should have all expected fields."""
        sdf = make_sdf(ASPIRIN_MOL_WITH_PROPS)
        result = parse_sdf_string(sdf)
        identifiers = result.molecules[0].identifiers

        assert hasattr(identifiers, "name")
        assert hasattr(identifiers, "smiles_from_sdf")
        assert hasattr(identifiers, "external_id")
        assert hasattr(identifiers, "external_id_type")


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_molecule_without_name(self):
        """Molecule without name in MOL block should still parse."""
        mol_no_name = """
     RDKit          2D

  1  0  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
M  END
"""
        sdf = make_sdf(mol_no_name)
        result = parse_sdf_string(sdf)

        assert result.success_count == 1
        # Name might be None or empty string
        assert result.molecules[0].name in (None, "", " ")

    def test_preserves_mol_block(self):
        """Should preserve original MOL block."""
        parsed = parse_mol_block(ETHANOL_MOL)

        assert parsed.mol_block is not None
        assert "ethanol" in parsed.mol_block

    def test_warnings_collected(self):
        """Warnings should be collected in parsed molecule."""
        sdf = make_sdf(ETHANOL_MOL)
        result = parse_sdf_string(sdf)
        mol = result.molecules[0]

        # warnings should be a list (possibly empty)
        assert isinstance(mol.warnings, list)

    def test_3d_coordinates_detected(self):
        """Should detect 3D coordinates."""
        # Note: Our test MOL blocks are 2D
        sdf = make_sdf(ETHANOL_MOL)
        result = parse_sdf_string(sdf)
        mol = result.molecules[0]

        assert mol.has_3d_coordinates is False
