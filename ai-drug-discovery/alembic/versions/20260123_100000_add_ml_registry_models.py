"""Add ML Model Registry tables

Revision ID: ml_registry_001
Revises: a1b2c3d4e5f6
Create Date: 2026-01-23 10:00:00.000000

Tables:
- ml_models: Main model entity (unique name per org)
- ml_model_versions: Versioned model instances with semantic versioning
- ml_model_artifacts: Model artifacts (weights, configs, etc.)
- ml_model_metrics: Training/validation metrics
- ml_model_deployments: Deployment configuration with A/B weights
- ml_model_lineage: Data lineage tracking
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ml_registry_001"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    op.execute(
        "CREATE TYPE modelversionstatus AS ENUM ('draft', 'validated', 'deprecated')"
    )
    op.execute(
        "CREATE TYPE artifacttype AS ENUM "
        "('weights', 'config', 'tokenizer', 'vocabulary', 'checkpoint', "
        "'onnx', 'torchscript', 'metadata', 'other')"
    )

    # ==========================================================================
    # ml_models table
    # ==========================================================================
    op.create_table(
        "ml_models",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, comment="Unique model name within organization"),
        sa.Column("display_name", sa.String(255), nullable=True, comment="Human-readable display name"),
        sa.Column("description", sa.Text(), nullable=True, comment="Model description and purpose"),
        sa.Column("model_type", sa.String(100), nullable=False, comment="Model type: classifier, regressor, generative, etc."),
        sa.Column("framework", sa.String(50), nullable=True, comment="ML framework: pytorch, tensorflow, sklearn, etc."),
        sa.Column("task", sa.String(100), nullable=True, comment="Task: activity_prediction, toxicity, binding_affinity, etc."),
        sa.Column("owner_team_id", sa.UUID(), nullable=True, comment="Team that owns this model"),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Tags for categorization"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}", comment="Extensible metadata"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_ml_model_org_name"),
        comment="ML models with versioning support",
    )
    op.create_index("ix_ml_models_organization_id", "ml_models", ["organization_id"])
    op.create_index("ix_ml_models_org_type", "ml_models", ["organization_id", "model_type"])
    op.create_index("ix_ml_models_org_task", "ml_models", ["organization_id", "task"])
    op.create_index("ix_ml_models_org_created", "ml_models", ["organization_id", "created_at"])
    op.create_index("ix_ml_models_deleted_at", "ml_models", ["deleted_at"])

    # ==========================================================================
    # ml_model_versions table
    # ==========================================================================
    op.create_table(
        "ml_model_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("model_id", sa.UUID(), nullable=False),
        sa.Column("version_major", sa.SmallInteger(), nullable=False, comment="Major version number"),
        sa.Column("version_minor", sa.SmallInteger(), nullable=False, comment="Minor version number"),
        sa.Column("version_patch", sa.SmallInteger(), nullable=False, comment="Patch version number"),
        sa.Column("version_label", sa.String(50), nullable=True, comment="Optional label: alpha, beta, rc1, etc."),
        sa.Column(
            "status",
            postgresql.ENUM("draft", "validated", "deprecated", name="modelversionstatus", create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True, comment="When status was last changed"),
        sa.Column("status_changed_by", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True, comment="Version-specific description and changelog"),
        sa.Column("release_notes", sa.Text(), nullable=True, comment="Release notes for this version"),
        sa.Column("training_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("training_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("training_duration_seconds", sa.Integer(), nullable=True, comment="Training duration in seconds"),
        sa.Column("hyperparameters", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Training hyperparameters"),
        sa.Column("model_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Model architecture configuration"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}", comment="Extensible metadata"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["model_id"], ["ml_models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["status_changed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "model_id", "version_major", "version_minor", "version_patch", "version_label",
            name="uq_ml_model_version_semver"
        ),
        sa.CheckConstraint(
            "version_major >= 0 AND version_minor >= 0 AND version_patch >= 0",
            name="ck_ml_model_version_non_negative"
        ),
        comment="ML model versions with semantic versioning",
    )
    op.create_index("ix_ml_model_versions_model_id", "ml_model_versions", ["model_id"])
    op.create_index("ix_ml_model_versions_status", "ml_model_versions", ["status"])
    op.create_index("ix_ml_model_versions_model_status", "ml_model_versions", ["model_id", "status"])
    op.create_index(
        "ix_ml_model_versions_semver",
        "ml_model_versions",
        ["model_id", "version_major", "version_minor", "version_patch"]
    )
    op.create_index("ix_ml_model_versions_deleted_at", "ml_model_versions", ["deleted_at"])

    # ==========================================================================
    # ml_model_artifacts table
    # ==========================================================================
    op.create_table(
        "ml_model_artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, comment="Artifact name/identifier"),
        sa.Column(
            "artifact_type",
            postgresql.ENUM(
                "weights", "config", "tokenizer", "vocabulary", "checkpoint",
                "onnx", "torchscript", "metadata", "other",
                name="artifacttype", create_type=False
            ),
            nullable=False,
            comment="Type of artifact",
        ),
        sa.Column("storage_path", sa.String(1000), nullable=False, comment="Storage path (S3 URI, local path, etc.)"),
        sa.Column("storage_backend", sa.String(50), nullable=False, server_default="s3", comment="Storage backend: s3, gcs, local, etc."),
        sa.Column("sha256_hash", sa.String(64), nullable=False, comment="SHA-256 hash for integrity verification"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, comment="File size in bytes"),
        sa.Column("content_type", sa.String(100), nullable=True, comment="MIME type or format identifier"),
        sa.Column("compression", sa.String(20), nullable=True, comment="Compression: gzip, lz4, none, etc."),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}", comment="Extensible metadata"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["ml_model_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "name", name="uq_ml_model_artifact_version_name"),
        comment="ML model artifacts (weights, configs, etc.)",
    )
    op.create_index("ix_ml_model_artifacts_version_id", "ml_model_artifacts", ["version_id"])
    op.create_index("ix_ml_model_artifacts_type", "ml_model_artifacts", ["artifact_type"])
    op.create_index("ix_ml_model_artifacts_hash", "ml_model_artifacts", ["sha256_hash"])

    # ==========================================================================
    # ml_model_metrics table
    # ==========================================================================
    op.create_table(
        "ml_model_metrics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("metric_set", sa.String(50), nullable=False, comment="Metric set: train, validation, test, cross_val, etc."),
        sa.Column("epoch", sa.Integer(), nullable=True, comment="Training epoch (if applicable)"),
        sa.Column("step", sa.Integer(), nullable=True, comment="Training step (if applicable)"),
        # Key metrics (structured)
        sa.Column("loss", sa.Numeric(15, 8), nullable=True, comment="Loss value"),
        sa.Column("accuracy", sa.Numeric(7, 6), nullable=True, comment="Accuracy (0.0 - 1.0)"),
        sa.Column("precision", sa.Numeric(7, 6), nullable=True, comment="Precision (0.0 - 1.0)"),
        sa.Column("recall", sa.Numeric(7, 6), nullable=True, comment="Recall (0.0 - 1.0)"),
        sa.Column("f1_score", sa.Numeric(7, 6), nullable=True, comment="F1 score (0.0 - 1.0)"),
        sa.Column("auc_roc", sa.Numeric(7, 6), nullable=True, comment="Area under ROC curve (0.0 - 1.0)"),
        sa.Column("auc_pr", sa.Numeric(7, 6), nullable=True, comment="Area under Precision-Recall curve (0.0 - 1.0)"),
        sa.Column("rmse", sa.Numeric(15, 8), nullable=True, comment="Root mean squared error"),
        sa.Column("mae", sa.Numeric(15, 8), nullable=True, comment="Mean absolute error"),
        sa.Column("r2_score", sa.Numeric(8, 6), nullable=True, comment="R-squared coefficient"),
        # Flexible metrics
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}", comment="Additional metrics as JSON"),
        # Dataset info
        sa.Column("dataset_size", sa.Integer(), nullable=True, comment="Number of samples in this metric set"),
        sa.Column("dataset_split", sa.String(50), nullable=True, comment="Dataset split identifier"),
        # Timestamps
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="When metrics were recorded"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["ml_model_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "metric_set", "epoch", "step", name="uq_ml_model_metrics_set"),
        sa.CheckConstraint("accuracy IS NULL OR (accuracy >= 0 AND accuracy <= 1)", name="ck_ml_metrics_accuracy_range"),
        sa.CheckConstraint("precision IS NULL OR (precision >= 0 AND precision <= 1)", name="ck_ml_metrics_precision_range"),
        sa.CheckConstraint("recall IS NULL OR (recall >= 0 AND recall <= 1)", name="ck_ml_metrics_recall_range"),
        comment="ML model training and validation metrics",
    )
    op.create_index("ix_ml_model_metrics_version_id", "ml_model_metrics", ["version_id"])
    op.create_index("ix_ml_model_metrics_version_set", "ml_model_metrics", ["version_id", "metric_set"])
    op.create_index("ix_ml_model_metrics_recorded", "ml_model_metrics", ["recorded_at"])

    # ==========================================================================
    # ml_model_deployments table
    # ==========================================================================
    op.create_table(
        "ml_model_deployments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("model_id", sa.UUID(), nullable=False),
        sa.Column("active_version_id", sa.UUID(), nullable=True, comment="Currently active model version"),
        sa.Column("name", sa.String(255), nullable=False, comment="Deployment name (e.g., production, staging, canary)"),
        sa.Column("environment", sa.String(50), nullable=False, server_default="production", comment="Deployment environment"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true", comment="Whether deployment is currently active"),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True, comment="When deployment was activated"),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True, comment="When deployment was deactivated"),
        sa.Column("ab_weights", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='A/B test weights: {"version_id": weight, ...}'),
        sa.Column("ab_enabled", sa.Boolean(), nullable=False, server_default="false", comment="Whether A/B testing is enabled"),
        sa.Column("endpoint_url", sa.String(500), nullable=True, comment="Deployment endpoint URL"),
        sa.Column("replicas", sa.SmallInteger(), nullable=False, server_default="1", comment="Number of replicas"),
        sa.Column("resources", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Resource configuration (CPU, memory, GPU)"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_id"], ["ml_models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["active_version_id"], ["ml_model_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "name", name="uq_ml_model_deployment_name"),
        comment="ML model deployment configurations",
    )
    op.create_index("ix_ml_deployments_organization_id", "ml_model_deployments", ["organization_id"])
    op.create_index("ix_ml_deployments_model_id", "ml_model_deployments", ["model_id"])
    op.create_index("ix_ml_deployments_org_env", "ml_model_deployments", ["organization_id", "environment"])
    op.create_index("ix_ml_deployments_active", "ml_model_deployments", ["is_active"])
    op.create_index("ix_ml_deployments_deleted_at", "ml_model_deployments", ["deleted_at"])

    # ==========================================================================
    # ml_model_lineage table
    # ==========================================================================
    op.create_table(
        "ml_model_lineage",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=False, comment="One lineage record per version"),
        # Dataset references
        sa.Column("training_dataset_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Training dataset identifiers"),
        sa.Column("validation_dataset_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Validation dataset identifiers"),
        sa.Column("test_dataset_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Test dataset identifiers"),
        # Code references
        sa.Column("git_commit_hash", sa.String(40), nullable=True, comment="Git commit SHA (40 characters)"),
        sa.Column("git_repository", sa.String(500), nullable=True, comment="Git repository URL"),
        sa.Column("git_branch", sa.String(255), nullable=True, comment="Git branch name"),
        sa.Column("git_tag", sa.String(255), nullable=True, comment="Git tag if any"),
        # Feature engineering
        sa.Column("feature_version", sa.String(50), nullable=True, comment="Feature engineering version/pipeline ID"),
        sa.Column("feature_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Feature configuration used"),
        sa.Column("feature_columns", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="List of feature column names"),
        # Environment
        sa.Column("python_version", sa.String(20), nullable=True, comment="Python version used"),
        sa.Column("dependencies", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Key dependencies with versions"),
        sa.Column("cuda_version", sa.String(20), nullable=True, comment="CUDA version if GPU training"),
        sa.Column("hardware_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Hardware configuration used for training"),
        # Reproducibility
        sa.Column("random_seed", sa.Integer(), nullable=True, comment="Random seed for reproducibility"),
        sa.Column("experiment_id", sa.String(255), nullable=True, comment="External experiment tracking ID (MLflow, W&B, etc.)"),
        sa.Column("experiment_url", sa.String(500), nullable=True, comment="Link to experiment tracker"),
        # Metadata
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["ml_model_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", name="uq_ml_model_lineage_version"),
        comment="ML model data lineage and reproducibility tracking",
    )
    op.create_index("ix_ml_lineage_version_id", "ml_model_lineage", ["version_id"], unique=True)
    op.create_index("ix_ml_lineage_commit", "ml_model_lineage", ["git_commit_hash"])
    op.create_index("ix_ml_lineage_experiment", "ml_model_lineage", ["experiment_id"])


def downgrade() -> None:
    # Drop tables in reverse order (respect foreign key constraints)
    op.drop_table("ml_model_lineage")
    op.drop_table("ml_model_deployments")
    op.drop_table("ml_model_metrics")
    op.drop_table("ml_model_artifacts")
    op.drop_table("ml_model_versions")
    op.drop_table("ml_models")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS artifacttype")
    op.execute("DROP TYPE IF EXISTS modelversionstatus")
