"""
Unit tests for SMILES validation and canonicalization.

Tests cover:
- validate_smiles: Basic validation
- smiles_to_mol: Parsing to RDKit Mol
- canonicalize_smiles: Canonicalization + InChIKey generation
- Salt/mixture handling
- Standardization
- Batch processing
- Error handling
"""

import pytest

from packages.chemistry.smiles import (
    CanonicalizeResult,
    SmilesError,
    SmilesErrorCode,
    ValidationResult,
    canonicalize_smiles,
    canonicalize_smiles_batch,
    get_molecular_formula,
    smiles_are_equivalent,
    smiles_to_mol,
    validate_smiles,
    validate_smiles_batch,
    validate_smiles_detailed,
)


# =============================================================================
# Test: validate_smiles
# =============================================================================


class TestValidateSmiles:
    """Tests for validate_smiles function."""

    def test_valid_simple_smiles(self):
        """Valid simple SMILES should return True."""
        assert validate_smiles("CCO") is True  # Ethanol
        assert validate_smiles("C") is True  # Methane
        assert validate_smiles("CC") is True  # Ethane
        assert validate_smiles("c1ccccc1") is True  # Benzene

    def test_valid_complex_smiles(self):
        """Valid complex SMILES should return True."""
        # Aspirin
        assert validate_smiles("CC(=O)OC1=CC=CC=C1C(=O)O") is True
        # Caffeine
        assert validate_smiles("CN1C=NC2=C1C(=O)N(C(=O)N2C)C") is True

    def test_valid_smiles_with_stereo(self):
        """SMILES with stereochemistry should be valid."""
        assert validate_smiles("C/C=C/C") is True  # Trans
        assert validate_smiles("C/C=C\\C") is True  # Cis
        assert validate_smiles("C[C@H](O)CC") is True  # R stereocenter
        assert validate_smiles("C[C@@H](O)CC") is True  # S stereocenter

    def test_invalid_smiles(self):
        """Invalid SMILES should return False."""
        assert validate_smiles("invalid") is False
        assert validate_smiles("C(C(C") is False  # Unbalanced parentheses
        assert validate_smiles("XYZ") is False  # Invalid atoms

    def test_empty_input(self):
        """Empty input should return False."""
        assert validate_smiles("") is False
        assert validate_smiles("   ") is False
        assert validate_smiles(None) is False  # type: ignore

    def test_smiles_with_whitespace(self):
        """SMILES with leading/trailing whitespace should be handled."""
        assert validate_smiles("  CCO  ") is True
        assert validate_smiles("\tCCO\n") is True


class TestValidateSmilesDetailed:
    """Tests for validate_smiles_detailed function."""

    def test_valid_smiles_returns_details(self):
        """Valid SMILES should return detailed info."""
        result = validate_smiles_detailed("CCO")

        assert result.is_valid is True
        assert result.error_message is None
        assert result.error_code is None
        assert result.atom_count == 3
        assert result.has_multiple_fragments is False

    def test_invalid_smiles_returns_error_details(self):
        """Invalid SMILES should return error details."""
        result = validate_smiles_detailed("invalid_smiles")

        assert result.is_valid is False
        assert result.error_message is not None
        assert result.error_code == SmilesErrorCode.INVALID_SMILES

    def test_empty_input_returns_error(self):
        """Empty input should return specific error."""
        result = validate_smiles_detailed("")

        assert result.is_valid is False
        assert result.error_code == SmilesErrorCode.EMPTY_INPUT

    def test_mixture_detection(self):
        """Mixtures should be detected."""
        result = validate_smiles_detailed("CCO.CC")

        assert result.is_valid is True
        assert result.has_multiple_fragments is True


# =============================================================================
# Test: smiles_to_mol
# =============================================================================


class TestSmilesToMol:
    """Tests for smiles_to_mol function."""

    def test_parse_simple_smiles(self):
        """Simple SMILES should parse to Mol."""
        mol = smiles_to_mol("CCO")

        assert mol is not None
        assert mol.GetNumAtoms() == 3

    def test_parse_complex_smiles(self):
        """Complex SMILES should parse correctly."""
        mol = smiles_to_mol("CC(=O)OC1=CC=CC=C1C(=O)O")  # Aspirin

        assert mol is not None
        assert mol.GetNumAtoms() == 13  # C9H8O4

    def test_invalid_smiles_raises_error(self):
        """Invalid SMILES should raise SmilesError."""
        with pytest.raises(SmilesError) as exc_info:
            smiles_to_mol("invalid")

        assert exc_info.value.code == SmilesErrorCode.INVALID_SMILES
        assert "invalid" in exc_info.value.smiles

    def test_empty_smiles_raises_error(self):
        """Empty SMILES should raise SmilesError."""
        with pytest.raises(SmilesError) as exc_info:
            smiles_to_mol("")

        assert exc_info.value.code == SmilesErrorCode.EMPTY_INPUT

    def test_strip_salts_keeps_largest_fragment(self):
        """With strip_salts=True, should keep largest fragment."""
        # Sodium acetate: acetic acid + sodium
        mol = smiles_to_mol("CC(=O)O.[Na]", strip_salts=True)

        # Should only have acetic acid (4 atoms), not sodium
        assert mol.GetNumAtoms() == 4

    def test_strip_salts_false_keeps_all(self):
        """With strip_salts=False, should keep all fragments."""
        mol = smiles_to_mol("CC(=O)O.[Na]", strip_salts=False)

        # Should have both (4 + 1 = 5 atoms)
        assert mol.GetNumAtoms() == 5


