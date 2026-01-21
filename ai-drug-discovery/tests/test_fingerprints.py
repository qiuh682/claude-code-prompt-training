"""
QA tests for molecular fingerprint generation and similarity calculations.

Tests cover:
1. Determinism: same molecule yields identical fingerprints
2. Tanimoto similarity: identical ~1.0, dissimilar <0.3
3. Error handling for invalid molecules

Reference molecules:
- Ethanol: CCO (simple alcohol)
- Aspirin: CC(=O)Oc1ccccc1C(=O)O (complex drug)
- Benzene: c1ccccc1 (aromatic ring)
- Toluene: Cc1ccccc1 (similar to benzene)
"""

import pytest

from packages.chemistry.features import (
    Fingerprint,
    FingerprintCalculationError,
    FingerprintType,
    calculate_fingerprint,
    calculate_maccs_fingerprint,
    calculate_morgan_fingerprint,
    calculate_rdkit_fingerprint,
)
from packages.chemistry.similarity import (
    tanimoto_similarity,
    tanimoto_similarity_bytes,
    dice_similarity,
    dice_similarity_bytes,
    tanimoto_from_smiles,
)


# =============================================================================
# Test Molecules
# =============================================================================

ETHANOL = "CCO"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
BENZENE = "c1ccccc1"
TOLUENE = "Cc1ccccc1"
CAFFEINE = "Cn1cnc2n(C)c(=O)n(C)c(=O)c12"
METHANE = "C"
WATER = "O"

# Invalid SMILES for error testing
INVALID_SMILES = [
    "C1CC",        # Unclosed ring
    "INVALID",    # Not valid SMILES
    "C(C(C",      # Unbalanced parentheses
    "   ",        # Whitespace only
    "C1CCC1C1",   # Invalid ring closure
]


# =============================================================================
# Test: Fingerprint Determinism
# =============================================================================

