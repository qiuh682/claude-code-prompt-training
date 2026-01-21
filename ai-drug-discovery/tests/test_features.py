"""Tests for molecular descriptors and fingerprint calculations."""

import base64
from decimal import Decimal

import pytest

from packages.chemistry.features import (
    DescriptorCalculationError,
    Fingerprint,
    FingerprintCalculationError,
    FingerprintType,
    MolecularDescriptors,
    calculate_all_fingerprints,
    calculate_descriptors,
    calculate_fingerprint,
    calculate_maccs_fingerprint,
    calculate_morgan_fingerprint,
    calculate_rdkit_fingerprint,
)


# ============================================================================
# Test data
# ============================================================================

# Simple molecules for testing
ETHANOL = "CCO"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
CAFFEINE = "Cn1cnc2c1c(=O)n(c(=O)n2C)C"
BENZENE = "c1ccccc1"
INVALID_SMILES = "INVALID_SMILES_XXX"


class TestMolecularDescriptors:
    """Tests for descriptor calculations."""

    def test_calculate_descriptors_ethanol(self):
        """Test descriptors for ethanol."""
        desc = calculate_descriptors(ETHANOL)

        assert isinstance(desc, MolecularDescriptors)
        # Ethanol MW ≈ 46.07
        assert 45.0 < float(desc.molecular_weight) < 47.0
        # Ethanol has 1 HBD (OH) and 1 HBA (O)
        assert desc.hbd == 1
        assert desc.hba == 1
        # No rotatable bonds in ethanol
        assert desc.num_rotatable_bonds == 0
        # No rings
        assert desc.num_rings == 0

    def test_calculate_descriptors_aspirin(self):
        """Test descriptors for aspirin."""
        desc = calculate_descriptors(ASPIRIN)

        # Aspirin MW ≈ 180.16
        assert 179.0 < float(desc.molecular_weight) < 181.0
        # Aspirin has 1 HBD (COOH)
        assert desc.hbd == 1
        # Aspirin has 4 HBA (3 oxygens + 1 ester)
        assert desc.hba >= 3
        # One aromatic ring
        assert desc.num_aromatic_rings == 1

    def test_calculate_descriptors_caffeine(self):
        """Test descriptors for caffeine."""
        desc = calculate_descriptors(CAFFEINE)

        # Caffeine MW ≈ 194.19
        assert 193.0 < float(desc.molecular_weight) < 195.0
        # Caffeine has 0 HBD (all nitrogens are tertiary)
        assert desc.hbd == 0
        # Has rings
        assert desc.num_rings >= 2

    def test_calculate_descriptors_invalid_smiles(self):
        """Test that invalid SMILES raises error."""
        with pytest.raises(ValueError, match="Invalid SMILES"):
            calculate_descriptors(INVALID_SMILES)

    def test_descriptors_to_dict(self):
        """Test conversion to dictionary."""
        desc = calculate_descriptors(ETHANOL)
        d = desc.to_dict()

        assert isinstance(d, dict)
        assert "molecular_weight" in d
        assert "logp" in d
        assert "tpsa" in d
        assert "hbd" in d
        assert "hba" in d
        assert isinstance(d["molecular_weight"], float)

    def test_lipinski_violations_ethanol(self):
        """Test Lipinski rule of five for small molecule."""
        desc = calculate_descriptors(ETHANOL)
        assert desc.lipinski_violations() == 0
        assert desc.is_lipinski_compliant() is True

    def test_lipinski_violations_large_molecule(self):
        """Test Lipinski violations for molecule that breaks rules."""
        # Create a large molecule that violates MW rule
        large_smiles = "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"  # Long alkane
        desc = calculate_descriptors(large_smiles)
        # Should violate MW > 500 and possibly LogP > 5
        assert desc.lipinski_violations() >= 1

    def test_descriptors_from_mol_object(self):
        """Test that Mol objects work as input."""
        from rdkit import Chem

        mol = Chem.MolFromSmiles(ETHANOL)
        desc = calculate_descriptors(mol)
        assert isinstance(desc, MolecularDescriptors)

    def test_descriptors_deterministic(self):
        """Test that calculations are deterministic."""
        desc1 = calculate_descriptors(ASPIRIN)
        desc2 = calculate_descriptors(ASPIRIN)

        assert desc1.molecular_weight == desc2.molecular_weight
        assert desc1.logp == desc2.logp
        assert desc1.tpsa == desc2.tpsa


