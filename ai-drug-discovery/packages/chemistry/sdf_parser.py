"""
SDF/MOL file parsing with RDKit.

This module provides robust parsing of SDF (Structure-Data File) and MOL files:
- Parse multiple molecules from SDF with error tolerance
- Extract best-available identifiers (name, SMILES, InChIKey, properties)
- Continue on bad records, collecting errors separately
- Output normalized ParsedMolecule objects for the pipeline

SDF Format Overview:
--------------------
SDF files contain one or more molecule records, each consisting of:
1. MOL block (atom/bond connection table)
2. Data items (key-value pairs like <COMPOUND_NAME>, <SMILES>, etc.)
3. Record terminator ($$$$)

Common property names in SDF files:
- Molecule name: First line of MOL block, or <NAME>, <COMPOUND_NAME>, <TITLE>
- SMILES: <SMILES>, <CANONICAL_SMILES>, <ISOMERIC_SMILES>
- Identifiers: <CAS>, <CHEMBL_ID>, <PUBCHEM_CID>, <INCHIKEY>

Usage:
    >>> from packages.chemistry.sdf_parser import parse_sdf_file, parse_sdf_string

    # Parse from file
    >>> result = parse_sdf_file("compounds.sdf")
    >>> print(f"Parsed {result.success_count} molecules, {result.error_count} errors")

    # Parse from string
    >>> result = parse_sdf_string(sdf_content)
    >>> for mol in result.molecules:
    ...     print(f"{mol.name}: {mol.canonical_smiles}")

    # Access errors
    >>> for err in result.errors:
    ...     print(f"Record {err.record_index}: {err.error_message}")
"""

from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO, StringIO
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, Iterator, TextIO

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
            "RDKit is required for SDF parsing. Install with: pip install rdkit"
        )
    from rdkit import Chem

    return Chem


def _get_inchi():
    """Get RDKit inchi module."""
    from rdkit.Chem import inchi

    return inchi


# =============================================================================
# Constants
# =============================================================================

# Common SDF property names for molecule name (checked in order)
NAME_PROPERTIES = [
    "_Name",  # RDKit internal
    "COMPOUND_NAME",
    "NAME",
    "TITLE",
    "MOLECULE_NAME",
    "MOL_NAME",
    "GENERIC_NAME",
    "IUPAC_NAME",
    "PREFERRED_NAME",
]

# Common SDF property names for SMILES
SMILES_PROPERTIES = [
    "SMILES",
    "CANONICAL_SMILES",
    "ISOMERIC_SMILES",
    "ORIGINAL_SMILES",
    "INPUT_SMILES",
]

# Common SDF property names for identifiers (ordered by priority)
ID_PROPERTIES = [
    "ID",
    "COMPOUND_ID",
    "MOL_ID",
    "MOLECULE_ID",
    "CAS",
    "CAS_NUMBER",
    "CHEMBL_ID",
    "PUBCHEM_CID",
    "INCHIKEY",
    "INCHI_KEY",
]


# =============================================================================
# Error Types
# =============================================================================


class SDFErrorCode(str, Enum):
    """Error codes for SDF parsing."""

    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_READ_ERROR = "FILE_READ_ERROR"
    EMPTY_FILE = "EMPTY_FILE"
    INVALID_MOL_BLOCK = "INVALID_MOL_BLOCK"
    SANITIZATION_FAILED = "SANITIZATION_FAILED"
    EMPTY_MOLECULE = "EMPTY_MOLECULE"
    SMILES_GENERATION_FAILED = "SMILES_GENERATION_FAILED"


class SDFParseError(Exception):
    """Exception for SDF parsing errors."""

    def __init__(self, message: str, code: SDFErrorCode):
        super().__init__(message)
        self.message = message
        self.code = code


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class MoleculeIdentifiers:
    """Extracted identifiers for a molecule."""

    name: str | None = None
    smiles_from_sdf: str | None = None  # SMILES found in SDF properties
    external_id: str | None = None  # External ID (ChEMBL, PubChem, CAS, etc.)
    external_id_type: str | None = None  # Type of external ID