# =============================================================================
# Test: canonicalize_smiles
# =============================================================================


class TestCanonicalizeSmiles:
    """Tests for canonicalize_smiles function."""

    def test_canonicalize_simple_smiles(self):
        """Simple SMILES should be canonicalized."""
        result = canonicalize_smiles("C(C)O")

        assert result.canonical_smiles == "CCO"
        assert result.inchikey is not None
        assert len(result.inchikey) == 27  # InChIKey format

    def test_canonicalize_returns_inchikey(self):
        """Should return correct InChIKey for known molecule."""
        result = canonicalize_smiles("CCO")  # Ethanol

        # Known InChIKey for ethanol
        assert result.inchikey == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"

    def test_canonicalize_returns_inchi(self):
        """Should return InChI string."""
        result = canonicalize_smiles("CCO")

        assert result.inchi is not None
        assert result.inchi.startswith("InChI=")

    def test_canonicalize_preserves_original(self):
        """Should preserve original SMILES in result."""
        result = canonicalize_smiles("C(C)O")

        assert result.original_smiles == "C(C)O"

    def test_canonicalize_equivalent_smiles(self):
        """Different representations should canonicalize to same form."""
        result1 = canonicalize_smiles("C(C)O")
        result2 = canonicalize_smiles("OCC")
        result3 = canonicalize_smiles("CCO")

        assert result1.canonical_smiles == result2.canonical_smiles
        assert result2.canonical_smiles == result3.canonical_smiles
        assert result1.inchikey == result2.inchikey

    def test_canonicalize_invalid_smiles_raises_error(self):
        """Invalid SMILES should raise SmilesError."""
        with pytest.raises(SmilesError) as exc_info:
            canonicalize_smiles("invalid")

        assert exc_info.value.code == SmilesErrorCode.INVALID_SMILES

    def test_isomeric_preserves_stereo(self):
        """With isomeric=True, stereochemistry should be preserved."""
        result = canonicalize_smiles("C[C@H](O)CC", isomeric=True)

        assert "@" in result.canonical_smiles

    def test_non_isomeric_removes_stereo(self):
        """With isomeric=False, stereochemistry should be removed."""
        result = canonicalize_smiles("C[C@H](O)CC", isomeric=False)

        assert "@" not in result.canonical_smiles


class TestCanonicalizeSmilesSaltHandling:
    """Tests for salt/mixture handling in canonicalize_smiles."""

    def test_salt_stripped_when_requested(self):
        """Salts should be stripped when strip_salts=True."""
        # Sodium acetate
        result = canonicalize_smiles("CC(=O)O.[Na]", strip_salts=True)

        assert result.canonical_smiles == "CC(=O)O"
        assert result.had_multiple_fragments is True
        assert result.warnings is not None
        assert any("largest fragment" in w.lower() for w in result.warnings)

    def test_salt_kept_when_not_requested(self):
        """Salts should be kept when strip_salts=False."""
        result = canonicalize_smiles("CC(=O)O.[Na]", strip_salts=False)

        assert "." in result.canonical_smiles
        assert result.had_multiple_fragments is True

    def test_hcl_salt_handling(self):
        """HCl salt should be handled correctly."""
        # Ethylamine HCl
        result = canonicalize_smiles("CCN.Cl", strip_salts=True)

        assert result.canonical_smiles == "CCN"

    def test_solvate_handling(self):
        """Solvates (e.g., hydrates) should be handled."""
        # Ethanol monohydrate
        result = canonicalize_smiles("CCO.O", strip_salts=True)

        assert result.canonical_smiles == "CCO"

    def test_largest_fragment_selected(self):
        """When stripping salts, largest fragment by atom count is kept."""
        # Larger fragment should be kept
        result = canonicalize_smiles("c1ccccc1.C", strip_salts=True)  # Benzene + methane

        assert result.canonical_smiles == "c1ccccc1"  # Benzene (6 atoms)


