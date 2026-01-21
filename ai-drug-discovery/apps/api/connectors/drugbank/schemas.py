"""
DrugBank-specific schemas for normalized data.

These schemas represent DrugBank data normalized to our internal format,
ready for import into Molecule, Target, and DTI models.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class DrugType(str, Enum):
    """DrugBank drug types."""

    SMALL_MOLECULE = "small molecule"
    BIOTECH = "biotech"
    UNKNOWN = "unknown"


class DrugGroup(str, Enum):
    """DrugBank drug groups/status."""

    APPROVED = "approved"
    INVESTIGATIONAL = "investigational"
    EXPERIMENTAL = "experimental"
    WITHDRAWN = "withdrawn"
    NUTRACEUTICAL = "nutraceutical"
    ILLICIT = "illicit"
    VET_APPROVED = "vet_approved"


class TargetAction(str, Enum):
    """Drug-target interaction action types."""

    INHIBITOR = "inhibitor"
    AGONIST = "agonist"
    ANTAGONIST = "antagonist"
    BINDER = "binder"
    ACTIVATOR = "activator"
    MODULATOR = "modulator"
    BLOCKER = "blocker"
    INDUCER = "inducer"
    SUBSTRATE = "substrate"
    CARRIER = "carrier"
    TRANSPORTER = "transporter"
    OTHER = "other"
    UNKNOWN = "unknown"


class TargetType(str, Enum):
    """Types of drug targets."""

    TARGET = "target"  # Pharmacological target
    ENZYME = "enzyme"
    CARRIER = "carrier"
    TRANSPORTER = "transporter"


# =============================================================================
# Supporting Schemas
# =============================================================================


class ExternalIdentifier(BaseModel):
    """External database identifier."""

    resource: str
    identifier: str


class DrugSynonym(BaseModel):
    """Drug synonym/alias."""

    name: str
    language: str | None = None
    coder: str | None = None


class DrugCategory(BaseModel):
    """Drug classification category."""

    category: str
    mesh_id: str | None = None


class DrugInteraction(BaseModel):
    """Drug-drug interaction."""

    drugbank_id: str
    drug_name: str
    description: str | None = None


class DrugPathway(BaseModel):
    """Pathway involvement."""

    smpdb_id: str | None = None
    name: str
    category: str | None = None
    drugs_in_pathway: list[str] = Field(default_factory=list)


# =============================================================================
# ADMET Schema
# =============================================================================


class ADMETProperties(BaseModel):
    """
    ADMET (Absorption, Distribution, Metabolism, Excretion, Toxicity) properties.

    Available when DrugBank provides pharmacokinetic data.
    """

    # --- Absorption ---
    absorption: str | None = Field(None, description="Absorption description")
    bioavailability: str | None = Field(None, description="Oral bioavailability")
    caco2_permeability: Decimal | None = Field(None, description="Caco-2 permeability")

    # --- Distribution ---
    distribution: str | None = Field(None, description="Distribution description")
    volume_of_distribution: str | None = None
    protein_binding: str | None = Field(None, description="Plasma protein binding %")

    # --- Metabolism ---
    metabolism: str | None = Field(None, description="Metabolism description")
    route_of_elimination: str | None = None
    half_life: str | None = Field(None, description="Elimination half-life")
    clearance: str | None = None

    # --- Excretion ---
    excretion: str | None = None

    # --- Toxicity ---
    toxicity: str | None = Field(None, description="Toxicity information")
    ld50: str | None = Field(None, description="Lethal dose 50%")

    # --- Pharmacodynamics ---
    pharmacodynamics: str | None = None
    mechanism_of_action: str | None = None
    indication: str | None = None

    model_config = {"extra": "allow"}


# =============================================================================
# Drug-Target Interaction Schema
# =============================================================================


class DrugTargetInteraction(BaseModel):
    """
    Drug-target interaction (DTI) record.

    Represents the relationship between a drug and its target.
    """

    # --- Drug Info ---
    drugbank_id: str
    drug_name: str | None = None

    # --- Target Info ---
    target_id: str | None = Field(None, description="DrugBank target ID")
    target_name: str | None = None
    target_type: TargetType = TargetType.TARGET
    gene_name: str | None = None
    uniprot_id: str | None = Field(None, description="UniProt accession")

    # --- Interaction Details ---
    action: TargetAction = TargetAction.UNKNOWN
    actions: list[str] = Field(default_factory=list, description="All action types")
    known_action: bool = Field(default=False, description="Is action confirmed?")

    # --- Organism ---
    organism: str | None = None

    # --- References ---
    references: list[str] = Field(default_factory=list)
    pubmed_ids: list[str] = Field(default_factory=list)

    # --- Polypeptide Info ---
    polypeptide_name: str | None = None
    polypeptide_sequence: str | None = None

    model_config = {"extra": "allow"}


# =============================================================================
# Main Drug Schema
# =============================================================================


class DrugBankDrug(BaseModel):
    """
    Normalized drug data from DrugBank.

    Maps to internal Molecule model with additional drug-specific fields.
    """

    # --- DrugBank Identification ---
    drugbank_id: str = Field(..., description="DrugBank ID (e.g., DB00945)")
    secondary_ids: list[str] = Field(default_factory=list)

    # --- Drug Type & Status ---
    drug_type: DrugType = DrugType.UNKNOWN
    groups: list[DrugGroup] = Field(default_factory=list)
    is_approved: bool = False

    # --- Names ---
    name: str = Field(..., description="Generic name")
    description: str | None = None
    synonyms: list[DrugSynonym] = Field(default_factory=list)
    brands: list[str] = Field(default_factory=list, description="Brand names")

    # --- Chemical Structure ---
    cas_number: str | None = Field(None, description="CAS registry number")
    unii: str | None = Field(None, description="FDA UNII identifier")
    canonical_smiles: str | None = Field(None, alias="smiles")
    inchi: str | None = None
    inchikey: str | None = None
    molecular_formula: str | None = Field(None, alias="formula")

    # --- Molecular Properties ---
    molecular_weight: Decimal | None = Field(None, alias="mw")
    average_mass: Decimal | None = None
    monoisotopic_mass: Decimal | None = None
    state: str | None = Field(None, description="Physical state")
    logp: Decimal | None = Field(None, description="Calculated LogP")
    psa: Decimal | None = Field(None, description="Polar surface area")
    hbd: int | None = Field(None, description="H-bond donors")
    hba: int | None = Field(None, description="H-bond acceptors")
    rotatable_bonds: int | None = None

    # --- Classification ---
    categories: list[DrugCategory] = Field(default_factory=list)
    atc_codes: list[str] = Field(default_factory=list, description="ATC classification")

    # --- Clinical Info ---
    indication: str | None = None
    pharmacodynamics: str | None = None
    mechanism_of_action: str | None = None

    # --- ADMET ---
    admet: ADMETProperties = Field(default_factory=ADMETProperties)

    # --- Cross References ---
    external_ids: list[ExternalIdentifier] = Field(default_factory=list)
    chembl_id: str | None = None
    pubchem_cid: int | None = None
    kegg_id: str | None = None
    chebi_id: str | None = None
    pdb_ids: list[str] = Field(default_factory=list)

    # --- Interactions ---
    drug_interactions: list[DrugInteraction] = Field(default_factory=list)
    food_interactions: list[str] = Field(default_factory=list)
    pathways: list[DrugPathway] = Field(default_factory=list)

    # --- Targets (summary) ---
    target_count: int = 0
    enzyme_count: int = 0
    carrier_count: int = 0
    transporter_count: int = 0

    # --- Metadata ---
    created_at: datetime | None = None
    updated_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "extra": "allow"}

    @property
    def all_synonyms(self) -> list[str]:
        """Get all synonym names."""
        return [s.name for s in self.synonyms]

    @property
    def is_small_molecule(self) -> bool:
        """Check if drug is a small molecule."""
        return self.drug_type == DrugType.SMALL_MOLECULE


# =============================================================================
# Search Results
# =============================================================================


class DrugSearchHit(BaseModel):
    """A single drug search result."""

    drugbank_id: str
    name: str
    drug_type: DrugType = DrugType.UNKNOWN
    groups: list[DrugGroup] = Field(default_factory=list)
    cas_number: str | None = None
    molecular_weight: Decimal | None = None


class DrugSearchResult(BaseModel):
    """Paginated drug search results."""

    query: str
    hits: list[DrugSearchHit] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 25
    has_more: bool = False

    @property
    def drugbank_ids(self) -> list[str]:
        """Get list of DrugBank IDs from hits."""
        return [hit.drugbank_id for hit in self.hits]


class DTISearchResult(BaseModel):
    """Drug-target interaction search results."""

    drugbank_id: str
    drug_name: str | None = None
    interactions: list[DrugTargetInteraction] = Field(default_factory=list)
    total_count: int = 0


# =============================================================================
# Configuration Status
# =============================================================================


class DrugBankMode(str, Enum):
    """DrugBank connector operating mode."""

    API = "api"  # Using DrugBank API with credentials
    LOCAL = "local"  # Using local XML/CSV dataset
    NOT_CONFIGURED = "not_configured"  # No access configured


class DrugBankStatus(BaseModel):
    """Current connector configuration status."""

    mode: DrugBankMode
    is_configured: bool
    api_available: bool = False
    local_data_available: bool = False
    local_data_path: str | None = None
    drug_count: int | None = None
    message: str | None = None