@dataclass
class ParsedMolecule:
    """
    Normalized molecule record from SDF parsing.

    Contains all extracted data in a pipeline-ready format.
    """

    # Record position
    record_index: int

    # RDKit Mol object (for further processing)
    mol: "Mol"

    # Canonical identifiers (computed)
    canonical_smiles: str
    inchikey: str
    inchi: str | None = None

    # Best-available name
    name: str | None = None

    # Original MOL block (for reference/debugging)
    mol_block: str | None = None

    # All SDF properties as dict
    properties: dict[str, str] = field(default_factory=dict)

    # Extracted identifiers
    identifiers: MoleculeIdentifiers = field(default_factory=MoleculeIdentifiers)

    # Molecular info
    atom_count: int = 0
    bond_count: int = 0
    has_3d_coordinates: bool = False

    # Processing notes
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParseError:
    """Error record for a failed molecule parse."""

    record_index: int
    error_code: SDFErrorCode
    error_message: str
    mol_block: str | None = None  # Original MOL block if available
    details: dict = field(default_factory=dict)


@dataclass
class SDFParseResult:
    """Result of SDF file parsing."""

    # Successfully parsed molecules
    molecules: list[ParsedMolecule] = field(default_factory=list)

    # Failed records
    errors: list[ParseError] = field(default_factory=list)

    # Statistics
    total_records: int = 0
    success_count: int = 0
    error_count: int = 0

    # Source info
    source_path: str | None = None
    source_type: str = "unknown"  # "file", "string", "bytes"

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_records == 0:
            return 0.0
        return (self.success_count / self.total_records) * 100.0

    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return self.error_count > 0


# =============================================================================
# Parser Class
# =============================================================================


