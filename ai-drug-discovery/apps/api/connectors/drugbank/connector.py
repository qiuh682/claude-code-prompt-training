"""
DrugBank high-level connector for drug discovery workflows.

Supports two operating modes:
1. API mode - Uses DrugBank commercial API (requires credentials)
2. Local mode - Uses downloaded XML/CSV dataset (free for academic use)

The connector auto-detects the best available mode based on configuration.

Example:
    connector = DrugBankConnector()

    # Check status
    status = await connector.get_status()
    print(f"Mode: {status.mode.value}")

    if status.is_configured:
        drug = await connector.get_drug("DB00945")
        targets = await connector.get_drug_targets("DB00945")
"""

import logging
from typing import AsyncIterator

from apps.api.connectors.drugbank.client import (
    DrugBankClient,
    NotConfiguredError,
    NotFoundError,
)
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
    DrugSearchHit,
    DrugSearchResult,
    DrugTargetInteraction,
    DTISearchResult,
)
from apps.api.connectors.settings import connector_settings

logger = logging.getLogger(__name__)


class DrugBankConnector:
    """
    High-level DrugBank connector with auto mode detection.

    Modes:
    - API: Uses DrugBank commercial API (set DRUGBANK_API_KEY)
    - Local: Uses downloaded dataset (set DRUGBANK_DATA_PATH)
    - Not Configured: Neither available

    Example:
        async with DrugBankConnector() as connector:
            # Get drug
            drug = await connector.get_drug("DB00945")

            # Get drug-target interactions
            result = await connector.get_drug_targets("DB00945")

            # Search drugs
            results = await connector.search_drugs("aspirin")
    """

    def __init__(
        self,
        api_key: str | None = None,
        data_path: str | None = None,
        prefer_api: bool = True,
    ):
        """
        Initialize connector.

        Args:
            api_key: DrugBank API key (or set DRUGBANK_API_KEY env var)
            data_path: Path to local DrugBank data (or set DRUGBANK_DATA_PATH env var)
            prefer_api: Prefer API over local data when both available
        """
        self._api_key = api_key or connector_settings.drugbank_api_key
        self._data_path = data_path or getattr(connector_settings, "drugbank_data_path", None)
        self._prefer_api = prefer_api

        self._client: DrugBankClient | None = None
        self._reader: DrugBankLocalReader | None = None
        self._normalizer = DrugBankNormalizer()

        self._mode: DrugBankMode | None = None

    # =========================================================================
    # Mode Detection
    # =========================================================================

    @property
    def mode(self) -> DrugBankMode:
        """Get current operating mode."""
        if self._mode is not None:
            return self._mode

        # Check API availability
        api_available = bool(self._api_key)

        # Check local data availability
        local_available = False
        if self._data_path:
            reader = DrugBankLocalReader(self._data_path)
            local_available = reader.is_available

        # Determine mode
        if api_available and (self._prefer_api or not local_available):
            self._mode = DrugBankMode.API
        elif local_available:
            self._mode = DrugBankMode.LOCAL
        else:
            self._mode = DrugBankMode.NOT_CONFIGURED

        return self._mode

    @property
    def is_configured(self) -> bool:
        """Check if connector is configured (either mode available)."""
        return self.mode != DrugBankMode.NOT_CONFIGURED

    async def get_status(self) -> DrugBankStatus:
        """
        Get detailed connector status.

        Returns:
            DrugBankStatus with mode and availability info
        """
        api_available = bool(self._api_key)

        local_available = False
        local_path = None
        drug_count = None

        if self._data_path:
            reader = DrugBankLocalReader(self._data_path)
            local_available = reader.is_available
            local_path = str(self._data_path) if local_available else None

            if local_available and self.mode == DrugBankMode.LOCAL:
                try:
                    await self._get_reader()
                    drug_count = len(self._reader._drug_index)
                except Exception:
                    pass

        message = None
        if not self.is_configured:
            message = (
                "DrugBank not configured. Set DRUGBANK_API_KEY for API access "
                "or DRUGBANK_DATA_PATH for local dataset."
            )

        return DrugBankStatus(
            mode=self.mode,
            is_configured=self.is_configured,
            api_available=api_available,
            local_data_available=local_available,
            local_data_path=local_path,
            drug_count=drug_count,
            message=message,
        )

    def _check_configured(self) -> None:
        """Raise error if not configured."""
        if not self.is_configured:
            raise NotConfiguredError()

    async def _get_client(self) -> DrugBankClient:
        """Get API client (API mode only)."""
        if self._client is None:
            self._client = DrugBankClient(api_key=self._api_key)
        return self._client

    async def _get_reader(self) -> DrugBankLocalReader:
        """Get local reader (local mode only)."""
        if self._reader is None:
            self._reader = DrugBankLocalReader(self._data_path)
            if not self._reader.is_available:
                raise LocalDataNotFoundError(self._data_path)
            await self._reader.load_index()
        return self._reader

    # =========================================================================
    # Core Drug Methods
    # =========================================================================

    async def get_drug(self, drugbank_id: str) -> DrugBankDrug:
        """
        Get drug by DrugBank ID.

        Args:
            drugbank_id: DrugBank ID (e.g., DB00945)

        Returns:
            Normalized DrugBankDrug

        Raises:
            NotConfiguredError: If connector not configured
            NotFoundError: If drug not found
        """
        self._check_configured()

        if self.mode == DrugBankMode.API:
            client = await self._get_client()
            raw_drug = await client.get_drug(drugbank_id)
            return self._normalizer.normalize_drug(raw_drug, source="api")

        else:  # Local mode
            reader = await self._get_reader()
            raw_drug = await reader.get_drug(drugbank_id)
            if not raw_drug:
                raise NotFoundError(drugbank_id)
            return self._normalizer.normalize_drug(raw_drug, source="local")

    async def get_drugs_batch(
        self,
        drugbank_ids: list[str],
    ) -> list[DrugBankDrug]:
        """
        Get multiple drugs by DrugBank IDs.

        Args:
            drugbank_ids: List of DrugBank IDs

        Returns:
            List of DrugBankDrug objects
        """
        self._check_configured()

        drugs = []
        for db_id in drugbank_ids:
            try:
                drug = await self.get_drug(db_id)
                drugs.append(drug)
            except NotFoundError:
                logger.warning(f"Drug not found: {db_id}")
                continue

        return drugs

    # =========================================================================
    # Drug-Target Interaction Methods
    # =========================================================================

    async def get_drug_targets(
        self,
        drugbank_id: str,
        include_enzymes: bool = True,
        include_carriers: bool = True,
        include_transporters: bool = True,
    ) -> DTISearchResult:
        """
        Get drug-target interactions for a drug.

        Args:
            drugbank_id: DrugBank ID
            include_enzymes: Include metabolizing enzymes
            include_carriers: Include carrier proteins
            include_transporters: Include transporters

        Returns:
            DTISearchResult with interactions
        """
        self._check_configured()

        interactions = []
        drug_name = None

        if self.mode == DrugBankMode.API:
            client = await self._get_client()

            # Get drug name
            try:
                drug_data = await client.get_drug(drugbank_id)
                drug_name = drug_data.get("name")
            except Exception:
                pass

            # Get targets
            try:
                raw_targets = await client.get_drug_targets(drugbank_id)
                for raw in raw_targets:
                    raw["target_type"] = "target"
                    dti = self._normalizer.normalize_dti(
                        raw, drugbank_id, drug_name, source="api"
                    )
                    interactions.append(dti)
            except NotFoundError:
                pass

            # Get enzymes
            if include_enzymes:
                try:
                    raw_enzymes = await client.get_drug_enzymes(drugbank_id)
                    for raw in raw_enzymes:
                        raw["target_type"] = "enzyme"
                        dti = self._normalizer.normalize_dti(
                            raw, drugbank_id, drug_name, source="api"
                        )
                        interactions.append(dti)
                except NotFoundError:
                    pass

            # Get carriers
            if include_carriers:
                try:
                    raw_carriers = await client.get_drug_carriers(drugbank_id)
                    for raw in raw_carriers:
                        raw["target_type"] = "carrier"
                        dti = self._normalizer.normalize_dti(
                            raw, drugbank_id, drug_name, source="api"
                        )
                        interactions.append(dti)
                except NotFoundError:
                    pass

            # Get transporters
            if include_transporters:
                try:
                    raw_transporters = await client.get_drug_transporters(drugbank_id)
                    for raw in raw_transporters:
                        raw["target_type"] = "transporter"
                        dti = self._normalizer.normalize_dti(
                            raw, drugbank_id, drug_name, source="api"
                        )
                        interactions.append(dti)
                except NotFoundError:
                    pass

        else:  # Local mode
            reader = await self._get_reader()

            # Get drug info
            drug_data = await reader.get_drug(drugbank_id)
            if drug_data:
                drug_name = drug_data.get("name")

                # Get all target types from local data
                for target in drug_data.get("targets", []):
                    dti = self._normalizer.normalize_dti(
                        target, drugbank_id, drug_name, source="local"
                    )
                    interactions.append(dti)

                if include_enzymes:
                    for enzyme in drug_data.get("enzymes", []):
                        enzyme["target_type"] = "enzyme"
                        dti = self._normalizer.normalize_dti(
                            enzyme, drugbank_id, drug_name, source="local"
                        )
                        interactions.append(dti)

                if include_carriers:
                    for carrier in drug_data.get("carriers", []):
                        carrier["target_type"] = "carrier"
                        dti = self._normalizer.normalize_dti(
                            carrier, drugbank_id, drug_name, source="local"
                        )
                        interactions.append(dti)

                if include_transporters:
                    for transporter in drug_data.get("transporters", []):
                        transporter["target_type"] = "transporter"
                        dti = self._normalizer.normalize_dti(
                            transporter, drugbank_id, drug_name, source="local"
                        )
                        interactions.append(dti)

        return DTISearchResult(
            drugbank_id=drugbank_id,
            drug_name=drug_name,
            interactions=interactions,
            total_count=len(interactions),
        )

    async def get_drugs_for_target(
        self,
        uniprot_id: str,
        limit: int = 100,
    ) -> list[DrugTargetInteraction]:
        """
        Get drugs that interact with a target (by UniProt ID).

        Note: Only available in API mode.

        Args:
            uniprot_id: UniProt accession
            limit: Maximum results

        Returns:
            List of DrugTargetInteraction objects
        """
        self._check_configured()

        if self.mode != DrugBankMode.API:
            logger.warning("get_drugs_for_target only available in API mode")
            return []

        client = await self._get_client()
        raw_drugs = await client.get_drugs_by_target(uniprot_id)

        interactions = []
        for raw in raw_drugs[:limit]:
            dti = DrugTargetInteraction(
                drugbank_id=raw.get("drugbank_id", ""),
                drug_name=raw.get("name"),
                uniprot_id=uniprot_id,
                target_name=raw.get("target_name"),
                actions=raw.get("actions", []),
            )
            interactions.append(dti)

        return interactions

    # =========================================================================
    # Search Methods
    # =========================================================================

    async def search_drugs(
        self,
        query: str,
        limit: int = 25,
    ) -> DrugSearchResult:
        """
        Search drugs by name or identifier.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            DrugSearchResult with hits
        """
        self._check_configured()

        if self.mode == DrugBankMode.API:
            client = await self._get_client()
            raw_results = await client.search_drugs(query, per_page=limit)

            hits = self._normalizer.normalize_search_hits(
                raw_results.get("drugs", raw_results.get("results", []))
            )
            total = raw_results.get("total", len(hits))

            return DrugSearchResult(
                query=query,
                hits=hits,
                total_count=total,
                page=1,
                page_size=limit,
                has_more=total > limit,
            )

        else:  # Local mode
            reader = await self._get_reader()
            raw_results = await reader.search_drugs(query, limit=limit)

            hits = self._normalizer.normalize_search_hits(raw_results)

            return DrugSearchResult(
                query=query,
                hits=hits,
                total_count=len(hits),
                page=1,
                page_size=limit,
                has_more=False,  # Local search doesn't track total
            )

    # =========================================================================
    # ADMET Methods
    # =========================================================================

    async def get_admet(self, drugbank_id: str) -> ADMETProperties:
        """
        Get ADMET properties for a drug.

        Args:
            drugbank_id: DrugBank ID

        Returns:
            ADMETProperties (may have null fields if data unavailable)
        """
        drug = await self.get_drug(drugbank_id)
        return drug.admet

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    async def get_approved_drugs(
        self,
        limit: int = 100,
    ) -> list[DrugSearchHit]:
        """
        Get approved drugs.

        Note: Only available in API mode (limited in local mode).

        Args:
            limit: Maximum results

        Returns:
            List of DrugSearchHit for approved drugs
        """
        result = await self.search_drugs("approved", limit=limit)
        return [hit for hit in result.hits if hit.groups]

    async def get_drug_by_name(
        self,
        name: str,
    ) -> DrugBankDrug | None:
        """
        Get drug by name (exact match preferred).

        Args:
            name: Drug name

        Returns:
            DrugBankDrug if found, None otherwise
        """
        result = await self.search_drugs(name, limit=5)

        # Find exact match
        for hit in result.hits:
            if hit.name.lower() == name.lower():
                return await self.get_drug(hit.drugbank_id)

        # Return first result if no exact match
        if result.hits:
            return await self.get_drug(result.hits[0].drugbank_id)

        return None

    # =========================================================================
    # Streaming Methods
    # =========================================================================

    async def iter_drugs(
        self,
        drugbank_ids: list[str] | None = None,
    ) -> AsyncIterator[DrugBankDrug]:
        """
        Stream drugs.

        Args:
            drugbank_ids: Specific IDs to iterate (None = all in local mode)

        Yields:
            DrugBankDrug objects
        """
        self._check_configured()

        if drugbank_ids:
            for db_id in drugbank_ids:
                try:
                    yield await self.get_drug(db_id)
                except NotFoundError:
                    continue
        elif self.mode == DrugBankMode.LOCAL:
            reader = await self._get_reader()
            async for raw_drug in reader.iter_drugs():
                yield self._normalizer.normalize_drug(raw_drug, source="local")
        else:
            logger.warning("iter_drugs without IDs only available in local mode")

    async def iter_dtis(
        self,
        drugbank_ids: list[str],
    ) -> AsyncIterator[DrugTargetInteraction]:
        """
        Stream drug-target interactions for multiple drugs.

        Args:
            drugbank_ids: DrugBank IDs to get DTIs for

        Yields:
            DrugTargetInteraction objects
        """
        for db_id in drugbank_ids:
            try:
                result = await self.get_drug_targets(db_id)
                for dti in result.interactions:
                    yield dti
            except NotFoundError:
                continue

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def close(self) -> None:
        """Close connections."""
        if self._client:
            await self._client.close()
            self._client = None

        if self._reader:
            self._reader.clear_cache()
            self._reader = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