class TestFingerprintDeterminism:
    """
    Verify fingerprint generation is deterministic.

    Same molecule must yield identical serialized fingerprints on repeated calls.
    """

    @pytest.mark.parametrize("smiles,name", [
        (ETHANOL, "ethanol"),
        (ASPIRIN, "aspirin"),
        (BENZENE, "benzene"),
        (CAFFEINE, "caffeine"),
    ])
    def test_morgan_fingerprint_deterministic(self, smiles: str, name: str):
        """Morgan fingerprint is deterministic for the same molecule."""
        fp1 = calculate_morgan_fingerprint(smiles)
        fp2 = calculate_morgan_fingerprint(smiles)

        # Binary representation must be identical
        assert fp1.bytes_data == fp2.bytes_data, f"Morgan bytes differ for {name}"

        # Base64 must be identical
        assert fp1.base64_str == fp2.base64_str, f"Morgan base64 differs for {name}"

        # Hex must be identical
        assert fp1.hex_str == fp2.hex_str, f"Morgan hex differs for {name}"

        # Bit counts must match
        assert fp1.num_on_bits == fp2.num_on_bits, f"Morgan bit count differs for {name}"

    @pytest.mark.parametrize("smiles,name", [
        (ETHANOL, "ethanol"),
        (ASPIRIN, "aspirin"),
        (BENZENE, "benzene"),
        (CAFFEINE, "caffeine"),
    ])
    def test_maccs_fingerprint_deterministic(self, smiles: str, name: str):
        """MACCS fingerprint is deterministic for the same molecule."""
        fp1 = calculate_maccs_fingerprint(smiles)
        fp2 = calculate_maccs_fingerprint(smiles)

        # Binary representation must be identical
        assert fp1.bytes_data == fp2.bytes_data, f"MACCS bytes differ for {name}"

        # Base64 must be identical
        assert fp1.base64_str == fp2.base64_str, f"MACCS base64 differs for {name}"

        # Hex must be identical
        assert fp1.hex_str == fp2.hex_str, f"MACCS hex differs for {name}"

    @pytest.mark.parametrize("smiles,name", [
        (ETHANOL, "ethanol"),
        (ASPIRIN, "aspirin"),
        (BENZENE, "benzene"),
        (CAFFEINE, "caffeine"),
    ])
    def test_rdkit_fingerprint_deterministic(self, smiles: str, name: str):
        """RDKit fingerprint is deterministic for the same molecule."""
        fp1 = calculate_rdkit_fingerprint(smiles)
        fp2 = calculate_rdkit_fingerprint(smiles)

        # Binary representation must be identical
        assert fp1.bytes_data == fp2.bytes_data, f"RDKit bytes differ for {name}"

        # Base64 must be identical
        assert fp1.base64_str == fp2.base64_str, f"RDKit base64 differs for {name}"

    def test_morgan_deterministic_multiple_calls(self):
        """Morgan fingerprint is identical across 10 repeated calls."""
        fps = [calculate_morgan_fingerprint(ASPIRIN) for _ in range(10)]

        reference_bytes = fps[0].bytes_data
        for i, fp in enumerate(fps[1:], start=2):
            assert fp.bytes_data == reference_bytes, f"Call {i} produced different result"

    def test_maccs_deterministic_multiple_calls(self):
        """MACCS fingerprint is identical across 10 repeated calls."""
        fps = [calculate_maccs_fingerprint(ASPIRIN) for _ in range(10)]

        reference_bytes = fps[0].bytes_data
        for i, fp in enumerate(fps[1:], start=2):
            assert fp.bytes_data == reference_bytes, f"Call {i} produced different result"

    def test_rdkit_deterministic_multiple_calls(self):
        """RDKit fingerprint is identical across 10 repeated calls."""
        fps = [calculate_rdkit_fingerprint(ASPIRIN) for _ in range(10)]

        reference_bytes = fps[0].bytes_data
        for i, fp in enumerate(fps[1:], start=2):
            assert fp.bytes_data == reference_bytes, f"Call {i} produced different result"

    def test_all_fingerprint_types_deterministic(self):
        """All fingerprint types are deterministic via calculate_fingerprint."""
        for fp_type in FingerprintType:
            fp1 = calculate_fingerprint(ASPIRIN, fp_type)
            fp2 = calculate_fingerprint(ASPIRIN, fp_type)

            assert fp1.bytes_data == fp2.bytes_data, f"{fp_type.value} not deterministic"


# =============================================================================
# Test: Tanimoto Similarity
# =============================================================================

