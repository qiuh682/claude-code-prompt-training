"""
Public database connectors for external chemical/biological data sources.

Connectors:
- ChEMBL: Bioactivity data, compounds, targets, assays
- PubChem: Chemical structures, properties, bioassays
- UniProt: Protein sequences, annotations, cross-references
- DrugBank: Drug-target interactions, pharmacology data

All connectors share:
- HTTP client with retries and exponential backoff
- Rate limit handling (429 + Retry-After)
- Caching layer (Redis preferred, in-memory fallback)
- Normalized output to internal schema (Molecule, Target, Assay)
- Consistent error types and logging
"""

from apps.api.connectors.base import BaseConnector, ConnectorError, RateLimitError
from apps.api.connectors.chembl import ChEMBLConnector
from apps.api.connectors.pubchem import PubChemConnector
from apps.api.connectors.uniprot import UniProtConnector

__all__ = [
    "BaseConnector",
    "ConnectorError",
    "RateLimitError",
    "ChEMBLConnector",
    "PubChemConnector",
    "UniProtConnector",
]
