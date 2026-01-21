"""
ChEMBL-specific schemas for normalized data.

These schemas represent ChEMBL data normalized to our internal format,
ready for import into Molecule, Target, Assay, and Prediction models.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class BioactivityType(str, Enum):
    """Standard bioactivity measurement types."""

    IC50 = "IC50"
    EC50 = "EC50"
    KI = "Ki"
    KD = "Kd"
    AC50 = "AC50"
    GI50 = "GI50"
    LC50 = "LC50"
    ED50 = "ED50"
    INHIBITION = "Inhibition"
    ACTIVITY = "Activity"
    POTENCY = "Potency"
    OTHER = "Other"


class AssayTypeEnum(str, Enum):
    """ChEMBL assay types."""

    BINDING = "B"  # Binding
    FUNCTIONAL = "F"  # Functional
    ADMET = "A"  # ADME
    TOXICITY = "T"  # Toxicity
    PHYSICOCHEMICAL = "P"  # Physicochemical
    UNCLASSIFIED = "U"  # Unclassified


class RelationshipType(str, Enum):
    """Result relationship/qualifier."""

    EQUALS = "="
    LESS_THAN = "<"
    GREATER_THAN = ">"
    LESS_EQUAL = "<="
    GREATER_EQUAL = ">="
    APPROXIMATELY = "~"


# =============================================================================
# Compound Schema
# =============================================================================


class ChEMBLCompound(BaseModel):
    """
    Normalized compound data from ChEMBL.

    Maps to internal Molecule model.
    """

    # --- ChEMBL Identification ---
    chembl_id: str = Field(..., description="ChEMBL molecule ID (e.g., CHEMBL25)")

    # --- Chemical Structure ---
    canonical_smiles: str | None = Field(None, max_length=2000)
    standard_inchi: str | None = Field(None, alias="inchi")
    standard_inchi_key: str | None = Field(None, alias="inchi_key", min_length=27, max_length=27)

    # --- Names ---
    pref_name: str | None = Field(None, alias="name", max_length=500)
    synonyms: list[str] = Field(default_factory=list)

    # --- Molecular Properties ---
    molecular_formula: str | None = None
    molecular_weight: Decimal | None = Field(None, alias="mw")
    exact_mass: Decimal | None = None
    alogp: Decimal | None = Field(None, alias="logp")
    hbd: int | None = Field(None, description="Hydrogen bond donors")
    hba: int | None = Field(None, description="Hydrogen bond acceptors")
    psa: Decimal | None = Field(None, alias="tpsa", description="Polar surface area")
    rtb: int | None = Field(None, alias="rotatable_bonds")
    num_ro5_violations: int | None = Field(None, description="Lipinski rule of 5 violations")
    aromatic_rings: int | None = None
    heavy_atoms: int | None = None

    # --- Drug Properties ---
    max_phase: int | None = Field(None, ge=0, le=4, description="Max clinical trial phase (0-4)")
    molecule_type: str | None = Field(None, description="Small molecule, Antibody, etc.")
    therapeutic_flag: bool = Field(default=False)
    natural_product: bool = Field(default=False)
    oral: bool = Field(default=False, description="Oral availability")

    # --- Cross References ---
    pubchem_cid: int | None = None
    drugbank_id: str | None = None

    # --- Metadata ---
    first_approval: int | None = Field(None, description="Year of first approval")
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "extra": "allow"}


# =============================================================================
# Target Schema
# =============================================================================


class ChEMBLTarget(BaseModel):
    """
    Normalized target data from ChEMBL.

    Maps to internal Target model.
    """

    # --- ChEMBL Identification ---
    chembl_id: str = Field(..., description="ChEMBL target ID (e.g., CHEMBL203)")

    # --- External IDs ---
    uniprot_id: str | None = Field(None, description="UniProt accession")
    gene_symbol: str | None = None

    # --- Basic Info ---
    pref_name: str = Field(..., alias="name")
    target_type: str | None = Field(None, description="SINGLE PROTEIN, PROTEIN COMPLEX, etc.")
    organism: str = Field(default="Homo sapiens")
    tax_id: int | None = Field(None, description="NCBI taxonomy ID")

    # --- Classification ---
    target_class: str | None = Field(None, alias="family")
    protein_class: list[str] = Field(default_factory=list)

    # --- Sequence (if single protein) ---
    sequence: str | None = None
    sequence_length: int | None = None

    # --- Cross References ---
    pdb_ids: list[str] = Field(default_factory=list)

    # --- Metadata ---
    description: str | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "extra": "allow"}


# =============================================================================
# Assay Schema
# =============================================================================


class AssayConditions(BaseModel):
    """Assay experimental conditions."""

    cell_type: str | None = None
    tissue: str | None = None
    subcellular_fraction: str | None = None
    assay_organism: str | None = None
    assay_strain: str | None = None
    assay_tax_id: int | None = None


class ChEMBLAssay(BaseModel):
    """
    Normalized assay data from ChEMBL.

    Maps to internal Assay model.
    """

    # --- ChEMBL Identification ---
    chembl_id: str = Field(..., description="ChEMBL assay ID (e.g., CHEMBL615116)")

    # --- Linked Entities ---
    target_chembl_id: str | None = None
    target_uniprot_id: str | None = None

    # --- Assay Description ---
    assay_type: AssayTypeEnum = Field(default=AssayTypeEnum.UNCLASSIFIED)
    assay_type_description: str | None = None
    description: str | None = None
    assay_category: str | None = None

    # --- Conditions ---
    conditions: AssayConditions = Field(default_factory=AssayConditions)

    # --- Confidence ---
    confidence_score: int | None = Field(None, ge=0, le=9, description="Target confidence 0-9")
    confidence_description: str | None = None

    # --- Source ---
    src_id: int | None = Field(None, description="Source database ID")
    src_description: str | None = None
    document_chembl_id: str | None = None

    # --- Metadata ---
    bao_format: str | None = Field(None, description="BioAssay Ontology format")
    bao_label: str | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "extra": "allow"}


# =============================================================================
# Bioactivity/AssayResult Schema
# =============================================================================


class ChEMBLBioactivity(BaseModel):
    """
    Normalized bioactivity (assay result) data from ChEMBL.

    Maps to internal AssayResult or can be used for Prediction import.
    """

    # --- ChEMBL Identification ---
    activity_id: int = Field(..., description="ChEMBL activity ID")

    # --- Linked Entities ---
    molecule_chembl_id: str
    target_chembl_id: str | None = None
    assay_chembl_id: str

    # --- Result Values ---
    standard_type: BioactivityType = Field(default=BioactivityType.OTHER)
    standard_value: Decimal | None = Field(None, description="Standardized numeric value")
    standard_units: str | None = Field(None, description="nM, uM, %, etc.")
    standard_relation: RelationshipType | None = Field(None, description="=, <, >, etc.")

    # --- Original Values (before standardization) ---
    published_type: str | None = None
    published_value: Decimal | None = None
    published_units: str | None = None
    published_relation: str | None = None

    # --- Activity Classification ---
    activity_comment: str | None = None
    data_validity_comment: str | None = None
    potential_duplicate: bool = Field(default=False)
    pchembl_value: Decimal | None = Field(None, description="Normalized -log10(value) for IC50/Ki/etc")

    # --- Ligand Efficiency ---
    ligand_efficiency_bei: Decimal | None = Field(None, description="Binding efficiency index")
    ligand_efficiency_le: Decimal | None = Field(None, description="Ligand efficiency")
    ligand_efficiency_lle: Decimal | None = Field(None, description="Lipophilic ligand efficiency")
    ligand_efficiency_sei: Decimal | None = Field(None, description="Surface efficiency index")

    # --- Source ---
    document_chembl_id: str | None = None
    src_id: int | None = None

    # --- Metadata ---
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "extra": "allow"}


# =============================================================================
# Result Containers
# =============================================================================


class PaginatedResult(BaseModel):
    """Base class for paginated results."""

    total_count: int
    page: int = 1
    page_size: int = 20
    has_more: bool = False


class CompoundSearchResult(PaginatedResult):
    """Paginated compound search results."""

    compounds: list[ChEMBLCompound]


class TargetSearchResult(PaginatedResult):
    """Paginated target search results."""

    targets: list[ChEMBLTarget]


class AssaySearchResult(PaginatedResult):
    """Paginated assay search results."""

    assays: list[ChEMBLAssay]


class BioactivitySearchResult(PaginatedResult):
    """Paginated bioactivity search results."""

    bioactivities: list[ChEMBLBioactivity]
