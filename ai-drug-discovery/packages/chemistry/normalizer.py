"""
Molecular normalization and canonicalization.

Provides:
- SMILES canonicalization
- InChI/InChIKey generation
- Standardization (salt stripping, charge neutralization)
- SMILES hash generation for fast lookup
"""

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from packages.chemistry.exceptions import ChemistryErrorCode, NormalizationError
from packages.chemistry.schemas import MoleculeIdentifiers

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
            "RDKit is required for normalization. "
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


@dataclass
class NormalizationOptions:
    """Options for molecule normalization."""

    # Canonicalization
    canonical: bool = True
    isomeric: bool = True  # Include stereochemistry

    # Standardization
    remove_salts: bool = False
    neutralize_charges: bool = False
    remove_stereo: bool = False

    # Output
    generate_inchi: bool = True
    generate_smiles_hash: bool = True


class MoleculeNormalizer:
    """Normalizer for molecular structures."""

    def __init__(self, options: NormalizationOptions | None = None):
        """
        Initialize normalizer.

        Args:
            options: Normalization options.
        """
        self.options = options or NormalizationOptions()
        self._Chem = _get_rdkit()
        self._inchi = _get_inchi()

    def normalize(self, mol: "Mol") -> tuple["Mol", MoleculeIdentifiers]:
        """
        Normalize a molecule and generate identifiers.

        Args:
            mol: RDKit Mol object.

        Returns:
            Tuple of (normalized Mol, MoleculeIdentifiers).

        Raises:
            NormalizationError: If normalization fails.
        """
        if mol is None:
            raise NormalizationError(
                message="Cannot normalize None molecule",
                code=ChemistryErrorCode.CANONICALIZATION_FAILED,
            )

        try:
            # Create a copy to avoid modifying original
            mol = self._Chem.RWMol(mol)

            # Apply standardization if requested
            if self.options.remove_salts:
                mol = self._remove_salts(mol)

            if self.options.neutralize_charges:
                mol = self._neutralize(mol)

            if self.options.remove_stereo:
                self._Chem.RemoveStereochemistry(mol)

            # Convert back to Mol
            mol = mol.GetMol()

            # Generate canonical SMILES
            canonical_smiles = self._Chem.MolToSmiles(
                mol,
                canonical=self.options.canonical,
                isomericSmiles=self.options.isomeric and not self.options.remove_stereo,
            )

            if not canonical_smiles:
                raise NormalizationError(
                    message="Failed to generate canonical SMILES",
                    code=ChemistryErrorCode.CANONICALIZATION_FAILED,
                )

            # Generate InChI and InChIKey
            inchi = None
            inchi_key = None

            if self.options.generate_inchi:
                inchi = self._inchi.MolToInchi(mol)
                if inchi:
                    inchi_key = self._inchi.InchiToInchiKey(inchi)

            if not inchi_key:
                # Fallback: use hash of canonical SMILES as pseudo-InChIKey
                inchi_key = self._generate_pseudo_inchikey(canonical_smiles)

            # Generate SMILES hash
            smiles_hash = ""
            if self.options.generate_smiles_hash:
                smiles_hash = self._generate_smiles_hash(canonical_smiles)

            identifiers = MoleculeIdentifiers(
                canonical_smiles=canonical_smiles,
                inchi=inchi,
                inchi_key=inchi_key,
                smiles_hash=smiles_hash,
            )

            return mol, identifiers

        except NormalizationError:
            raise
        except Exception as e:
            raise NormalizationError(
                message=f"Normalization failed: {e}",
                code=ChemistryErrorCode.CANONICALIZATION_FAILED,
                details={"error": str(e)},
            )

    def _remove_salts(self, mol: "Mol") -> "Mol":
        """Remove salt fragments, keeping largest fragment."""
        try:
            from rdkit.Chem.SaltRemover import SaltRemover

            remover = SaltRemover()
            mol = remover.StripMol(mol, dontRemoveEverything=True)
            return mol
        except Exception:
            # If salt removal fails, return original
            return mol

    def _neutralize(self, mol: "Mol") -> "Mol":
        """Neutralize charges where possible."""
        try:
            # Common neutralization patterns
            patterns = [
                # Carboxylic acids
                ("[O-:1]", "[OH:1]"),
                # Amines
                ("[N+:1]([H])([H])([H])", "[N:1]([H])([H])"),
                ("[n+:1]([H])", "[nH:1]"),
                # Sulfonates
                ("[S-:1]", "[SH:1]"),
            ]

            for reactant, product in patterns:
                rxn_smarts = f"[{reactant}>>{product}]"
                try:
                    # Simple charge neutralization by modifying atoms directly
                    for atom in mol.GetAtoms():
                        charge = atom.GetFormalCharge()
                        if charge != 0:
                            # Try to neutralize
                            num_hs = atom.GetTotalNumHs()
                            if charge < 0 and num_hs >= 0:
                                # Add H to neutralize negative
                                atom.SetFormalCharge(0)
                                atom.SetNumExplicitHs(num_hs + abs(charge))
                            elif charge > 0 and num_hs > 0:
                                # Remove H to neutralize positive
                                new_hs = max(0, num_hs - charge)
                                atom.SetFormalCharge(0)
                                atom.SetNumExplicitHs(new_hs)
                except Exception:
                    pass

            return mol
        except Exception:
            return mol

    def _generate_smiles_hash(self, smiles: str) -> str:
        """Generate SHA-256 hash of SMILES for fast lookup."""
        return hashlib.sha256(smiles.encode("utf-8")).hexdigest()

    def _generate_pseudo_inchikey(self, smiles: str) -> str:
        """Generate pseudo-InChIKey from SMILES hash when InChI fails."""
        hash_val = hashlib.sha256(smiles.encode("utf-8")).hexdigest().upper()
        # Format like InChIKey: XXXXXXXXXXXXXX-XXXXXXXXXX-X
        return f"{hash_val[:14]}-{hash_val[14:24]}-N"

    def canonicalize_smiles(self, smiles: str) -> str:
        """
        Canonicalize a SMILES string.

        Args:
            smiles: Input SMILES string.

        Returns:
            Canonical SMILES string.

        Raises:
            NormalizationError: If canonicalization fails.
        """
        mol = self._Chem.MolFromSmiles(smiles)
        if mol is None:
            raise NormalizationError(
                message=f"Invalid SMILES: {smiles}",
                code=ChemistryErrorCode.CANONICALIZATION_FAILED,
            )

        canonical = self._Chem.MolToSmiles(
            mol,
            canonical=True,
            isomericSmiles=self.options.isomeric,
        )

        if not canonical:
            raise NormalizationError(
                message="Failed to generate canonical SMILES",
                code=ChemistryErrorCode.CANONICALIZATION_FAILED,
            )

        return canonical


def normalize_molecule(
    mol: "Mol",
    options: NormalizationOptions | None = None,
) -> tuple["Mol", MoleculeIdentifiers]:
    """
    Convenience function to normalize a molecule.

    Args:
        mol: RDKit Mol object.
        options: Normalization options.

    Returns:
        Tuple of (normalized Mol, MoleculeIdentifiers).
    """
    normalizer = MoleculeNormalizer(options=options)
    return normalizer.normalize(mol)


def canonicalize_smiles(
    smiles: str,
    isomeric: bool = True,
) -> str:
    """
    Convenience function to canonicalize a SMILES string.

    Args:
        smiles: Input SMILES string.
        isomeric: Include stereochemistry.

    Returns:
        Canonical SMILES string.
    """
    options = NormalizationOptions(isomeric=isomeric)
    normalizer = MoleculeNormalizer(options=options)
    return normalizer.canonicalize_smiles(smiles)


def generate_smiles_hash(smiles: str) -> str:
    """
    Generate SHA-256 hash of a SMILES string.

    Args:
        smiles: SMILES string (should be canonical).

    Returns:
        64-character hex hash.
    """
    return hashlib.sha256(smiles.encode("utf-8")).hexdigest()
