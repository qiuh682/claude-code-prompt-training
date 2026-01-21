"""
Settings for public database connectors.

Environment variables:
- CHEMBL_BASE_URL: ChEMBL API base URL
- PUBCHEM_BASE_URL: PubChem API base URL
- UNIPROT_BASE_URL: UniProt API base URL
- DRUGBANK_BASE_URL: DrugBank API base URL (requires API key)
- DRUGBANK_API_KEY: DrugBank API key
- DRUGBANK_DATA_PATH: Path to local DrugBank XML/CSV dataset

- CONNECTOR_TIMEOUT: Default request timeout (seconds)
- CONNECTOR_MAX_RETRIES: Max retry attempts
- CONNECTOR_CACHE_TTL: Default cache TTL (seconds)
- CONNECTOR_CACHE_BACKEND: "redis" or "memory"

- REDIS_URL: Redis connection URL (for caching)
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class ConnectorSettings(BaseSettings):
    """Settings for external database connectors."""

    # ==========================================================================
    # API Base URLs
    # ==========================================================================

    chembl_base_url: str = Field(
        default="https://www.ebi.ac.uk/chembl/api/data",
        description="ChEMBL REST API base URL",
    )
    pubchem_base_url: str = Field(
        default="https://pubchem.ncbi.nlm.nih.gov/rest/pug",
        description="PubChem PUG REST API base URL",
    )
    uniprot_base_url: str = Field(
        default="https://rest.uniprot.org",
        description="UniProt REST API base URL",
    )
    drugbank_base_url: str = Field(
        default="https://api.drugbank.com/v1",
        description="DrugBank API base URL (requires subscription)",
    )

    # ==========================================================================
    # API Keys (where required)
    # ==========================================================================

    drugbank_api_key: str | None = Field(
        default=None,
        description="DrugBank API key (required for DrugBank API mode)",
    )
    drugbank_data_path: str | None = Field(
        default=None,
        description="Path to local DrugBank XML/CSV dataset (for local mode)",
    )

    # ==========================================================================
    # HTTP Client Settings
    # ==========================================================================

    connector_timeout: int = Field(
        default=30,
        description="Default request timeout in seconds",
        ge=1,
        le=300,
    )
    connector_max_retries: int = Field(
        default=3,
        description="Maximum number of retry attempts",
        ge=0,
        le=10,
    )
    connector_retry_backoff_base: float = Field(
        default=1.0,
        description="Base delay for exponential backoff (seconds)",
        ge=0.1,
        le=10.0,
    )
    connector_retry_backoff_max: float = Field(
        default=60.0,
        description="Maximum backoff delay (seconds)",
        ge=1.0,
        le=300.0,
    )

    # ==========================================================================
    # Rate Limiting
    # ==========================================================================

    chembl_rate_limit_rpm: int = Field(
        default=300,
        description="ChEMBL requests per minute limit",
    )
    pubchem_rate_limit_rpm: int = Field(
        default=300,
        description="PubChem requests per minute limit (5 req/sec)",
    )
    uniprot_rate_limit_rpm: int = Field(
        default=600,
        description="UniProt requests per minute limit",
    )
    drugbank_rate_limit_rpm: int = Field(
        default=60,
        description="DrugBank requests per minute limit",
    )

    # ==========================================================================
    # Caching
    # ==========================================================================

    connector_cache_backend: str = Field(
        default="redis",
        description="Cache backend: 'redis' or 'memory'",
        pattern="^(redis|memory)$",
    )
    connector_cache_ttl: int = Field(
        default=3600,
        description="Default cache TTL in seconds (1 hour)",
        ge=60,
        le=86400,
    )
    connector_cache_ttl_compound: int = Field(
        default=86400,
        description="Cache TTL for compound data (24 hours - stable data)",
    )
    connector_cache_ttl_search: int = Field(
        default=1800,
        description="Cache TTL for search results (30 min - may change)",
    )
    connector_cache_ttl_assay: int = Field(
        default=3600,
        description="Cache TTL for assay data (1 hour)",
    )

    # ==========================================================================
    # Redis Settings (inherited from main config, but can override)
    # ==========================================================================

    redis_url: str = Field(
        default="redis://localhost:6379/1",
        description="Redis URL for connector cache (separate DB from main)",
    )

    # ==========================================================================
    # Logging
    # ==========================================================================

    connector_log_requests: bool = Field(
        default=True,
        description="Log all connector requests",
    )
    connector_log_cache_hits: bool = Field(
        default=False,
        description="Log cache hits (verbose)",
    )

    model_config = {
        "env_prefix": "",
        "case_sensitive": False,
    }


# Singleton instance
connector_settings = ConnectorSettings()
