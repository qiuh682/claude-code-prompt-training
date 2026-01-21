"""
High-level ChEMBL connector for drug discovery workflows.

Provides convenient methods for common drug discovery operations:
- Search compounds by target
- Get bioactivity data (IC50/Ki/EC50)
- Get assays by target
- Sync data to internal models

This connector uses:
- ChEMBLClient: Low-level HTTP with caching/rate limiting
- ChEMBLNormalizer: Data transformation to typed schemas
"""

import logging
from typing import AsyncIterator

from apps.api.connectors.chembl.client import ChEMBLClient, NotFoundError
from apps.api.connectors.chembl.normalizer import ChEMBLNormalizer
from apps.api.connectors.chembl.schemas import (
    AssaySearchResult,
    BioactivitySearchResult,
    ChEMBLAssay,
    ChEMBLBioactivity,
    ChEMBLCompound,
    ChEMBLTarget,
    CompoundSearchResult,
    TargetSearchResult,
)
from apps.api.connectors.settings import connector_settings

logger = logging.getLogger(__name__)


class ChEMBLConnector:
    """
    High-level ChEMBL connector for drug discovery workflows.

    Example:
        async with ChEMBLConnector() as chembl:
            # Search compounds active against EGFR
            compounds = await chembl.search_compounds_by_target("P00533")

            # Get bioactivity data for a target
            bioactivities = await chembl.get_bioactivities_by_target("CHEMBL203")

            # Get specific compound
            compound = await chembl.get_compound("CHEMBL25")

            # Stream all bioactivities (for sync)
            async for batch in chembl.iter_bioactivities_by_target("CHEMBL203"):
                for activity in batch:
                    print(f"{activity.molecule_chembl_id}: {activity.standard_value}")
    """

    def __init__(
        self,
        client: ChEMBLClient | None = None,
        normalizer: ChEMBLNormalizer | None = None,
    ):
        """
        Initialize connector.

        Args:
            client: Custom ChEMBL client (default: new instance)
            normalizer: Custom normalizer (default: new instance)
        """
        self._client = client or ChEMBLClient()
        self._normalizer = normalizer or ChEMBLNormalizer()
        self._owns_client = client is None

    async def close(self) -> None:
        """Close resources."""
        if self._owns_client:
            await self._client.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # =========================================================================
    # Compound Methods
    # =========================================================================

    async def get_compound(self, chembl_id: str) -> ChEMBLCompound:
        """
        Get a single compound by ChEMBL ID.

        Args:
            chembl_id: ChEMBL molecule ID (e.g., "CHEMBL25")

        Returns:
            Normalized ChEMBLCompound

        Raises:
            NotFoundError: Compound not found
        """
        endpoint = f"/molecule/{chembl_id}.json"
        data = await self._client.get(
            endpoint,
            cache_ttl=connector_settings.connector_cache_ttl_compound,
        )
        return self._normalizer.normalize_compound(data)

    async def search_compounds(
        self,
        query: str,
        page: int = 1,
        page_size: int = 20,
    ) -> CompoundSearchResult:
        """
        Search compounds by name, SMILES, or InChIKey.

        Args:
            query: Search query
            page: Page number (1-indexed)
            page_size: Results per page

        Returns:
            CompoundSearchResult with normalized compounds
        """
        offset = (page - 1) * page_size

        # Determine search strategy
        if query.startswith("CHEMBL"):
            # Direct ID lookup
            try:
                compound = await self.get_compound(query)
                return CompoundSearchResult(
                    compounds=[compound],
                    total_count=1,
                    page=1,
                    page_size=1,
                    has_more=False,
                )
            except NotFoundError:
                return CompoundSearchResult(
                    compounds=[],
                    total_count=0,
                    page=page,
                    page_size=page_size,
                    has_more=False,
                )

        # Text search
        data = await self._client.get(
            "/molecule/search.json",
            params={"q": query, "limit": page_size, "offset": offset},
            cache_ttl=connector_settings.connector_cache_ttl_search,
        )

        molecules = data.get("molecules", [])
        total = data.get("page_meta", {}).get("total_count", len(molecules))

        return CompoundSearchResult(
            compounds=self._normalizer.normalize_compounds(molecules),
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=offset + len(molecules) < total,
        )

    async def search_compounds_by_target(
        self,
        target_id: str,
        *,
        min_pchembl: float | None = None,
        activity_types: list[str] | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> CompoundSearchResult:
        """
        Search compounds with activity against a target.

        Args:
            target_id: ChEMBL target ID (e.g., "CHEMBL203") or UniProt ID (e.g., "P00533")
            min_pchembl: Minimum pChEMBL value (activity threshold, e.g., 6.0 = 1uM)
            activity_types: Filter by activity type (IC50, Ki, etc.)
            page: Page number
            page_size: Results per page

        Returns:
            CompoundSearchResult with compounds active against target
        """
        # Resolve UniProt to ChEMBL ID if needed
        chembl_target_id = await self._resolve_target_id(target_id)

        offset = (page - 1) * page_size

        # Build query params
        params = {
            "target_chembl_id": chembl_target_id,
            "limit": page_size,
            "offset": offset,
        }
        if min_pchembl:
            params["pchembl_value__gte"] = min_pchembl
        if activity_types:
            params["standard_type__in"] = ",".join(activity_types)

        # Fetch activities
        data = await self._client.get(
            "/activity.json",
            params=params,
            cache_ttl=connector_settings.connector_cache_ttl_assay,
        )

        activities = data.get("activities", [])
        total = data.get("page_meta", {}).get("total_count", len(activities))

        # Extract unique compound IDs
        compound_ids = list(dict.fromkeys(
            a.get("molecule_chembl_id") for a in activities if a.get("molecule_chembl_id")
        ))

        # Fetch full compound data for each unique ID
        compounds = []
        for cid in compound_ids[:page_size]:  # Limit batch size
            try:
                compound = await self.get_compound(cid)
                compounds.append(compound)
            except NotFoundError:
                logger.warning(f"Compound {cid} not found")
                continue

        return CompoundSearchResult(
            compounds=compounds,
            total_count=len(compound_ids),  # Unique compounds
            page=page,
            page_size=page_size,
            has_more=len(compound_ids) > len(compounds),
        )

    # =========================================================================
    # Target Methods
    # =========================================================================

    async def get_target(self, target_id: str) -> ChEMBLTarget:
        """
        Get a single target by ChEMBL ID or UniProt accession.

        Args:
            target_id: ChEMBL target ID (e.g., "CHEMBL203") or UniProt ID (e.g., "P00533")

        Returns:
            Normalized ChEMBLTarget

        Raises:
            NotFoundError: Target not found
        """
        if target_id.startswith("CHEMBL"):
            endpoint = f"/target/{target_id}.json"
            data = await self._client.get(
                endpoint,
                cache_ttl=connector_settings.connector_cache_ttl_compound,
            )
            return self._normalizer.normalize_target(data)

        # Search by UniProt ID
        data = await self._client.get(
            "/target.json",
            params={"target_components__accession": target_id, "limit": 1},
            cache_ttl=connector_settings.connector_cache_ttl_compound,
        )

        targets = data.get("targets", [])
        if not targets:
            raise NotFoundError(f"UniProt:{target_id}")

        return self._normalizer.normalize_target(targets[0])

    async def search_targets(
        self,
        query: str,
        *,
        organism: str | None = "Homo sapiens",
        target_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> TargetSearchResult:
        """
        Search targets by name, gene, or description.

        Args:
            query: Search query
            organism: Filter by organism
            target_type: Filter by type (SINGLE PROTEIN, PROTEIN COMPLEX, etc.)
            page: Page number
            page_size: Results per page

        Returns:
            TargetSearchResult with normalized targets
        """
        offset = (page - 1) * page_size

        params = {
            "q": query,
            "limit": page_size,
            "offset": offset,
        }
        if organism:
            params["organism"] = organism
        if target_type:
            params["target_type"] = target_type

        data = await self._client.get(
            "/target/search.json",
            params=params,
            cache_ttl=connector_settings.connector_cache_ttl_search,
        )

        targets = data.get("targets", [])
        total = data.get("page_meta", {}).get("total_count", len(targets))

        return TargetSearchResult(
            targets=self._normalizer.normalize_targets(targets),
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=offset + len(targets) < total,
        )

    # =========================================================================
    # Assay Methods
    # =========================================================================

    async def get_assay(self, assay_id: str) -> ChEMBLAssay:
        """
        Get a single assay by ChEMBL ID.

        Args:
            assay_id: ChEMBL assay ID (e.g., "CHEMBL615116")

        Returns:
            Normalized ChEMBLAssay
        """
        endpoint = f"/assay/{assay_id}.json"
        data = await self._client.get(
            endpoint,
            cache_ttl=connector_settings.connector_cache_ttl_assay,
        )
        return self._normalizer.normalize_assay(data)

    async def get_assays_by_target(
        self,
        target_id: str,
        *,
        assay_type: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> AssaySearchResult:
        """
        Get assays for a specific target.

        Args:
            target_id: ChEMBL target ID or UniProt ID
            assay_type: Filter by type (B=Binding, F=Functional, A=ADMET, etc.)
            page: Page number
            page_size: Results per page

        Returns:
            AssaySearchResult with normalized assays
        """
        chembl_target_id = await self._resolve_target_id(target_id)
        offset = (page - 1) * page_size

        params = {
            "target_chembl_id": chembl_target_id,
            "limit": page_size,
            "offset": offset,
        }
        if assay_type:
            params["assay_type"] = assay_type

        data = await self._client.get(
            "/assay.json",
            params=params,
            cache_ttl=connector_settings.connector_cache_ttl_assay,
        )

        assays = data.get("assays", [])
        total = data.get("page_meta", {}).get("total_count", len(assays))

        return AssaySearchResult(
            assays=self._normalizer.normalize_assays(assays),
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=offset + len(assays) < total,
        )

    # =========================================================================
    # Bioactivity Methods
    # =========================================================================

    async def get_bioactivities_by_target(
        self,
        target_id: str,
        *,
        activity_types: list[str] | None = None,
        min_pchembl: float | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> BioactivitySearchResult:
        """
        Get bioactivity data for a target.

        Args:
            target_id: ChEMBL target ID or UniProt ID
            activity_types: Filter by type (IC50, Ki, EC50, etc.)
            min_pchembl: Minimum pChEMBL value threshold
            page: Page number
            page_size: Results per page

        Returns:
            BioactivitySearchResult with normalized bioactivities
        """
        chembl_target_id = await self._resolve_target_id(target_id)
        offset = (page - 1) * page_size

        params = {
            "target_chembl_id": chembl_target_id,
            "limit": page_size,
            "offset": offset,
        }
        if activity_types:
            params["standard_type__in"] = ",".join(activity_types)
        if min_pchembl:
            params["pchembl_value__gte"] = min_pchembl

        data = await self._client.get(
            "/activity.json",
            params=params,
            cache_ttl=connector_settings.connector_cache_ttl_assay,
        )

        activities = data.get("activities", [])
        total = data.get("page_meta", {}).get("total_count", len(activities))

        return BioactivitySearchResult(
            bioactivities=self._normalizer.normalize_bioactivities(activities),
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=offset + len(activities) < total,
        )

    async def get_bioactivities_by_compound(
        self,
        compound_id: str,
        *,
        target_id: str | None = None,
        activity_types: list[str] | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> BioactivitySearchResult:
        """
        Get bioactivity data for a compound.

        Args:
            compound_id: ChEMBL compound ID
            target_id: Optional target filter
            activity_types: Filter by type
            page: Page number
            page_size: Results per page

        Returns:
            BioactivitySearchResult with normalized bioactivities
        """
        offset = (page - 1) * page_size

        params = {
            "molecule_chembl_id": compound_id,
            "limit": page_size,
            "offset": offset,
        }
        if target_id:
            chembl_target_id = await self._resolve_target_id(target_id)
            params["target_chembl_id"] = chembl_target_id
        if activity_types:
            params["standard_type__in"] = ",".join(activity_types)

        data = await self._client.get(
            "/activity.json",
            params=params,
            cache_ttl=connector_settings.connector_cache_ttl_assay,
        )

        activities = data.get("activities", [])
        total = data.get("page_meta", {}).get("total_count", len(activities))

        return BioactivitySearchResult(
            bioactivities=self._normalizer.normalize_bioactivities(activities),
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=offset + len(activities) < total,
        )

    # =========================================================================
    # Streaming Methods (for sync/bulk operations)
    # =========================================================================

    async def iter_bioactivities_by_target(
        self,
        target_id: str,
        *,
        activity_types: list[str] | None = None,
        min_pchembl: float | None = None,
        batch_size: int = 1000,
        max_results: int | None = None,
    ) -> AsyncIterator[list[ChEMBLBioactivity]]:
        """
        Stream all bioactivities for a target in batches.

        Useful for syncing large datasets to internal database.

        Args:
            target_id: ChEMBL target ID or UniProt ID
            activity_types: Filter by type
            min_pchembl: Minimum pChEMBL threshold
            batch_size: Results per batch
            max_results: Maximum total results

        Yields:
            Batches of normalized ChEMBLBioactivity
        """
        chembl_target_id = await self._resolve_target_id(target_id)

        params = {"target_chembl_id": chembl_target_id}
        if activity_types:
            params["standard_type__in"] = ",".join(activity_types)
        if min_pchembl:
            params["pchembl_value__gte"] = min_pchembl

        total_yielded = 0

        async for page in self._client.paginate(
            "/activity.json",
            params=params,
            page_size=batch_size,
        ):
            activities = page.get("activities", [])
            if not activities:
                break

            normalized = self._normalizer.normalize_bioactivities(activities)
            yield normalized

            total_yielded += len(normalized)
            if max_results and total_yielded >= max_results:
                break

    async def iter_compounds_by_target(
        self,
        target_id: str,
        *,
        min_pchembl: float | None = 5.0,
        batch_size: int = 100,
        max_results: int | None = None,
    ) -> AsyncIterator[list[ChEMBLCompound]]:
        """
        Stream compounds active against a target.

        Args:
            target_id: ChEMBL target ID or UniProt ID
            min_pchembl: Minimum pChEMBL value (default 5.0 = 10uM)
            batch_size: Compounds per batch
            max_results: Maximum total compounds

        Yields:
            Batches of normalized ChEMBLCompound
        """
        chembl_target_id = await self._resolve_target_id(target_id)
        seen_compounds = set()
        total_yielded = 0

        params = {"target_chembl_id": chembl_target_id}
        if min_pchembl:
            params["pchembl_value__gte"] = min_pchembl

        async for page in self._client.paginate("/activity.json", params=params):
            activities = page.get("activities", [])
            if not activities:
                break

            # Get unique compound IDs from this batch
            compound_ids = [
                a.get("molecule_chembl_id")
                for a in activities
                if a.get("molecule_chembl_id") and a.get("molecule_chembl_id") not in seen_compounds
            ]

            if not compound_ids:
                continue

            # Fetch compound details
            batch = []
            for cid in compound_ids[:batch_size]:
                if cid in seen_compounds:
                    continue
                seen_compounds.add(cid)

                try:
                    compound = await self.get_compound(cid)
                    batch.append(compound)
                except NotFoundError:
                    continue

                if max_results and total_yielded + len(batch) >= max_results:
                    break

            if batch:
                yield batch
                total_yielded += len(batch)

            if max_results and total_yielded >= max_results:
                break

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _resolve_target_id(self, target_id: str) -> str:
        """
        Resolve target ID to ChEMBL ID.

        If target_id starts with "CHEMBL", returns as-is.
        Otherwise, looks up by UniProt accession.
        """
        if target_id.startswith("CHEMBL"):
            return target_id

        # Cache UniProt -> ChEMBL mapping
        cache_key = f"uniprot_to_chembl:{target_id}"
        cached = await self._client._cache_get(cache_key)
        if cached:
            return cached

        target = await self.get_target(target_id)
        chembl_id = target.chembl_id

        await self._client._cache_set(cache_key, chembl_id, 86400)  # Cache 24h
        return chembl_id
