"""
Molecular descriptors and fingerprint calculations using RDKit.

This module provides deterministic calculation of:
- Molecular descriptors: MW, LogP, TPSA, HBD, HBA
- Fingerprints: Morgan (ECFP), MACCS, RDKit

Fingerprints are returned in multiple representations for flexibility:
- Binary bytes (compact storage)
- Base64 string (JSON-safe)
- Hex string (human-readable)
- Bit vector (for similarity calculations)
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rdkit.Chem import Mol
    from rdkit.DataStructs import ExplicitBitVect


class FingerprintType(str, Enum):
    """Supported fingerprint types."""

    MORGAN = "morgan"  # ECFP-like circular fingerprint
    MACCS = "maccs"  # MACCS structural keys (166 bits)
    RDKIT = "rdkit"  # RDKit topological fingerprint


@dataclass(frozen=True)
class MolecularDescriptors:
    """Container for calculated molecular descriptors."""

    molecular_weight: Decimal
    logp: Decimal
    tpsa: Decimal
    hbd: int  # Hydrogen bond donors
    hba: int  # Hydrogen bond acceptors

    # Additional useful descriptors
    num_rotatable_bonds: int
    num_rings: int
    num_aromatic_rings: int
    num_heavy_atoms: int
    fraction_sp3: Decimal

    def to_dict(self) -> dict:
        """Convert to dictionary with float values for JSON serialization."""
        return {
            "molecular_weight": float(self.molecular_weight),
            "logp": float(self.logp),
            "tpsa": float(self.tpsa),
            "hbd": self.hbd,
            "hba": self.hba,
            "num_rotatable_bonds": self.num_rotatable_bonds,
            "num_rings": self.num_rings,
            "num_aromatic_rings": self.num_aromatic_rings,
            "num_heavy_atoms": self.num_heavy_atoms,
            "fraction_sp3": float(self.fraction_sp3),
        }

    def lipinski_violations(self) -> int:
        """Count Lipinski's Rule of Five violations."""
        violations = 0
        if float(self.molecular_weight) > 500:
            violations += 1
        if float(self.logp) > 5:
            violations += 1
        if self.hbd > 5:
            violations += 1
        if self.hba > 10:
            violations += 1
        return violations

    def is_lipinski_compliant(self) -> bool:
        """Check if molecule passes Lipinski's Rule of Five."""
        return self.lipinski_violations() == 0


@dataclass(frozen=True)
class Fingerprint:
    """Container for molecular fingerprint with multiple representations."""

    fp_type: FingerprintType
    num_bits: int
    num_on_bits: int

    # Representations
    bytes_data: bytes  # Raw binary
    base64_str: str  # Base64 encoded
    hex_str: str  # Hexadecimal

    # Parameters used to generate (for reproducibility)
    radius: int | None = None  # For Morgan
    use_features: bool = False  # For Morgan (FCFP vs ECFP)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "fp_type": self.fp_type.value,
            "num_bits": self.num_bits,
            "num_on_bits": self.num_on_bits,
            "base64": self.base64_str,
            "hex": self.hex_str,
            "radius": self.radius,
            "use_features": self.use_features,
        }

    @classmethod
    def from_base64(
        cls,
        base64_str: str,
        fp_type: FingerprintType,
        num_bits: int,
        radius: int | None = None,
        use_features: bool = False,
    ) -> "Fingerprint":
        """Reconstruct fingerprint from base64 representation."""
        bytes_data = base64.b64decode(base64_str)
        hex_str = bytes_data.hex()
        # Count on bits from bytes
        num_on_bits = sum(bin(b).count("1") for b in bytes_data)
        return cls(
            fp_type=fp_type,
            num_bits=num_bits,
            num_on_bits=num_on_bits,
            bytes_data=bytes_data,
            base64_str=base64_str,
            hex_str=hex_str,
            radius=radius,
            use_features=use_features,
        )

    def get_on_bits(self) -> list[int]:
        """Get list of bit indices that are set to 1."""
        on_bits = []
        for byte_idx, byte_val in enumerate(self.bytes_data):
            for bit_idx in range(8):
                if byte_val & (1 << bit_idx):
                    global_bit_idx = byte_idx * 8 + bit_idx
                    if global_bit_idx < self.num_bits:
                        on_bits.append(global_bit_idx)
        return sorted(on_bits)