class TestMorganFingerprint:
    """Tests for Morgan (ECFP) fingerprint."""

    def test_calculate_morgan_fingerprint_default(self):
        """Test Morgan fingerprint with defaults."""
        fp = calculate_morgan_fingerprint(ASPIRIN)

        assert isinstance(fp, Fingerprint)
        assert fp.fp_type == FingerprintType.MORGAN
        assert fp.num_bits == 2048
        assert fp.radius == 2
        assert fp.use_features is False

    def test_calculate_morgan_fingerprint_custom_params(self):
        """Test Morgan fingerprint with custom parameters."""
        fp = calculate_morgan_fingerprint(ASPIRIN, radius=3, num_bits=1024)

        assert fp.num_bits == 1024
        assert fp.radius == 3

    def test_calculate_morgan_fingerprint_fcfp(self):
        """Test FCFP (feature-based) fingerprint."""
        fp = calculate_morgan_fingerprint(ASPIRIN, use_features=True)
        assert fp.use_features is True

    def test_morgan_fingerprint_representations(self):
        """Test different fingerprint representations."""
        fp = calculate_morgan_fingerprint(ETHANOL)

        # Bytes should match num_bits / 8
        assert len(fp.bytes_data) == fp.num_bits // 8

        # Base64 should decode to same bytes
        decoded = base64.b64decode(fp.base64_str)
        assert decoded == fp.bytes_data

        # Hex should match bytes
        assert bytes.fromhex(fp.hex_str) == fp.bytes_data

    def test_morgan_fingerprint_on_bits(self):
        """Test getting on bits."""
        fp = calculate_morgan_fingerprint(BENZENE)
        on_bits = fp.get_on_bits()

        assert isinstance(on_bits, list)
        assert len(on_bits) == fp.num_on_bits
        assert all(0 <= b < fp.num_bits for b in on_bits)
        assert on_bits == sorted(on_bits)

    def test_morgan_fingerprint_deterministic(self):
        """Test deterministic fingerprint generation."""
        fp1 = calculate_morgan_fingerprint(ASPIRIN)
        fp2 = calculate_morgan_fingerprint(ASPIRIN)

        assert fp1.bytes_data == fp2.bytes_data
        assert fp1.num_on_bits == fp2.num_on_bits

    def test_morgan_fingerprint_invalid_smiles(self):
        """Test error handling for invalid SMILES."""
        with pytest.raises(ValueError, match="Invalid SMILES"):
            calculate_morgan_fingerprint(INVALID_SMILES)


class TestMACCSFingerprint:
    """Tests for MACCS structural keys."""

    def test_calculate_maccs_fingerprint(self):
        """Test MACCS fingerprint calculation."""
        fp = calculate_maccs_fingerprint(ASPIRIN)

        assert isinstance(fp, Fingerprint)
        assert fp.fp_type == FingerprintType.MACCS
        assert fp.num_bits == 167  # MACCS has 167 bits

    def test_maccs_fingerprint_benzene(self):
        """Test MACCS for simple aromatic."""
        fp = calculate_maccs_fingerprint(BENZENE)
        assert fp.num_on_bits > 0

    def test_maccs_fingerprint_deterministic(self):
        """Test deterministic generation."""
        fp1 = calculate_maccs_fingerprint(CAFFEINE)
        fp2 = calculate_maccs_fingerprint(CAFFEINE)
        assert fp1.bytes_data == fp2.bytes_data


class TestRDKitFingerprint:
    """Tests for RDKit topological fingerprint."""

    def test_calculate_rdkit_fingerprint_default(self):
        """Test RDKit fingerprint with defaults."""
        fp = calculate_rdkit_fingerprint(ASPIRIN)

        assert isinstance(fp, Fingerprint)
        assert fp.fp_type == FingerprintType.RDKIT
        assert fp.num_bits == 2048

    def test_calculate_rdkit_fingerprint_custom(self):
        """Test with custom parameters."""
        fp = calculate_rdkit_fingerprint(ASPIRIN, min_path=2, max_path=5, num_bits=1024)
        assert fp.num_bits == 1024

    def test_rdkit_fingerprint_deterministic(self):
        """Test deterministic generation."""
        fp1 = calculate_rdkit_fingerprint(ETHANOL)
        fp2 = calculate_rdkit_fingerprint(ETHANOL)
        assert fp1.bytes_data == fp2.bytes_data


class TestFingerprintGeneric:
    """Tests for generic fingerprint function."""

    def test_calculate_fingerprint_morgan(self):
        """Test generic function with Morgan type."""
        fp = calculate_fingerprint(ASPIRIN, FingerprintType.MORGAN)
        assert fp.fp_type == FingerprintType.MORGAN

    def test_calculate_fingerprint_maccs(self):
        """Test generic function with MACCS type."""
        fp = calculate_fingerprint(ASPIRIN, FingerprintType.MACCS)
        assert fp.fp_type == FingerprintType.MACCS

    def test_calculate_fingerprint_rdkit(self):
        """Test generic function with RDKit type."""
        fp = calculate_fingerprint(ASPIRIN, FingerprintType.RDKIT)
        assert fp.fp_type == FingerprintType.RDKIT

    def test_calculate_fingerprint_with_kwargs(self):
        """Test passing kwargs through generic function."""
        fp = calculate_fingerprint(ASPIRIN, FingerprintType.MORGAN, radius=3, num_bits=512)
        assert fp.radius == 3
        assert fp.num_bits == 512