class TestTanimotoSimilarity:
    """
    Verify Tanimoto similarity calculations.

    - Identical molecules: similarity ~1.0
    - Dissimilar molecules: similarity < threshold
    """

    # -------------------------------------------------------------------------
    # Identical molecules should have similarity ~1.0
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("smiles,name", [
        (ETHANOL, "ethanol"),
        (ASPIRIN, "aspirin"),
        (BENZENE, "benzene"),
        (CAFFEINE, "caffeine"),
    ])
    def test_identical_molecules_morgan_similarity_one(self, smiles: str, name: str):
        """Identical molecules have Morgan Tanimoto similarity of 1.0."""
        fp1 = calculate_morgan_fingerprint(smiles)
        fp2 = calculate_morgan_fingerprint(smiles)

        similarity = tanimoto_similarity(fp1, fp2)

        assert similarity == pytest.approx(1.0), f"{name} self-similarity is not 1.0"

    @pytest.mark.parametrize("smiles,name", [
        (ETHANOL, "ethanol"),
        (ASPIRIN, "aspirin"),
        (BENZENE, "benzene"),
        (CAFFEINE, "caffeine"),
    ])
    def test_identical_molecules_maccs_similarity_one(self, smiles: str, name: str):
        """Identical molecules have MACCS Tanimoto similarity of 1.0."""
        fp1 = calculate_maccs_fingerprint(smiles)
        fp2 = calculate_maccs_fingerprint(smiles)

        similarity = tanimoto_similarity(fp1, fp2)

        assert similarity == pytest.approx(1.0), f"{name} self-similarity is not 1.0"

    @pytest.mark.parametrize("smiles,name", [
        (ETHANOL, "ethanol"),
        (ASPIRIN, "aspirin"),
        (BENZENE, "benzene"),
        (CAFFEINE, "caffeine"),
    ])
    def test_identical_molecules_rdkit_similarity_one(self, smiles: str, name: str):
        """Identical molecules have RDKit Tanimoto similarity of 1.0."""
        fp1 = calculate_rdkit_fingerprint(smiles)
        fp2 = calculate_rdkit_fingerprint(smiles)

        similarity = tanimoto_similarity(fp1, fp2)

        assert similarity == pytest.approx(1.0), f"{name} self-similarity is not 1.0"

    def test_identical_smiles_tanimoto_from_smiles(self):
        """tanimoto_from_smiles returns 1.0 for identical molecules."""
        similarity = tanimoto_from_smiles(ASPIRIN, ASPIRIN)
        assert similarity == pytest.approx(1.0)

    # -------------------------------------------------------------------------
    # Dissimilar molecules should have low similarity
    # -------------------------------------------------------------------------

    DISSIMILAR_THRESHOLD = 0.3  # Ethanol vs Aspirin should be below this

    def test_ethanol_vs_aspirin_morgan_low_similarity(self):
        """Ethanol and Aspirin have low Morgan Tanimoto similarity (<0.3)."""
        fp_ethanol = calculate_morgan_fingerprint(ETHANOL)
        fp_aspirin = calculate_morgan_fingerprint(ASPIRIN)

        similarity = tanimoto_similarity(fp_ethanol, fp_aspirin)

        assert similarity < self.DISSIMILAR_THRESHOLD, (
            f"Ethanol-Aspirin Morgan similarity {similarity:.3f} >= {self.DISSIMILAR_THRESHOLD}"
        )

    def test_ethanol_vs_aspirin_maccs_low_similarity(self):
        """Ethanol and Aspirin have low MACCS Tanimoto similarity (<0.3)."""
        fp_ethanol = calculate_maccs_fingerprint(ETHANOL)
        fp_aspirin = calculate_maccs_fingerprint(ASPIRIN)

        similarity = tanimoto_similarity(fp_ethanol, fp_aspirin)

        assert similarity < self.DISSIMILAR_THRESHOLD, (
            f"Ethanol-Aspirin MACCS similarity {similarity:.3f} >= {self.DISSIMILAR_THRESHOLD}"
        )

    def test_ethanol_vs_aspirin_rdkit_low_similarity(self):
        """Ethanol and Aspirin have low RDKit Tanimoto similarity (<0.3)."""
        fp_ethanol = calculate_rdkit_fingerprint(ETHANOL)
        fp_aspirin = calculate_rdkit_fingerprint(ASPIRIN)

        similarity = tanimoto_similarity(fp_ethanol, fp_aspirin)

        assert similarity < self.DISSIMILAR_THRESHOLD, (
            f"Ethanol-Aspirin RDKit similarity {similarity:.3f} >= {self.DISSIMILAR_THRESHOLD}"
        )

    def test_ethanol_vs_aspirin_from_smiles(self):
        """tanimoto_from_smiles gives low similarity for dissimilar molecules."""
        similarity = tanimoto_from_smiles(ETHANOL, ASPIRIN)

        assert similarity < self.DISSIMILAR_THRESHOLD, (
            f"Ethanol-Aspirin similarity {similarity:.3f} >= {self.DISSIMILAR_THRESHOLD}"
        )

    def test_methane_vs_caffeine_very_low_similarity(self):
        """Methane (C) and Caffeine should have very low similarity."""
        fp_methane = calculate_morgan_fingerprint(METHANE)
        fp_caffeine = calculate_morgan_fingerprint(CAFFEINE)

        similarity = tanimoto_similarity(fp_methane, fp_caffeine)

        # Methane is just a single carbon - should be very different from caffeine
        assert similarity < 0.15, f"Methane-Caffeine similarity {similarity:.3f} unexpectedly high"

    # -------------------------------------------------------------------------
    # Similar molecules should have moderate to high similarity
    # -------------------------------------------------------------------------

    def test_benzene_vs_toluene_moderate_similarity(self):
        """Benzene and Toluene should have moderate similarity (structurally similar)."""
        fp_benzene = calculate_morgan_fingerprint(BENZENE)
        fp_toluene = calculate_morgan_fingerprint(TOLUENE)

        similarity = tanimoto_similarity(fp_benzene, fp_toluene)

        # Should be similar but not identical (toluene adds a methyl group)
        # Morgan fingerprints can give lower similarity due to circular substructures
        assert 0.1 < similarity < 1.0, f"Benzene-Toluene similarity {similarity:.3f} out of range"

    # -------------------------------------------------------------------------
    # Tanimoto properties
    # -------------------------------------------------------------------------

    def test_tanimoto_is_symmetric(self):
        """Tanimoto similarity is symmetric: sim(A,B) == sim(B,A)."""
        fp_ethanol = calculate_morgan_fingerprint(ETHANOL)
        fp_aspirin = calculate_morgan_fingerprint(ASPIRIN)

        sim_ab = tanimoto_similarity(fp_ethanol, fp_aspirin)
        sim_ba = tanimoto_similarity(fp_aspirin, fp_ethanol)

        assert sim_ab == pytest.approx(sim_ba), "Tanimoto is not symmetric"

    def test_tanimoto_range_zero_to_one(self):
        """Tanimoto similarity is always in range [0, 1]."""
        molecules = [ETHANOL, ASPIRIN, BENZENE, TOLUENE, CAFFEINE]

        for smiles1 in molecules:
            for smiles2 in molecules:
                fp1 = calculate_morgan_fingerprint(smiles1)
                fp2 = calculate_morgan_fingerprint(smiles2)

                similarity = tanimoto_similarity(fp1, fp2)

                assert 0.0 <= similarity <= 1.0, (
                    f"Similarity {similarity} out of range for {smiles1} vs {smiles2}"
                )

    def test_tanimoto_bytes_matches_object(self):
        """tanimoto_similarity_bytes gives same result as tanimoto_similarity."""
        fp1 = calculate_morgan_fingerprint(ETHANOL)
        fp2 = calculate_morgan_fingerprint(ASPIRIN)

        sim_objects = tanimoto_similarity(fp1, fp2)
        sim_bytes = tanimoto_similarity_bytes(fp1.bytes_data, fp2.bytes_data)

        assert sim_objects == pytest.approx(sim_bytes)


