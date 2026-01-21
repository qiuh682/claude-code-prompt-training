"""
PubChem high-level connector for drug discovery workflows.

Provides domain-specific methods for:
- Compound search by name, SMILES, CID
- Property retrieval (MW, LogP, TPSA, etc.)
- Bioassay data retrieval

This connector uses ChEMBLClient for HTTP and ChEMBLNormalizer for
data transformation.
"""

import asyncio
import logging
from typing import AsyncIterator

from apps.api.connectors.pubchem.client import (
    BadRequestError,
    NotFoundError,
    PubChemClient,
)
from apps.api.connectors.pubchem.normalizer import PubChemNormalizer
from apps.api.connectors.pubchem.schemas import (
    AssayOutcome,
    BioassaySearchResult,
    CompoundProperties,
    CompoundSearchResult,
    PubChemAssay,
    PubChemBioactivity,
    PubChemCompound,
    SearchResult,
    SearchType,
)

logger = logging.getLogger(__name__)


class PubChemConnector:
    """
    High-level PubChem connector for drug discovery workflows.

    Example:
        async with PubChemConnector() as connector:
            # Search by name
            result = await connector.search_compounds("aspirin")

            # Get compound details
            compound = await connector.get_compound(2244)

            # Get properties
            props = await connector.get_properties(2244)

            # Get bioassay data
            assays = await connector.get_bioassays(2244)
    """

    # Cache TTLs
    SEARCH_CACHE_TTL = 300  # 5 minutes for searches
    COMPOUND_CACHE_TTL = 3600  # 1 hour for compound data
    ASSAY_CACHE_TTL = 1800  # 30 minutes for assay data

    def __init__(
        self,
        client: PubChemClient | None = None,
        normalizer: PubChemNormalizer | None = None,
    ):
        self._client = client
        self._normalizer = normalizer or PubChemNormalizer()
        self._owns_client = client is None

    async def _get_client(self) -> PubChemClient:
        """Lazy initialize client."""
        if self._client is None:
            self._client = PubChemClient()
        return self._client

    # =========================================================================
    # Search Methods
    # =========================================================================

    async def search_compounds(
        self,
        query: str,
        search_type: SearchType | str = SearchType.NAME,
        max_results: int = 100,
    ) -> SearchResult:
        """
        Search for compounds and return CIDs.

        Args:
            query: Search query (name, SMILES, InChI, etc.)
            search_type: Type of search (name, smiles, inchi, inchikey, formula)
            max_results: Maximum CIDs to return

        Returns:
            SearchResult with list of CIDs
        """
        client = await self._get_client()

        if isinstance(search_type, str):
            search_type = SearchType(search_type)

        try:
            cids = await client.search_cids(
                search_type.value,
                query,
                cache_ttl=self.SEARCH_CACHE_TTL,
            )
            cids = cids[:max_results]

            return SearchResult(
                query=query,
                search_type=search_type,
                cids=cids,
                total_count=len(cids),
            )
        except BadRequestError as e:
            logger.warning(f"Invalid search query '{query}': {e}")
            return SearchResult(
                query=query,
                search_type=search_type,
                cids=[],
                total_count=0,
            )

    async def search_compounds_with_details(
        self,
        query: str,
        search_type: SearchType | str = SearchType.NAME,
        limit: int = 20,
        include_synonyms: bool = False,
    ) -> CompoundSearchResult:
        """
        Search for compounds and return full compound data.

        Args:
            query: Search query
            search_type: Type of search
            limit: Maximum compounds to return with details
            include_synonyms: Whether to fetch synonyms (extra API calls)

        Returns:
            CompoundSearchResult with compound details
        """
        # First get CIDs
        search_result = await self.search_compounds(query, search_type, max_results=limit)

        if not search_result.cids:
            return CompoundSearchResult(
                query=query,
                search_type=search_result.search_type,
                compounds=[],
                total_count=0,
            )

        # Fetch properties in batch (max 100 per request)
        client = await self._get_client()
        compounds = []

        for i in range(0, len(search_result.cids), 100):
            batch_cids = search_result.cids[i : i + 100]

            try:
                raw_props = await client.get_properties_batch(
                    batch_cids,
                    cache_ttl=self.COMPOUND_CACHE_TTL,
                )

                # Optionally fetch synonyms
                synonyms_map: dict[int, list[str]] = {}
                if include_synonyms:
                    synonym_tasks = [
                        client.get_synonyms(cid, cache_ttl=self.COMPOUND_CACHE_TTL)
                        for cid in batch_cids
                    ]
                    synonym_results = await asyncio.gather(
                        *synonym_tasks, return_exceptions=True
                    )
                    for cid, syns in zip(batch_cids, synonym_results):
                        if isinstance(syns, list):
                            synonyms_map[cid] = syns[:30]  # Limit synonyms

                # Normalize
                batch_compounds = self._normalizer.normalize_compounds(
                    raw_props, synonyms_map
                )
                compounds.extend(batch_compounds)

            except Exception as e:
                logger.error(f"Error fetching batch properties: {e}")
                continue

        return CompoundSearchResult(
            query=query,
            search_type=search_result.search_type,
            compounds=compounds,
            total_count=len(compounds),
            page=1,
            page_size=limit,
            has_more=len(search_result.cids) > limit,
        )

    async def search_by_smiles(
        self,
        smiles: str,
        limit: int = 20,
    ) -> CompoundSearchResult:
        """
        Search compounds by SMILES string.

        Args:
            smiles: SMILES string
            limit: Maximum results

        Returns:
            CompoundSearchResult
        """
        return await self.search_compounds_with_details(
            smiles,
            search_type=SearchType.SMILES,
            limit=limit,
        )

    async def search_by_name(
        self,
        name: str,
        limit: int = 20,
        include_synonyms: bool = False,
    ) -> CompoundSearchResult:
        """
        Search compounds by name.

        Args:
            name: Compound name
            limit: Maximum results
            include_synonyms: Whether to include synonyms

        Returns:
            CompoundSearchResult
        """
        return await self.search_compounds_with_details(
            name,
            search_type=SearchType.NAME,
            limit=limit,
            include_synonyms=include_synonyms,
        )

    # =========================================================================
    # Compound Methods
    # =========================================================================

    async def get_compound(
        self,
        cid: int,
        include_synonyms: bool = True,
    ) -> PubChemCompound:
        """
        Get compound by CID.

        Args:
            cid: PubChem Compound ID
            include_synonyms: Whether to fetch synonyms

        Returns:
            Normalized PubChemCompound

        Raises:
            NotFoundError: If compound not found
        """
        client = await self._get_client()

        # Get properties
        raw_props = await client.get_properties(cid, cache_ttl=self.COMPOUND_CACHE_TTL)

        if not raw_props:
            raise NotFoundError(f"CID {cid}")

        # Get synonyms
        synonyms = []
        if include_synonyms:
            synonyms = await client.get_synonyms(cid, cache_ttl=self.COMPOUND_CACHE_TTL)
            synonyms = synonyms[:30]

        # Get title (first synonym is usually the title)
        compound = self._normalizer.normalize_compound_from_properties(raw_props, synonyms)

        # Set title from first synonym
        if synonyms and not compound.title:
            compound.title = synonyms[0]

        return compound

    async def get_compounds_batch(
        self,
        cids: list[int],
        include_synonyms: bool = False,
    ) -> list[PubChemCompound]:
        """
        Get multiple compounds by CIDs.

        Args:
            cids: List of CIDs (max 100)
            include_synonyms: Whether to fetch synonyms

        Returns:
            List of PubChemCompound objects
        """
        if not cids:
            return []

        if len(cids) > 100:
            # Split into batches
            compounds = []
            for i in range(0, len(cids), 100):
                batch = await self.get_compounds_batch(
                    cids[i : i + 100],
                    include_synonyms=include_synonyms,
                )
                compounds.extend(batch)
            return compounds

        client = await self._get_client()

        try:
            raw_props = await client.get_properties_batch(
                cids,
                cache_ttl=self.COMPOUND_CACHE_TTL,
            )

            synonyms_map: dict[int, list[str]] = {}
            if include_synonyms:
                synonym_tasks = [
                    client.get_synonyms(cid, cache_ttl=self.COMPOUND_CACHE_TTL)
                    for cid in cids
                ]
                results = await asyncio.gather(*synonym_tasks, return_exceptions=True)
                for cid, syns in zip(cids, results):
                    if isinstance(syns, list):
                        synonyms_map[cid] = syns[:30]

            return self._normalizer.normalize_compounds(raw_props, synonyms_map)

        except NotFoundError:
            return []

    # =========================================================================
    # Property Methods
    # =========================================================================

    async def get_properties(
        self,
        cid: int,
    ) -> CompoundProperties:
        """
        Get computed properties for a compound.

        Args:
            cid: PubChem Compound ID

        Returns:
            CompoundProperties with MW, LogP, TPSA, etc.
        """
        client = await self._get_client()
        raw_props = await client.get_properties(cid, cache_ttl=self.COMPOUND_CACHE_TTL)
        return self._normalizer.normalize_properties(raw_props)

    async def get_properties_dict(
        self,
        cid: int,
    ) -> dict:
        """
        Get properties as a raw dictionary.

        Args:
            cid: PubChem Compound ID

        Returns:
            Dict of property name -> value
        """
        client = await self._get_client()
        return await client.get_properties(cid, cache_ttl=self.COMPOUND_CACHE_TTL)

    # =========================================================================
    # Bioassay Methods
    # =========================================================================

    async def get_bioassays(
        self,
        cid: int,
        active_only: bool = False,
        limit: int = 100,
    ) -> BioassaySearchResult:
        """
        Get bioassay data for a compound.

        Args:
            cid: PubChem Compound ID
            active_only: Only return assays where compound was active
            limit: Maximum number of activities to return

        Returns:
            BioassaySearchResult with assays and activities
        """
        client = await self._get_client()

        # Get assay summary for this compound
        raw_summary = await client.get_assays_for_cid(cid, cache_ttl=self.ASSAY_CACHE_TTL)

        if not raw_summary:
            return BioassaySearchResult(
                cid=cid,
                assays=[],
                activities=[],
                total_assays=0,
                total_activities=0,
            )

        # Extract columns from first row header
        columns = []
        if raw_summary:
            columns = [
                "AID",
                "Assay Name",
                "Bioactivity Outcome",
                "Activity Value",
                "Activity Name",
                "Target Name",
                "Target GI",
            ]

        # Normalize activities
        activities = self._normalizer.normalize_bioactivities_from_summary(
            raw_summary,
            columns,
            cid,
        )

        # Filter active only if requested
        if active_only:
            activities = [a for a in activities if a.outcome == AssayOutcome.ACTIVE]

        activities = activities[:limit]

        # Get unique assay IDs and fetch assay details
        unique_aids = list(set(a.aid for a in activities))[:20]  # Limit assay fetches
        assays = []

        for aid in unique_aids:
            try:
                raw_assay = await client.get_assay(aid, cache_ttl=self.ASSAY_CACHE_TTL)
                assay = self._normalizer.normalize_assay(raw_assay)
                assays.append(assay)
            except Exception as e:
                logger.warning(f"Failed to fetch assay {aid}: {e}")
                continue

        return BioassaySearchResult(
            cid=cid,
            assays=assays,
            activities=activities,
            total_assays=len(assays),
            total_activities=len(activities),
        )

    async def get_assay(
        self,
        aid: int,
    ) -> PubChemAssay:
        """
        Get assay metadata by AID.

        Args:
            aid: PubChem Assay ID

        Returns:
            Normalized PubChemAssay
        """
        client = await self._get_client()
        raw_assay = await client.get_assay(aid, cache_ttl=self.ASSAY_CACHE_TTL)
        return self._normalizer.normalize_assay(raw_assay)

    async def get_active_compounds_for_target(
        self,
        target_gi: int,
        limit: int = 100,
    ) -> list[int]:
        """
        Get CIDs of active compounds for a target.

        Note: This uses the target GI number from NCBI.

        Args:
            target_gi: NCBI GI number for target
            limit: Maximum CIDs to return

        Returns:
            List of CIDs
        """
        client = await self._get_client()

        # PubChem allows searching assays by target
        endpoint = f"/assay/target/gi/{target_gi}/cids/JSON"

        try:
            data = await client.get(endpoint, cache_ttl=self.SEARCH_CACHE_TTL)
            cids = data.get("IdentifierList", {}).get("CID", [])
            return cids[:limit]
        except NotFoundError:
            return []

    # =========================================================================
    # Cross-Reference Methods
    # =========================================================================

    async def get_chembl_id(
        self,
        cid: int,
    ) -> str | None:
        """
        Get ChEMBL ID for a PubChem compound.

        Args:
            cid: PubChem CID

        Returns:
            ChEMBL ID if available, None otherwise
        """
        client = await self._get_client()

        try:
            xrefs = await client.get_xrefs(cid, "RegistryID", cache_ttl=self.COMPOUND_CACHE_TTL)
            for xref in xrefs:
                if xref.startswith("CHEMBL"):
                    return xref
            return None
        except NotFoundError:
            return None

    async def get_cas_number(
        self,
        cid: int,
    ) -> str | None:
        """
        Get CAS registry number for a compound.

        Args:
            cid: PubChem CID

        Returns:
            CAS number if available
        """
        client = await self._get_client()

        try:
            xrefs = await client.get_xrefs(cid, "RN", cache_ttl=self.COMPOUND_CACHE_TTL)
            return xrefs[0] if xrefs else None
        except NotFoundError:
            return None

    # =========================================================================
    # Streaming Methods (for bulk operations)
    # =========================================================================

    async def iter_compounds(
        self,
        cids: list[int],
        include_synonyms: bool = False,
        batch_size: int = 50,
    ) -> AsyncIterator[PubChemCompound]:
        """
        Stream compounds for bulk sync operations.

        Args:
            cids: List of CIDs to fetch
            include_synonyms: Whether to include synonyms
            batch_size: Compounds per batch

        Yields:
            PubChemCompound objects
        """
        for i in range(0, len(cids), batch_size):
            batch_cids = cids[i : i + batch_size]
            compounds = await self.get_compounds_batch(
                batch_cids,
                include_synonyms=include_synonyms,
            )
            for compound in compounds:
                yield compound

    async def iter_search_results(
        self,
        query: str,
        search_type: SearchType = SearchType.NAME,
        batch_size: int = 50,
        max_results: int = 1000,
    ) -> AsyncIterator[PubChemCompound]:
        """
        Stream search results for bulk operations.

        Args:
            query: Search query
            search_type: Type of search
            batch_size: Compounds per batch
            max_results: Maximum total results

        Yields:
            PubChemCompound objects
        """
        # Get all CIDs first
        search_result = await self.search_compounds(
            query,
            search_type,
            max_results=max_results,
        )

        async for compound in self.iter_compounds(
            search_result.cids,
            batch_size=batch_size,
        ):
            yield compound

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def close(self) -> None:
        """Close client connection."""
        if self._owns_client and self._client:
            await self._client.close()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
