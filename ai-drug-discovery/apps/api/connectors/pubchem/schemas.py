"""
PubChem-specific schemas for normalized data.

These schemas represent PubChem data normalized to our internal format,
ready for import into Molecule, Assay, and related models.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class SearchType(str, Enum):
    """PubChem search types."""

    NAME = "name"
    SMILES = "smiles"
    INCHI = "inchi"
    INCHIKEY = "inchikey"
    FORMULA = "formula"
    CID = "cid"


class AssayOutcome(str, Enum):
    """PubChem bioassay activity outcome."""

    ACTIVE = "Active"
    INACTIVE = "Inactive"
    INCONCLUSIVE = "Inconclusive"
    UNSPECIFIED = "Unspecified"
    PROBE = "Probe"


class AssayType(str, Enum):
    """PubChem assay types."""

    SCREENING = "Screening"
    CONFIRMATORY = "Confirmatory"
    SUMMARY = "Summary"
    OTHER = "Other"


# =============================================================================
# Compound Schema
# =============================================================================


class PubChemCompound(BaseModel):
    """
    Normalized compound data from PubChem.

    Maps to internal Molecule model.
    """

    # --- PubChem Identification ---
    cid: int = Field(..., description="PubChem Compound ID")

    # --- Chemical Structure ---
    canonical_smiles: str | None = Field(None, alias="smiles", max_length=2000)
    isomeric_smiles: str | None = Field(None, max_length=2000)
    inchi: str | None = None
    inchikey: str | None = Field(None, min_length=27, max_length=27)

    # --- Names ---
    iupac_name: str | None = Field(None, alias="name", max_length=1000)
    title: str | None = Field(None, description="Preferred name/title")
    synonyms: list[str] = Field(default_factory=list)

    # --- Molecular Properties ---
    molecular_formula: str | None = Field(None, alias="formula")
    molecular_weight: Decimal | None = Field(None, alias="mw")
    exact_mass: Decimal | None = Field(None, alias="monoisotopic_mass")
    xlogp: Decimal | None = Field(None, alias="logp", description="XLogP3")
    tpsa: Decimal | None = Field(None, description="Topological polar surface area")
    complexity: Decimal | None = Field(None, description="Molecular complexity")

    # --- Counts ---
    heavy_atom_count: int | None = None
    atom_stereo_count: int | None = None
    defined_atom_stereo_count: int | None = None
    undefined_atom_stereo_count: int | None = None
    bond_stereo_count: int | None = None
    covalent_unit_count: int | None = None
    hbond_acceptor_count: int | None = Field(None, alias="hba")
    hbond_donor_count: int | None = Field(None, alias="hbd")
    rotatable_bond_count: int | None = Field(None, alias="rotatable_bonds")

    # --- Charge ---
    charge: int | None = None

    # --- Cross References ---
    chembl_id: str | None = Field(None, description="ChEMBL ID if available")
    drugbank_id: str | None = None
    cas_number: str | None = None

    # --- Metadata ---
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "extra": "allow"}


class CompoundProperties(BaseModel):
    """
    Computed properties for a compound.

    Subset of PubChemCompound focused on physicochemical properties.
    """

    cid: int
    molecular_weight: Decimal | None = None
    exact_mass: Decimal | None = None
    xlogp: Decimal | None = None
    tpsa: Decimal | None = None
    complexity: Decimal | None = None
    heavy_atom_count: int | None = None
    hbond_acceptor_count: int | None = None
    hbond_donor_count: int | None = None
    rotatable_bond_count: int | None = None
    charge: int | None = None

    # Lipinski rule of 5 violations (computed)
    ro5_violations: int | None = Field(None, description="Computed Lipinski violations")

    model_config = {"extra": "allow"}


# =============================================================================
# Bioassay Schema
# =============================================================================


class PubChemAssay(BaseModel):
    """
    Normalized assay metadata from PubChem.

    Maps to internal Assay model.
    """

    # --- PubChem Identification ---
    aid: int = Field(..., description="PubChem Assay ID")

    # --- Basic Info ---
    name: str | None = None
    description: str | None = None
    assay_type: AssayType = Field(default=AssayType.OTHER)
    protocol: str | None = Field(None, description="Assay protocol description")

    # --- Target ---
    target_name: str | None = None
    target_gi: int | None = Field(None, description="NCBI GI number")
    target_gene_id: int | None = Field(None, description="NCBI Gene ID")
    target_gene_symbol: str | None = None

    # --- Source ---
    source_name: str | None = Field(None, description="Depositor name")
    source_id: str | None = None

    # --- Metadata ---
    activity_outcome_method: str | None = None
    comment: str | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "extra": "allow"}


class PubChemBioactivity(BaseModel):
    """
    Normalized bioactivity result from PubChem.

    Maps to internal AssayResult or Prediction model.
    """

    # --- Identification ---
    sid: int | None = Field(None, description="PubChem Substance ID")
    cid: int = Field(..., description="PubChem Compound ID")
    aid: int = Field(..., description="PubChem Assay ID")

    # --- Activity ---
    outcome: AssayOutcome = Field(default=AssayOutcome.UNSPECIFIED)
    activity_value: Decimal | None = Field(None, description="Primary activity value")
    activity_name: str | None = Field(None, description="Name of activity measure")
    activity_unit: str | None = None

    # --- Additional Data ---
    data: dict | None = Field(None, description="Additional assay data columns")

    # --- Metadata ---
    comment: str | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "extra": "allow"}


# =============================================================================
# Search Results
# =============================================================================


class SearchResult(BaseModel):
    """Result of a compound search."""

    query: str
    search_type: SearchType
    cids: list[int] = Field(default_factory=list)
    total_count: int = 0

    model_config = {"extra": "allow"}


class CompoundSearchResult(BaseModel):
    """Paginated compound search results with full compound data."""

    query: str
    search_type: SearchType
    compounds: list[PubChemCompound] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 20
    has_more: bool = False


class BioassaySearchResult(BaseModel):
    """Bioassay search results for a compound."""

    cid: int
    assays: list[PubChemAssay] = Field(default_factory=list)
    activities: list[PubChemBioactivity] = Field(default_factory=list)
    total_assays: int = 0
    total_activities: int = 0