# =============================================================================
# Test: Dice Similarity (Alternative Metric)
# =============================================================================

class TestDiceSimilarity:
    """Verify Dice similarity calculations."""

    def test_identical_molecules_dice_one(self):
        """Identical molecules have Dice similarity of 1.0."""
        fp1 = calculate_morgan_fingerprint(ASPIRIN)
        fp2 = calculate_morgan_fingerprint(ASPIRIN)

        similarity = dice_similarity(fp1, fp2)

        assert similarity == pytest.approx(1.0)

    def test_dice_vs_tanimoto_relationship(self):
        """Dice >= Tanimoto for the same fingerprint pair."""
        fp1 = calculate_morgan_fingerprint(ETHANOL)
        fp2 = calculate_morgan_fingerprint(ASPIRIN)

        tanimoto = tanimoto_similarity(fp1, fp2)
        dice = dice_similarity(fp1, fp2)

        # Dice coefficient is always >= Tanimoto for binary fingerprints
        assert dice >= tanimoto, f"Dice ({dice}) < Tanimoto ({tanimoto})"


# =============================================================================
# Test: Error Handling for Invalid Molecules
# =============================================================================

class TestFingerprintErrorHandling:
    """
    Verify fingerprint calculation fails gracefully for invalid input.

    Should raise clear errors, not crash or return garbage.
    """

    @pytest.mark.parametrize("invalid_smiles", INVALID_SMILES)
    def test_morgan_invalid_smiles_raises_error(self, invalid_smiles: str):
        """Morgan fingerprint raises error for invalid SMILES."""
        with pytest.raises((ValueError, FingerprintCalculationError)):
            calculate_morgan_fingerprint(invalid_smiles)

    @pytest.mark.parametrize("invalid_smiles", INVALID_SMILES)
    def test_maccs_invalid_smiles_raises_error(self, invalid_smiles: str):
        """MACCS fingerprint raises error for invalid SMILES."""
        with pytest.raises((ValueError, FingerprintCalculationError)):
            calculate_maccs_fingerprint(invalid_smiles)

    @pytest.mark.parametrize("invalid_smiles", INVALID_SMILES)
    def test_rdkit_invalid_smiles_raises_error(self, invalid_smiles: str):
        """RDKit fingerprint raises error for invalid SMILES."""
        with pytest.raises((ValueError, FingerprintCalculationError)):
            calculate_rdkit_fingerprint(invalid_smiles)

    @pytest.mark.parametrize("invalid_smiles", INVALID_SMILES)
    def test_calculate_fingerprint_invalid_raises_error(self, invalid_smiles: str):
        """calculate_fingerprint raises error for invalid SMILES."""
        with pytest.raises((ValueError, FingerprintCalculationError)):
            calculate_fingerprint(invalid_smiles, FingerprintType.MORGAN)

    def test_error_message_is_descriptive(self):
        """Error message should indicate the problem."""
        with pytest.raises((ValueError, FingerprintCalculationError)) as exc_info:
            calculate_morgan_fingerprint("INVALID")

        error_msg = str(exc_info.value).lower()
        # Error should mention "invalid" or "smiles" or similar
        assert any(word in error_msg for word in ["invalid", "smiles", "failed", "error"])

    def test_tanimoto_mismatched_fingerprint_types_raises(self):
        """Tanimoto similarity raises error for mismatched fingerprint types."""
        fp_morgan = calculate_morgan_fingerprint(ETHANOL)
        fp_maccs = calculate_maccs_fingerprint(ETHANOL)

        with pytest.raises(ValueError) as exc_info:
            tanimoto_similarity(fp_morgan, fp_maccs)

        assert "type" in str(exc_info.value).lower()

    def test_tanimoto_bytes_mismatched_length_raises(self):
        """tanimoto_similarity_bytes raises error for different length fingerprints."""
        fp_morgan = calculate_morgan_fingerprint(ETHANOL)  # 2048 bits = 256 bytes
        fp_maccs = calculate_maccs_fingerprint(ETHANOL)    # 167 bits = 21 bytes

        with pytest.raises(ValueError) as exc_info:
            tanimoto_similarity_bytes(fp_morgan.bytes_data, fp_maccs.bytes_data)

        assert "length" in str(exc_info.value).lower()

    def test_tanimoto_from_smiles_invalid_raises(self):
        """tanimoto_from_smiles raises error for invalid SMILES."""
        with pytest.raises((ValueError, FingerprintCalculationError)):
            tanimoto_from_smiles("INVALID", ETHANOL)

        with pytest.raises((ValueError, FingerprintCalculationError)):
            tanimoto_from_smiles(ETHANOL, "INVALID")