class DescriptorCalculationError(Exception):
    """Error during descriptor calculation."""

    pass


class FingerprintCalculationError(Exception):
    """Error during fingerprint calculation."""

    pass


def _get_mol(mol_or_smiles: "Mol | str") -> "Mol":
    """Convert SMILES to Mol if needed."""
    from rdkit import Chem

    if isinstance(mol_or_smiles, str):
        mol = Chem.MolFromSmiles(mol_or_smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {mol_or_smiles}")
        return mol
    return mol_or_smiles


def calculate_descriptors(mol_or_smiles: "Mol | str") -> MolecularDescriptors:
    """
    Calculate molecular descriptors for a molecule.

    Args:
        mol_or_smiles: RDKit Mol object or SMILES string

    Returns:
        MolecularDescriptors with calculated values

    Raises:
        DescriptorCalculationError: If calculation fails
    """
    try:
        from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors

        mol = _get_mol(mol_or_smiles)

        # Core descriptors
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        tpsa = Descriptors.TPSA(mol)
        hbd = Lipinski.NumHDonors(mol)
        hba = Lipinski.NumHAcceptors(mol)

        # Additional descriptors
        num_rotatable = Lipinski.NumRotatableBonds(mol)
        num_rings = rdMolDescriptors.CalcNumRings(mol)
        num_aromatic = rdMolDescriptors.CalcNumAromaticRings(mol)
        num_heavy = Lipinski.HeavyAtomCount(mol)
        frac_sp3 = rdMolDescriptors.CalcFractionCSP3(mol)

        return MolecularDescriptors(
            molecular_weight=Decimal(str(round(mw, 4))),
            logp=Decimal(str(round(logp, 4))),
            tpsa=Decimal(str(round(tpsa, 4))),
            hbd=hbd,
            hba=hba,
            num_rotatable_bonds=num_rotatable,
            num_rings=num_rings,
            num_aromatic_rings=num_aromatic,
            num_heavy_atoms=num_heavy,
            fraction_sp3=Decimal(str(round(frac_sp3, 4))),
        )
    except ValueError:
        raise
    except Exception as e:
        raise DescriptorCalculationError(f"Failed to calculate descriptors: {e}") from e


def _bitvect_to_bytes(bitvect: "ExplicitBitVect") -> bytes:
    """Convert RDKit bit vector to bytes."""
    num_bits = bitvect.GetNumBits()
    num_bytes = (num_bits + 7) // 8
    result = bytearray(num_bytes)
    for i in range(num_bits):
        if bitvect.GetBit(i):
            result[i // 8] |= 1 << (i % 8)
    return bytes(result)


def calculate_morgan_fingerprint(
    mol_or_smiles: "Mol | str",
    radius: int = 2,
    num_bits: int = 2048,
    use_features: bool = False,
) -> Fingerprint:
    """
    Calculate Morgan (ECFP/FCFP) fingerprint.

    Args:
        mol_or_smiles: RDKit Mol object or SMILES string
        radius: Fingerprint radius (2 = ECFP4, 3 = ECFP6)
        num_bits: Number of bits in fingerprint
        use_features: If True, use feature invariants (FCFP), else atom invariants (ECFP)

    Returns:
        Fingerprint object with multiple representations
    """
    try:
        from rdkit.Chem import AllChem

        mol = _get_mol(mol_or_smiles)

        # Generate fingerprint (deterministic with same parameters)
        fp = AllChem.GetMorganFingerprintAsBitVect(
            mol,
            radius=radius,
            nBits=num_bits,
            useFeatures=use_features,
        )

        bytes_data = _bitvect_to_bytes(fp)
        return Fingerprint(
            fp_type=FingerprintType.MORGAN,
            num_bits=num_bits,
            num_on_bits=fp.GetNumOnBits(),
            bytes_data=bytes_data,
            base64_str=base64.b64encode(bytes_data).decode("ascii"),
            hex_str=bytes_data.hex(),
            radius=radius,
            use_features=use_features,
        )
    except ValueError:
        raise
    except Exception as e:
        raise FingerprintCalculationError(f"Failed to calculate Morgan fingerprint: {e}") from e


def calculate_maccs_fingerprint(mol_or_smiles: "Mol | str") -> Fingerprint:
    """
    Calculate MACCS structural keys fingerprint (166 bits).

    Args:
        mol_or_smiles: RDKit Mol object or SMILES string

    Returns:
        Fingerprint object with multiple representations
    """
    try:
        from rdkit.Chem import MACCSkeys

        mol = _get_mol(mol_or_smiles)

        fp = MACCSkeys.GenMACCSKeys(mol)

        bytes_data = _bitvect_to_bytes(fp)
        return Fingerprint(
            fp_type=FingerprintType.MACCS,
            num_bits=167,  # MACCS has 167 bits (0-166, bit 0 unused)
            num_on_bits=fp.GetNumOnBits(),
            bytes_data=bytes_data,
            base64_str=base64.b64encode(bytes_data).decode("ascii"),
            hex_str=bytes_data.hex(),
        )
    except ValueError:
        raise
    except Exception as e:
        raise FingerprintCalculationError(f"Failed to calculate MACCS fingerprint: {e}") from e


def calculate_rdkit_fingerprint(
    mol_or_smiles: "Mol | str",
    min_path: int = 1,
    max_path: int = 7,
    num_bits: int = 2048,
) -> Fingerprint:
    """
    Calculate RDKit topological fingerprint.

    Args:
        mol_or_smiles: RDKit Mol object or SMILES string
        min_path: Minimum path length
        max_path: Maximum path length
        num_bits: Number of bits in fingerprint

    Returns:
        Fingerprint object with multiple representations
    """
    try:
        from rdkit.Chem import RDKFingerprint

        mol = _get_mol(mol_or_smiles)

        fp = RDKFingerprint(mol, minPath=min_path, maxPath=max_path, fpSize=num_bits)

        bytes_data = _bitvect_to_bytes(fp)
        return Fingerprint(
            fp_type=FingerprintType.RDKIT,
            num_bits=num_bits,
            num_on_bits=fp.GetNumOnBits(),
            bytes_data=bytes_data,
            base64_str=base64.b64encode(bytes_data).decode("ascii"),
            hex_str=bytes_data.hex(),
        )
    except ValueError:
        raise
    except Exception as e:
        raise FingerprintCalculationError(f"Failed to calculate RDKit fingerprint: {e}") from e


def calculate_fingerprint(
    mol_or_smiles: "Mol | str",
    fp_type: FingerprintType = FingerprintType.MORGAN,
    **kwargs,
) -> Fingerprint:
    """
    Calculate fingerprint of specified type.

    Args:
        mol_or_smiles: RDKit Mol object or SMILES string
        fp_type: Type of fingerprint to calculate
        **kwargs: Type-specific parameters (radius, num_bits, etc.)

    Returns:
        Fingerprint object
    """
    if fp_type == FingerprintType.MORGAN:
        return calculate_morgan_fingerprint(mol_or_smiles, **kwargs)
    elif fp_type == FingerprintType.MACCS:
        return calculate_maccs_fingerprint(mol_or_smiles)
    elif fp_type == FingerprintType.RDKIT:
        return calculate_rdkit_fingerprint(mol_or_smiles, **kwargs)
    else:
        raise ValueError(f"Unknown fingerprint type: {fp_type}")


def calculate_all_fingerprints(
    mol_or_smiles: "Mol | str",
    morgan_radius: int = 2,
    morgan_bits: int = 2048,
    rdkit_bits: int = 2048,
) -> dict[FingerprintType, Fingerprint]:
    """
    Calculate all supported fingerprint types for a molecule.

    Args:
        mol_or_smiles: RDKit Mol object or SMILES string
        morgan_radius: Radius for Morgan fingerprint
        morgan_bits: Number of bits for Morgan fingerprint
        rdkit_bits: Number of bits for RDKit fingerprint

    Returns:
        Dictionary mapping fingerprint type to Fingerprint object
    """
    mol = _get_mol(mol_or_smiles)
    return {
        FingerprintType.MORGAN: calculate_morgan_fingerprint(
            mol, radius=morgan_radius, num_bits=morgan_bits
        ),
        FingerprintType.MACCS: calculate_maccs_fingerprint(mol),
        FingerprintType.RDKIT: calculate_rdkit_fingerprint(mol, num_bits=rdkit_bits),
    }
