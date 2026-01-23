"""
SQLAlchemy models for ML Model Registry.

Tables:
- MLModel: Main model record (unique name per organization)
- MLModelVersion: Versioned model instances with semantic versioning
- MLModelArtifact: Model artifacts (weights, configs, etc.)
- MLModelMetrics: Training/validation metrics
- MLModelDeployment: Deployment configuration with A/B weights
- MLModelLineage: Data lineage tracking

Status Flow:
    DRAFT -> VALIDATED -> DEPRECATED
    DRAFT -> DEPRECATED (skip validation)
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
# Enums
# =============================================================================


class ModelVersionStatus(str, Enum):
    """Status of a model version."""

    DRAFT = "draft"  # Initial state, not yet validated
    VALIDATED = "validated"  # Passed validation, ready for deployment
    DEPRECATED = "deprecated"  # No longer recommended for use


class ArtifactType(str, Enum):
    """Types of model artifacts."""

    WEIGHTS = "weights"  # Model weights (e.g., .pt, .h5, .pkl)
    CONFIG = "config"  # Model configuration (e.g., hyperparameters)
    TOKENIZER = "tokenizer"  # Tokenizer files
    VOCABULARY = "vocabulary"  # Vocabulary files
    CHECKPOINT = "checkpoint"  # Training checkpoint
    ONNX = "onnx"  # ONNX export
    TORCHSCRIPT = "torchscript"  # TorchScript export
    METADATA = "metadata"  # Additional metadata files
    OTHER = "other"  # Other artifact types


# Valid status transitions
VALID_VERSION_TRANSITIONS: dict[ModelVersionStatus, list[ModelVersionStatus]] = {
    ModelVersionStatus.DRAFT: [
        ModelVersionStatus.VALIDATED,
        ModelVersionStatus.DEPRECATED,
    ],
    ModelVersionStatus.VALIDATED: [
        ModelVersionStatus.DEPRECATED,
    ],
    ModelVersionStatus.DEPRECATED: [],  # Terminal state
}


def can_transition_version(
    current: ModelVersionStatus, target: ModelVersionStatus
) -> bool:
    """Check if a version status transition is valid."""
    return target in VALID_VERSION_TRANSITIONS.get(current, [])


# =============================================================================
# MLModel - Main Model Entity
# =============================================================================


class MLModel(AuditedModel):
    """
    ML Model entity - represents a machine learning model.

    A model has multiple versions, each with its own artifacts and metrics.
    Model names must be unique within an organization.
    """

    __tablename__ = "ml_models"

    # --- Tenant Isolation ---
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Model Identity ---
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Unique model name within organization",
    )
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Human-readable display name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Model description and purpose",
    )

    # --- Model Type & Framework ---
    model_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Model type: classifier, regressor, generative, etc.",
    )
    framework: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="ML framework: pytorch, tensorflow, sklearn, etc.",
    )
    task: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Task: activity_prediction, toxicity, binding_affinity, etc.",
    )

    # --- Ownership ---
    owner_team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        comment="Team that owns this model",
    )

    # --- Configuration ---
    tags: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Tags for categorization",
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Extensible metadata",
    )

    # --- Relationships ---
    organization = relationship("Organization", back_populates="ml_models")
    owner_team = relationship("Team", back_populates="ml_models")
    versions = relationship(
        "MLModelVersion",
        back_populates="model",
        cascade="all, delete-orphan",
        order_by="desc(MLModelVersion.created_at)",
    )
    deployments = relationship(
        "MLModelDeployment",
        back_populates="model",
        cascade="all, delete-orphan",
    )

    # --- Table Configuration ---
    __table_args__ = (
        # Unique model name per organization (for non-deleted records)
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_ml_model_org_name",
        ),
        Index("ix_ml_models_org_type", "organization_id", "model_type"),
        Index("ix_ml_models_org_task", "organization_id", "task"),
        Index("ix_ml_models_org_created", "organization_id", "created_at"),
        {"comment": "ML models with versioning support"},
    )

    def __repr__(self) -> str:
        return f"<MLModel {self.name} ({self.model_type})>"


# =============================================================================
# MLModelVersion - Versioned Model Instances
# =============================================================================


class MLModelVersion(AuditedModel):
    """
    Versioned instance of an ML model.

    Uses semantic versioning (major.minor.patch) with uniqueness per model.
    Tracks status transitions: DRAFT -> VALIDATED -> DEPRECATED.
    """

    __tablename__ = "ml_model_versions"

    # --- Foreign Key ---
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ml_models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Semantic Version ---
    version_major: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="Major version number",
    )
    version_minor: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="Minor version number",
    )
    version_patch: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="Patch version number",
    )
    version_label: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Optional label: alpha, beta, rc1, etc.",
    )

    # --- Status ---
    status: Mapped[ModelVersionStatus] = mapped_column(
        default=ModelVersionStatus.DRAFT,
        nullable=False,
        index=True,
    )
    status_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When status was last changed",
    )
    status_changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- Version Metadata ---
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Version-specific description and changelog",
    )
    release_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Release notes for this version",
    )

    # --- Training Info ---
    training_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    training_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    training_duration_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Training duration in seconds",
    )

    # --- Configuration ---
    hyperparameters: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Training hyperparameters",
    )
    model_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Model architecture configuration",
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Extensible metadata",
    )

    # --- Relationships ---
    model = relationship("MLModel", back_populates="versions")
    artifacts = relationship(
        "MLModelArtifact",
        back_populates="version",
        cascade="all, delete-orphan",
    )
    metrics = relationship(
        "MLModelMetrics",
        back_populates="version",
        cascade="all, delete-orphan",
    )
    lineage = relationship(
        "MLModelLineage",
        back_populates="version",
        uselist=False,
        cascade="all, delete-orphan",
    )
    # Deployments where this is the active version
    active_deployments = relationship(
        "MLModelDeployment",
        back_populates="active_version",
        foreign_keys="MLModelDeployment.active_version_id",
    )

    # --- Computed Properties ---
    @property
    def version_string(self) -> str:
        """Return semantic version string (e.g., '1.2.3' or '1.2.3-beta')."""
        base = f"{self.version_major}.{self.version_minor}.{self.version_patch}"
        if self.version_label:
            return f"{base}-{self.version_label}"
        return base

    # --- Table Configuration ---
    __table_args__ = (
        # Unique semantic version per model (for non-deleted records)
        UniqueConstraint(
            "model_id",
            "version_major",
            "version_minor",
            "version_patch",
            "version_label",
            name="uq_ml_model_version_semver",
        ),
        # Version components must be non-negative
        CheckConstraint(
            "version_major >= 0 AND version_minor >= 0 AND version_patch >= 0",
            name="ck_ml_model_version_non_negative",
        ),
        Index("ix_ml_model_versions_model_status", "model_id", "status"),
        Index(
            "ix_ml_model_versions_semver",
            "model_id",
            "version_major",
            "version_minor",
            "version_patch",
        ),
        {"comment": "ML model versions with semantic versioning"},
    )

    def __repr__(self) -> str:
        return f"<MLModelVersion {self.version_string} ({self.status.value})>"


# =============================================================================
# MLModelArtifact - Model Artifacts
# =============================================================================


class MLModelArtifact(BaseModel, TimestampMixin):
    """
    Model artifact storage reference.

    Stores metadata about model artifacts (weights, configs, etc.) with
    integrity verification via SHA-256 hash.
    """

    __tablename__ = "ml_model_artifacts"

    # --- Foreign Key ---
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ml_model_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Artifact Identity ---
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Artifact name/identifier",
    )
    artifact_type: Mapped[ArtifactType] = mapped_column(
        nullable=False,
        comment="Type of artifact",
    )

    # --- Storage ---
    storage_path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="Storage path (S3 URI, local path, etc.)",
    )
    storage_backend: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="s3",
        comment="Storage backend: s3, gcs, local, etc.",
    )

    # --- Integrity ---
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash for integrity verification",
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="File size in bytes",
    )

    # --- Format ---
    content_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="MIME type or format identifier",
    )
    compression: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Compression: gzip, lz4, none, etc.",
    )

    # --- Metadata ---
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Extensible metadata",
    )

    # --- Relationships ---
    version = relationship("MLModelVersion", back_populates="artifacts")

    # --- Table Configuration ---
    __table_args__ = (
        # Unique artifact name per version
        UniqueConstraint(
            "version_id",
            "name",
            name="uq_ml_model_artifact_version_name",
        ),
        Index("ix_ml_model_artifacts_type", "artifact_type"),
        Index("ix_ml_model_artifacts_hash", "sha256_hash"),
        {"comment": "ML model artifacts (weights, configs, etc.)"},
    )

    def __repr__(self) -> str:
        return f"<MLModelArtifact {self.name} ({self.artifact_type.value})>"


# =============================================================================
# MLModelMetrics - Training/Validation Metrics
# =============================================================================


class MLModelMetrics(BaseModel, TimestampMixin):
    """
    Model performance metrics.

    Stores both structured key metrics and a flexible JSON blob for
    additional metrics. Supports different metric sets (train, validation, test).
    """

    __tablename__ = "ml_model_metrics"

    # --- Foreign Key ---
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ml_model_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Metric Set Identity ---
    metric_set: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Metric set: train, validation, test, cross_val, etc.",
    )
    epoch: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Training epoch (if applicable)",
    )
    step: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Training step (if applicable)",
    )

    # --- Key Metrics (structured for easy querying) ---
    loss: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 8),
        nullable=True,
        comment="Loss value",
    )
    accuracy: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 6),
        nullable=True,
        comment="Accuracy (0.0 - 1.0)",
    )
    precision: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 6),
        nullable=True,
        comment="Precision (0.0 - 1.0)",
    )
    recall: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 6),
        nullable=True,
        comment="Recall (0.0 - 1.0)",
    )
    f1_score: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 6),
        nullable=True,
        comment="F1 score (0.0 - 1.0)",
    )
    auc_roc: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 6),
        nullable=True,
        comment="Area under ROC curve (0.0 - 1.0)",
    )
    auc_pr: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 6),
        nullable=True,
        comment="Area under Precision-Recall curve (0.0 - 1.0)",
    )
    rmse: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 8),
        nullable=True,
        comment="Root mean squared error",
    )
    mae: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 8),
        nullable=True,
        comment="Mean absolute error",
    )
    r2_score: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 6),
        nullable=True,
        comment="R-squared coefficient",
    )

    # --- Flexible Metrics (JSON blob) ---
    metrics_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Additional metrics as JSON",
    )

    # --- Dataset Info ---
    dataset_size: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of samples in this metric set",
    )
    dataset_split: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Dataset split identifier",
    )

    # --- Metadata ---
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When metrics were recorded",
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
    )

    # --- Relationships ---
    version = relationship("MLModelVersion", back_populates="metrics")

    # --- Table Configuration ---
    __table_args__ = (
        # Unique metric set per version/epoch/step combination
        UniqueConstraint(
            "version_id",
            "metric_set",
            "epoch",
            "step",
            name="uq_ml_model_metrics_set",
        ),
        CheckConstraint(
            "accuracy IS NULL OR (accuracy >= 0 AND accuracy <= 1)",
            name="ck_ml_metrics_accuracy_range",
        ),
        CheckConstraint(
            "precision IS NULL OR (precision >= 0 AND precision <= 1)",
            name="ck_ml_metrics_precision_range",
        ),
        CheckConstraint(
            "recall IS NULL OR (recall >= 0 AND recall <= 1)",
            name="ck_ml_metrics_recall_range",
        ),
        Index("ix_ml_model_metrics_version_set", "version_id", "metric_set"),
        Index("ix_ml_model_metrics_recorded", "recorded_at"),
        {"comment": "ML model training and validation metrics"},
    )

    def __repr__(self) -> str:
        return f"<MLModelMetrics {self.metric_set} epoch={self.epoch}>"


# =============================================================================
# MLModelDeployment - Deployment Configuration
# =============================================================================


class MLModelDeployment(AuditedModel):
    """
    Model deployment configuration.

    Tracks which version is actively deployed and supports A/B testing
    via optional weight distribution across versions.
    """

    __tablename__ = "ml_model_deployments"

    # --- Tenant Isolation ---
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Foreign Keys ---
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ml_models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ml_model_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Currently active model version",
    )

    # --- Deployment Identity ---
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Deployment name (e.g., production, staging, canary)",
    )
    environment: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="production",
        comment="Deployment environment",
    )

    # --- Status ---
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
        comment="Whether deployment is currently active",
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When deployment was activated",
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When deployment was deactivated",
    )

    # --- A/B Testing ---
    ab_weights: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment='A/B test weights: {"version_id": weight, ...}',
    )
    ab_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Whether A/B testing is enabled",
    )

    # --- Configuration ---
    endpoint_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Deployment endpoint URL",
    )
    replicas: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default="1",
        comment="Number of replicas",
    )
    resources: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Resource configuration (CPU, memory, GPU)",
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
    )

    # --- Relationships ---
    organization = relationship("Organization", back_populates="ml_deployments")
    model = relationship("MLModel", back_populates="deployments")
    active_version = relationship(
        "MLModelVersion",
        back_populates="active_deployments",
        foreign_keys=[active_version_id],
    )

    # --- Table Configuration ---
    __table_args__ = (
        # Unique deployment name per model
        UniqueConstraint(
            "model_id",
            "name",
            name="uq_ml_model_deployment_name",
        ),
        Index("ix_ml_deployments_org_env", "organization_id", "environment"),
        Index("ix_ml_deployments_active", "is_active"),
        {"comment": "ML model deployment configurations"},
    )

    def __repr__(self) -> str:
        return f"<MLModelDeployment {self.name} ({self.environment})>"


# =============================================================================
# MLModelLineage - Data Lineage Tracking
# =============================================================================


class MLModelLineage(BaseModel, TimestampMixin):
    """
    Data lineage tracking for model versions.

    Records what data, code, and features were used to train a model version,
    enabling reproducibility and audit trails.
    """

    __tablename__ = "ml_model_lineage"

    # --- Foreign Key ---
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ml_model_versions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="One lineage record per version",
    )

    # --- Dataset References ---
    training_dataset_ids: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Training dataset identifiers",
    )
    validation_dataset_ids: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Validation dataset identifiers",
    )
    test_dataset_ids: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Test dataset identifiers",
    )

    # --- Code References ---
    git_commit_hash: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        comment="Git commit SHA (40 characters)",
    )
    git_repository: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Git repository URL",
    )
    git_branch: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Git branch name",
    )
    git_tag: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Git tag if any",
    )

    # --- Feature Engineering ---
    feature_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Feature engineering version/pipeline ID",
    )
    feature_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Feature configuration used",
    )
    feature_columns: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="List of feature column names",
    )

    # --- Environment ---
    python_version: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Python version used",
    )
    dependencies: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Key dependencies with versions",
    )
    cuda_version: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="CUDA version if GPU training",
    )
    hardware_info: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Hardware configuration used for training",
    )

    # --- Reproducibility ---
    random_seed: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Random seed for reproducibility",
    )
    experiment_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="External experiment tracking ID (MLflow, W&B, etc.)",
    )
    experiment_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Link to experiment tracker",
    )

    # --- Additional Metadata ---
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
    )

    # --- Relationships ---
    version = relationship("MLModelVersion", back_populates="lineage")

    # --- Table Configuration ---
    __table_args__ = (
        Index("ix_ml_lineage_commit", "git_commit_hash"),
        Index("ix_ml_lineage_experiment", "experiment_id"),
        {"comment": "ML model data lineage and reproducibility tracking"},
    )

    def __repr__(self) -> str:
        return f"<MLModelLineage commit={self.git_commit_hash[:8] if self.git_commit_hash else 'N/A'}>"
