"""
Molecular property computation using RDKit.

Provides:
- Molecular descriptors (MW, LogP, TPSA, HBD, HBA, etc.)
- Fingerprints (Morgan, MACCS, RDKit, etc.)
- 2D structure rendering (SVG, PNG)
"""

from decimal import Decimal
from typing import TYPE_CHECKING

from packages.chemistry.exceptions import ChemistryErrorCode, ComputationError
from packages.chemistry.schemas import (
    FingerprintData,
    FingerprintType,
    MolecularDescriptors,
)

if TYPE_CHECKING:
    from rdkit.Chem import Mol

# Lazy imports for RDKit modules
_rdkit_available: bool | None = None


def _check_rdkit() -> bool:
    """Check if RDKit is available."""
    global _rdkit_available
    if _rdkit_available is None:
        try:
            from rdkit import Chem  # noqa: F401

            _rdkit_available = True
        except ImportError:
            _rdkit_available = False
    return _rdkit_available


def _get_rdkit():
    """Get RDKit Chem module."""
    if not _check_rdkit():
        raise ImportError(
            "RDKit is required for molecular computation. "
            "Install with: pip install rdkit"
        )
    from rdkit import Chem

    return Chem


def _get_descriptors():
    """Get RDKit Descriptors module."""
    if not _check_rdkit():
        raise ImportError("RDKit is required for descriptor calculation.")
    from rdkit.Chem import Descriptors

    return Descriptors


def _get_lipinski():
    """Get RDKit Lipinski module."""
    if not _check_rdkit():
        raise ImportError("RDKit is required for Lipinski calculations.")
    from rdkit.Chem import Lipinski

    return Lipinski


def _get_rdmolfp():
    """Get RDKit fingerprint generators."""
    if not _check_rdkit():
        raise ImportError("RDKit is required for fingerprint calculation.")
    from rdkit.Chem import AllChem, MACCSkeys, rdMolDescriptors

    return AllChem, MACCSkeys, rdMolDescriptors


def _get_draw():
    """Get RDKit Draw module."""
    if not _check_rdkit():
        raise ImportError("RDKit is required for 2D rendering.")
    from rdkit.Chem import Draw

    return Draw


class DescriptorCalculator:
    """Calculator for molecular descriptors."""

    def __init__(self):
        """Initialize descriptor calculator."""
        self._Descriptors = _get_descriptors()
        self._Lipinski = _get_lipinski()
        self._Chem = _get_rdkit()

    def calculate(self, mol: "Mol") -> MolecularDescriptors:
        """
        Calculate molecular descriptors.

        Args:
            mol: RDKit Mol object.

        Returns:
            MolecularDescriptors with computed values.

        Raises:
            ComputationError: If calculation fails.
        """
        if mol is None:
            raise ComputationError(
                message="Cannot calculate descriptors for None molecule",
                code=ChemistryErrorCode.DESCRIPTOR_CALCULATION_FAILED,
            )

        try:
            # Basic properties
            mw = self._Descriptors.MolWt(mol)
            exact_mass = self._Descriptors.ExactMolWt(mol)
            formula = self._Chem.rdMolDescriptors.CalcMolFormula(mol)

            # Lipinski descriptors
            logp = self._Descriptors.MolLogP(mol)
            hbd = self._Lipinski.NumHDonors(mol)
            hba = self._Lipinski.NumHAcceptors(mol)
            tpsa = self._Descriptors.TPSA(mol)
            rotatable = self._Lipinski.NumRotatableBonds(mol)

            # Additional descriptors
            num_atoms = mol.GetNumAtoms()
            num_heavy = self._Lipinski.HeavyAtomCount(mol)
            num_rings = self._Chem.rdMolDescriptors.CalcNumRings(mol)
            num_aromatic = self._Chem.rdMolDescriptors.CalcNumAromaticRings(mol)
            fsp3 = self._Chem.rdMolDescriptors.CalcFractionCSP3(mol)

            return MolecularDescriptors(
                molecular_weight=Decimal(str(round(mw, 4))),
                exact_mass=Decimal(str(round(exact_mass, 6))),
                molecular_formula=formula,
                logp=Decimal(str(round(logp, 3))),
                hbd=hbd,
                hba=hba,
                tpsa=Decimal(str(round(tpsa, 2))),
                rotatable_bonds=rotatable,
                num_atoms=num_atoms,
                num_heavy_atoms=num_heavy,
                num_rings=num_rings,
                num_aromatic_rings=num_aromatic,
                fraction_sp3=Decimal(str(round(fsp3, 3))),
            )

        except Exception as e:
            raise ComputationError(
                message=f"Descriptor calculation failed: {e}",
                code=ChemistryErrorCode.DESCRIPTOR_CALCULATION_FAILED,
                details={"error": str(e)},
            )