class SDFParser:
    """
    Parser for SDF/MOL files with error tolerance.

    Extracts molecules and their properties, continuing on errors.
    """

    def __init__(
        self,
        sanitize: bool = True,
        remove_hs: bool = False,
        strict_parsing: bool = False,
        compute_identifiers: bool = True,
    ):
        """
        Initialize SDF parser.

        Args:
            sanitize: Whether to sanitize molecules after parsing.
            remove_hs: Whether to remove explicit hydrogens.
            strict_parsing: If True, raise on first error instead of collecting.
            compute_identifiers: Whether to compute SMILES/InChIKey for each molecule.
        """
        self.sanitize = sanitize
        self.remove_hs = remove_hs
        self.strict_parsing = strict_parsing
        self.compute_identifiers = compute_identifiers
        self._Chem = _get_chem()

    def parse_file(self, filepath: str | Path) -> SDFParseResult:
        """
        Parse molecules from an SDF file.

        Args:
            filepath: Path to SDF file.

        Returns:
            SDFParseResult with molecules and errors.

        Raises:
            SDFParseError: If file cannot be read (only in strict mode).
        """
        filepath = Path(filepath)

        if not filepath.exists():
            error = SDFParseError(
                message=f"File not found: {filepath}",
                code=SDFErrorCode.FILE_NOT_FOUND,
            )
            if self.strict_parsing:
                raise error
            return SDFParseResult(
                errors=[
                    ParseError(
                        record_index=-1,
                        error_code=SDFErrorCode.FILE_NOT_FOUND,
                        error_message=str(error),
                    )
                ],
                error_count=1,
                source_path=str(filepath),
                source_type="file",
            )

        try:
            supplier = self._Chem.SDMolSupplier(
                str(filepath),
                sanitize=self.sanitize,
                removeHs=self.remove_hs,
            )
        except Exception as e:
            error = SDFParseError(
                message=f"Failed to read SDF file: {e}",
                code=SDFErrorCode.FILE_READ_ERROR,
            )
            if self.strict_parsing:
                raise error
            return SDFParseResult(
                errors=[
                    ParseError(
                        record_index=-1,
                        error_code=SDFErrorCode.FILE_READ_ERROR,
                        error_message=str(error),
                    )
                ],
                error_count=1,
                source_path=str(filepath),
                source_type="file",
            )

        return self._process_supplier(
            supplier,
            source_path=str(filepath),
            source_type="file",
        )

    def parse_string(self, sdf_content: str) -> SDFParseResult:
        """
        Parse molecules from an SDF string.

        Args:
            sdf_content: SDF format string.

        Returns:
            SDFParseResult with molecules and errors.
        """
        if not sdf_content or not sdf_content.strip():
            return SDFParseResult(
                errors=[
                    ParseError(
                        record_index=-1,
                        error_code=SDFErrorCode.EMPTY_FILE,
                        error_message="Empty SDF content",
                    )
                ],
                error_count=1,
                source_type="string",
            )

        supplier = self._Chem.SDMolSupplier()
        supplier.SetData(sdf_content, sanitize=self.sanitize, removeHs=self.remove_hs)

        return self._process_supplier(supplier, source_type="string")

    def parse_bytes(self, sdf_bytes: bytes) -> SDFParseResult:
        """
        Parse molecules from SDF bytes.

        Args:
            sdf_bytes: SDF content as bytes.

        Returns:
            SDFParseResult with molecules and errors.
        """
        try:
            sdf_content = sdf_bytes.decode("utf-8")
        except UnicodeDecodeError:
            # Try latin-1 as fallback
            sdf_content = sdf_bytes.decode("latin-1")

        result = self.parse_string(sdf_content)
        result.source_type = "bytes"
        return result

    def parse_mol_block(self, mol_block: str) -> ParsedMolecule:
        """
        Parse a single MOL block.

        Args:
            mol_block: MDL MOL format string.

        Returns:
            ParsedMolecule.

        Raises:
            SDFParseError: If parsing fails.
        """
        if not mol_block or not mol_block.strip():
            raise SDFParseError(
                message="Empty MOL block",
                code=SDFErrorCode.INVALID_MOL_BLOCK,
            )

        mol = self._Chem.MolFromMolBlock(
            mol_block,
            sanitize=self.sanitize,
            removeHs=self.remove_hs,
        )

        if mol is None:
            raise SDFParseError(
                message="Invalid MOL block - failed to parse",
                code=SDFErrorCode.INVALID_MOL_BLOCK,
            )

        if mol.GetNumAtoms() == 0:
            raise SDFParseError(
                message="MOL block parsed to empty molecule",
                code=SDFErrorCode.EMPTY_MOLECULE,
            )

        return self._create_parsed_molecule(mol, record_index=0, mol_block=mol_block)

    def _process_supplier(
        self,
        supplier,
        source_path: str | None = None,
        source_type: str = "unknown",
    ) -> SDFParseResult:
        """Process an RDKit SDMolSupplier and collect results."""
        molecules = []
        errors = []
        record_index = 0

        for mol in supplier:
            if mol is None:
                # Failed to parse this record
                errors.append(
                    ParseError(
                        record_index=record_index,
                        error_code=SDFErrorCode.INVALID_MOL_BLOCK,
                        error_message=f"Failed to parse molecule at record {record_index}",
                    )
                )
                if self.strict_parsing:
                    raise SDFParseError(
                        message=f"Failed to parse record {record_index}",
                        code=SDFErrorCode.INVALID_MOL_BLOCK,
                    )
            elif mol.GetNumAtoms() == 0:
                # Empty molecule (parsed but no atoms)
                errors.append(
                    ParseError(
                        record_index=record_index,
                        error_code=SDFErrorCode.EMPTY_MOLECULE,
                        error_message=f"Empty molecule (0 atoms) at record {record_index}",
                    )
                )
                if self.strict_parsing:
                    raise SDFParseError(
                        message=f"Empty molecule at record {record_index}",
                        code=SDFErrorCode.EMPTY_MOLECULE,
                    )
            else:
                try:
                    parsed = self._create_parsed_molecule(mol, record_index)
                    molecules.append(parsed)
                except Exception as e:
                    errors.append(
                        ParseError(
                            record_index=record_index,
                            error_code=SDFErrorCode.SANITIZATION_FAILED,
                            error_message=str(e),
                        )
                    )
                    if self.strict_parsing:
                        raise

            record_index += 1

        return SDFParseResult(
            molecules=molecules,
            errors=errors,
            total_records=record_index,
            success_count=len(molecules),
            error_count=len(errors),
            source_path=source_path,
            source_type=source_type,
        )

    def _create_parsed_molecule(
        self,
        mol: "Mol",
        record_index: int,
        mol_block: str | None = None,
    ) -> ParsedMolecule:
        """Create a ParsedMolecule from an RDKit Mol object."""
        warnings = []

        # Extract all properties
        properties = {}
        for prop_name in mol.GetPropsAsDict():
            try:
                properties[prop_name] = str(mol.GetProp(prop_name))
            except Exception:
                pass

        # Extract identifiers
        identifiers = self._extract_identifiers(mol, properties)

        # Compute canonical SMILES
        canonical_smiles = ""
        if self.compute_identifiers:
            try:
                canonical_smiles = self._Chem.MolToSmiles(mol, canonical=True)
            except Exception as e:
                warnings.append(f"SMILES generation failed: {e}")

        # Compute InChI/InChIKey
        inchi = None
        inchikey = ""
        if self.compute_identifiers and canonical_smiles:
            try:
                inchi_mod = _get_inchi()
                inchi = inchi_mod.MolToInchi(mol)
                if inchi:
                    inchikey = inchi_mod.InchiToInchiKey(inchi)
            except Exception as e:
                warnings.append(f"InChI generation failed: {e}")

        # Fallback InChIKey from hash
        if not inchikey and canonical_smiles:
            import hashlib

            hash_val = hashlib.sha256(canonical_smiles.encode()).hexdigest().upper()
            inchikey = f"{hash_val[:14]}-{hash_val[14:24]}-N"
            warnings.append("Using hash-based InChIKey (InChI generation failed)")

        # Get MOL block if not provided
        if mol_block is None:
            try:
                mol_block = self._Chem.MolToMolBlock(mol)
            except Exception:
                pass

        # Check for 3D coordinates
        has_3d = False
        if mol.GetNumConformers() > 0:
            conf = mol.GetConformer()
            has_3d = any(
                abs(conf.GetAtomPosition(i).z) > 0.01
                for i in range(min(mol.GetNumAtoms(), 10))  # Check first 10 atoms
            )

        return ParsedMolecule(
            record_index=record_index,
            mol=mol,
            canonical_smiles=canonical_smiles,
            inchikey=inchikey,
            inchi=inchi,
            name=identifiers.name,
            mol_block=mol_block,
            properties=properties,
            identifiers=identifiers,
            atom_count=mol.GetNumAtoms(),
            bond_count=mol.GetNumBonds(),
            has_3d_coordinates=has_3d,
            warnings=warnings,
        )

    def _extract_identifiers(
        self,
        mol: "Mol",
        properties: dict[str, str],
    ) -> MoleculeIdentifiers:
        """Extract best-available identifiers from molecule and properties."""
        # Find name
        name = None
        for prop in NAME_PROPERTIES:
            if prop in properties and properties[prop].strip():
                name = properties[prop].strip()
                break

        # Try first line of MOL block as name (RDKit stores as _Name)
        if not name and mol.HasProp("_Name"):
            name = mol.GetProp("_Name").strip() or None

        # Find SMILES from properties
        smiles_from_sdf = None
        for prop in SMILES_PROPERTIES:
            # Case-insensitive search
            for key, value in properties.items():
                if key.upper() == prop and value.strip():
                    smiles_from_sdf = value.strip()
                    break
            if smiles_from_sdf:
                break

        # Find external ID
        external_id = None
        external_id_type = None
        for prop in ID_PROPERTIES:
            for key, value in properties.items():
                if key.upper() == prop and value.strip():
                    external_id = value.strip()
                    external_id_type = key
                    break
            if external_id:
                break

        return MoleculeIdentifiers(
            name=name,
            smiles_from_sdf=smiles_from_sdf,
            external_id=external_id,
            external_id_type=external_id_type,
        )


