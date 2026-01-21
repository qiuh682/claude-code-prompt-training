"""
ChEMBL database connector.

ChEMBL is a manually curated database of bioactive molecules with drug-like properties.
API Documentation: https://www.ebi.ac.uk/chembl/api/data/docs

Features:
- Compound search and retrieval
- Target search by UniProt ID
- Bioactivity/assay data
- Mechanism of action data
"""

from decimal import Decimal
from typing import Any

from apps.api.connectors.base import BaseConnector
from apps.api.connectors.exceptions import NotFoundError
from apps.api.connectors.schemas import (
    AssaySearchResult,
    AssayType,
    CompoundSearchResult,
    DataSource,
    ExternalAssay,
    ExternalCompound,
    ExternalTarget,
    ResultType,
    TargetSearchResult,
)
from apps.api.connectors.settings import connector_settings


class ChEMBLConnector(BaseConnector):
    """
    Connector for ChEMBL REST API.

    Example usage:
        connector = ChEMBLConnector()

        # Search compounds
        results = await connector.search_compounds("aspirin")

        # Get specific compound
        compound = await connector.get_compound("CHEMBL25")

        # Get target by UniProt
        target = await connector.get_target("P00533")

        # Get bioactivity for compound
        assays = await connector.get_bioactivity("CHEMBL25")
    """

    source = DataSource.CHEMBL
    base_url = connector_settings.chembl_base_url
    rate_limit_rpm = connector_settings.chembl_rate_limit_rpm

    # ==========================================================================
    # Normalization Methods
    # ==========================================================================

    def normalize_compound(self, raw: dict) -> ExternalCompound:
        """Normalize ChEMBL molecule data."""
        props = raw.get("molecule_properties") or {}
        structures = raw.get("molecule_structures") or {}

        return ExternalCompound(
            source=DataSource.CHEMBL,
            source_id=raw.get("molecule_chembl_id", ""),
            # Chemical identifiers
            canonical_smiles=structures.get("canonical_smiles"),
            inchi=structures.get("standard_inchi"),
            inchi_key=structures.get("standard_inchi_key"),
            # Names
            name=raw.get("pref_name"),
            synonyms=self._extract_synonyms(raw),
            # Properties
            molecular_formula=props.get("full_molformula"),
            molecular_weight=self._to_decimal(props.get("full_mwt")),
            exact_mass=self._to_decimal(props.get("mw_monoisotopic")),
            logp=self._to_decimal(props.get("alogp")),
            hbd=self._to_int(props.get("hbd")),
            hba=self._to_int(props.get("hba")),
            tpsa=self._to_decimal(props.get("psa")),
            rotatable_bonds=self._to_int(props.get("rtb")),
            # External refs
            chembl_id=raw.get("molecule_chembl_id"),
            # Metadata
            description=raw.get("molecule_type"),
        )

    def normalize_target(self, raw: dict) -> ExternalTarget:
        """Normalize ChEMBL target data."""
        # Extract UniProt ID from cross-references
        uniprot_id = None
        components = raw.get("target_components") or []
        for comp in components:
            xrefs = comp.get("target_component_xrefs") or []
            for xref in xrefs:
                if xref.get("xref_src_db") == "UniProt":
                    uniprot_id = xref.get("xref_id")
                    break
            if uniprot_id:
                break

        return ExternalTarget(
            source=DataSource.CHEMBL,
            source_id=raw.get("target_chembl_id", ""),
            uniprot_id=uniprot_id,
            gene_symbol=None,  # Not directly available in target response
            name=raw.get("pref_name", ""),
            organism=raw.get("organism", ""),
            target_type=raw.get("target_type"),
            family=raw.get("target_class"),
            chembl_target_id=raw.get("target_chembl_id"),
            description=raw.get("target_description"),
        )

    def normalize_assay(self, raw: dict) -> ExternalAssay:
        """Normalize ChEMBL activity/assay data."""
        return ExternalAssay(
            source=DataSource.CHEMBL,
            source_id=raw.get("activity_id", str(raw.get("assay_chembl_id", ""))),
            compound_source_id=raw.get("molecule_chembl_id"),
            target_source_id=raw.get("target_chembl_id"),
            assay_type=self._map_assay_type(raw.get("assay_type")),
            assay_name=raw.get("assay_description"),
            assay_description=raw.get("assay_description"),
            result_type=self._map_result_type(raw.get("standard_type")),
            result_value=self._to_decimal(raw.get("standard_value")),
            result_unit=raw.get("standard_units"),
            result_qualifier=raw.get("standard_relation"),
            confidence_score=self._to_int(raw.get("data_validity_comment")),
            publication_doi=raw.get("document_chembl_id"),
        )

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
        """
        Search for compounds in ChEMBL.

        Supports:
        - Name search: "aspirin"
        - SMILES search: "CC(=O)OC1=CC=CC=C1C(=O)O"
        - InChIKey search: "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
        - ChEMBL ID search: "CHEMBL25"
        """
        cache_key = self.make_cache_key("search_compounds", query, page, page_size)
        offset = (page - 1) * page_size

        # Determine search type
        if query.startswith("CHEMBL"):
            # Direct ChEMBL ID lookup
            endpoint = f"/molecule/{query}.json"
            params = None
        elif len(query) == 27 and "-" in query:
            # InChIKey search
            endpoint = "/molecule.json"
            params = {
                "molecule_structures__standard_inchi_key": query,
                "limit": page_size,
                "offset": offset,
            }
        else:
            # Name/synonym search
            endpoint = "/molecule/search.json"
            params = {
                "q": query,
                "limit": page_size,
                "offset": offset,
            }

        data = await self.request(
            "GET",
            endpoint,
            params=params,
            cache_key=cache_key,
            cache_ttl=connector_settings.connector_cache_ttl_search,
        )

        # Handle single result vs list
        if isinstance(data, dict) and "molecules" in data:
            molecules = data.get("molecules", [])
            total = data.get("page_meta", {}).get("total_count", len(molecules))
        elif isinstance(data, dict) and "molecule_chembl_id" in data:
            molecules = [data]
            total = 1
        else:
            molecules = []
            total = 0

        compounds = [self.normalize_compound(m) for m in molecules]

        return CompoundSearchResult(
            compounds=compounds,
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=offset + len(compounds) < total,
        )

    async def get_compound(self, compound_id: str) -> ExternalCompound:
        """
        Get compound by ChEMBL ID.

        Args:
            compound_id: ChEMBL ID (e.g., "CHEMBL25")
        """
        cache_key = self.make_cache_key("get_compound", compound_id)

        try:
            data = await self.request(
                "GET",
                f"/molecule/{compound_id}.json",
                cache_key=cache_key,
                cache_ttl=connector_settings.connector_cache_ttl_compound,
            )
        except NotFoundError:
            raise NotFoundError(
                resource_type="Compound",
                resource_id=compound_id,
                connector=self.source.value,
            )

        return self.normalize_compound(data)

    async def get_target(self, target_id: str) -> ExternalTarget:
        """
        Get target by ChEMBL ID or UniProt accession.

        Args:
            target_id: ChEMBL target ID (e.g., "CHEMBL203") or UniProt ID (e.g., "P00533")
        """
        cache_key = self.make_cache_key("get_target", target_id)

        # Check if it's a UniProt ID (typically 6-10 alphanumeric chars)
        if not target_id.startswith("CHEMBL"):
            # Search by UniProt
            data = await self.request(
                "GET",
                "/target.json",
                params={
                    "target_components__accession": target_id,
                    "limit": 1,
                },
                cache_key=cache_key,
                cache_ttl=connector_settings.connector_cache_ttl_compound,
            )
            targets = data.get("targets", [])
            if not targets:
                raise NotFoundError(
                    resource_type="Target",
                    resource_id=target_id,
                    connector=self.source.value,
                )
            return self.normalize_target(targets[0])

        # Direct ChEMBL ID lookup
        try:
            data = await self.request(
                "GET",
                f"/target/{target_id}.json",
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
        page: int = 1,
        page_size: int = 20,
    ) -> TargetSearchResult:
        """
        Search for targets by name or gene symbol.

        Args:
            query: Target name or gene symbol
            organism: Filter by organism (default: human)
            page: Page number
            page_size: Results per page
        """
        cache_key = self.make_cache_key("search_targets", query, organism, page, page_size)
        offset = (page - 1) * page_size

        params = {
            "q": query,
            "limit": page_size,
            "offset": offset,
        }
        if organism:
            params["organism"] = organism

        data = await self.request(
            "GET",
            "/target/search.json",
            params=params,
            cache_key=cache_key,
            cache_ttl=connector_settings.connector_cache_ttl_search,
        )

        targets_data = data.get("targets", [])
        total = data.get("page_meta", {}).get("total_count", len(targets_data))

        targets = [self.normalize_target(t) for t in targets_data]

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
        Get bioactivity data for a target.

        Args:
            target_id: ChEMBL target ID or UniProt accession
        """
        cache_key = self.make_cache_key("get_assays_by_target", target_id, page, page_size)
        offset = (page - 1) * page_size

        # Resolve UniProt to ChEMBL if needed
        if not target_id.startswith("CHEMBL"):
            target = await self.get_target(target_id)
            target_id = target.chembl_target_id or target_id

        data = await self.request(
            "GET",
            "/activity.json",
            params={
                "target_chembl_id": target_id,
                "limit": page_size,
                "offset": offset,
            },
            cache_key=cache_key,
            cache_ttl=connector_settings.connector_cache_ttl_assay,
        )

        activities = data.get("activities", [])
        total = data.get("page_meta", {}).get("total_count", len(activities))

        assays = [self.normalize_assay(a) for a in activities]

        return AssaySearchResult(
            assays=assays,
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=offset + len(assays) < total,
        )

    async def get_bioactivity(
        self,
        compound_id: str,
        *,
        target_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AssaySearchResult:
        """
        Get bioactivity data for a compound.

        Args:
            compound_id: ChEMBL compound ID
            target_id: Optional filter by target
            page: Page number
            page_size: Results per page
        """
        cache_key = self.make_cache_key("get_bioactivity", compound_id, target_id, page, page_size)
        offset = (page - 1) * page_size

        params = {
            "molecule_chembl_id": compound_id,
            "limit": page_size,
            "offset": offset,
        }
        if target_id:
            if not target_id.startswith("CHEMBL"):
                target = await self.get_target(target_id)
                target_id = target.chembl_target_id or target_id
            params["target_chembl_id"] = target_id

        data = await self.request(
            "GET",
            "/activity.json",
            params=params,
            cache_key=cache_key,
            cache_ttl=connector_settings.connector_cache_ttl_assay,
        )

        activities = data.get("activities", [])
        total = data.get("page_meta", {}).get("total_count", len(activities))

        assays = [self.normalize_assay(a) for a in activities]

        return AssaySearchResult(
            assays=assays,
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=offset + len(assays) < total,
        )

    # ==========================================================================
    # Helper Methods
    # ==========================================================================

    def _extract_synonyms(self, raw: dict) -> list[str]:
        """Extract synonyms from molecule data."""
        synonyms = []
        syn_list = raw.get("molecule_synonyms") or []
        for syn in syn_list:
            if isinstance(syn, dict):
                name = syn.get("molecule_synonym")
                if name:
                    synonyms.append(name)
            elif isinstance(syn, str):
                synonyms.append(syn)
        return synonyms[:20]  # Limit to 20 synonyms

    def _to_decimal(self, value: Any) -> Decimal | None:
        """Convert value to Decimal."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (ValueError, TypeError):
            return None

    def _to_int(self, value: Any) -> int | None:
        """Convert value to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _map_assay_type(self, chembl_type: str | None) -> AssayType:
        """Map ChEMBL assay type to internal enum."""
        if not chembl_type:
            return AssayType.OTHER
        mapping = {
            "B": AssayType.BINDING,
            "F": AssayType.FUNCTIONAL,
            "A": AssayType.ADMET,
            "T": AssayType.CYTOTOXICITY,
            "P": AssayType.PHYSICOCHEMICAL,
        }
        return mapping.get(chembl_type.upper(), AssayType.OTHER)

    def _map_result_type(self, standard_type: str | None) -> ResultType:
        """Map ChEMBL standard type to internal enum."""
        if not standard_type:
            return ResultType.OTHER
        mapping = {
            "IC50": ResultType.IC50,
            "EC50": ResultType.EC50,
            "Ki": ResultType.KI,
            "Kd": ResultType.KD,
            "Inhibition": ResultType.PERCENT_INHIBITION,
            "Activity": ResultType.PERCENT_ACTIVITY,
        }
        return mapping.get(standard_type, ResultType.OTHER)