# =============================================================================
# Test: Fingerprint Properties and Metadata
# =============================================================================

class TestFingerprintProperties:
    """Verify fingerprint objects have correct properties."""

    def test_morgan_fingerprint_properties(self):
        """Morgan fingerprint has correct metadata."""
        fp = calculate_morgan_fingerprint(ASPIRIN)

        assert fp.fp_type == FingerprintType.MORGAN
        assert fp.num_bits == 2048  # Default
        assert fp.radius == 2       # Default ECFP4
        assert fp.use_features is False  # Default ECFP (not FCFP)
        assert fp.num_on_bits > 0
        assert len(fp.bytes_data) == 256  # 2048 bits / 8

    def test_maccs_fingerprint_properties(self):
        """MACCS fingerprint has correct metadata."""
        fp = calculate_maccs_fingerprint(ASPIRIN)

        assert fp.fp_type == FingerprintType.MACCS
        assert fp.num_bits == 167  # MACCS keys
        assert fp.num_on_bits > 0
        assert len(fp.bytes_data) == 21  # ceil(167/8)

    def test_rdkit_fingerprint_properties(self):
        """RDKit fingerprint has correct metadata."""
        fp = calculate_rdkit_fingerprint(ASPIRIN)

        assert fp.fp_type == FingerprintType.RDKIT
        assert fp.num_bits == 2048  # Default
        assert fp.num_on_bits > 0
        assert len(fp.bytes_data) == 256  # 2048 bits / 8

    def test_fingerprint_to_dict(self):
        """Fingerprint.to_dict() returns valid dictionary."""
        fp = calculate_morgan_fingerprint(ASPIRIN)
        d = fp.to_dict()

        assert d["fp_type"] == "morgan"
        assert d["num_bits"] == 2048
        assert d["num_on_bits"] > 0
        assert isinstance(d["base64"], str)
        assert isinstance(d["hex"], str)
        assert d["radius"] == 2

    def test_fingerprint_from_base64_roundtrip(self):
        """Fingerprint can be reconstructed from base64."""
        original = calculate_morgan_fingerprint(ASPIRIN)

        reconstructed = Fingerprint.from_base64(
            original.base64_str,
            FingerprintType.MORGAN,
            num_bits=2048,
            radius=2,
        )

        assert reconstructed.bytes_data == original.bytes_data
        assert reconstructed.num_on_bits == original.num_on_bits

    def test_get_on_bits_returns_sorted_indices(self):
        """get_on_bits() returns sorted list of set bit indices."""
        fp = calculate_morgan_fingerprint(ETHANOL)
        on_bits = fp.get_on_bits()

        assert len(on_bits) == fp.num_on_bits
        assert on_bits == sorted(on_bits)  # Should be sorted
        assert all(0 <= bit < fp.num_bits for bit in on_bits)  # All in range