class TestCanonicalizeStandardization:
    """Tests for standardization in canonicalize_smiles."""

    def test_standardize_neutralizes_carboxylate(self):
        """Carboxylates should be neutralized when standardize=True."""
        # Acetate anion
        result = canonicalize_smiles("CC(=O)[O-]", standardize=True)

        assert result.was_standardized is True
        # Should be neutralized (no negative charge in canonical SMILES)
        assert "-" not in result.canonical_smiles or result.canonical_smiles == "CC(=O)O"

    def test_no_standardize_keeps_charges(self):
        """Charges should be kept when standardize=False."""
        result = canonicalize_smiles("CC(=O)[O-]", standardize=False)

        assert result.was_standardized is False
        assert "-" in result.canonical_smiles


# =============================================================================
# Test: Helper Functions
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_molecular_formula(self):
        """Should return correct molecular formula."""
        assert get_molecular_formula("CCO") == "C2H6O"
        assert get_molecular_formula("c1ccccc1") == "C6H6"

    def test_smiles_are_equivalent_true(self):
        """Equivalent SMILES should return True."""
        assert smiles_are_equivalent("CCO", "C(C)O") is True
        assert smiles_are_equivalent("CCO", "OCC") is True

    def test_smiles_are_equivalent_false(self):
        """Non-equivalent SMILES should return False."""
        assert smiles_are_equivalent("CCO", "CC") is False
        assert smiles_are_equivalent("CCO", "CCCO") is False

    def test_smiles_are_equivalent_invalid_returns_false(self):
        """Invalid SMILES should return False, not raise."""
        assert smiles_are_equivalent("CCO", "invalid") is False
        assert smiles_are_equivalent("invalid1", "invalid2") is False


# =============================================================================
# Test: Batch Processing
# =============================================================================


class TestBatchProcessing:
    """Tests for batch processing functions."""

    def test_validate_batch_separates_valid_invalid(self):
        """Batch validation should separate valid and invalid SMILES."""
        smiles_list = ["CCO", "invalid", "CC", "also_invalid", "c1ccccc1"]

        valid, invalid = validate_smiles_batch(smiles_list)

        assert len(valid) == 3
        assert len(invalid) == 2
        assert "CCO" in valid
        assert "CC" in valid
        assert "c1ccccc1" in valid

    def test_validate_batch_returns_indices(self):
        """Invalid entries should include original indices."""
        smiles_list = ["CCO", "invalid", "CC"]

        valid, invalid = validate_smiles_batch(smiles_list)

        assert invalid[0][0] == 1  # Index
        assert invalid[0][1] == "invalid"  # SMILES
        assert "INVALID_SMILES" in invalid[0][2]  # Error message

    def test_canonicalize_batch_processes_all(self):
        """Batch canonicalization should process all valid SMILES."""
        smiles_list = ["C(C)O", "OCC", "CCO"]

        results, errors = canonicalize_smiles_batch(smiles_list)

        assert len(results) == 3
        assert len(errors) == 0
        # All should canonicalize to same form
        assert all(r.canonical_smiles == "CCO" for r in results)

    def test_canonicalize_batch_with_errors(self):
        """Batch should handle mixed valid/invalid input."""
        smiles_list = ["CCO", "invalid", "CC"]

        results, errors = canonicalize_smiles_batch(smiles_list)

        assert len(results) == 2
        assert len(errors) == 1
        assert errors[0][0] == 1  # Index of "invalid"

    def test_canonicalize_batch_with_salt_stripping(self):
        """Batch should apply salt stripping to all."""
        smiles_list = ["CCO", "CC(=O)O.[Na]", "CCN.Cl"]

        results, errors = canonicalize_smiles_batch(smiles_list, strip_salts=True)

        assert len(results) == 3
        assert results[1].canonical_smiles == "CC(=O)O"  # Salt stripped
        assert results[2].canonical_smiles == "CCN"  # Salt stripped


# =============================================================================
# Test: Error Messages
# =============================================================================


class TestErrorMessages:
    """Tests for clear error messages."""

    def test_error_includes_smiles(self):
        """Error should include the problematic SMILES."""
        try:
            smiles_to_mol("bad_smiles_xyz")
        except SmilesError as e:
            assert "bad_smiles_xyz" in str(e) or e.smiles == "bad_smiles_xyz"

    def test_error_code_in_string(self):
        """Error string should include error code."""
        try:
            smiles_to_mol("invalid")
        except SmilesError as e:
            assert "INVALID_SMILES" in str(e)

    def test_empty_error_is_specific(self):
        """Empty input error should be distinguishable."""
        try:
            smiles_to_mol("")
        except SmilesError as e:
            assert e.code == SmilesErrorCode.EMPTY_INPUT
            assert "empty" in str(e).lower()
