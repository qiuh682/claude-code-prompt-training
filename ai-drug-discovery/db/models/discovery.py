"""
SQLAlchemy models for AI Drug Discovery platform.

Core entities:
- Molecule: Chemical compounds with SMILES, InChI, properties, fingerprints
- Target: Biological targets (proteins) with UniProt IDs, sequences
- Project: Research projects grouping molecules and targets
- Assay: Experimental measurements linking molecules to targets
- Prediction: ML model predictions

Association tables:
- MoleculeTarget: Many-to-many molecule-target relationships
- ProjectMolecule: Many-to-many project-molecule relationships
- ProjectTarget: Many-to-many project-target relationships
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base_model import AuditedModel, BaseModel, TimestampMixin

# =============================================================================
# Molecule Model
# =============================================================================


class Molecule(AuditedModel):
    """
    Chemical compound entity.

    Uniqueness: InChIKey within organization (partial unique index on active records).
    Fast lookup: smiles_hash (SHA-256 of canonical SMILES) for O(1) exact match.
    Similarity search: fingerprint columns (Morgan, MACCS) for future RDKit integration.
    """

    __tablename__ = "molecules"

    # --- Tenant Isolation ---
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Chemical Identifiers ---
    canonical_smiles: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        comment="Canonical SMILES string",
    )
    inchi: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="InChI string (can be long)",
    )
    inchi_key: Mapped[str] = mapped_column(
        String(27),
        nullable=False,
        comment="InChIKey (fixed 27 chars)",
    )
    smiles_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 of canonical_smiles for fast lookup",
    )

    # --- Basic Properties ---
    molecular_formula: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="e.g., C21H30O2",
    )
    molecular_weight: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
        comment="Molecular weight in Daltons",
    )
    exact_mass: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6),
        nullable=True,
        comment="Monoisotopic mass",
    )
    logp: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 3),
        nullable=True,
        comment="Lipophilicity (logP)",
    )
    hbd: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Hydrogen bond donors",
    )
    hba: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Hydrogen bond acceptors",
    )
    tpsa: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2),
        nullable=True,
        comment="Topological polar surface area",
    )
    rotatable_bonds: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Rotatable bond count",
    )

    # --- Extended Descriptors ---
    num_rings: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Total ring count",
    )
    num_aromatic_rings: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Aromatic ring count",
    )
    num_heavy_atoms: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Heavy atom count (non-hydrogen)",
    )
    fraction_sp3: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="Fraction of sp3 carbons (0.0000-1.0000)",
    )
    lipinski_violations: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Number of Lipinski Rule of 5 violations (0-4)",
    )

    # --- Fingerprints (for similarity search) ---
    fingerprint_morgan: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
        comment="Morgan fingerprint (2048 bits, radius 2)",
    )
    fingerprint_maccs: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
        comment="MACCS keys (167 bits)",
    )
    fingerprint_rdkit: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
        comment="RDKit topological fingerprint (2048 bits)",
    )

    # --- Naming ---
    name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Common name",
    )
    synonyms: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Alternative names",
    )

    # --- Extensible Metadata ---
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Extensible properties",
    )

    # --- Relationships ---
    organization = relationship("Organization", back_populates="molecules")
    assays = relationship("Assay", back_populates="molecule", cascade="all, delete-orphan")
    predictions = relationship(
        "Prediction", back_populates="molecule", cascade="all, delete-orphan"
    )
    target_associations = relationship(
        "MoleculeTarget", back_populates="molecule", cascade="all, delete-orphan"
    )
    project_associations = relationship(
        "ProjectMolecule", back_populates="molecule", cascade="all, delete-orphan"
    )
    fingerprints = relationship(
        "MoleculeFingerprint", back_populates="molecule", cascade="all, delete-orphan"
    )

    # --- Table Configuration ---
    __table_args__ = (
        # Unique InChIKey per org (only for non-deleted records)
        UniqueConstraint(
            "organization_id",
            "inchi_key",
            name="uq_molecule_org_inchikey",
        ),
        # Indexes for chemical searches
        Index("ix_molecules_org_inchikey", "organization_id", "inchi_key"),
        Index("ix_molecules_org_smiles_hash", "organization_id", "smiles_hash"),
        Index("ix_molecules_canonical_smiles", "canonical_smiles"),
        Index("ix_molecules_org_name", "organization_id", "name"),
        Index("ix_molecules_org_mw", "organization_id", "molecular_weight"),
        Index("ix_molecules_org_created", "organization_id", "created_at"),
        # Note: Fingerprint indexes require RDKit extension, placeholder for future
        {"comment": "Chemical compounds with structure and properties"},
    )

    def __repr__(self) -> str:
        return f"<Molecule {self.inchi_key[:14]}... ({self.name or 'unnamed'})>"


# =============================================================================
# MoleculeFingerprint Model (for vector similarity indexing)
# =============================================================================


class MoleculeFingerprint(BaseModel, TimestampMixin):
    """
    Molecular fingerprint storage with metadata for similarity search.

    This table stores fingerprints with their generation parameters, enabling:
    - Multiple fingerprint types per molecule
    - Vector similarity indexing (pg_similarity, pgvector, or external like Pinecone)
    - Reproducibility tracking (parameters used to generate)

    Fingerprint Index Strategies:
    1. PostgreSQL pg_similarity: Install RDKit cartridge, use BIT(n) columns
    2. pgvector: Convert fingerprints to float vectors, use ivfflat/hnsw indexes
    3. Pinecone/external: Store fingerprints here, sync to vector DB for search
    """

    __tablename__ = "molecule_fingerprints"

    # --- Foreign Key ---
    molecule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("molecules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Fingerprint Type ---
    fingerprint_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="morgan, maccs, rdkit, ecfp4, fcfp4, etc.",
    )

    # --- Fingerprint Data ---
    fingerprint_bytes: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
        comment="Raw fingerprint bytes",
    )
    fingerprint_base64: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Base64 encoded for JSON APIs",
    )
    fingerprint_hex: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Hex encoded for debugging",
    )

    # --- Generation Parameters (for reproducibility) ---
    num_bits: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="Number of bits in fingerprint",
    )
    radius: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Radius for circular fingerprints (Morgan)",
    )
    use_features: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Feature-based (FCFP) vs atom-based (ECFP)",
    )

    # --- Statistics ---
    num_on_bits: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Number of bits set to 1",
    )

    # --- External Index Reference ---
    external_index_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="ID in external vector DB (e.g., Pinecone vector ID)",
    )
    external_index_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When last synced to external index",
    )

    # --- Relationships ---
    molecule = relationship("Molecule", back_populates="fingerprints")

    # --- Table Configuration ---
    __table_args__ = (
        # Unique fingerprint type per molecule
        UniqueConstraint(
            "molecule_id",
            "fingerprint_type",
            name="uq_molecule_fingerprint_type",
        ),
        Index("ix_molecule_fp_type", "fingerprint_type"),
        Index("ix_molecule_fp_external_id", "external_index_id"),
        # Note: For pg_similarity or pgvector, add specialized indexes via migration
        {"comment": "Molecular fingerprints for similarity search"},
    )

    def __repr__(self) -> str:
        return f"<MoleculeFingerprint {self.fingerprint_type} ({self.num_bits} bits)>"


# =============================================================================
# Target Model
# =============================================================================


class Target(AuditedModel):
    """
    Biological target entity (proteins, receptors, enzymes).

    Uniqueness: UniProt ID within organization (partial unique index on active records).
    """

    __tablename__ = "targets"

    # --- Tenant Isolation ---
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Identifiers ---
    uniprot_id: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="UniProt accession (e.g., P00533)",
    )
    gene_symbol: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Gene symbol (e.g., EGFR)",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Full target name",
    )

    # --- Organism ---
    organism: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        server_default="Homo sapiens",
        comment="Species",
    )

    # --- Sequence Data ---
    sequence: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Amino acid sequence",
    )
    sequence_length: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Amino acid count",
    )

    # --- Classification ---
    family: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Target family (kinase, GPCR, etc.)",
    )
    subfamily: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="More specific classification",
    )

    # --- Structure References ---
    pdb_ids: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="PDB structure IDs",
    )

    # --- Description ---
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Functional description",
    )

    # --- Extensible Metadata ---
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Extensible properties",
    )

    # --- Relationships ---
    organization = relationship("Organization", back_populates="targets")
    assays = relationship("Assay", back_populates="target")
    predictions = relationship("Prediction", back_populates="target")
    molecule_associations = relationship(
        "MoleculeTarget", back_populates="target", cascade="all, delete-orphan"
    )
    project_associations = relationship(
        "ProjectTarget", back_populates="target", cascade="all, delete-orphan"
    )

    # --- Table Configuration ---
    __table_args__ = (
        # Unique UniProt ID per org (only for non-deleted, non-null)
        Index(
            "ix_targets_org_uniprot",
            "organization_id",
            "uniprot_id",
            unique=True,
            postgresql_where=(uniprot_id.isnot(None)),
        ),
        Index("ix_targets_org_gene", "organization_id", "gene_symbol"),
        Index("ix_targets_org_family", "organization_id", "family"),
        {"comment": "Biological targets (proteins, receptors, enzymes)"},
    )

    def __repr__(self) -> str:
        return f"<Target {self.uniprot_id or self.gene_symbol or self.name}>"


# =============================================================================
# Project Model
# =============================================================================


class Project(AuditedModel):
    """
    Research project grouping molecules, targets, and experiments.

    Uniqueness: Project name within organization.
    """

    __tablename__ = "projects"

    # --- Tenant Isolation ---
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Basic Info ---
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Project name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Project description",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="active",
        comment="active, archived, completed",
    )
    therapeutic_area: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="e.g., Oncology, CNS, Cardiovascular",
    )

    # --- Extensible Metadata ---
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Extensible properties",
    )

    # --- Relationships ---
    organization = relationship("Organization", back_populates="projects")
    assays = relationship("Assay", back_populates="project")
    predictions = relationship("Prediction", back_populates="project")
    molecule_associations = relationship(
        "ProjectMolecule", back_populates="project", cascade="all, delete-orphan"
    )
    target_associations = relationship(
        "ProjectTarget", back_populates="project", cascade="all, delete-orphan"
    )

    # --- Table Configuration ---
    __table_args__ = (
        # Unique name per org
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_project_org_name",
        ),
        Index("ix_projects_org_status", "organization_id", "status"),
        {"comment": "Research projects grouping molecules and targets"},
    )

    def __repr__(self) -> str:
        return f"<Project {self.name} ({self.status})>"


# =============================================================================
# Assay Model
# =============================================================================


class Assay(AuditedModel):
    """
    Experimental measurement linking molecules to targets.

    Stores IC50, EC50, Ki, % inhibition, and other assay results.
    """

    __tablename__ = "assays"

    # --- Tenant Isolation ---
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Relationships ---
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    molecule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("molecules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("targets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Nullable for ADMET assays",
    )

    # --- Assay Type ---
    assay_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="binding, functional, admet, cytotox",
    )
    assay_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Specific assay name",
    )

    # --- Results ---
    result_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="IC50, EC50, Ki, % inhibition, etc.",
    )
    result_value: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 6),
        nullable=True,
        comment="Numeric result",
    )
    result_unit: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="nM, uM, %, etc.",
    )
    result_qualifier: Mapped[str | None] = mapped_column(
        String(5),
        nullable=True,
        comment="=, <, >, ~",
    )
    confidence: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="high, medium, low",
    )

    # --- Conditions ---
    conditions: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Temperature, pH, concentration, time, etc.",
    )

    # --- Source ---
    source: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="internal, ChEMBL, literature",
    )
    source_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="External reference ID",
    )

    # --- Extensible Metadata ---
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Extensible properties",
    )

    # --- Relationships ---
    organization = relationship("Organization", back_populates="assays")
    project = relationship("Project", back_populates="assays")
    molecule = relationship("Molecule", back_populates="assays")
    target = relationship("Target", back_populates="assays")

    # --- Table Configuration ---
    __table_args__ = (
        Index("ix_assays_org_type", "organization_id", "assay_type"),
        Index("ix_assays_molecule_target", "molecule_id", "target_id"),
        CheckConstraint(
            "result_qualifier IN ('=', '<', '>', '>=', '<=', '~')",
            name="ck_assay_result_qualifier",
        ),
        {"comment": "Experimental assay results"},
    )

    def __repr__(self) -> str:
        return f"<Assay {self.assay_type} {self.result_type}={self.result_value}>"


# =============================================================================
# Prediction Model
# =============================================================================


class Prediction(BaseModel, TimestampMixin):
    """
    ML model prediction.

    Predictions are immutable (no updated_by/updated_at).
    Soft delete supported for cleanup.
    """

    __tablename__ = "predictions"

    # --- Tenant Isolation ---
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Relationships ---
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    molecule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("molecules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("targets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="For binding/activity predictions",
    )

    # --- Model Info ---
    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Model identifier",
    )
    model_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Model version",
    )
    prediction_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="activity, admet, toxicity, binding",
    )

    # --- Prediction Results ---
    predicted_value: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 6),
        nullable=True,
        comment="Numeric prediction",
    )
    predicted_class: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Classification result",
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="0.0000 - 1.0000",
    )
    uncertainty: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 6),
        nullable=True,
        comment="Model uncertainty estimate",
    )

    # --- Explainability ---
    input_features: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Features used for prediction",
    )
    explanation: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="SHAP values, attention weights, etc.",
    )

    # --- Extensible Metadata ---
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Extensible properties",
    )

    # --- Audit (created only, predictions are immutable) ---
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )

    # --- Soft Delete ---
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # --- Relationships ---
    organization = relationship("Organization", back_populates="predictions")
    project = relationship("Project", back_populates="predictions")
    molecule = relationship("Molecule", back_populates="predictions")
    target = relationship("Target", back_populates="predictions")

    # --- Table Configuration ---
    __table_args__ = (
        Index("ix_predictions_org_model", "organization_id", "model_name"),
        Index("ix_predictions_org_type", "organization_id", "prediction_type"),
        Index("ix_predictions_org_created", "organization_id", "created_at"),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_prediction_confidence_range",
        ),
        {"comment": "ML model predictions"},
    )

    def __repr__(self) -> str:
        return f"<Prediction {self.model_name} {self.prediction_type}>"


# =============================================================================
# Association Tables
# =============================================================================


class MoleculeTarget(BaseModel):
    """
    Many-to-many: Molecule <-> Target relationship.

    Tracks which molecules have been tested/linked to which targets.
    """

    __tablename__ = "molecule_targets"

    molecule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("molecules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("targets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="tested",
        comment="tested, active, inactive, unknown",
    )

    # --- Relationships ---
    molecule = relationship("Molecule", back_populates="target_associations")
    target = relationship("Target", back_populates="molecule_associations")

    # --- Table Configuration ---
    __table_args__ = (
        UniqueConstraint("molecule_id", "target_id", name="uq_molecule_target"),
        {"comment": "Molecule-Target relationships"},
    )

    def __repr__(self) -> str:
        return f"<MoleculeTarget {self.molecule_id} -> {self.target_id}>"


class ProjectMolecule(BaseModel):
    """
    Many-to-many: Project <-> Molecule relationship.

    Tracks which molecules belong to which projects.
    """

    __tablename__ = "project_molecules"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    molecule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("molecules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    added_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional notes",
    )

    # --- Relationships ---
    project = relationship("Project", back_populates="molecule_associations")
    molecule = relationship("Molecule", back_populates="project_associations")

    # --- Table Configuration ---
    __table_args__ = (
        UniqueConstraint("project_id", "molecule_id", name="uq_project_molecule"),
        {"comment": "Project-Molecule relationships"},
    )

    def __repr__(self) -> str:
        return f"<ProjectMolecule {self.project_id} <- {self.molecule_id}>"


class ProjectTarget(BaseModel):
    """
    Many-to-many: Project <-> Target relationship.

    Tracks which targets are studied in which projects.
    """

    __tablename__ = "project_targets"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("targets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Primary target for project",
    )
    added_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- Relationships ---
    project = relationship("Project", back_populates="target_associations")
    target = relationship("Target", back_populates="project_associations")

    # --- Table Configuration ---
    __table_args__ = (
        UniqueConstraint("project_id", "target_id", name="uq_project_target"),
        {"comment": "Project-Target relationships"},
    )

    def __repr__(self) -> str:
        return f"<ProjectTarget {self.project_id} <- {self.target_id}>"
