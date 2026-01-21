"""
PubChem database connector.

PubChem is the world's largest collection of freely accessible chemical information.
API Documentation: https://pubchemdocs.ncbi.nlm.nih.gov/pug-rest

Features:
- Compound search by name, SMILES, InChIKey
- Compound properties and structures
- Bioassay data
- Cross-references to other databases
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


class PubChemConnector(BaseConnector):
    """
    Connector for PubChem PUG REST API.

    Example usage:
        connector = PubChemConnector()

        # Search compounds by name
        results = await connector.search_compounds("aspirin")

        # Get compound by CID
        compound = await connector.get_compound("2244")

        # Get compound by name
        compound = await connector.get_compound_by_name("caffeine")

        # Get bioassay data
        assays = await connector.get_bioactivity("2244")
    """

    source = DataSource.PUBCHEM
    base_url = connector_settings.pubchem_base_url
    rate_limit_rpm = connector_settings.pubchem_rate_limit_rpm  # 5 req/sec

    # ==========================================================================
    # Normalization Methods
    # ==========================================================================

    def normalize_compound(self, raw: dict) -> ExternalCompound:
        """Normalize PubChem compound data."""
        cid = raw.get("CID")
        props = self._extract_properties(raw)

        return ExternalCompound(
            source=DataSource.PUBCHEM,
            source_id=str(cid) if cid else "",
            # Chemical identifiers
            canonical_smiles=props.get("CanonicalSMILES"),
            inchi=props.get("InChI"),
            inchi_key=props.get("InChIKey"),
            # Names
            name=props.get("IUPACName") or props.get("Title"),
            synonyms=[],  # Requires separate API call
            # Properties
            molecular_formula=props.get("MolecularFormula"),
            molecular_weight=self._to_decimal(props.get("MolecularWeight")),
            exact_mass=self._to_decimal(props.get("ExactMass")),
            logp=self._to_decimal(props.get("XLogP")),
            hbd=self._to_int(props.get("HBondDonorCount")),
            hba=self._to_int(props.get("HBondAcceptorCount")),
            tpsa=self._to_decimal(props.get("TPSA")),
            rotatable_bonds=self._to_int(props.get("RotatableBondCount")),
            # External refs
            pubchem_cid=cid,
        )

    def normalize_target(self, raw: dict) -> ExternalTarget:
        """Normalize PubChem target data (from BioAssay)."""
        return ExternalTarget(
            source=DataSource.PUBCHEM,
            source_id=str(raw.get("aid", "")),
            uniprot_id=raw.get("target", {}).get("uniprot_accession"),
            gene_symbol=raw.get("target", {}).get("gene_symbol"),
            name=raw.get("target", {}).get("name", ""),
            organism=raw.get("target", {}).get("organism", ""),
            description=raw.get("description"),
        )

    def normalize_assay(self, raw: dict) -> ExternalAssay:
        """Normalize PubChem bioassay data."""
        return ExternalAssay(
            source=DataSource.PUBCHEM,
            source_id=str(raw.get("aid", "")),
            compound_source_id=str(raw.get("cid", "")),
            target_source_id=raw.get("target", {}).get("gene_id"),
            assay_type=self._map_assay_type(raw.get("assay_type")),
            assay_name=raw.get("name"),
            assay_description=raw.get("description"),
            result_type=self._map_result_type(raw.get("activity_outcome")),
            result_value=self._to_decimal(raw.get("activity_value")),
            result_unit=raw.get("activity_unit"),
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
        Search for compounds in PubChem.

        Supports:
        - Name search: "aspirin"
        - SMILES search: "CC(=O)OC1=CC=CC=C1C(=O)O"
        - InChIKey search: "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
        - CID search: "2244"
        """
        cache_key = self.make_cache_key("search_compounds", query, page, page_size)

        # Determine search type
        if query.isdigit():
            # CID search
            search_type = "cid"
            search_value = query
        elif len(query) == 27 and "-" in query:
            # InChIKey search
            search_type = "inchikey"
            search_value = query
        elif any(c in query for c in "=()[]@"):
            # Likely SMILES
            search_type = "smiles"
            search_value = query
        else:
            # Name search
            search_type = "name"
            search_value = query

        # First, get CIDs from search
        try:
            cid_data = await self.request(
                "GET",
                f"/compound/{search_type}/{search_value}/cids/JSON",
                cache_key=f"{cache_key}_cids",
                cache_ttl=connector_settings.connector_cache_ttl_search,
            )
            cids = cid_data.get("IdentifierList", {}).get("CID", [])
        except NotFoundError:
            return CompoundSearchResult(
                compounds=[],
                total_count=0,
                page=page,
                page_size=page_size,
                has_more=False,
            )

        total = len(cids)

        # Paginate CIDs
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_cids = cids[start_idx:end_idx]

        if not page_cids:
            return CompoundSearchResult(
                compounds=[],
                total_count=total,
                page=page,
                page_size=page_size,
                has_more=False,
            )

        # Get properties for page CIDs
        cid_list = ",".join(str(c) for c in page_cids)
        props_data = await self.request(
            "GET",
            f"/compound/cid/{cid_list}/property/"
            "MolecularFormula,MolecularWeight,CanonicalSMILES,InChI,InChIKey,"
            "XLogP,HBondDonorCount,HBondAcceptorCount,TPSA,RotatableBondCount,ExactMass,IUPACName/JSON",
            cache_key=cache_key,
            cache_ttl=connector_settings.connector_cache_ttl_search,
        )

        properties = props_data.get("PropertyTable", {}).get("Properties", [])
        compounds = [self.normalize_compound(p) for p in properties]

        return CompoundSearchResult(
            compounds=compounds,
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=end_idx < total,
        )

    async def get_compound(self, compound_id: str) -> ExternalCompound:
        """
        Get compound by PubChem CID.

        Args:
            compound_id: PubChem Compound ID (CID)
        """
        cache_key = self.make_cache_key("get_compound", compound_id)

        try:
            data = await self.request(
                "GET",
                f"/compound/cid/{compound_id}/property/"
                "MolecularFormula,MolecularWeight,CanonicalSMILES,InChI,InChIKey,"
                "XLogP,HBondDonorCount,HBondAcceptorCount,TPSA,RotatableBondCount,"
                "ExactMass,IUPACName,Title/JSON",
                cache_key=cache_key,
                cache_ttl=connector_settings.connector_cache_ttl_compound,
            )
        except NotFoundError:
            raise NotFoundError(
                resource_type="Compound",
                resource_id=compound_id,
                connector=self.source.value,
            )

        properties = data.get("PropertyTable", {}).get("Properties", [])
        if not properties:
            raise NotFoundError(
                resource_type="Compound",
                resource_id=compound_id,
                connector=self.source.value,
            )

        return self.normalize_compound(properties[0])

    async def get_compound_by_name(self, name: str) -> ExternalCompound:
        """
        Get compound by name (returns first match).

        Args:
            name: Compound name (e.g., "aspirin")
        """
        results = await self.search_compounds(name, page=1, page_size=1)
        if not results.compounds:
            raise NotFoundError(
                resource_type="Compound",
                resource_id=name,
                connector=self.source.value,
            )
        return results.compounds[0]

    async def get_compound_by_smiles(self, smiles: str) -> ExternalCompound:
        """
        Get compound by SMILES.

        Args:
            smiles: SMILES string
        """
        results = await self.search_compounds(smiles, page=1, page_size=1)
        if not results.compounds:
            raise NotFoundError(
                resource_type="Compound",
                resource_id=smiles,
                connector=self.source.value,
            )
        return results.compounds[0]

    async def get_target(self, target_id: str) -> ExternalTarget:
        """
        Get target info from PubChem BioAssay.

        Note: PubChem is compound-centric; target info is limited.
        For detailed target data, use UniProtConnector.
        """
        # PubChem doesn't have a direct target endpoint
        # This is a placeholder that searches assays
        raise NotFoundError(
            resource_type="Target",
            resource_id=target_id,
            connector=self.source.value,
        )

    async def get_assays_by_target(
        self,
        target_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> AssaySearchResult:
        """
        Get bioassays by target gene ID.

        Note: PubChem BioAssay requires gene ID, not UniProt ID.
        """
        cache_key = self.make_cache_key("get_assays_by_target", target_id, page, page_size)

        try:
            data = await self.request(
                "GET",
                f"/assay/target/genesymbol/{target_id}/aids/JSON",
                cache_key=cache_key,
                cache_ttl=connector_settings.connector_cache_ttl_assay,
            )
            aids = data.get("IdentifierList", {}).get("AID", [])
        except NotFoundError:
            return AssaySearchResult(
                assays=[],
                total_count=0,
                page=page,
                page_size=page_size,
                has_more=False,
            )

        total = len(aids)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_aids = aids[start_idx:end_idx]

        assays = []
        for aid in page_aids:
            try:
                assay_data = await self._get_assay_summary(str(aid))
                assays.append(assay_data)
            except Exception:
                continue

        return AssaySearchResult(
            assays=assays,
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=end_idx < total,
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
            compound_id: PubChem CID
            target_id: Optional gene symbol filter
            page: Page number
            page_size: Results per page
        """
        cache_key = self.make_cache_key("get_bioactivity", compound_id, target_id, page, page_size)

        try:
            data = await self.request(
                "GET",
                f"/compound/cid/{compound_id}/assaysummary/JSON",
                cache_key=cache_key,
                cache_ttl=connector_settings.connector_cache_ttl_assay,
            )
        except NotFoundError:
            return AssaySearchResult(
                assays=[],
                total_count=0,
                page=page,
                page_size=page_size,
                has_more=False,
            )

        # Extract assay data from response
        table = data.get("Table", {})
        columns = table.get("Columns", {}).get("Column", [])
        rows = table.get("Row", [])

        # Parse rows into assay objects
        assays_raw = []
        for row in rows:
            cells = row.get("Cell", [])
            if len(cells) >= len(columns):
                assay_dict = dict(zip(columns, cells))
                assay_dict["cid"] = compound_id
                assays_raw.append(assay_dict)

        # Filter by target if specified
        if target_id:
            assays_raw = [
                a for a in assays_raw
                if target_id.lower() in str(a.get("TargetGeneSymbol", "")).lower()
            ]

        total = len(assays_raw)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_assays = assays_raw[start_idx:end_idx]

        assays = [self._normalize_assay_summary(a) for a in page_assays]

        return AssaySearchResult(
            assays=assays,
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=end_idx < total,
        )

    async def get_synonyms(self, compound_id: str) -> list[str]:
        """Get compound synonyms."""
        cache_key = self.make_cache_key("get_synonyms", compound_id)

        try:
            data = await self.request(
                "GET",
                f"/compound/cid/{compound_id}/synonyms/JSON",
                cache_key=cache_key,
                cache_ttl=connector_settings.connector_cache_ttl_compound,
            )
            info = data.get("InformationList", {}).get("Information", [])
            if info:
                return info[0].get("Synonym", [])[:50]  # Limit to 50
        except NotFoundError:
            pass
        return []

    # ==========================================================================
    # Helper Methods
    # ==========================================================================

    def _extract_properties(self, raw: dict) -> dict:
        """Extract properties from various PubChem response formats."""
        # Handle PropertyTable format
        if "CID" in raw:
            return raw
        # Handle other formats
        return raw

    async def _get_assay_summary(self, aid: str) -> ExternalAssay:
        """Get assay summary by AID."""
        data = await self.request(
            "GET",
            f"/assay/aid/{aid}/summary/JSON",
            cache_key=self.make_cache_key("assay_summary", aid),
            cache_ttl=connector_settings.connector_cache_ttl_assay,
        )
        summary = data.get("AssaySummaries", {}).get("AssaySummary", [{}])[0]
        return ExternalAssay(
            source=DataSource.PUBCHEM,
            source_id=aid,
            assay_name=summary.get("AssayName"),
            assay_description=summary.get("AssayDescription"),
            assay_type=AssayType.OTHER,
            result_type=ResultType.OTHER,
        )

    def _normalize_assay_summary(self, raw: dict) -> ExternalAssay:
        """Normalize assay summary row data."""
        return ExternalAssay(
            source=DataSource.PUBCHEM,
            source_id=str(raw.get("AID", "")),
            compound_source_id=str(raw.get("cid", "")),
            target_source_id=raw.get("TargetGeneID"),
            assay_type=AssayType.OTHER,
            assay_name=raw.get("AssayName"),
            result_type=ResultType.OTHER,
            result_value=self._to_decimal(raw.get("ActivityValue")),
            result_unit=raw.get("ActivityUnit"),
        )

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

    def _map_assay_type(self, assay_type: str | None) -> AssayType:
        """Map PubChem assay type to internal enum."""
        return AssayType.OTHER

    def _map_result_type(self, outcome: str | None) -> ResultType:
        """Map PubChem activity outcome to result type."""
        return ResultType.OTHER
