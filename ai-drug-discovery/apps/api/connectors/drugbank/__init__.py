"""
DrugBank connector package.

Provides two operating modes:
- API mode: Uses DrugBank commercial API (requires DRUGBANK_API_KEY)
- Local mode: Uses downloaded XML/CSV dataset (set DRUGBANK_DATA_PATH)

Components:
- DrugBankConnector: High-level API with auto mode detection
- DrugBankClient: Low-level HTTP client for API mode
- DrugBankLocalReader: Local file reader for offline access
- DrugBankNormalizer: Data normalization layer
"""

from apps.api.connectors.drugbank.client import (
    AuthenticationError,
    DrugBankClient,
    DrugBankClientError,
    NotConfiguredError,
    NotFoundError,
    RateLimitError,
)
from apps.api.connectors.drugbank.connector import DrugBankConnector
from apps.api.connectors.drugbank.local import (
    DrugBankLocalReader,
    LocalDataNotFoundError,
)
from apps.api.connectors.drugbank.normalizer import DrugBankNormalizer
from apps.api.connectors.drugbank.schemas import (
    ADMETProperties,
    DrugBankDrug,
    DrugBankMode,
    DrugBankStatus,
    DrugCategory,
    DrugGroup,
    DrugInteraction,
    DrugPathway,
    DrugSearchHit,
    DrugSearchResult,
    DrugSynonym,
    DrugTargetInteraction,
    DrugType,
    DTISearchResult,
    ExternalIdentifier,
    TargetAction,
    TargetType,
)

__all__ = [
    # Connector
    "DrugBankConnector",
    # Client
    "DrugBankClient",
    "DrugBankClientError",
    "NotConfiguredError",
    "AuthenticationError",
    "RateLimitError",
    "NotFoundError",
    # Local reader
    "DrugBankLocalReader",
    "LocalDataNotFoundError",
    # Normalizer
    "DrugBankNormalizer",
    # Main schemas
    "DrugBankDrug",
    "DrugTargetInteraction",
    "ADMETProperties",
    "DrugBankStatus",
    # Search schemas
    "DrugSearchHit",
    "DrugSearchResult",
    "DTISearchResult",
    # Supporting schemas
    "DrugSynonym",
    "DrugCategory",
    "DrugInteraction",
    "DrugPathway",
    "ExternalIdentifier",
    # Enums
    "DrugType",
    "DrugGroup",
    "DrugBankMode",
    "TargetAction",
    "TargetType",
]
