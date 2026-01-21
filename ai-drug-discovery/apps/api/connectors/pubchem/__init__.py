"""
PubChem connector package.

Provides:
- PubChemClient: Low-level HTTP client with caching and rate limiting
- PubChemNormalizer: Maps raw PubChem data to internal schemas
- PubChemConnector: High-level API for drug discovery workflows
"""

from apps.api.connectors.pubchem.client import (
    BadRequestError,
    NotFoundError,
    PubChemClient,
    PubChemClientError,
    RateLimitError,
)
from apps.api.connectors.pubchem.connector import PubChemConnector
from apps.api.connectors.pubchem.normalizer import PubChemNormalizer
from apps.api.connectors.pubchem.schemas import (
    AssayOutcome,
    AssayType,
    BioassaySearchResult,
    CompoundProperties,
    CompoundSearchResult,
    PubChemAssay,
    PubChemBioactivity,
    PubChemCompound,
    SearchResult,
    SearchType,
)

__all__ = [
    # Client
    "PubChemClient",
    "PubChemClientError",
    "RateLimitError",
    "NotFoundError",
    "BadRequestError",
    # Connector
    "PubChemConnector",
    # Normalizer
    "PubChemNormalizer",
    # Schemas
    "PubChemCompound",
    "PubChemAssay",
    "PubChemBioactivity",
    "CompoundProperties",
    "SearchResult",
    "CompoundSearchResult",
    "BioassaySearchResult",
    # Enums
    "SearchType",
    "AssayType",
    "AssayOutcome",
]