class TestCalculateAllFingerprints:
    """Tests for calculating all fingerprint types."""

    def test_calculate_all_fingerprints(self):
        """Test calculating all fingerprints at once."""
        fps = calculate_all_fingerprints(ASPIRIN)

        assert FingerprintType.MORGAN in fps
        assert FingerprintType.MACCS in fps
        assert FingerprintType.RDKIT in fps

        assert fps[FingerprintType.MORGAN].fp_type == FingerprintType.MORGAN
        assert fps[FingerprintType.MACCS].fp_type == FingerprintType.MACCS
        assert fps[FingerprintType.RDKIT].fp_type == FingerprintType.RDKIT

    def test_calculate_all_fingerprints_custom_params(self):
        """Test with custom parameters."""
        fps = calculate_all_fingerprints(ASPIRIN, morgan_radius=3, morgan_bits=1024, rdkit_bits=512)

        assert fps[FingerprintType.MORGAN].radius == 3
        assert fps[FingerprintType.MORGAN].num_bits == 1024
        assert fps[FingerprintType.RDKIT].num_bits == 512


class TestFingerprintSerialization:
    """Tests for fingerprint serialization."""

    def test_fingerprint_to_dict(self):
        """Test converting fingerprint to dictionary."""
        fp = calculate_morgan_fingerprint(ASPIRIN)
        d = fp.to_dict()

        assert "fp_type" in d
        assert "num_bits" in d
        assert "num_on_bits" in d
        assert "base64" in d
        assert "hex" in d
        assert d["fp_type"] == "morgan"

    def test_fingerprint_from_base64(self):
        """Test reconstructing fingerprint from base64."""
        fp1 = calculate_morgan_fingerprint(ASPIRIN)

        fp2 = Fingerprint.from_base64(
            fp1.base64_str,
            FingerprintType.MORGAN,
            fp1.num_bits,
            radius=2,
        )

        assert fp2.bytes_data == fp1.bytes_data
        assert fp2.num_bits == fp1.num_bits

    def test_fingerprint_round_trip(self):
        """Test serialization round trip."""
        fp1 = calculate_morgan_fingerprint(ETHANOL)
        d = fp1.to_dict()

        fp2 = Fingerprint.from_base64(
            d["base64"],
            FingerprintType(d["fp_type"]),
            d["num_bits"],
            radius=d["radius"],
            use_features=d["use_features"],
        )

        assert fp2.bytes_data == fp1.bytes_data


class TestDifferentMolecules:
    """Tests ensuring different molecules produce different fingerprints."""

    def test_different_molecules_different_fingerprints(self):
        """Test that different molecules have different fingerprints."""
        fp_ethanol = calculate_morgan_fingerprint(ETHANOL)
        fp_aspirin = calculate_morgan_fingerprint(ASPIRIN)
        fp_caffeine = calculate_morgan_fingerprint(CAFFEINE)

        assert fp_ethanol.bytes_data != fp_aspirin.bytes_data
        assert fp_aspirin.bytes_data != fp_caffeine.bytes_data
        assert fp_ethanol.bytes_data != fp_caffeine.bytes_data

    def test_different_molecules_different_descriptors(self):
        """Test that different molecules have different descriptors."""
        d1 = calculate_descriptors(ETHANOL)
        d2 = calculate_descriptors(ASPIRIN)

        assert d1.molecular_weight != d2.molecular_weight
        assert d1.num_rings != d2.num_rings


class TestEdgeCases:
    """Tests for edge cases."""

    def test_single_atom(self):
        """Test with single atom molecule."""
        fp = calculate_morgan_fingerprint("[Na+]")
        desc = calculate_descriptors("[Na+]")

        assert fp.num_on_bits > 0
        assert desc.num_heavy_atoms == 1

    def test_charged_molecule(self):
        """Test with charged molecule."""
        # Acetate ion
        fp = calculate_morgan_fingerprint("CC(=O)[O-]")
        assert fp.num_on_bits > 0

    def test_stereochemistry(self):
        """Test that stereochemistry is captured."""
        # L-alanine and D-alanine
        l_ala = "N[C@@H](C)C(=O)O"
        d_ala = "N[C@H](C)C(=O)O"

        fp_l = calculate_morgan_fingerprint(l_ala)
        fp_d = calculate_morgan_fingerprint(d_ala)

        # Morgan fingerprints don't distinguish stereochemistry by default
        # So they should be the same
        assert fp_l.bytes_data == fp_d.bytes_data