# =============================================================================
# Convenience Functions
# =============================================================================


def parse_sdf_file(
    filepath: str | Path,
    sanitize: bool = True,
    strict: bool = False,
) -> SDFParseResult:
    """
    Parse molecules from an SDF file.

    Args:
        filepath: Path to SDF file.
        sanitize: Whether to sanitize molecules.
        strict: If True, raise on first error.

    Returns:
        SDFParseResult with molecules and errors.

    Example:
        >>> result = parse_sdf_file("compounds.sdf")
        >>> print(f"Parsed {result.success_count} molecules")
        >>> for mol in result.molecules:
        ...     print(f"{mol.name}: {mol.canonical_smiles}")
    """
    parser = SDFParser(sanitize=sanitize, strict_parsing=strict)
    return parser.parse_file(filepath)


def parse_sdf_string(
    sdf_content: str,
    sanitize: bool = True,
    strict: bool = False,
) -> SDFParseResult:
    """
    Parse molecules from an SDF string.

    Args:
        sdf_content: SDF format string.
        sanitize: Whether to sanitize molecules.
        strict: If True, raise on first error.

    Returns:
        SDFParseResult with molecules and errors.

    Example:
        >>> sdf = open("compounds.sdf").read()
        >>> result = parse_sdf_string(sdf)
        >>> print(f"Success rate: {result.success_rate:.1f}%")
    """
    parser = SDFParser(sanitize=sanitize, strict_parsing=strict)
    return parser.parse_string(sdf_content)


