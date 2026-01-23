"""Add discovery models (Task 1.3)

Creates tables for drug discovery domain:
- molecules: Chemical compounds with SMILES, InChI, properties, fingerprints
- targets: Biological targets with UniProt IDs, sequences
- projects: Research projects grouping molecules and targets
- assays: Experimental measurements
- predictions: ML model predictions
- Association tables: molecule_targets, project_molecules, project_targets

Revision ID: a1b2c3d4e5f6
Revises: 4039686027fc
Create Date: 2026-01-20 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "4039686027fc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    # ==========================================================================
    # MOLECULES TABLE
    # ==========================================================================
    op.create_table(
        "molecules",
        # Primary key
        sa.Column("id", sa.UUID(), nullable=False),
        # Tenant isolation
        sa.Column("organization_id", sa.UUID(), nullable=False),
        # Chemical identifiers
        sa.Column(
            "canonical_smiles",
            sa.String(length=2000),
            nullable=False,
            comment="Canonical SMILES string",
        ),
        sa.Column("inchi", sa.Text(), nullable=True, comment="InChI string (can be long)"),
        sa.Column(
            "inchi_key",
            sa.String(length=27),
            nullable=False,
            comment="InChIKey (fixed 27 chars)",
        ),
        sa.Column(
            "smiles_hash",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 of canonical_smiles for fast lookup",
        ),
        # Basic properties
        sa.Column(
            "molecular_formula",
            sa.String(length=100),
            nullable=True,
            comment="e.g., C21H30O2",
        ),
        sa.Column(
            "molecular_weight",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
            comment="Molecular weight in Daltons",
        ),
        sa.Column(
            "exact_mass",
            sa.Numeric(precision=12, scale=6),
            nullable=True,
            comment="Monoisotopic mass",
        ),
        sa.Column(
            "logp",
            sa.Numeric(precision=6, scale=3),
            nullable=True,
            comment="Lipophilicity (logP)",
        ),
        sa.Column(
            "hbd", sa.SmallInteger(), nullable=True, comment="Hydrogen bond donors"
        ),
        sa.Column(
            "hba", sa.SmallInteger(), nullable=True, comment="Hydrogen bond acceptors"
        ),
        sa.Column(
            "tpsa",
            sa.Numeric(precision=8, scale=2),
            nullable=True,
            comment="Topological polar surface area",
        ),
        sa.Column(
            "rotatable_bonds",
            sa.SmallInteger(),
            nullable=True,
            comment="Rotatable bond count",
        ),
        # Fingerprints
        sa.Column(
            "fingerprint_morgan",
            sa.LargeBinary(),
            nullable=True,
            comment="Morgan fingerprint (2048 bits)",
        ),
        sa.Column(
            "fingerprint_maccs",
            sa.LargeBinary(),
            nullable=True,
            comment="MACCS keys (166 bits)",
        ),
        # Naming
        sa.Column("name", sa.String(length=255), nullable=True, comment="Common name"),
        sa.Column(
            "synonyms",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            comment="Alternative names",
        ),
        # Metadata
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
            comment="Extensible properties",
        ),
        # Audit fields
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Soft delete
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "inchi_key", name="uq_molecule_org_inchikey"),
        comment="Chemical compounds with structure and properties",
    )
    # Molecule indexes
    op.create_index("ix_molecules_organization_id", "molecules", ["organization_id"])
    op.create_index("ix_molecules_org_inchikey", "molecules", ["organization_id", "inchi_key"])
    op.create_index("ix_molecules_org_smiles_hash", "molecules", ["organization_id", "smiles_hash"])
    op.create_index("ix_molecules_canonical_smiles", "molecules", ["canonical_smiles"])
    op.create_index("ix_molecules_org_name", "molecules", ["organization_id", "name"])
    op.create_index("ix_molecules_org_mw", "molecules", ["organization_id", "molecular_weight"])
    op.create_index("ix_molecules_org_created", "molecules", ["organization_id", "created_at"])
    op.create_index("ix_molecules_deleted_at", "molecules", ["deleted_at"])

    # ==========================================================================
    # TARGETS TABLE
    # ==========================================================================
    op.create_table(
        "targets",
        # Primary key
        sa.Column("id", sa.UUID(), nullable=False),
        # Tenant isolation
        sa.Column("organization_id", sa.UUID(), nullable=False),
        # Identifiers
        sa.Column(
            "uniprot_id",
            sa.String(length=20),
            nullable=True,
            comment="UniProt accession (e.g., P00533)",
        ),
        sa.Column(
            "gene_symbol",
            sa.String(length=50),
            nullable=True,
            comment="Gene symbol (e.g., EGFR)",
        ),
        sa.Column("name", sa.String(length=255), nullable=False, comment="Full target name"),
        # Organism
        sa.Column(
            "organism",
            sa.String(length=100),
            nullable=False,
            server_default="Homo sapiens",
            comment="Species",
        ),
        # Sequence data
        sa.Column("sequence", sa.Text(), nullable=True, comment="Amino acid sequence"),
        sa.Column(
            "sequence_length", sa.SmallInteger(), nullable=True, comment="Amino acid count"
        ),
        # Classification
        sa.Column(
            "family",
            sa.String(length=100),
            nullable=True,
            comment="Target family (kinase, GPCR, etc.)",
        ),
        sa.Column(
            "subfamily",
            sa.String(length=100),
            nullable=True,
            comment="More specific classification",
        ),
        # Structure references
        sa.Column(
            "pdb_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            comment="PDB structure IDs",
        ),
        # Description
        sa.Column("description", sa.Text(), nullable=True, comment="Functional description"),
        # Metadata
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
            comment="Extensible properties",
        ),
        # Audit fields
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Soft delete
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        comment="Biological targets (proteins, receptors, enzymes)",
    )
    # Target indexes
    op.create_index("ix_targets_organization_id", "targets", ["organization_id"])
    op.create_index(
        "ix_targets_org_uniprot",
        "targets",
        ["organization_id", "uniprot_id"],
        unique=True,
        postgresql_where=sa.text("uniprot_id IS NOT NULL"),
    )
    op.create_index("ix_targets_org_gene", "targets", ["organization_id", "gene_symbol"])
    op.create_index("ix_targets_org_family", "targets", ["organization_id", "family"])
    op.create_index("ix_targets_deleted_at", "targets", ["deleted_at"])

    # ==========================================================================
    # PROJECTS TABLE
    # ==========================================================================
    op.create_table(
        "projects",
        # Primary key
        sa.Column("id", sa.UUID(), nullable=False),
        # Tenant isolation
        sa.Column("organization_id", sa.UUID(), nullable=False),
        # Basic info
        sa.Column("name", sa.String(length=255), nullable=False, comment="Project name"),
        sa.Column("description", sa.Text(), nullable=True, comment="Project description"),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="active",
            comment="active, archived, completed",
        ),
        sa.Column(
            "therapeutic_area",
            sa.String(length=100),
            nullable=True,
            comment="e.g., Oncology, CNS, Cardiovascular",
        ),
        # Metadata
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
            comment="Extensible properties",
        ),
        # Audit fields
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Soft delete
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "name", name="uq_project_org_name"),
        comment="Research projects grouping molecules and targets",
    )
    # Project indexes
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])
    op.create_index("ix_projects_org_status", "projects", ["organization_id", "status"])
    op.create_index("ix_projects_deleted_at", "projects", ["deleted_at"])

    # ==========================================================================
    # ASSAYS TABLE
    # ==========================================================================
    op.create_table(
        "assays",
        # Primary key
        sa.Column("id", sa.UUID(), nullable=False),
        # Tenant isolation
        sa.Column("organization_id", sa.UUID(), nullable=False),
        # Relationships
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("molecule_id", sa.UUID(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=True, comment="Nullable for ADMET assays"),
        # Assay type
        sa.Column(
            "assay_type",
            sa.String(length=50),
            nullable=False,
            comment="binding, functional, admet, cytotox",
        ),
        sa.Column(
            "assay_name", sa.String(length=255), nullable=True, comment="Specific assay name"
        ),
        # Results
        sa.Column(
            "result_type",
            sa.String(length=50),
            nullable=False,
            comment="IC50, EC50, Ki, % inhibition, etc.",
        ),
        sa.Column(
            "result_value",
            sa.Numeric(precision=15, scale=6),
            nullable=True,
            comment="Numeric result",
        ),
        sa.Column(
            "result_unit", sa.String(length=20), nullable=True, comment="nM, uM, %, etc."
        ),
        sa.Column(
            "result_qualifier", sa.String(length=5), nullable=True, comment="=, <, >, ~"
        ),
        sa.Column(
            "confidence", sa.String(length=20), nullable=True, comment="high, medium, low"
        ),
        # Conditions
        sa.Column(
            "conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
            comment="Temperature, pH, concentration, time, etc.",
        ),
        # Source
        sa.Column(
            "source",
            sa.String(length=100),
            nullable=True,
            comment="internal, ChEMBL, literature",
        ),
        sa.Column(
            "source_id", sa.String(length=100), nullable=True, comment="External reference ID"
        ),
        # Metadata
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
            comment="Extensible properties",
        ),
        # Audit fields
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Soft delete
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["molecule_id"], ["molecules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "result_qualifier IN ('=', '<', '>', '>=', '<=', '~')",
            name="ck_assay_result_qualifier",
        ),
        comment="Experimental assay results",
    )
    # Assay indexes
    op.create_index("ix_assays_organization_id", "assays", ["organization_id"])
    op.create_index("ix_assays_project_id", "assays", ["project_id"])
    op.create_index("ix_assays_molecule_id", "assays", ["molecule_id"])
    op.create_index("ix_assays_target_id", "assays", ["target_id"])
    op.create_index("ix_assays_org_type", "assays", ["organization_id", "assay_type"])
    op.create_index("ix_assays_molecule_target", "assays", ["molecule_id", "target_id"])
    op.create_index("ix_assays_deleted_at", "assays", ["deleted_at"])

    # ==========================================================================
    # PREDICTIONS TABLE
    # ==========================================================================
    op.create_table(
        "predictions",
        # Primary key
        sa.Column("id", sa.UUID(), nullable=False),
        # Tenant isolation
        sa.Column("organization_id", sa.UUID(), nullable=False),
        # Relationships
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("molecule_id", sa.UUID(), nullable=False),
        sa.Column(
            "target_id", sa.UUID(), nullable=True, comment="For binding/activity predictions"
        ),
        # Model info
        sa.Column(
            "model_name", sa.String(length=100), nullable=False, comment="Model identifier"
        ),
        sa.Column("model_version", sa.String(length=50), nullable=True, comment="Model version"),
        sa.Column(
            "prediction_type",
            sa.String(length=50),
            nullable=False,
            comment="activity, admet, toxicity, binding",
        ),
        # Prediction results
        sa.Column(
            "predicted_value",
            sa.Numeric(precision=15, scale=6),
            nullable=True,
            comment="Numeric prediction",
        ),
        sa.Column(
            "predicted_class",
            sa.String(length=50),
            nullable=True,
            comment="Classification result",
        ),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=5, scale=4),
            nullable=True,
            comment="0.0000 - 1.0000",
        ),
        sa.Column(
            "uncertainty",
            sa.Numeric(precision=15, scale=6),
            nullable=True,
            comment="Model uncertainty estimate",
        ),
        # Explainability
        sa.Column(
            "input_features",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Features used for prediction",
        ),
        sa.Column(
            "explanation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="SHAP values, attention weights, etc.",
        ),
        # Metadata
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
            comment="Extensible properties",
        ),
        # Audit (created only - predictions are immutable)
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Soft delete
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["molecule_id"], ["molecules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_prediction_confidence_range",
        ),
        comment="ML model predictions",
    )
    # Prediction indexes
    op.create_index("ix_predictions_organization_id", "predictions", ["organization_id"])
    op.create_index("ix_predictions_project_id", "predictions", ["project_id"])
    op.create_index("ix_predictions_molecule_id", "predictions", ["molecule_id"])
    op.create_index("ix_predictions_target_id", "predictions", ["target_id"])
    op.create_index("ix_predictions_org_model", "predictions", ["organization_id", "model_name"])
    op.create_index("ix_predictions_org_type", "predictions", ["organization_id", "prediction_type"])
    op.create_index("ix_predictions_org_created", "predictions", ["organization_id", "created_at"])
    op.create_index("ix_predictions_deleted_at", "predictions", ["deleted_at"])

    # ==========================================================================
    # MOLECULE_TARGETS ASSOCIATION TABLE
    # ==========================================================================
    op.create_table(
        "molecule_targets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("molecule_id", sa.UUID(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column(
            "relationship_type",
            sa.String(length=50),
            nullable=False,
            server_default="tested",
            comment="tested, active, inactive, unknown",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["molecule_id"], ["molecules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("molecule_id", "target_id", name="uq_molecule_target"),
        comment="Molecule-Target relationships",
    )
    op.create_index("ix_molecule_targets_molecule_id", "molecule_targets", ["molecule_id"])
    op.create_index("ix_molecule_targets_target_id", "molecule_targets", ["target_id"])

    # ==========================================================================
    # PROJECT_MOLECULES ASSOCIATION TABLE
    # ==========================================================================
    op.create_table(
        "project_molecules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("molecule_id", sa.UUID(), nullable=False),
        sa.Column("added_by", sa.UUID(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True, comment="Optional notes"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["molecule_id"], ["molecules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("project_id", "molecule_id", name="uq_project_molecule"),
        comment="Project-Molecule relationships",
    )
    op.create_index("ix_project_molecules_project_id", "project_molecules", ["project_id"])
    op.create_index("ix_project_molecules_molecule_id", "project_molecules", ["molecule_id"])

    # ==========================================================================
    # PROJECT_TARGETS ASSOCIATION TABLE
    # ==========================================================================
    op.create_table(
        "project_targets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Primary target for project",
        ),
        sa.Column("added_by", sa.UUID(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("project_id", "target_id", name="uq_project_target"),
        comment="Project-Target relationships",
    )
    op.create_index("ix_project_targets_project_id", "project_targets", ["project_id"])
    op.create_index("ix_project_targets_target_id", "project_targets", ["target_id"])


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop association tables first (they have FKs to main tables)
    op.drop_index("ix_project_targets_target_id", table_name="project_targets")
    op.drop_index("ix_project_targets_project_id", table_name="project_targets")
    op.drop_table("project_targets")

    op.drop_index("ix_project_molecules_molecule_id", table_name="project_molecules")
    op.drop_index("ix_project_molecules_project_id", table_name="project_molecules")
    op.drop_table("project_molecules")

    op.drop_index("ix_molecule_targets_target_id", table_name="molecule_targets")
    op.drop_index("ix_molecule_targets_molecule_id", table_name="molecule_targets")
    op.drop_table("molecule_targets")

    # Drop predictions
    op.drop_index("ix_predictions_deleted_at", table_name="predictions")
    op.drop_index("ix_predictions_org_created", table_name="predictions")
    op.drop_index("ix_predictions_org_type", table_name="predictions")
    op.drop_index("ix_predictions_org_model", table_name="predictions")
    op.drop_index("ix_predictions_target_id", table_name="predictions")
    op.drop_index("ix_predictions_molecule_id", table_name="predictions")
    op.drop_index("ix_predictions_project_id", table_name="predictions")
    op.drop_index("ix_predictions_organization_id", table_name="predictions")
    op.drop_table("predictions")

    # Drop assays
    op.drop_index("ix_assays_deleted_at", table_name="assays")
    op.drop_index("ix_assays_molecule_target", table_name="assays")
    op.drop_index("ix_assays_org_type", table_name="assays")
    op.drop_index("ix_assays_target_id", table_name="assays")
    op.drop_index("ix_assays_molecule_id", table_name="assays")
    op.drop_index("ix_assays_project_id", table_name="assays")
    op.drop_index("ix_assays_organization_id", table_name="assays")
    op.drop_table("assays")

    # Drop projects
    op.drop_index("ix_projects_deleted_at", table_name="projects")
    op.drop_index("ix_projects_org_status", table_name="projects")
    op.drop_index("ix_projects_organization_id", table_name="projects")
    op.drop_table("projects")

    # Drop targets
    op.drop_index("ix_targets_deleted_at", table_name="targets")
    op.drop_index("ix_targets_org_family", table_name="targets")
    op.drop_index("ix_targets_org_gene", table_name="targets")
    op.drop_index("ix_targets_org_uniprot", table_name="targets")
    op.drop_index("ix_targets_organization_id", table_name="targets")
    op.drop_table("targets")

    # Drop molecules
    op.drop_index("ix_molecules_deleted_at", table_name="molecules")
    op.drop_index("ix_molecules_org_created", table_name="molecules")
    op.drop_index("ix_molecules_org_mw", table_name="molecules")
    op.drop_index("ix_molecules_org_name", table_name="molecules")
    op.drop_index("ix_molecules_canonical_smiles", table_name="molecules")
    op.drop_index("ix_molecules_org_smiles_hash", table_name="molecules")
    op.drop_index("ix_molecules_org_inchikey", table_name="molecules")
    op.drop_index("ix_molecules_organization_id", table_name="molecules")
    op.drop_table("molecules")
