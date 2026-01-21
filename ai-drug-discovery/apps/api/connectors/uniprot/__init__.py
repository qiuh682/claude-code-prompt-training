"""
UniProt connector package.

Provides:
- UniProtClient: Low-level HTTP client with caching and rate limiting
- UniProtNormalizer: Maps raw UniProt data to internal schemas
- UniProtConnector: High-level API for target profiling workflows
"""

from apps.api.connectors.uniprot.client import (
    BadRequestError,
    NotFoundError,
    RateLimitError,
    UniProtClient,
    UniProtClientError,
)
from apps.api.connectors.uniprot.connector import UniProtConnector
from apps.api.connectors.uniprot.normalizer import UniProtNormalizer
from apps.api.connectors.uniprot.schemas import (
    CrossReference,
    DiseaseAssociation,
    DrugInteraction,
    FeatureType,
    FunctionAnnotation,
    GeneInfo,
    OrganismInfo,
    ProteinExistence,
    ProteinName,
    ReviewStatus,
    SequenceFeature,
    SubcellularLocation,
    TargetSearchHit,
    TargetSearchResult,
    TargetSummary,
    UniProtTarget,
)

__all__ = [
    # Client
    "UniProtClient",
    "UniProtClientError",
    "RateLimitError",
    "NotFoundError",
    "BadRequestError",
    # Connector
    "UniProtConnector",
    # Normalizer
    "UniProtNormalizer",
    # Main schemas
    "UniProtTarget",
    "TargetSummary",
    "TargetSearchHit",
    "TargetSearchResult",
    # Supporting schemas
    "ProteinName",
    "GeneInfo",
    "OrganismInfo",
    "SequenceFeature",
    "FunctionAnnotation",
    "SubcellularLocation",
    "DiseaseAssociation",
    "DrugInteraction",
    "CrossReference",
    # Enums
    "ReviewStatus",
    "ProteinExistence",
    "FeatureType",
]
