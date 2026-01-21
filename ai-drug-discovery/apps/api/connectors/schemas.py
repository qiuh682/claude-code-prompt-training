"""
Normalized output schemas for connector responses.

These schemas provide a consistent interface regardless of data source.
Map to internal Molecule, Target, Assay models for import.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class DataSource(str, Enum):
    """External data source identifier."""

    CHEMBL = "chembl"
    PUBCHEM = "pubchem"
    UNIPROT = "uniprot"
    DRUGBANK = "drugbank"


class AssayType(str, Enum):
    """Standardized assay type."""

    BINDING = "binding"
    FUNCTIONAL = "functional"
    ADMET = "admet"
    CYTOTOXICITY = "cytotoxicity"
    PHYSICOCHEMICAL = "physicochemical"
    OTHER = "other"


class ResultType(str, Enum):
    """Standardized result type."""

    IC50 = "IC50"
    EC50 = "EC50"
    KI = "Ki"
    KD = "Kd"
    PERCENT_INHIBITION = "% inhibition"
    PERCENT_ACTIVITY = "% activity"
    OTHER = "other"


# =============================================================================
# Compound/Molecule Schema
# =============================================================================


class ExternalCompound(BaseModel):
    """
    Normalized compound data from external sources.

    Maps to internal Molecule model for import.
    """

    # --- Source Identification ---
    source: DataSource
    source_id: str = Field(..., description="ID in source database (e.g., CHEMBL25)")

    # --- Chemical Identifiers ---
    canonical_smiles: str | None = Field(None, max_length=2000)
    inchi: str | None = None
    inchi_key: str | None = Field(None, min_length=27, max_length=27)

    # --- Names ---
    name: str | None = Field(None, max_length=500)
    synonyms: list[str] = Field(default_factory=list)

    # --- Molecular Properties ---
    molecular_formula: str | None = None
    molecular_weight: Decimal | None = None
    exact_mass: Decimal | None = None
    logp: Decimal | None = Field(None, description="Calculated LogP")
    hbd: int | None = Field(None, description="Hydrogen bond donors")
    hba: int | None = Field(None, description="Hydrogen bond acceptors")
    tpsa: Decimal | None = Field(None, description="Topological polar surface area")
    rotatable_bonds: int | None = None

    # --- External References ---
    chembl_id: str | None = None
    pubchem_cid: int | None = None
    drugbank_id: str | None = None
    cas_number: str | None = None

    # --- Metadata ---
    description: str | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"extra": "allow"}


# =============================================================================
# Target Schema
# =============================================================================


class ExternalTarget(BaseModel):
    """
    Normalized target data from external sources.

    Maps to internal Target model for import.
    """

    # --- Source Identification ---
    source: DataSource
    source_id: str = Field(..., description="ID in source database")

    # --- Identifiers ---
    uniprot_id: str | None = Field(None, description="UniProt accession")
    gene_symbol: str | None = Field(None, max_length=50)
    gene_name: str | None = None

    # --- Basic Info ---
    name: str = Field(..., max_length=500)
    organism: str = Field(default="Homo sapiens")

    # --- Classification ---
    target_type: str | None = Field(None, description="e.g., SINGLE PROTEIN, PROTEIN COMPLEX")
    family: str | None = Field(None, description="Target family (Kinase, GPCR, etc.)")
    subfamily: str | None = None

    # --- Sequence ---
    sequence: str | None = Field(None, description="Amino acid sequence")
    sequence_length: int | None = None

    # --- External References ---
    chembl_target_id: str | None = None
    pdb_ids: list[str] = Field(default_factory=list)

    # --- Metadata ---
    description: str | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"extra": "allow"}


# =============================================================================
# Assay/Bioactivity Schema
# =============================================================================


class ExternalAssay(BaseModel):
    """
    Normalized assay/bioactivity data from external sources.

    Maps to internal Assay model for import.
    """

    # --- Source Identification ---
    source: DataSource
    source_id: str = Field(..., description="Assay ID in source database")

    # --- Linked Entities (by source ID) ---
    compound_source_id: str | None = Field(None, description="Compound ID in source")
    target_source_id: str | None = Field(None, description="Target ID in source")

    # --- Assay Description ---
    assay_type: AssayType = AssayType.OTHER
    assay_name: str | None = None
    assay_description: str | None = None

    # --- Results ---
    result_type: ResultType = ResultType.OTHER
    result_value: Decimal | None = None
    result_unit: str | None = Field(None, description="nM, uM, %, etc.")
    result_qualifier: str | None = Field(None, description="=, <, >, ~")

    # --- Quality ---
    confidence_score: int | None = Field(None, ge=0, le=9, description="ChEMBL confidence 0-9")
    data_validity: str | None = None

    # --- Conditions ---
    conditions: dict = Field(default_factory=dict)

    # --- Metadata ---
    publication_doi: str | None = None
    publication_pmid: str | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"extra": "allow"}


# =============================================================================
# Drug-Target Interaction (DTI) / Prediction Schema
# =============================================================================


class ExternalDTI(BaseModel):
    """
    Normalized drug-target interaction data.

    Used for known interactions from DrugBank, ChEMBL, etc.
    """

    # --- Source Identification ---
    source: DataSource
    source_id: str | None = None

    # --- Linked Entities ---
    compound_source_id: str
    target_source_id: str

    # --- Interaction Details ---
    interaction_type: str | None = Field(None, description="inhibitor, agonist, antagonist, etc.")
    action: str | None = Field(None, description="Pharmacological action")
    known_action: bool = Field(default=False, description="Is this a known/validated action?")

    # --- Affinity ---
    affinity_value: Decimal | None = None
    affinity_type: str | None = Field(None, description="Ki, Kd, IC50, etc.")
    affinity_unit: str | None = None

    # --- References ---
    references: list[str] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"extra": "allow"}


# =============================================================================
# Search Result Containers
# =============================================================================


class SearchResult(BaseModel):
    """Generic search result with pagination info."""

    total_count: int
    page: int = 1
    page_size: int = 20
    has_more: bool = False


class CompoundSearchResult(SearchResult):
    """Search results for compounds."""

    compounds: list[ExternalCompound]


class TargetSearchResult(SearchResult):
    """Search results for targets."""

    targets: list[ExternalTarget]


class AssaySearchResult(SearchResult):
    """Search results for assays/bioactivity."""

    assays: list[ExternalAssay]
