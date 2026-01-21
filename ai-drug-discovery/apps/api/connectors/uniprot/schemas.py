"""
UniProt-specific schemas for normalized data.

These schemas represent UniProt data normalized to our internal format,
ready for import into Target and related models.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class ProteinExistence(str, Enum):
    """UniProt protein existence evidence levels."""

    EVIDENCE_AT_PROTEIN_LEVEL = "Evidence at protein level"
    EVIDENCE_AT_TRANSCRIPT_LEVEL = "Evidence at transcript level"
    INFERRED_FROM_HOMOLOGY = "Inferred from homology"
    PREDICTED = "Predicted"
    UNCERTAIN = "Uncertain"


class ReviewStatus(str, Enum):
    """UniProt review status."""

    REVIEWED = "reviewed"  # Swiss-Prot
    UNREVIEWED = "unreviewed"  # TrEMBL


class FeatureType(str, Enum):
    """UniProt sequence feature types relevant for drug discovery."""

    DOMAIN = "Domain"
    BINDING_SITE = "Binding site"
    ACTIVE_SITE = "Active site"
    METAL_BINDING = "Metal binding"
    SITE = "Site"
    MODIFIED_RESIDUE = "Modified residue"
    LIPIDATION = "Lipidation"
    GLYCOSYLATION = "Glycosylation site"
    DISULFIDE_BOND = "Disulfide bond"
    TRANSMEMBRANE = "Transmembrane"
    SIGNAL = "Signal peptide"
    PROPEPTIDE = "Propeptide"
    CHAIN = "Chain"
    REGION = "Region"
    MOTIF = "Motif"
    COMPOSITIONAL_BIAS = "Compositional bias"
    COILED_COIL = "Coiled coil"
    HELIX = "Helix"
    STRAND = "Beta strand"
    TURN = "Turn"


# =============================================================================
# Annotation Schemas
# =============================================================================


class GeneInfo(BaseModel):
    """Gene information for a protein."""

    name: str | None = Field(None, description="Primary gene name")
    synonyms: list[str] = Field(default_factory=list, description="Gene name synonyms")
    orf_names: list[str] = Field(default_factory=list, description="ORF names")
    ordered_locus_names: list[str] = Field(default_factory=list)


class OrganismInfo(BaseModel):
    """Organism information."""

    scientific_name: str = Field(..., description="Scientific name (e.g., Homo sapiens)")
    common_name: str | None = Field(None, description="Common name (e.g., Human)")
    tax_id: int | None = Field(None, description="NCBI Taxonomy ID")
    lineage: list[str] = Field(default_factory=list, description="Taxonomic lineage")


class ProteinName(BaseModel):
    """Protein naming information."""

    recommended_name: str | None = Field(None, description="Recommended full name")
    short_names: list[str] = Field(default_factory=list)
    alternative_names: list[str] = Field(default_factory=list)
    ec_numbers: list[str] = Field(default_factory=list, description="EC enzyme numbers")


class SequenceFeature(BaseModel):
    """A sequence feature/annotation."""

    type: FeatureType | str
    description: str | None = None
    start: int | None = None
    end: int | None = None
    evidence: str | None = None


class CrossReference(BaseModel):
    """Cross-reference to external database."""

    database: str
    identifier: str
    properties: dict[str, str] = Field(default_factory=dict)


class FunctionAnnotation(BaseModel):
    """Functional annotation."""

    text: str
    evidence: list[str] = Field(default_factory=list)


class SubcellularLocation(BaseModel):
    """Subcellular location annotation."""

    location: str
    topology: str | None = None
    orientation: str | None = None


class DiseaseAssociation(BaseModel):
    """Disease association information."""

    disease_name: str
    disease_id: str | None = None  # MIM number
    description: str | None = None
    evidence: str | None = None


class DrugInteraction(BaseModel):
    """Drug interaction from DrugBank cross-reference."""

    drugbank_id: str
    drug_name: str | None = None


# =============================================================================
# Main Target Schema
# =============================================================================


class UniProtTarget(BaseModel):
    """
    Normalized protein/target data from UniProt.

    Maps to internal Target model.
    """

    # --- UniProt Identification ---
    uniprot_id: str = Field(..., description="UniProt accession (e.g., P00533)")
    entry_name: str | None = Field(None, description="UniProt entry name (e.g., EGFR_HUMAN)")

    # --- Review Status ---
    review_status: ReviewStatus = Field(default=ReviewStatus.UNREVIEWED)
    protein_existence: ProteinExistence | None = None

    # --- Names ---
    protein_name: ProteinName = Field(default_factory=ProteinName)

    # --- Gene ---
    gene: GeneInfo = Field(default_factory=GeneInfo)

    # --- Organism ---
    organism: OrganismInfo

    # --- Sequence ---
    sequence: str | None = Field(None, description="Amino acid sequence")
    sequence_length: int | None = None
    sequence_mass: int | None = Field(None, description="Molecular mass in Da")
    sequence_checksum: str | None = Field(None, description="CRC64 checksum")

    # --- Function ---
    function: list[FunctionAnnotation] = Field(default_factory=list)
    catalytic_activity: list[str] = Field(default_factory=list)
    pathway: list[str] = Field(default_factory=list)

    # --- Localization ---
    subcellular_locations: list[SubcellularLocation] = Field(default_factory=list)

    # --- Structure Features ---
    domains: list[SequenceFeature] = Field(default_factory=list)
    binding_sites: list[SequenceFeature] = Field(default_factory=list)
    active_sites: list[SequenceFeature] = Field(default_factory=list)
    other_features: list[SequenceFeature] = Field(default_factory=list)

    # --- Classification ---
    keywords: list[str] = Field(default_factory=list, description="UniProt keywords")
    go_terms: list[str] = Field(default_factory=list, description="GO annotations")
    protein_families: list[str] = Field(default_factory=list, description="InterPro/Pfam families")

    # --- Disease ---
    disease_associations: list[DiseaseAssociation] = Field(default_factory=list)

    # --- Cross References ---
    pdb_ids: list[str] = Field(default_factory=list, description="PDB structure IDs")
    chembl_id: str | None = Field(None, description="ChEMBL target ID")
    drugbank_drugs: list[DrugInteraction] = Field(default_factory=list)
    ensembl_gene_id: str | None = None
    refseq_ids: list[str] = Field(default_factory=list)

    # --- Metadata ---
    created_at: datetime | None = Field(None, description="Entry creation date")
    modified_at: datetime | None = Field(None, description="Last modification date")
    version: int | None = Field(None, description="Entry version")
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "extra": "allow"}

    @property
    def display_name(self) -> str:
        """Get best display name for the target."""
        if self.protein_name.recommended_name:
            return self.protein_name.recommended_name
        if self.gene.name:
            return self.gene.name
        return self.uniprot_id

    @property
    def gene_symbol(self) -> str | None:
        """Get primary gene symbol."""
        return self.gene.name


# =============================================================================
# Search Results
# =============================================================================


class TargetSearchHit(BaseModel):
    """A single search result hit."""

    uniprot_id: str
    entry_name: str | None = None
    protein_name: str | None = None
    gene_name: str | None = None
    organism: str | None = None
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    sequence_length: int | None = None


class TargetSearchResult(BaseModel):
    """Paginated target search results."""

    query: str
    hits: list[TargetSearchHit] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 25
    has_more: bool = False

    @property
    def uniprot_ids(self) -> list[str]:
        """Get list of UniProt IDs from hits."""
        return [hit.uniprot_id for hit in self.hits]


# =============================================================================
# Simplified Target (for quick lookups)
# =============================================================================


class TargetSummary(BaseModel):
    """
    Simplified target summary for quick lookups.

    Contains essential fields needed for target identification and display.
    """

    uniprot_id: str
    entry_name: str | None = None
    protein_name: str | None = None
    gene_symbol: str | None = None
    organism: str
    tax_id: int | None = None
    sequence_length: int | None = None
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    chembl_id: str | None = None
    pdb_count: int = 0

    model_config = {"extra": "allow"}
