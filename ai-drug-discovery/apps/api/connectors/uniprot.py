"""
UniProt database connector.

UniProt is a comprehensive resource for protein sequence and functional information.
API Documentation: https://www.uniprot.org/help/api

Features:
- Protein/target search by name, gene, organism
- Full protein details by UniProt accession
- Sequence retrieval
- Cross-references to PDB, ChEMBL, etc.
"""

from typing import Any

from apps.api.connectors.base import BaseConnector
from apps.api.connectors.exceptions import NotFoundError
from apps.api.connectors.schemas import (
    AssaySearchResult,
    CompoundSearchResult,
    DataSource,
    ExternalAssay,
    ExternalCompound,
    ExternalTarget,
    TargetSearchResult,
)
from apps.api.connectors.settings import connector_settings


class UniProtConnector(BaseConnector):
    """
    Connector for UniProt REST API.

    Example usage:
        connector = UniProtConnector()

        # Search targets by gene name
        results = await connector.search_targets("EGFR")

        # Get protein by UniProt ID
        target = await connector.get_target("P00533")

        # Get sequence
        sequence = await connector.get_sequence("P00533")
    """

    source = DataSource.UNIPROT
    base_url = connector_settings.uniprot_base_url
    rate_limit_rpm = connector_settings.uniprot_rate_limit_rpm

    def _get_default_headers(self) -> dict[str, str]:
        """UniProt prefers specific Accept headers."""
        return {
            "Accept": "application/json",
            "User-Agent": "AIdrugDiscovery/1.0 (research platform; contact@example.com)",
        }

    # ==========================================================================
    # Normalization Methods
    # ==========================================================================

    def normalize_compound(self, raw: dict) -> ExternalCompound:
        """UniProt doesn't have compound data."""
        raise NotImplementedError("UniProt connector does not support compound data")

    def normalize_target(self, raw: dict) -> ExternalTarget:
        """Normalize UniProt protein data."""
        # Extract gene info
        genes = raw.get("genes", [])
        gene_symbol = None
        gene_name = None
        if genes:
            primary_gene = genes[0]
            gene_symbol = primary_gene.get("geneName", {}).get("value")
            synonyms = primary_gene.get("synonyms", [])
            if synonyms:
                gene_name = synonyms[0].get("value")

        # Extract organism
        organism = raw.get("organism", {})
        organism_name = organism.get("scientificName", "")

        # Extract sequence
        sequence = raw.get("sequence", {})
        seq_value = sequence.get("value")
        seq_length = sequence.get("length")

        # Extract protein name
        protein = raw.get("proteinDescription", {})
        rec_name = protein.get("recommendedName", {})
        full_name = rec_name.get("fullName", {}).get("value", "")
        if not full_name:
            # Try submitted name
            sub_names = protein.get("submissionNames", [])
            if sub_names:
                full_name = sub_names[0].get("fullName", {}).get("value", "")

        # Extract family
        family = None
        comments = raw.get("comments", [])
        for comment in comments:
            if comment.get("commentType") == "SIMILARITY":
                texts = comment.get("texts", [])
                if texts:
                    family = texts[0].get("value", "")[:100]
                    break

        # Extract PDB IDs from cross-references
        pdb_ids = []
        xrefs = raw.get("uniProtKBCrossReferences", [])
        for xref in xrefs:
            if xref.get("database") == "PDB":
                pdb_id = xref.get("id")
                if pdb_id:
                    pdb_ids.append(pdb_id)

        # Extract ChEMBL target ID
        chembl_id = None
        for xref in xrefs:
            if xref.get("database") == "ChEMBL":
                chembl_id = xref.get("id")
                break

        return ExternalTarget(
            source=DataSource.UNIPROT,
            source_id=raw.get("primaryAccession", ""),
            uniprot_id=raw.get("primaryAccession"),
            gene_symbol=gene_symbol,
            gene_name=gene_name,
            name=full_name or gene_symbol or raw.get("primaryAccession", ""),
            organism=organism_name,
            target_type="SINGLE PROTEIN",
            family=family,
            sequence=seq_value,
            sequence_length=seq_length,
            chembl_target_id=chembl_id,
            pdb_ids=pdb_ids[:10],  # Limit to 10 PDB IDs
            description=self._extract_function(raw),
        )

    def normalize_assay(self, raw: dict) -> ExternalAssay:
        """UniProt doesn't have assay data."""
        raise NotImplementedError("UniProt connector does not support assay data")

    # ==========================================================================
    # Connector Contract Implementation
    # ==========================================================================

    async def search_compounds(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> CompoundSearchResult:
        """UniProt doesn't have compound data."""
        return CompoundSearchResult(
            compounds=[],
            total_count=0,
            page=page,
            page_size=page_size,
            has_more=False,
        )

    async def get_compound(self, compound_id: str) -> ExternalCompound:
        """UniProt doesn't have compound data."""
        raise NotFoundError(
            resource_type="Compound",
            resource_id=compound_id,
            connector=self.source.value,
        )

    async def get_target(self, target_id: str) -> ExternalTarget:
        """
        Get protein by UniProt accession.

        Args:
            target_id: UniProt accession (e.g., "P00533")
        """
        cache_key = self.make_cache_key("get_target", target_id)

        try:
            data = await self.request(
                "GET",
                f"/uniprotkb/{target_id}.json",
                cache_key=cache_key,
                cache_ttl=connector_settings.connector_cache_ttl_compound,
            )
        except NotFoundError:
            raise NotFoundError(
                resource_type="Target",
                resource_id=target_id,
                connector=self.source.value,
            )

        return self.normalize_target(data)

    async def search_targets(
        self,
        query: str,
        *,
        organism: str | None = "Homo sapiens",
        reviewed: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> TargetSearchResult:
        """
        Search for proteins/targets.

        Args:
            query: Search query (gene name, protein name, etc.)
            organism: Filter by organism (default: human)
            reviewed: Only return reviewed (Swiss-Prot) entries
            page: Page number
            page_size: Results per page
        """
        cache_key = self.make_cache_key(
            "search_targets", query, organism, reviewed, page, page_size
        )

        # Build query
        query_parts = [query]
        if organism:
            query_parts.append(f'(organism_name:"{organism}")')
        if reviewed:
            query_parts.append("(reviewed:true)")

        full_query = " AND ".join(query_parts)
        offset = (page - 1) * page_size

        data = await self.request(
            "GET",
            "/uniprotkb/search",
            params={
                "query": full_query,
                "format": "json",
                "size": page_size,
                "from": offset,
                "fields": "accession,id,gene_names,organism_name,protein_name,sequence,xref_pdb,xref_chembl",
            },
            cache_key=cache_key,
            cache_ttl=connector_settings.connector_cache_ttl_search,
        )

        results = data.get("results", [])

        # Get total from headers or estimate
        total = len(results)
        if "x-total-results" in data:
            total = int(data.get("x-total-results", 0))

        targets = [self.normalize_target(r) for r in results]

        return TargetSearchResult(
            targets=targets,
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=offset + len(targets) < total,
        )

    async def get_assays_by_target(
        self,
        target_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> AssaySearchResult:
        """
        UniProt doesn't have assay data.

        For assays, use ChEMBLConnector.get_assays_by_target() with the UniProt ID.
        """
        return AssaySearchResult(
            assays=[],
            total_count=0,
            page=page,
            page_size=page_size,
            has_more=False,
        )

    async def get_bioactivity(
        self,
        compound_id: str,
        *,
        target_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AssaySearchResult:
        """UniProt doesn't have bioactivity data."""
        return AssaySearchResult(
            assays=[],
            total_count=0,
            page=page,
            page_size=page_size,
            has_more=False,
        )

    # ==========================================================================
    # Additional UniProt-Specific Methods
    # ==========================================================================

    async def get_sequence(self, uniprot_id: str) -> str:
        """
        Get protein sequence in FASTA format.

        Args:
            uniprot_id: UniProt accession

        Returns:
            Amino acid sequence (without FASTA header)
        """
        cache_key = self.make_cache_key("get_sequence", uniprot_id)

        data = await self.request(
            "GET",
            f"/uniprotkb/{uniprot_id}.fasta",
            cache_key=cache_key,
            cache_ttl=connector_settings.connector_cache_ttl_compound,
        )

        # Parse FASTA - skip header line
        if isinstance(data, str):
            lines = data.strip().split("\n")
            sequence_lines = [l for l in lines if not l.startswith(">")]
            return "".join(sequence_lines)

        return ""

    async def get_by_gene(
        self,
        gene_symbol: str,
        organism: str = "Homo sapiens",
    ) -> ExternalTarget:
        """
        Get protein by gene symbol.

        Args:
            gene_symbol: Gene symbol (e.g., "EGFR")
            organism: Organism name

        Returns:
            ExternalTarget for the primary isoform
        """
        results = await self.search_targets(
            f'(gene:{gene_symbol})',
            organism=organism,
            reviewed=True,
            page=1,
            page_size=1,
        )

        if not results.targets:
            raise NotFoundError(
                resource_type="Target",
                resource_id=f"{gene_symbol} ({organism})",
                connector=self.source.value,
            )

        return results.targets[0]

    async def get_cross_references(
        self,
        uniprot_id: str,
        database: str | None = None,
    ) -> list[dict]:
        """
        Get cross-references to other databases.

        Args:
            uniprot_id: UniProt accession
            database: Filter by database (PDB, ChEMBL, etc.)

        Returns:
            List of cross-reference dicts
        """
        target = await self.get_target(uniprot_id)

        # This would require parsing the full response
        # For now, return PDB IDs from the target
        xrefs = []
        if target.pdb_ids:
            for pdb_id in target.pdb_ids:
                xrefs.append({"database": "PDB", "id": pdb_id})
        if target.chembl_target_id:
            xrefs.append({"database": "ChEMBL", "id": target.chembl_target_id})

        if database:
            xrefs = [x for x in xrefs if x["database"].upper() == database.upper()]

        return xrefs

    # ==========================================================================
    # Helper Methods
    # ==========================================================================

    def _extract_function(self, raw: dict) -> str | None:
        """Extract function description from comments."""
        comments = raw.get("comments", [])
        for comment in comments:
            if comment.get("commentType") == "FUNCTION":
                texts = comment.get("texts", [])
                if texts:
                    return texts[0].get("value", "")[:1000]
        return None
