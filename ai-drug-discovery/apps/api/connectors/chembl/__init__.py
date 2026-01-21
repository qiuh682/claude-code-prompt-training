"""
ChEMBL connector package.

Provides:
- ChEMBLClient: Low-level HTTP client with caching and rate limiting
- ChEMBLNormalizer: Maps raw ChEMBL data to internal schemas
- ChEMBLConnector: High-level API for drug discovery workflows
"""

from apps.api.connectors.chembl.client import ChEMBLClient
from apps.api.connectors.chembl.connector import ChEMBLConnector
from apps.api.connectors.chembl.normalizer import ChEMBLNormalizer
from apps.api.connectors.chembl.schemas import (
    ChEMBLAssay,
    ChEMBLBioactivity,
    ChEMBLCompound,
    ChEMBLTarget,
)

__all__ = [
    "ChEMBLClient",
    "ChEMBLConnector",
    "ChEMBLNormalizer",
    "ChEMBLAssay",
    "ChEMBLBioactivity",
    "ChEMBLCompound",
    "ChEMBLTarget",
]
