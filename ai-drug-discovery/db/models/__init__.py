"""Database models package."""

from db.models.base_model import (
    AuditedModel,
    AuditMixin,
    BaseModel,
    SoftDeleteMixin,
    TimestampMixin,
)
from db.models.discovery import (
    Assay,
    Molecule,
    MoleculeFingerprint,
    MoleculeTarget,
    Prediction,
    Project,
    ProjectMolecule,
    ProjectTarget,
    Target,
)
from db.models.ml_registry import (
    ArtifactType,
    MLModel,
    MLModelArtifact,
    MLModelDeployment,
    MLModelLineage,
    MLModelMetrics,
    MLModelVersion,
    ModelVersionStatus,
    can_transition_version,
)
from db.models.upload import (
    DuplicateAction,
    FileType,
    Upload,
    UploadFile,
    UploadProgress,
    UploadResultSummary,
    UploadRowError,
    UploadStatus,
    can_transition,
)

__all__ = [
    # Base models and mixins
    "AuditedModel",
    "AuditMixin",
    "BaseModel",
    "SoftDeleteMixin",
    "TimestampMixin",
    # Discovery models
    "Assay",
    "Molecule",
    "MoleculeFingerprint",
    "MoleculeTarget",
    "Prediction",
    "Project",
    "ProjectMolecule",
    "ProjectTarget",
    "Target",
    # ML Registry models
    "ArtifactType",
    "MLModel",
    "MLModelArtifact",
    "MLModelDeployment",
    "MLModelLineage",
    "MLModelMetrics",
    "MLModelVersion",
    "ModelVersionStatus",
    "can_transition_version",
    # Upload models
    "DuplicateAction",
    "FileType",
    "Upload",
    "UploadFile",
    "UploadProgress",
    "UploadResultSummary",
    "UploadRowError",
    "UploadStatus",
    "can_transition",
]