# =============================================================================
# Test: Custom Fingerprint Parameters
# =============================================================================

class TestCustomFingerprintParameters:
    """Verify fingerprints can be generated with custom parameters."""

    def test_morgan_custom_radius(self):
        """Morgan fingerprint with custom radius (ECFP6)."""
        fp_r2 = calculate_morgan_fingerprint(ASPIRIN, radius=2)  # ECFP4
        fp_r3 = calculate_morgan_fingerprint(ASPIRIN, radius=3)  # ECFP6

        # Different radii should produce different fingerprints
        assert fp_r2.bytes_data != fp_r3.bytes_data
        assert fp_r2.radius == 2
        assert fp_r3.radius == 3

    def test_morgan_custom_bits(self):
        """Morgan fingerprint with custom bit count."""
        fp_1024 = calculate_morgan_fingerprint(ASPIRIN, num_bits=1024)
        fp_2048 = calculate_morgan_fingerprint(ASPIRIN, num_bits=2048)

        assert fp_1024.num_bits == 1024
        assert fp_2048.num_bits == 2048
        assert len(fp_1024.bytes_data) == 128  # 1024/8
        assert len(fp_2048.bytes_data) == 256  # 2048/8

    def test_morgan_fcfp_vs_ecfp(self):
        """Morgan with use_features=True gives FCFP (different from ECFP)."""
        fp_ecfp = calculate_morgan_fingerprint(ASPIRIN, use_features=False)
        fp_fcfp = calculate_morgan_fingerprint(ASPIRIN, use_features=True)

        # ECFP and FCFP should be different
        assert fp_ecfp.bytes_data != fp_fcfp.bytes_data
        assert fp_ecfp.use_features is False
        assert fp_fcfp.use_features is True
