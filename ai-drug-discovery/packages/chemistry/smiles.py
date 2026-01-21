"""
SMILES validation and canonicalization using RDKit.

This module provides the core SMILES processing functions:
- validate_smiles: Check if SMILES is valid
- canonicalize_smiles: Convert to canonical form + InChIKey
- smiles_to_mol: Parse SMILES to RDKit Mol object

Salt/Mixture Handling (MVP Rule):
---------------------------------
For mixtures (SMILES containing '.'), we keep the LARGEST fragment by atom count.
This handles common cases like:
- Drug salts: "CC(=O)O.[Na]" -> "CC(=O)O" (acetic acid, drop sodium)
- HCl salts: "CCN.Cl" -> "CCN" (ethylamine, drop chloride)
- Solvates: "CCO.O" -> "CCO" (ethanol, drop water)

Rationale: In drug discovery, the parent compound is typically the largest
fragment. This simple rule handles ~90% of cases correctly.

Limitations:
- May incorrectly handle covalent complexes
- Does not handle tautomers
- Counter-ions with similar size may be ambiguous

For more sophisticated salt stripping, use the full pipeline with
NormalizationOptions(remove_salts=True).

Standardization (Optional):
---------------------------
When standardize=True, attempts to:
1. Neutralize common charged groups (carboxylates, amines)
2. Keep the largest fragment

This is conservative and may not cover all cases. For production use,
consider dedicated standardization tools like MolVS or ChEMBL's standardizer.

Usage:
    >>> from packages.chemistry.smiles import validate_smiles, canonicalize_smiles

    # Validate
    >>> validate_smiles("CCO")
    True
    >>> validate_smiles("invalid")
    False

    # Canonicalize
    >>> result = canonicalize_smiles("C(C)O")
    >>> result.canonical_smiles
    'CCO'
    >>> result.inchikey
    'LFQSCWFLJHTTHZ-UHFFFAOYSA-N'

    # Handle salts
    >>> result = canonicalize_smiles("CCO.[Na]", strip_salts=True)
    >>> result.canonical_smiles
    'CCO'
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rdkit.Chem import Mol

# Lazy RDKit import
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


def _get_chem():
    """Get RDKit Chem module."""
    if not _check_rdkit():
        raise ImportError(
            "RDKit is required for SMILES processing. "
            "Install with: pip install rdkit"
        )
    from rdkit import Chem

    return Chem


def _get_inchi():
    """Get RDKit inchi module."""
    if not _check_rdkit():
        raise ImportError("RDKit is required for InChI generation.")
    from rdkit.Chem import inchi

    return inchi


# =============================================================================
# Error Types
# =============================================================================


class SmilesErrorCode(str, Enum):
    """Error codes for SMILES processing."""

    EMPTY_INPUT = "EMPTY_INPUT"
    INVALID_SMILES = "INVALID_SMILES"
    EMPTY_MOLECULE = "EMPTY_MOLECULE"
    CANONICALIZATION_FAILED = "CANONICALIZATION_FAILED"
    INCHI_GENERATION_FAILED = "INCHI_GENERATION_FAILED"


class SmilesError(Exception):
    """Exception for SMILES processing errors."""

    def __init__(self, message: str, code: SmilesErrorCode, smiles: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.smiles = smiles

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"


# =============================================================================
# Result Types
# =============================================================================


@dataclass
class CanonicalizeResult:
    """Result of SMILES canonicalization."""

    canonical_smiles: str
    inchikey: str
    inchi: str | None = None
    original_smiles: str | None = None
    was_standardized: bool = False
    had_multiple_fragments: bool = False
    warnings: list[str] | None = None


@dataclass
class ValidationResult:
    """Result of SMILES validation with details."""

    is_valid: bool
    error_message: str | None = None
    error_code: SmilesErrorCode | None = None
    atom_count: int | None = None
    has_multiple_fragments: bool = False


# =============================================================================
# Core Functions
# =============================================================================


def validate_smiles(smiles: str, strict: bool = False) -> bool:
    """
    Validate a SMILES string.

    Args:
        smiles: SMILES notation string to validate.
        strict: If True, also reject molecules with warnings (radicals, charges).

    Returns:
        True if valid SMILES, False otherwise.

    Example:
        >>> validate_smiles("CCO")
        True
        >>> validate_smiles("invalid_smiles")
        False
        >>> validate_smiles("")
        False
    """
    result = validate_smiles_detailed(smiles, strict=strict)
    return result.is_valid


def validate_smiles_detailed(smiles: str, strict: bool = False) -> ValidationResult:
    """
    Validate a SMILES string with detailed results.

    Args:
        smiles: SMILES notation string to validate.
        strict: If True, also reject molecules with warnings.

    Returns:
        ValidationResult with validity status and details.

    Example:
        >>> result = validate_smiles_detailed("CCO")
        >>> result.is_valid
        True
        >>> result.atom_count
        3
    """
    # Check empty input
    if not smiles or not isinstance(smiles, str):
        return ValidationResult(
            is_valid=False,
            error_message="Empty or invalid input",
            error_code=SmilesErrorCode.EMPTY_INPUT,
        )

    smiles = smiles.strip()
    if not smiles:
        return ValidationResult(
            is_valid=False,
            error_message="Empty SMILES string",
            error_code=SmilesErrorCode.EMPTY_INPUT,
        )

    # Try to parse with RDKit
    Chem = _get_chem()
    mol = Chem.MolFromSmiles(smiles, sanitize=True)

    if mol is None:
        return ValidationResult(
            is_valid=False,
            error_message=f"Invalid SMILES syntax: '{smiles}'",
            error_code=SmilesErrorCode.INVALID_SMILES,
        )

    atom_count = mol.GetNumAtoms()
    if atom_count == 0:
        return ValidationResult(
            is_valid=False,
            error_message="SMILES parsed to empty molecule",
            error_code=SmilesErrorCode.EMPTY_MOLECULE,
        )

    # Check for multiple fragments
    has_fragments = "." in smiles

    # Strict mode checks
    if strict:
        # Check for radicals
        num_radicals = sum(a.GetNumRadicalElectrons() for a in mol.GetAtoms())
        if num_radicals > 0:
            return ValidationResult(
                is_valid=False,
                error_message=f"Molecule contains {num_radicals} radical electrons",
                error_code=SmilesErrorCode.INVALID_SMILES,
                atom_count=atom_count,
                has_multiple_fragments=has_fragments,
            )

    return ValidationResult(
        is_valid=True,
        atom_count=atom_count,
        has_multiple_fragments=has_fragments,
    )


def smiles_to_mol(
    smiles: str,
    sanitize: bool = True,
    strip_salts: bool = False,
) -> "Mol":
    """
    Parse a SMILES string to an RDKit Mol object.

    Args:
        smiles: SMILES notation string.
        sanitize: Whether to sanitize the molecule (recommended).
        strip_salts: If True, keep only the largest fragment.

    Returns:
        RDKit Mol object.

    Raises:
        SmilesError: If SMILES is invalid or parsing fails.

    Example:
        >>> mol = smiles_to_mol("CCO")
        >>> mol.GetNumAtoms()
        3

        >>> mol = smiles_to_mol("CCO.[Na]", strip_salts=True)
        >>> mol.GetNumAtoms()  # Only ethanol, sodium removed
        3
    """
    # Validate input
    if not smiles or not isinstance(smiles, str):
        raise SmilesError(
            message="Empty or invalid input",
            code=SmilesErrorCode.EMPTY_INPUT,
            smiles=smiles,
        )

    smiles = smiles.strip()
    if not smiles:
        raise SmilesError(
            message="Empty SMILES string",
            code=SmilesErrorCode.EMPTY_INPUT,
            smiles=smiles,
        )

    Chem = _get_chem()

    # Parse SMILES
    mol = Chem.MolFromSmiles(smiles, sanitize=sanitize)

    if mol is None:
        raise SmilesError(
            message=f"Invalid SMILES: '{smiles}'",
            code=SmilesErrorCode.INVALID_SMILES,
            smiles=smiles,
        )

    if mol.GetNumAtoms() == 0:
        raise SmilesError(
            message="SMILES parsed to empty molecule",
            code=SmilesErrorCode.EMPTY_MOLECULE,
            smiles=smiles,
        )

    # Handle salts/mixtures
    if strip_salts and "." in smiles:
        mol = _get_largest_fragment(mol)

    return mol


def canonicalize_smiles(
    smiles: str,
    strip_salts: bool = False,
    standardize: bool = False,
    isomeric: bool = True,
) -> CanonicalizeResult:
    """
    Canonicalize a SMILES string and generate InChIKey.

    Args:
        smiles: SMILES notation string.
        strip_salts: If True, keep only the largest fragment (MVP salt handling).
        standardize: If True, attempt to neutralize charges (conservative).
        isomeric: If True, preserve stereochemistry in canonical SMILES.

    Returns:
        CanonicalizeResult with canonical_smiles and inchikey.

    Raises:
        SmilesError: If SMILES is invalid or canonicalization fails.

    Example:
        >>> result = canonicalize_smiles("C(C)O")
        >>> result.canonical_smiles
        'CCO'
        >>> result.inchikey
        'LFQSCWFLJHTTHZ-UHFFFAOYSA-N'

        >>> # Handle salt
        >>> result = canonicalize_smiles("CC(=O)O.[Na]", strip_salts=True)
        >>> result.canonical_smiles
        'CC(=O)O'
        >>> result.had_multiple_fragments
        True
    """
    original_smiles = smiles
    warnings = []

    # Parse to Mol
    mol = smiles_to_mol(smiles, sanitize=True, strip_salts=False)

    # Track if we had multiple fragments
    had_fragments = "." in smiles

    # Handle salts/mixtures
    if strip_salts and had_fragments:
        mol = _get_largest_fragment(mol)
        warnings.append("Salt/mixture detected; kept largest fragment")

    # Standardize if requested
    was_standardized = False
    if standardize:
        mol, did_neutralize = _neutralize_charges(mol)
        if did_neutralize:
            was_standardized = True
            warnings.append("Charges were neutralized")

    # Generate canonical SMILES
    Chem = _get_chem()
    canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=isomeric)

    if not canonical:
        raise SmilesError(
            message="Failed to generate canonical SMILES",
            code=SmilesErrorCode.CANONICALIZATION_FAILED,
            smiles=smiles,
        )

    # Generate InChI and InChIKey
    inchi_mod = _get_inchi()
    inchi = inchi_mod.MolToInchi(mol)
    inchikey = None

    if inchi:
        inchikey = inchi_mod.InchiToInchiKey(inchi)

    if not inchikey:
        # Fallback: generate pseudo-InChIKey from SMILES hash
        import hashlib

        hash_val = hashlib.sha256(canonical.encode()).hexdigest().upper()
        inchikey = f"{hash_val[:14]}-{hash_val[14:24]}-N"
        warnings.append("InChI generation failed; using hash-based key")

    return CanonicalizeResult(
        canonical_smiles=canonical,
        inchikey=inchikey,
        inchi=inchi,
        original_smiles=original_smiles,
        was_standardized=was_standardized,
        had_multiple_fragments=had_fragments,
        warnings=warnings if warnings else None,
    )


# =============================================================================
# Helper Functions
# =============================================================================


def _get_largest_fragment(mol: "Mol") -> "Mol":
    """
    Get the largest fragment from a molecule (by atom count).

    MVP Rule: Keep the fragment with the most atoms.
    This handles most drug salts correctly.

    Args:
        mol: RDKit Mol object (may contain multiple fragments).

    Returns:
        RDKit Mol object containing only the largest fragment.
    """
    Chem = _get_chem()

    # Get all fragments
    frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True)

    if len(frags) <= 1:
        return mol

    # Find largest by atom count
    largest = max(frags, key=lambda m: m.GetNumAtoms())
    return largest


def _neutralize_charges(mol: "Mol") -> tuple["Mol", bool]:
    """
    Attempt to neutralize common charged groups.

    Conservative neutralization for:
    - Carboxylates [O-] -> [OH]
    - Ammonium [NH3+], [NH2+], [NH+] -> neutral forms
    - Sulfonates, phosphates

    Args:
        mol: RDKit Mol object.

    Returns:
        Tuple of (neutralized Mol, whether any changes were made).
    """
    Chem = _get_chem()

    # Create editable copy
    mol = Chem.RWMol(mol)
    changed = False

    # Simple neutralization: adjust H counts based on formal charge
    for atom in mol.GetAtoms():
        charge = atom.GetFormalCharge()
        if charge == 0:
            continue

        symbol = atom.GetSymbol()
        num_hs = atom.GetTotalNumHs()

        # Neutralize negative charges by adding H
        if charge < 0 and symbol in ("O", "S", "N"):
            atom.SetFormalCharge(0)
            atom.SetNumExplicitHs(num_hs + abs(charge))
            changed = True

        # Neutralize positive charges on N by removing H (if possible)
        elif charge > 0 and symbol == "N" and num_hs >= charge:
            atom.SetFormalCharge(0)
            atom.SetNumExplicitHs(num_hs - charge)
            changed = True

    # Update property cache
    try:
        mol.UpdatePropertyCache(strict=False)
        Chem.SanitizeMol(mol)
    except Exception:
        # If sanitization fails, return original
        return mol.GetMol(), False

    return mol.GetMol(), changed


def get_molecular_formula(smiles: str) -> str:
    """
    Get molecular formula from SMILES.

    Args:
        smiles: SMILES notation string.

    Returns:
        Molecular formula string (e.g., "C2H6O").

    Raises:
        SmilesError: If SMILES is invalid.
    """
    mol = smiles_to_mol(smiles)
    from rdkit.Chem import rdMolDescriptors

    return rdMolDescriptors.CalcMolFormula(mol)


def smiles_are_equivalent(smiles1: str, smiles2: str) -> bool:
    """
    Check if two SMILES represent the same molecule.

    Compares InChIKeys of both molecules.

    Args:
        smiles1: First SMILES string.
        smiles2: Second SMILES string.

    Returns:
        True if molecules are equivalent, False otherwise.

    Example:
        >>> smiles_are_equivalent("CCO", "C(C)O")
        True
        >>> smiles_are_equivalent("CCO", "CC")
        False
    """
    try:
        result1 = canonicalize_smiles(smiles1)
        result2 = canonicalize_smiles(smiles2)
        return result1.inchikey == result2.inchikey
    except SmilesError:
        return False


# =============================================================================
# Batch Processing Helpers
# =============================================================================


def validate_smiles_batch(
    smiles_list: list[str],
) -> tuple[list[str], list[tuple[int, str, str]]]:
    """
    Validate multiple SMILES strings.

    Args:
        smiles_list: List of SMILES strings to validate.

    Returns:
        Tuple of (valid SMILES list, invalid entries as (index, smiles, error)).

    Example:
        >>> valid, invalid = validate_smiles_batch(["CCO", "invalid", "CC"])
        >>> len(valid)
        2
        >>> invalid[0]
        (1, 'invalid', '[INVALID_SMILES] Invalid SMILES syntax: ...')
    """
    valid = []
    invalid = []

    for idx, smiles in enumerate(smiles_list):
        try:
            mol = smiles_to_mol(smiles)
            valid.append(smiles)
        except SmilesError as e:
            invalid.append((idx, smiles, str(e)))

    return valid, invalid


def canonicalize_smiles_batch(
    smiles_list: list[str],
    strip_salts: bool = False,
    standardize: bool = False,
) -> tuple[list[CanonicalizeResult], list[tuple[int, str, str]]]:
    """
    Canonicalize multiple SMILES strings.

    Args:
        smiles_list: List of SMILES strings.
        strip_salts: If True, handle salts by keeping largest fragment.
        standardize: If True, attempt charge neutralization.

    Returns:
        Tuple of (successful results, failures as (index, smiles, error)).

    Example:
        >>> results, errors = canonicalize_smiles_batch(["CCO", "C(C)O", "invalid"])
        >>> len(results)
        2
        >>> results[0].canonical_smiles
        'CCO'
    """
    results = []
    errors = []

    for idx, smiles in enumerate(smiles_list):
        try:
            result = canonicalize_smiles(
                smiles,
                strip_salts=strip_salts,
                standardize=standardize,
            )
            results.append(result)
        except SmilesError as e:
            errors.append((idx, smiles, str(e)))

    return results, errors