class FingerprintCalculator:
    """Calculator for molecular fingerprints."""

    def __init__(self):
        """Initialize fingerprint calculator."""
        self._AllChem, self._MACCSkeys, self._rdMolDescriptors = _get_rdmolfp()
        self._Chem = _get_rdkit()

    def calculate(
        self,
        mol: "Mol",
        fp_type: FingerprintType,
        **kwargs,
    ) -> FingerprintData:
        """
        Calculate a fingerprint for a molecule.

        Args:
            mol: RDKit Mol object.
            fp_type: Type of fingerprint to calculate.
            **kwargs: Additional parameters for fingerprint generation.

        Returns:
            FingerprintData with computed fingerprint.

        Raises:
            ComputationError: If calculation fails.
        """
        if mol is None:
            raise ComputationError(
                message="Cannot calculate fingerprint for None molecule",
                code=ChemistryErrorCode.FINGERPRINT_CALCULATION_FAILED,
            )

        try:
            if fp_type == FingerprintType.MORGAN:
                return self._calculate_morgan(mol, **kwargs)
            elif fp_type == FingerprintType.MACCS:
                return self._calculate_maccs(mol)
            elif fp_type == FingerprintType.RDKIT:
                return self._calculate_rdkit_fp(mol, **kwargs)
            elif fp_type == FingerprintType.ATOM_PAIR:
                return self._calculate_atom_pair(mol, **kwargs)
            elif fp_type == FingerprintType.TORSION:
                return self._calculate_torsion(mol, **kwargs)
            else:
                raise ComputationError(
                    message=f"Unsupported fingerprint type: {fp_type}",
                    code=ChemistryErrorCode.FINGERPRINT_CALCULATION_FAILED,
                )
        except ComputationError:
            raise
        except Exception as e:
            raise ComputationError(
                message=f"Fingerprint calculation failed: {e}",
                code=ChemistryErrorCode.FINGERPRINT_CALCULATION_FAILED,
                details={"fp_type": fp_type.value, "error": str(e)},
            )

    def _calculate_morgan(
        self,
        mol: "Mol",
        radius: int = 2,
        n_bits: int = 2048,
    ) -> FingerprintData:
        """Calculate Morgan (circular) fingerprint."""
        from rdkit import DataStructs

        fp = self._AllChem.GetMorganFingerprintAsBitVect(
            mol, radius=radius, nBits=n_bits
        )

        # Convert to bytes
        arr = bytearray(n_bits // 8)
        DataStructs.ConvertToNumpyArray(fp, arr)
        bits_bytes = bytes(arr)

        # Get on bits
        on_bits = list(fp.GetOnBits())

        return FingerprintData(
            fingerprint_type=FingerprintType.MORGAN,
            bit_length=n_bits,
            bits=bits_bytes,
            on_bits=on_bits,
            num_on_bits=len(on_bits),
        )

    def _calculate_maccs(self, mol: "Mol") -> FingerprintData:
        """Calculate MACCS keys fingerprint."""
        from rdkit import DataStructs

        fp = self._MACCSkeys.GenMACCSKeys(mol)

        # MACCS has 167 bits (0-166)
        n_bits = 167
        arr = bytearray((n_bits + 7) // 8)
        DataStructs.ConvertToNumpyArray(fp, arr)
        bits_bytes = bytes(arr)

        on_bits = list(fp.GetOnBits())

        return FingerprintData(
            fingerprint_type=FingerprintType.MACCS,
            bit_length=n_bits,
            bits=bits_bytes,
            on_bits=on_bits,
            num_on_bits=len(on_bits),
        )

    def _calculate_rdkit_fp(
        self,
        mol: "Mol",
        min_path: int = 1,
        max_path: int = 7,
        n_bits: int = 2048,
    ) -> FingerprintData:
        """Calculate RDKit topological fingerprint."""
        from rdkit import DataStructs

        fp = self._Chem.RDKFingerprint(
            mol, minPath=min_path, maxPath=max_path, fpSize=n_bits
        )

        arr = bytearray(n_bits // 8)
        DataStructs.ConvertToNumpyArray(fp, arr)
        bits_bytes = bytes(arr)

        on_bits = list(fp.GetOnBits())

        return FingerprintData(
            fingerprint_type=FingerprintType.RDKIT,
            bit_length=n_bits,
            bits=bits_bytes,
            on_bits=on_bits,
            num_on_bits=len(on_bits),
        )

    def _calculate_atom_pair(
        self,
        mol: "Mol",
        n_bits: int = 2048,
    ) -> FingerprintData:
        """Calculate atom pair fingerprint."""
        from rdkit import DataStructs

        fp = self._rdMolDescriptors.GetHashedAtomPairFingerprintAsBitVect(
            mol, nBits=n_bits
        )

        arr = bytearray(n_bits // 8)
        DataStructs.ConvertToNumpyArray(fp, arr)
        bits_bytes = bytes(arr)

        on_bits = list(fp.GetOnBits())

        return FingerprintData(
            fingerprint_type=FingerprintType.ATOM_PAIR,
            bit_length=n_bits,
            bits=bits_bytes,
            on_bits=on_bits,
            num_on_bits=len(on_bits),
        )

    def _calculate_torsion(
        self,
        mol: "Mol",
        n_bits: int = 2048,
    ) -> FingerprintData:
        """Calculate topological torsion fingerprint."""
        from rdkit import DataStructs

        fp = self._rdMolDescriptors.GetHashedTopologicalTorsionFingerprintAsBitVect(
            mol, nBits=n_bits
        )

        arr = bytearray(n_bits // 8)
        DataStructs.ConvertToNumpyArray(fp, arr)
        bits_bytes = bytes(arr)

        on_bits = list(fp.GetOnBits())

        return FingerprintData(
            fingerprint_type=FingerprintType.TORSION,
            bit_length=n_bits,
            bits=bits_bytes,
            on_bits=on_bits,
            num_on_bits=len(on_bits),
        )

    def calculate_multiple(
        self,
        mol: "Mol",
        fp_types: list[FingerprintType],
    ) -> dict[FingerprintType, FingerprintData]:
        """
        Calculate multiple fingerprints for a molecule.

        Args:
            mol: RDKit Mol object.
            fp_types: List of fingerprint types to calculate.

        Returns:
            Dict mapping fingerprint type to data.
        """
        results = {}
        for fp_type in fp_types:
            try:
                results[fp_type] = self.calculate(mol, fp_type)
            except ComputationError:
                # Skip failed fingerprints
                pass
        return results


class MoleculeRenderer:
    """2D structure renderer for molecules."""

    def __init__(
        self,
        width: int = 300,
        height: int = 300,
    ):
        """
        Initialize renderer.

        Args:
            width: Image width in pixels.
            height: Image height in pixels.
        """
        self.width = width
        self.height = height
        self._Draw = _get_draw()
        self._Chem = _get_rdkit()

    def render_svg(self, mol: "Mol") -> str:
        """
        Render molecule as SVG.

        Args:
            mol: RDKit Mol object.

        Returns:
            SVG string.

        Raises:
            ComputationError: If rendering fails.
        """
        if mol is None:
            raise ComputationError(
                message="Cannot render None molecule",
                code=ChemistryErrorCode.RENDERING_FAILED,
            )

        try:
            # Generate 2D coordinates if needed
            if mol.GetNumConformers() == 0:
                from rdkit.Chem import AllChem

                AllChem.Compute2DCoords(mol)

            # Create SVG drawer
            drawer = self._Draw.MolDraw2DSVG(self.width, self.height)
            drawer.DrawMolecule(mol)
            drawer.FinishDrawing()

            return drawer.GetDrawingText()

        except Exception as e:
            raise ComputationError(
                message=f"SVG rendering failed: {e}",
                code=ChemistryErrorCode.RENDERING_FAILED,
                details={"error": str(e)},
            )

    def render_png(self, mol: "Mol") -> bytes:
        """
        Render molecule as PNG.

        Args:
            mol: RDKit Mol object.

        Returns:
            PNG image as bytes.

        Raises:
            ComputationError: If rendering fails.
        """
        if mol is None:
            raise ComputationError(
                message="Cannot render None molecule",
                code=ChemistryErrorCode.RENDERING_FAILED,
            )

        try:
            # Generate 2D coordinates if needed
            if mol.GetNumConformers() == 0:
                from rdkit.Chem import AllChem

                AllChem.Compute2DCoords(mol)

            # Create PNG
            img = self._Draw.MolToImage(mol, size=(self.width, self.height))

            # Convert to bytes
            import io

            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()

        except Exception as e:
            raise ComputationError(
                message=f"PNG rendering failed: {e}",
                code=ChemistryErrorCode.RENDERING_FAILED,
                details={"error": str(e)},
            )


# Convenience functions


def calculate_descriptors(mol: "Mol") -> MolecularDescriptors:
    """
    Calculate molecular descriptors.

    Args:
        mol: RDKit Mol object.

    Returns:
        MolecularDescriptors.
    """
    calculator = DescriptorCalculator()
    return calculator.calculate(mol)


def calculate_fingerprint(
    mol: "Mol",
    fp_type: FingerprintType = FingerprintType.MORGAN,
    **kwargs,
) -> FingerprintData:
    """
    Calculate a molecular fingerprint.

    Args:
        mol: RDKit Mol object.
        fp_type: Fingerprint type.
        **kwargs: Additional fingerprint parameters.

    Returns:
        FingerprintData.
    """
    calculator = FingerprintCalculator()
    return calculator.calculate(mol, fp_type, **kwargs)


def calculate_fingerprints(
    mol: "Mol",
    fp_types: list[FingerprintType] | None = None,
) -> dict[FingerprintType, FingerprintData]:
    """
    Calculate multiple fingerprints.

    Args:
        mol: RDKit Mol object.
        fp_types: List of fingerprint types (default: Morgan and MACCS).

    Returns:
        Dict of fingerprint type to data.
    """
    if fp_types is None:
        fp_types = [FingerprintType.MORGAN, FingerprintType.MACCS]

    calculator = FingerprintCalculator()
    return calculator.calculate_multiple(mol, fp_types)


def render_molecule_svg(mol: "Mol", width: int = 300, height: int = 300) -> str:
    """
    Render molecule as SVG.

    Args:
        mol: RDKit Mol object.
        width: Image width.
        height: Image height.

    Returns:
        SVG string.
    """
    renderer = MoleculeRenderer(width=width, height=height)
    return renderer.render_svg(mol)


def render_molecule_png(mol: "Mol", width: int = 300, height: int = 300) -> bytes:
    """
    Render molecule as PNG.

    Args:
        mol: RDKit Mol object.
        width: Image width.
        height: Image height.

    Returns:
        PNG bytes.
    """
    renderer = MoleculeRenderer(width=width, height=height)
    return renderer.render_png(mol)