def parse_sdf_bytes(
    sdf_bytes: bytes,
    sanitize: bool = True,
    strict: bool = False,
) -> SDFParseResult:
    """
    Parse molecules from SDF bytes.

    Args:
        sdf_bytes: SDF content as bytes.
        sanitize: Whether to sanitize molecules.
        strict: If True, raise on first error.

    Returns:
        SDFParseResult with molecules and errors.
    """
    parser = SDFParser(sanitize=sanitize, strict_parsing=strict)
    return parser.parse_bytes(sdf_bytes)


def parse_mol_block(
    mol_block: str,
    sanitize: bool = True,
) -> ParsedMolecule:
    """
    Parse a single MOL block.

    Args:
        mol_block: MDL MOL format string.
        sanitize: Whether to sanitize the molecule.

    Returns:
        ParsedMolecule.

    Raises:
        SDFParseError: If parsing fails.

    Example:
        >>> mol_block = '''
        ... ethanol
        ...   RDKit          2D
        ...
        ...   3  2  0  0  0  0  0  0  0  0999 V2000
        ...     0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
        ...     1.2990    0.7500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
        ...     2.5981    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
        ...   1  2  1  0
        ...   2  3  1  0
        ... M  END
        ... '''
        >>> parsed = parse_mol_block(mol_block)
        >>> parsed.canonical_smiles
        'CCO'
    """
    parser = SDFParser(sanitize=sanitize)
    return parser.parse_mol_block(mol_block)


def iter_sdf_file(
    filepath: str | Path,
    sanitize: bool = True,
    skip_failures: bool = True,
) -> Iterator[ParsedMolecule | ParseError]:
    """
    Iterate over molecules in an SDF file (memory efficient).

    Yields molecules one at a time without loading entire file.

    Args:
        filepath: Path to SDF file.
        sanitize: Whether to sanitize molecules.
        skip_failures: If True, yield ParseError for failures; if False, skip.

    Yields:
        ParsedMolecule for successful parses, ParseError for failures.

    Example:
        >>> for item in iter_sdf_file("large_library.sdf"):
        ...     if isinstance(item, ParsedMolecule):
        ...         process(item)
        ...     else:
        ...         log_error(item)
    """
    Chem = _get_chem()
    filepath = Path(filepath)

    if not filepath.exists():
        yield ParseError(
            record_index=-1,
            error_code=SDFErrorCode.FILE_NOT_FOUND,
            error_message=f"File not found: {filepath}",
        )
        return

    supplier = Chem.SDMolSupplier(str(filepath), sanitize=sanitize)
    parser = SDFParser(sanitize=sanitize, compute_identifiers=True)

    for idx, mol in enumerate(supplier):
        if mol is None:
            if skip_failures:
                yield ParseError(
                    record_index=idx,
                    error_code=SDFErrorCode.INVALID_MOL_BLOCK,
                    error_message=f"Failed to parse record {idx}",
                )
        elif mol.GetNumAtoms() == 0:
            if skip_failures:
                yield ParseError(
                    record_index=idx,
                    error_code=SDFErrorCode.EMPTY_MOLECULE,
                    error_message=f"Empty molecule (0 atoms) at record {idx}",
                )
        else:
            try:
                yield parser._create_parsed_molecule(mol, idx)
            except Exception as e:
                if skip_failures:
                    yield ParseError(
                        record_index=idx,
                        error_code=SDFErrorCode.SANITIZATION_FAILED,
                        error_message=str(e),
                    )


