"""
SMILES string parsing and validation using RDKit.

Provides:
- SMILES validation
- SMILES to RDKit Mol conversion
- Error handling with detailed messages
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

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
    """Get RDKit Chem module or raise ImportError."""
    if not _check_rdkit():
        raise ImportError(
            "RDKit is required for SMILES parsing. "
            "Install with: pip install rdkit"
        )
    from rdkit import Chem

    return Chem


@dataclass
class ParsedSmiles:
    """Result of SMILES parsing."""

    mol: "Mol"
    original_smiles: str
    is_valid: bool = True
    warnings: list[str] | None = None


class SmilesParser:
    """Parser for SMILES strings using RDKit."""

    def __init__(self, sanitize: bool = True, strict: bool = False):
        """
        Initialize SMILES parser.

        Args:
            sanitize: Whether to sanitize molecules after parsing.
            strict: If True, raise errors for any warnings.
        """
        self.sanitize = sanitize
        self.strict = strict
        self._Chem = _get_rdkit()

    def parse(self, smiles: str) -> ParsedSmiles:
        """
        Parse a SMILES string into an RDKit Mol object.

        Args:
            smiles: SMILES notation string.

        Returns:
            ParsedSmiles with RDKit Mol object.

        Raises:
            ParsingError: If SMILES is invalid.
        """
        if not smiles or not smiles.strip():
            raise ParsingError(
                message="Empty SMILES string",
                code=ChemistryErrorCode.EMPTY_INPUT,
            )

        smiles = smiles.strip()

        # Attempt to parse SMILES
        mol = self._Chem.MolFromSmiles(smiles, sanitize=self.sanitize)

        if mol is None:
            raise ParsingError(
                message=f"Invalid SMILES: '{smiles}'",
                code=ChemistryErrorCode.INVALID_SMILES,
                details={"smiles": smiles},
            )

        warnings = []

        # Check for potential issues
        if mol.GetNumAtoms() == 0:
            raise ParsingError(
                message="SMILES parsed to empty molecule",
                code=ChemistryErrorCode.INVALID_SMILES,
                details={"smiles": smiles},
            )

        # Check for charged species without counter-ions (warning)
        net_charge = sum(atom.GetFormalCharge() for atom in mol.GetAtoms())
        if abs(net_charge) > 0:
            warnings.append(f"Molecule has net charge of {net_charge}")

        # Check for radicals (warning)
        num_radical = sum(atom.GetNumRadicalElectrons() for atom in mol.GetAtoms())
        if num_radical > 0:
            warnings.append(f"Molecule contains {num_radical} radical electrons")

        if self.strict and warnings:
            raise ParsingError(
                message=f"SMILES parsing warnings: {'; '.join(warnings)}",
                code=ChemistryErrorCode.INVALID_SMILES,
                details={"smiles": smiles, "warnings": warnings},
            )

        return ParsedSmiles(
            mol=mol,
            original_smiles=smiles,
            is_valid=True,
            warnings=warnings if warnings else None,
        )

    def validate(self, smiles: str) -> bool:
        """
        Check if a SMILES string is valid without full parsing.

        Args:
            smiles: SMILES notation string.

        Returns:
            True if valid, False otherwise.
        """
        if not smiles or not smiles.strip():
            return False

        mol = self._Chem.MolFromSmiles(smiles.strip(), sanitize=False)
        return mol is not None and mol.GetNumAtoms() > 0

    def parse_batch(
        self, smiles_list: list[str]
    ) -> tuple[list[ParsedSmiles], list[tuple[int, str, str]]]:
        """
        Parse multiple SMILES strings.

        Args:
            smiles_list: List of SMILES strings.

        Returns:
            Tuple of (successful parses, failures as (index, smiles, error)).
        """
        successes = []
        failures = []

        for idx, smiles in enumerate(smiles_list):
            try:
                parsed = self.parse(smiles)
                successes.append(parsed)
            except ParsingError as e:
                failures.append((idx, smiles, e.message))

        return successes, failures


def parse_smiles(smiles: str, sanitize: bool = True) -> "Mol":
    """
    Convenience function to parse a SMILES string.

    Args:
        smiles: SMILES notation string.
        sanitize: Whether to sanitize the molecule.

    Returns:
        RDKit Mol object.

    Raises:
        ParsingError: If SMILES is invalid.
    """
    parser = SmilesParser(sanitize=sanitize)
    return parser.parse(smiles).mol


def validate_smiles_rdkit(smiles: str) -> bool:
    """
    Validate a SMILES string using RDKit.

    Args:
        smiles: SMILES notation string.

    Returns:
        True if valid, False otherwise.
    """
    if not _check_rdkit():
        # Fallback to basic validation if RDKit not available
        return bool(smiles and smiles.strip())

    Chem = _get_rdkit()
    if not smiles or not smiles.strip():
        return False

    mol = Chem.MolFromSmiles(smiles.strip(), sanitize=False)
    return mol is not None and mol.GetNumAtoms() > 0
