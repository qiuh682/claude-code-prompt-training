"""
MDL Molfile (MOL/SDF) parsing using RDKit.

Supports:
- MDL MOL format (V2000/V3000)
- SDF files (multiple molecules with properties)
- Property extraction from SDF
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from packages.chemistry.exceptions import ChemistryErrorCode, ParsingError

if TYPE_CHECKING:
    from rdkit.Chem import Mol

# Lazy import for RDKit
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
            "RDKit is required for MOL/SDF parsing. "
            "Install with: pip install rdkit"
        )
    from rdkit import Chem

    return Chem


@dataclass
class ParsedMolfile:
    """Result of MOL/SDF parsing."""

    mol: "Mol"
    name: str | None = None
    properties: dict[str, str] = field(default_factory=dict)
    is_valid: bool = True
    warnings: list[str] | None = None


@dataclass
class SDFRecord:
    """Single record from an SDF file."""

    mol: "Mol"
    index: int
    name: str | None = None
    properties: dict[str, str] = field(default_factory=dict)


class MolfileParser:
    """Parser for MDL MOL and SDF files."""

    def __init__(self, sanitize: bool = True, remove_hs: bool = False):
        """
        Initialize MOL/SDF parser.

        Args:
            sanitize: Whether to sanitize molecules after parsing.
            remove_hs: Whether to remove explicit hydrogens.
        """
        self.sanitize = sanitize
        self.remove_hs = remove_hs
        self._Chem = _get_rdkit()

    def parse_molblock(self, molblock: str) -> ParsedMolfile:
        """
        Parse a MOL block string.

        Args:
            molblock: MDL MOL format string.

        Returns:
            ParsedMolfile with RDKit Mol object.

        Raises:
            ParsingError: If MOL block is invalid.
        """
        if not molblock or not molblock.strip():
            raise ParsingError(
                message="Empty MOL block",
                code=ChemistryErrorCode.EMPTY_INPUT,
            )

        mol = self._Chem.MolFromMolBlock(
            molblock,
            sanitize=self.sanitize,
            removeHs=self.remove_hs,
        )

        if mol is None:
            raise ParsingError(
                message="Invalid MOL block format",
                code=ChemistryErrorCode.INVALID_MOLFILE,
                details={"molblock_length": len(molblock)},
            )

        warnings = []

        if mol.GetNumAtoms() == 0:
            raise ParsingError(
                message="MOL block parsed to empty molecule",
                code=ChemistryErrorCode.INVALID_MOLFILE,
            )

        # Extract name from first line of MOL block
        lines = molblock.strip().split("\n")
        name = lines[0].strip() if lines and lines[0].strip() else None

        # Check for 2D vs 3D coordinates
        conf = mol.GetConformer() if mol.GetNumConformers() > 0 else None
        if conf is not None:
            is_3d = any(
                abs(conf.GetAtomPosition(i).z) > 0.01 for i in range(mol.GetNumAtoms())
            )
            if not is_3d:
                warnings.append("Molecule has 2D coordinates only")

        return ParsedMolfile(
            mol=mol,
            name=name,
            properties={},
            is_valid=True,
            warnings=warnings if warnings else None,
        )

    def parse_sdf_string(self, sdf_content: str) -> list[SDFRecord]:
        """
        Parse an SDF string containing multiple molecules.

        Args:
            sdf_content: SDF format string.

        Returns:
            List of SDFRecord objects.

        Raises:
            ParsingError: If SDF format is invalid.
        """
        if not sdf_content or not sdf_content.strip():
            raise ParsingError(
                message="Empty SDF content",
                code=ChemistryErrorCode.EMPTY_INPUT,
            )

        records = []
        supplier = self._Chem.SDMolSupplier()
        supplier.SetData(sdf_content, sanitize=self.sanitize, removeHs=self.remove_hs)

        for idx, mol in enumerate(supplier):
            if mol is None:
                continue

            # Extract properties
            properties = {}
            for prop_name in mol.GetPropsAsDict():
                try:
                    properties[prop_name] = str(mol.GetProp(prop_name))
                except Exception:
                    pass

            # Get molecule name
            name = mol.GetProp("_Name") if mol.HasProp("_Name") else None

            records.append(
                SDFRecord(
                    mol=mol,
                    index=idx,
                    name=name,
                    properties=properties,
                )
            )

        if not records:
            raise ParsingError(
                message="No valid molecules found in SDF",
                code=ChemistryErrorCode.INVALID_SDF,
            )

        return records

    def parse_sdf_file(self, filepath: str | Path) -> Iterator[SDFRecord]:
        """
        Parse an SDF file, yielding molecules one at a time.

        Args:
            filepath: Path to SDF file.

        Yields:
            SDFRecord for each valid molecule.

        Raises:
            ParsingError: If file cannot be read.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise ParsingError(
                message=f"SDF file not found: {filepath}",
                code=ChemistryErrorCode.INVALID_SDF,
            )

        supplier = self._Chem.SDMolSupplier(
            str(filepath),
            sanitize=self.sanitize,
            removeHs=self.remove_hs,
        )

        for idx, mol in enumerate(supplier):
            if mol is None:
                continue

            properties = {}
            for prop_name in mol.GetPropsAsDict():
                try:
                    properties[prop_name] = str(mol.GetProp(prop_name))
                except Exception:
                    pass

            name = mol.GetProp("_Name") if mol.HasProp("_Name") else None

            yield SDFRecord(
                mol=mol,
                index=idx,
                name=name,
                properties=properties,
            )


def parse_molblock(molblock: str, sanitize: bool = True) -> "Mol":
    """
    Convenience function to parse a MOL block.

    Args:
        molblock: MDL MOL format string.
        sanitize: Whether to sanitize the molecule.

    Returns:
        RDKit Mol object.

    Raises:
        ParsingError: If MOL block is invalid.
    """
    parser = MolfileParser(sanitize=sanitize)
    return parser.parse_molblock(molblock).mol


def parse_sdf(sdf_content: str, sanitize: bool = True) -> list[SDFRecord]:
    """
    Convenience function to parse SDF content.

    Args:
        sdf_content: SDF format string.
        sanitize: Whether to sanitize molecules.

    Returns:
        List of SDFRecord objects.

    Raises:
        ParsingError: If SDF is invalid.
    """
    parser = MolfileParser(sanitize=sanitize)
    return parser.parse_sdf_string(sdf_content)
