"""
Pydantic schemas for molecular data processing pipeline.

Defines input/output models for:
- Single molecule processing
- Batch processing
- Computed properties
- Fingerprints
"""

from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class InputFormat(str, Enum):
    """Supported molecular input formats."""

    SMILES = "smiles"
    MOL = "mol"  # MDL MOL format (V2000/V3000)
    SDF = "sdf"  # Structure-Data File (multi-molecule)
    INCHI = "inchi"


class FingerprintType(str, Enum):
    """Supported fingerprint types."""

    MORGAN = "morgan"  # Morgan/circular fingerprint (ECFP-like)
    MACCS = "maccs"  # MACCS 166 keys
    RDKIT = "rdkit"  # RDKit topological fingerprint
    ATOM_PAIR = "atom_pair"  # Atom pair fingerprint
    TORSION = "torsion"  # Topological torsion fingerprint


class MoleculeInput(BaseModel):
    """Single molecule input for processing."""

    model_config = ConfigDict(str_strip_whitespace=True)

    value: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Molecular representation (SMILES, MOL block, InChI)",
    )
    format: InputFormat = Field(
        default=InputFormat.SMILES,
        description="Input format",
    )
    name: str | None = Field(
        default=None,
        max_length=255,
        description="Optional molecule name",
    )
    metadata: dict | None = Field(
        default=None,
        description="Additional metadata to store with molecule",
    )


class BatchInput(BaseModel):
    """Batch molecule input from CSV/Excel."""

    model_config = ConfigDict(str_strip_whitespace=True)

    molecules: list[MoleculeInput] = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="List of molecules to process",
    )
    skip_errors: bool = Field(
        default=True,
        description="Continue processing if some molecules fail",
    )
    compute_descriptors: bool = Field(
        default=True,
        description="Calculate molecular descriptors",
    )
    compute_fingerprints: list[FingerprintType] = Field(
        default=[FingerprintType.MORGAN, FingerprintType.MACCS],
        description="Fingerprint types to compute",
    )


class MolecularDescriptors(BaseModel):
    """Computed molecular descriptors."""

    model_config = ConfigDict(populate_by_name=True)

    molecular_weight: Annotated[
        Decimal | None,
        Field(decimal_places=4, description="Molecular weight in Daltons"),
    ] = None
    exact_mass: Annotated[
        Decimal | None,
        Field(decimal_places=6, description="Monoisotopic mass"),
    ] = None
    molecular_formula: str | None = Field(
        default=None,
        description="Molecular formula (e.g., C21H30O2)",
    )

    # Lipinski descriptors
    logp: Annotated[
        Decimal | None,
        Field(decimal_places=3, description="Calculated LogP (Wildman-Crippen)"),
    ] = None
    hbd: int | None = Field(
        default=None,
        ge=0,
        description="Hydrogen bond donors",
    )
    hba: int | None = Field(
        default=None,
        ge=0,
        description="Hydrogen bond acceptors",
    )
    tpsa: Annotated[
        Decimal | None,
        Field(decimal_places=2, description="Topological polar surface area"),
    ] = None
    rotatable_bonds: int | None = Field(
        default=None,
        ge=0,
        description="Number of rotatable bonds",
    )

    # Additional descriptors
    num_atoms: int | None = Field(
        default=None,
        ge=0,
        description="Total atom count",
    )
    num_heavy_atoms: int | None = Field(
        default=None,
        ge=0,
        description="Heavy (non-hydrogen) atom count",
    )
    num_rings: int | None = Field(
        default=None,
        ge=0,
        description="Number of rings",
    )
    num_aromatic_rings: int | None = Field(
        default=None,
        ge=0,
        description="Number of aromatic rings",
    )
    fraction_sp3: Annotated[
        Decimal | None,
        Field(decimal_places=3, description="Fraction of sp3 carbons"),
    ] = None

    # Lipinski Rule of 5
    @property
    def lipinski_violations(self) -> int | None:
        """Count Lipinski Rule of 5 violations."""
        if any(
            x is None for x in [self.molecular_weight, self.logp, self.hbd, self.hba]
        ):
            return None

        violations = 0
        if self.molecular_weight and self.molecular_weight > 500:
            violations += 1
        if self.logp and self.logp > 5:
            violations += 1
        if self.hbd and self.hbd > 5:
            violations += 1
        if self.hba and self.hba > 10:
            violations += 1
        return violations


class FingerprintData(BaseModel):
    """Computed fingerprint data."""

    fingerprint_type: FingerprintType
    bit_length: int = Field(
        description="Number of bits in fingerprint",
    )
    bits: bytes = Field(
        description="Fingerprint as binary data",
    )
    on_bits: list[int] | None = Field(
        default=None,
        description="Indices of set bits (for sparse representation)",
    )
    num_on_bits: int = Field(
        description="Count of set bits",
    )

    @property
    def density(self) -> float:
        """Calculate bit density (fraction of set bits)."""
        return self.num_on_bits / self.bit_length if self.bit_length > 0 else 0.0


class MoleculeIdentifiers(BaseModel):
    """Canonical molecular identifiers."""

    canonical_smiles: str = Field(
        description="Canonical SMILES string",
    )
    inchi: str | None = Field(
        default=None,
        description="InChI string",
    )
    inchi_key: str = Field(
        description="InChIKey (27 characters)",
    )
    smiles_hash: str = Field(
        description="SHA-256 hash of canonical SMILES for fast lookup",
    )


class ProcessedMolecule(BaseModel):
    """Fully processed molecule with all computed data."""

    model_config = ConfigDict(from_attributes=True)

    # Identifiers
    identifiers: MoleculeIdentifiers

    # Original input
    original_input: str
    input_format: InputFormat
    name: str | None = None

    # Computed properties
    descriptors: MolecularDescriptors | None = None
    fingerprints: dict[FingerprintType, FingerprintData] = Field(
        default_factory=dict,
    )

    # 2D rendering
    svg_image: str | None = Field(
        default=None,
        description="2D structure as SVG",
    )
    png_image: bytes | None = Field(
        default=None,
        description="2D structure as PNG (base64 encoded in JSON)",
    )

    # Status
    is_valid: bool = True
    warnings: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class BatchProcessingResult(BaseModel):
    """Result of batch molecule processing."""

    successful: list[ProcessedMolecule] = Field(
        default_factory=list,
        description="Successfully processed molecules",
    )
    failed: list[dict] = Field(
        default_factory=list,
        description="Failed molecules with error details",
    )
    total_count: int
    successful_count: int
    failed_count: int

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_count == 0:
            return 0.0
        return (self.successful_count / self.total_count) * 100.0


class StorageResult(BaseModel):
    """Result of molecule storage operation."""

    molecule_id: str = Field(
        description="UUID of stored molecule",
    )
    inchi_key: str
    is_new: bool = Field(
        description="True if molecule was created, False if already existed",
    )
    message: str | None = None
