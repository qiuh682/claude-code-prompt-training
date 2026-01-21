"""
UniProt high-level connector for drug discovery workflows.

Provides domain-specific methods for:
- Fetching protein/target data by UniProt ID
- Searching targets by gene, protein name, or keywords
- Target profiling with annotations (function, domains, families)

This connector uses UniProtClient for HTTP and UniProtNormalizer for
data transformation.
"""

import logging
from typing import AsyncIterator

from apps.api.connectors.uniprot.client import (
    NotFoundError,
    UniProtClient,
)
from apps.api.connectors.uniprot.normalizer import UniProtNormalizer
from apps.api.connectors.uniprot.schemas import (
    ReviewStatus,
    TargetSearchHit,
    TargetSearchResult,
    TargetSummary,
    UniProtTarget,
)

logger = logging.getLogger(__name__)


class UniProtConnector:
    """
    High-level UniProt connector for drug discovery target profiling.

    Example:
        async with UniProtConnector() as connector:
            # Get target by UniProt ID
            target = await connector.get_target("P00533")

            # Search targets
            result = await connector.search_targets("EGFR human")

            # Get sequence
            sequence = await connector.get_sequence("P00533")
    """

    # Cache TTLs - protein data is very stable
    ENTRY_CACHE_TTL = 86400  # 24 hours
    SEARCH_CACHE_TTL = 3600  # 1 hour

    # Common organism IDs
    HUMAN = 9606
    MOUSE = 10090
    RAT = 10116
    ZEBRAFISH = 7955
    YEAST = 559292
    ECOLI = 83333

    def __init__(
        self,
        client: UniProtClient | None = None,
        normalizer: UniProtNormalizer | None = None,
    ):
        self._client = client
        self._normalizer = normalizer or UniProtNormalizer()
        self._owns_client = client is None

    async def _get_client(self) -> UniProtClient:
        """Lazy initialize client."""
        if self._client is None:
            self._client = UniProtClient()
        return self._client

    # =========================================================================
    # Core Target Methods
    # =========================================================================

    async def get_target(
        self,
        uniprot_id: str,
    ) -> UniProtTarget:
        """
        Get target by UniProt accession.

        Args:
            uniprot_id: UniProt accession (e.g., P00533)

        Returns:
            Normalized UniProtTarget with full annotations

        Raises:
            NotFoundError: If target not found
        """
        client = await self._get_client()
        raw_entry = await client.get_entry(uniprot_id, cache_ttl=self.ENTRY_CACHE_TTL)
        return self._normalizer.normalize_target(raw_entry)

    async def get_target_summary(
        self,
        uniprot_id: str,
    ) -> TargetSummary:
        """
        Get simplified target summary.

        Args:
            uniprot_id: UniProt accession

        Returns:
            TargetSummary with essential fields
        """
        client = await self._get_client()
        raw_entry = await client.get_entry(uniprot_id, cache_ttl=self.ENTRY_CACHE_TTL)
        return self._normalizer.normalize_target_summary(raw_entry)

    async def get_targets_batch(
        self,
        uniprot_ids: list[str],
    ) -> list[UniProtTarget]:
        """
        Get multiple targets by UniProt accessions.

        Args:
            uniprot_ids: List of UniProt accessions

        Returns:
            List of UniProtTarget objects
        """
        if not uniprot_ids:
            return []

        client = await self._get_client()
        raw_entries = await client.get_entry_batch(
            uniprot_ids,
            cache_ttl=self.ENTRY_CACHE_TTL,
        )
        return self._normalizer.normalize_targets(raw_entries)

    async def get_sequence(
        self,
        uniprot_id: str,
    ) -> str:
        """
        Get protein sequence.

        Args:
            uniprot_id: UniProt accession

        Returns:
            Amino acid sequence string
        """
        target = await self.get_target(uniprot_id)
        if target.sequence:
            return target.sequence

        # Fallback to FASTA endpoint
        client = await self._get_client()
        fasta = await client.get_fasta(uniprot_id, cache_ttl=self.ENTRY_CACHE_TTL)

        # Parse FASTA
        lines = fasta.strip().split("\n")
        sequence_lines = [line for line in lines if not line.startswith(">")]
        return "".join(sequence_lines)

    async def get_fasta(
        self,
        uniprot_id: str,
    ) -> str:
        """
        Get protein sequence in FASTA format.

        Args:
            uniprot_id: UniProt accession

        Returns:
            FASTA formatted sequence
        """
        client = await self._get_client()
        return await client.get_fasta(uniprot_id, cache_ttl=self.ENTRY_CACHE_TTL)

    # =========================================================================
    # Search Methods
    # =========================================================================

    async def search_targets(
        self,
        query: str,
        limit: int = 25,
        reviewed_only: bool = True,
    ) -> TargetSearchResult:
        """
        Search targets by query string.

        Args:
            query: Search query (gene name, protein name, keyword, etc.)
            limit: Maximum results to return
            reviewed_only: Only return Swiss-Prot (reviewed) entries

        Returns:
            TargetSearchResult with hits and pagination info
        """
        client = await self._get_client()

        raw_results = await client.search(
            query,
            size=limit,
            reviewed_only=reviewed_only,
            cache_ttl=self.SEARCH_CACHE_TTL,
        )

        hits = self._normalizer.normalize_search_results(raw_results)

        # Get total from response
        total = len(hits)
        link_header = raw_results.get("_links", {})
        if "next" in link_header:
            total = 9999  # Unknown total, but has more

        return TargetSearchResult(
            query=query,
            hits=hits,
            total_count=total,
            page=1,
            page_size=limit,
            has_more="next" in raw_results.get("_links", {}),
        )

    async def search_by_gene(
        self,
        gene_name: str,
        organism_id: int | None = None,
        reviewed_only: bool = True,
        limit: int = 25,
    ) -> TargetSearchResult:
        """
        Search targets by gene name/symbol.

        Args:
            gene_name: Gene symbol or name (e.g., "EGFR", "TP53")
            organism_id: NCBI taxonomy ID (default: human 9606)
            reviewed_only: Only Swiss-Prot entries
            limit: Maximum results

        Returns:
            TargetSearchResult
        """
        client = await self._get_client()

        raw_results = await client.search_by_gene(
            gene_name,
            organism_id=organism_id,
            reviewed_only=reviewed_only,
            size=limit,
            cache_ttl=self.SEARCH_CACHE_TTL,
        )

        hits = self._normalizer.normalize_search_results(raw_results)

        return TargetSearchResult(
            query=f"gene:{gene_name}",
            hits=hits,
            total_count=len(hits),
            page=1,
            page_size=limit,
            has_more="next" in raw_results.get("_links", {}),
        )

    async def search_by_protein_name(
        self,
        name: str,
        organism_id: int | None = None,
        reviewed_only: bool = True,
        limit: int = 25,
    ) -> TargetSearchResult:
        """
        Search targets by protein name.

        Args:
            name: Protein name or keyword
            organism_id: NCBI taxonomy ID
            reviewed_only: Only Swiss-Prot entries
            limit: Maximum results

        Returns:
            TargetSearchResult
        """
        client = await self._get_client()

        raw_results = await client.search_by_protein_name(
            name,
            organism_id=organism_id,
            reviewed_only=reviewed_only,
            size=limit,
            cache_ttl=self.SEARCH_CACHE_TTL,
        )

        hits = self._normalizer.normalize_search_results(raw_results)

        return TargetSearchResult(
            query=f"protein_name:{name}",
            hits=hits,
            total_count=len(hits),
            page=1,
            page_size=limit,
            has_more="next" in raw_results.get("_links", {}),
        )

    async def search_human_gene(
        self,
        gene_name: str,
        reviewed_only: bool = True,
    ) -> UniProtTarget | None:
        """
        Get human protein by gene symbol.

        Convenience method for the most common use case.

        Args:
            gene_name: Gene symbol (e.g., "EGFR")
            reviewed_only: Only Swiss-Prot entries

        Returns:
            UniProtTarget if found, None otherwise
        """
        result = await self.search_by_gene(
            gene_name,
            organism_id=self.HUMAN,
            reviewed_only=reviewed_only,
            limit=1,
        )

        if not result.hits:
            return None

        return await self.get_target(result.hits[0].uniprot_id)

    async def search_by_keyword(
        self,
        keyword: str,
        organism_id: int | None = None,
        reviewed_only: bool = True,
        limit: int = 100,
    ) -> TargetSearchResult:
        """
        Search targets by UniProt keyword.

        Args:
            keyword: UniProt keyword (e.g., "Kinase", "GPCR", "Ion channel")
            organism_id: NCBI taxonomy ID
            reviewed_only: Only Swiss-Prot entries
            limit: Maximum results

        Returns:
            TargetSearchResult
        """
        query = f'keyword:"{keyword}"'
        if organism_id:
            query += f" AND organism_id:{organism_id}"

        return await self.search_targets(
            query,
            limit=limit,
            reviewed_only=reviewed_only,
        )

    async def search_by_ec_number(
        self,
        ec_number: str,
        organism_id: int | None = None,
        reviewed_only: bool = True,
        limit: int = 50,
    ) -> TargetSearchResult:
        """
        Search enzymes by EC number.

        Args:
            ec_number: EC number (e.g., "2.7.10.1" for receptor tyrosine kinases)
            organism_id: NCBI taxonomy ID
            reviewed_only: Only Swiss-Prot entries
            limit: Maximum results

        Returns:
            TargetSearchResult
        """
        client = await self._get_client()

        raw_results = await client.search_by_ec_number(
            ec_number,
            organism_id=organism_id,
            reviewed_only=reviewed_only,
            size=limit,
            cache_ttl=self.SEARCH_CACHE_TTL,
        )

        hits = self._normalizer.normalize_search_results(raw_results)

        return TargetSearchResult(
            query=f"ec:{ec_number}",
            hits=hits,
            total_count=len(hits),
            page=1,
            page_size=limit,
            has_more="next" in raw_results.get("_links", {}),
        )

    # =========================================================================
    # Drug Discovery Target Categories
    # =========================================================================

    async def get_human_kinases(
        self,
        limit: int = 500,
    ) -> list[TargetSearchHit]:
        """
        Get all human protein kinases.

        Common drug discovery targets.

        Args:
            limit: Maximum results

        Returns:
            List of TargetSearchHit for kinases
        """
        result = await self.search_by_keyword(
            "Kinase",
            organism_id=self.HUMAN,
            reviewed_only=True,
            limit=limit,
        )
        return result.hits

    async def get_human_gpcrs(
        self,
        limit: int = 500,
    ) -> list[TargetSearchHit]:
        """
        Get human G protein-coupled receptors.

        Major drug target class.

        Args:
            limit: Maximum results

        Returns:
            List of TargetSearchHit for GPCRs
        """
        result = await self.search_by_keyword(
            "G-protein coupled receptor",
            organism_id=self.HUMAN,
            reviewed_only=True,
            limit=limit,
        )
        return result.hits

    async def get_human_ion_channels(
        self,
        limit: int = 500,
    ) -> list[TargetSearchHit]:
        """
        Get human ion channels.

        Args:
            limit: Maximum results

        Returns:
            List of TargetSearchHit for ion channels
        """
        result = await self.search_by_keyword(
            "Ion channel",
            organism_id=self.HUMAN,
            reviewed_only=True,
            limit=limit,
        )
        return result.hits

    async def get_human_proteases(
        self,
        limit: int = 500,
    ) -> list[TargetSearchHit]:
        """
        Get human proteases.

        Args:
            limit: Maximum results

        Returns:
            List of TargetSearchHit for proteases
        """
        result = await self.search_by_keyword(
            "Protease",
            organism_id=self.HUMAN,
            reviewed_only=True,
            limit=limit,
        )
        return result.hits

    # =========================================================================
    # Cross-Reference Methods
    # =========================================================================

    async def get_chembl_id(
        self,
        uniprot_id: str,
    ) -> str | None:
        """
        Get ChEMBL target ID for a UniProt entry.

        Args:
            uniprot_id: UniProt accession

        Returns:
            ChEMBL ID if available
        """
        try:
            target = await self.get_target(uniprot_id)
            return target.chembl_id
        except NotFoundError:
            return None

    async def get_pdb_ids(
        self,
        uniprot_id: str,
    ) -> list[str]:
        """
        Get PDB structure IDs for a protein.

        Args:
            uniprot_id: UniProt accession

        Returns:
            List of PDB IDs
        """
        try:
            target = await self.get_target(uniprot_id)
            return target.pdb_ids
        except NotFoundError:
            return []

    async def uniprot_to_chembl(
        self,
        uniprot_ids: list[str],
    ) -> dict[str, str | None]:
        """
        Map UniProt IDs to ChEMBL IDs.

        Args:
            uniprot_ids: List of UniProt accessions

        Returns:
            Dict mapping UniProt ID -> ChEMBL ID (or None)
        """
        targets = await self.get_targets_batch(uniprot_ids)

        result = {}
        for target in targets:
            result[target.uniprot_id] = target.chembl_id

        # Fill in missing IDs as None
        for uid in uniprot_ids:
            if uid not in result:
                result[uid] = None

        return result

    # =========================================================================
    # Streaming Methods
    # =========================================================================

    async def iter_targets(
        self,
        uniprot_ids: list[str],
        batch_size: int = 25,
    ) -> AsyncIterator[UniProtTarget]:
        """
        Stream targets for bulk operations.

        Args:
            uniprot_ids: List of UniProt IDs
            batch_size: IDs per batch

        Yields:
            UniProtTarget objects
        """
        for i in range(0, len(uniprot_ids), batch_size):
            batch_ids = uniprot_ids[i : i + batch_size]
            targets = await self.get_targets_batch(batch_ids)
            for target in targets:
                yield target

    async def iter_search_results(
        self,
        query: str,
        reviewed_only: bool = True,
        max_results: int = 1000,
    ) -> AsyncIterator[TargetSearchHit]:
        """
        Stream search results.

        Args:
            query: Search query
            reviewed_only: Only Swiss-Prot entries
            max_results: Maximum total results

        Yields:
            TargetSearchHit objects
        """
        client = await self._get_client()
        cursor = None
        total_yielded = 0

        while total_yielded < max_results:
            remaining = max_results - total_yielded
            size = min(remaining, 500)

            raw_results = await client.search(
                query,
                size=size,
                cursor=cursor,
                reviewed_only=reviewed_only,
                cache_ttl=self.SEARCH_CACHE_TTL,
            )

            hits = self._normalizer.normalize_search_results(raw_results)
            if not hits:
                break

            for hit in hits:
                yield hit
                total_yielded += 1
                if total_yielded >= max_results:
                    break

            # Get next cursor
            links = raw_results.get("_links", {})
            next_link = links.get("next", {}).get("href")
            if not next_link:
                break

            # Extract cursor from next link
            import re
            cursor_match = re.search(r"cursor=([^&]+)", next_link)
            if cursor_match:
                cursor = cursor_match.group(1)
            else:
                break

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