# =============================================================================
# Example Usage
# =============================================================================

EXAMPLE_USAGE = '''
"""
Example: Parse SDF file and process molecules
"""

from packages.chemistry.sdf_parser import (
    parse_sdf_file,
    parse_sdf_string,
    iter_sdf_file,
    ParsedMolecule,
    ParseError,
)

# -----------------------------------------------------------------------------
# Example 1: Parse SDF file
# -----------------------------------------------------------------------------

result = parse_sdf_file("compounds.sdf")

print(f"Total records: {result.total_records}")
print(f"Successfully parsed: {result.success_count}")
print(f"Errors: {result.error_count}")
print(f"Success rate: {result.success_rate:.1f}%")

# Process successful molecules
for mol in result.molecules:
    print(f"\\nRecord {mol.record_index}:")
    print(f"  Name: {mol.name or 'N/A'}")
    print(f"  SMILES: {mol.canonical_smiles}")
    print(f"  InChIKey: {mol.inchikey}")
    print(f"  Atoms: {mol.atom_count}, Bonds: {mol.bond_count}")
    print(f"  3D coords: {mol.has_3d_coordinates}")

    # Access SDF properties
    if mol.properties:
        print(f"  Properties: {list(mol.properties.keys())[:5]}...")

# Review errors
for err in result.errors:
    print(f"\\nError at record {err.record_index}:")
    print(f"  Code: {err.error_code.value}")
    print(f"  Message: {err.error_message}")

# -----------------------------------------------------------------------------
# Example 2: Parse SDF string
# -----------------------------------------------------------------------------

sdf_content = """
aspirin
     RDKit          2D

 13 13  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0
    ...
M  END
> <COMPOUND_NAME>
Aspirin

> <SMILES>
CC(=O)OC1=CC=CC=C1C(=O)O

> <CAS>
50-78-2

$$$$
"""

result = parse_sdf_string(sdf_content)
if result.molecules:
    mol = result.molecules[0]
    print(f"Parsed: {mol.identifiers.name}")
    print(f"SMILES from SDF: {mol.identifiers.smiles_from_sdf}")
    print(f"External ID: {mol.identifiers.external_id} ({mol.identifiers.external_id_type})")

# -----------------------------------------------------------------------------
# Example 3: Memory-efficient iteration for large files
# -----------------------------------------------------------------------------

success_count = 0
error_count = 0

for item in iter_sdf_file("large_library.sdf"):
    if isinstance(item, ParsedMolecule):
        success_count += 1
        # Process molecule...
        process_molecule(item.mol, item.canonical_smiles)
    elif isinstance(item, ParseError):
        error_count += 1
        # Log error...
        log_parsing_error(item.record_index, item.error_message)

print(f"Processed {success_count} molecules, {error_count} errors")

# -----------------------------------------------------------------------------
# Example 4: Integration with pipeline
# -----------------------------------------------------------------------------

from packages.chemistry import process_molecule_input, InputFormat

result = parse_sdf_file("compounds.sdf")

for parsed in result.molecules:
    # Use the pre-computed SMILES to process through full pipeline
    if parsed.canonical_smiles:
        processed = process_molecule_input(
            value=parsed.canonical_smiles,
            format=InputFormat.SMILES,
            name=parsed.name,
            metadata=parsed.properties,
        )
        # processed now has descriptors, fingerprints, etc.
'''


if __name__ == "__main__":
    print(EXAMPLE_USAGE)
