"""
Tests for ChEMBL connector with mocked API responses.

Tests:
1. search_compounds_by_target returns a list of normalized ChEMBLCompound
2. get_bioactivities_by_target returns normalized results with value+unit
3. Pagination: mocked multiple pages are merged correctly
4. Cache is used on repeat calls
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from apps.api.connectors.chembl import (
    ChEMBLBioactivity,
    ChEMBLCompound,
    ChEMBLConnector,
)
from apps.api.connectors.chembl.client import ChEMBLClient
from apps.api.connectors.chembl.schemas import BioactivityType, RelationshipType


# =============================================================================
# Mock JSON Fixtures - ChEMBL API Response Format
# =============================================================================

# EGFR target data (CHEMBL203 / P00533)
MOCK_TARGET_EGFR = {
    "target_chembl_id": "CHEMBL203",
    "pref_name": "Epidermal growth factor receptor erbB1",
    "target_type": "SINGLE PROTEIN",
    "organism": "Homo sapiens",
    "tax_id": 9606,
    "target_components": [
        {
            "accession": "P00533",
            "component_type": "PROTEIN",
            "sequence": "MRPSGTAGAALLALLAALCPASRALEEKKVCQGTSNKLTQLGTF...",
            "target_component_xrefs": [
                {"xref_src_db": "UniProt", "xref_id": "P00533"},
                {"xref_src_db": "PDBe", "xref_id": "1M14"},
            ],
            "target_component_synonyms": [
                {"syn_type": "GENE_SYMBOL", "component_synonym": "EGFR"},
            ],
        }
    ],
}

# Activity data for EGFR inhibitors
MOCK_ACTIVITIES_PAGE_1 = {
    "activities": [
        {
            "activity_id": 1001,
            "molecule_chembl_id": "CHEMBL553",
            "target_chembl_id": "CHEMBL203",
            "assay_chembl_id": "CHEMBL615116",
            "standard_type": "IC50",
            "standard_value": 2.3,
            "standard_units": "nM",
            "standard_relation": "=",
            "pchembl_value": 8.64,
            "document_chembl_id": "CHEMBL1153734",
        },
        {
            "activity_id": 1002,
            "molecule_chembl_id": "CHEMBL939",
            "target_chembl_id": "CHEMBL203",
            "assay_chembl_id": "CHEMBL615117",
            "standard_type": "Ki",
            "standard_value": 0.5,
            "standard_units": "nM",
            "standard_relation": "<",
            "pchembl_value": 9.30,
            "document_chembl_id": "CHEMBL1153735",
        },
        {
            "activity_id": 1003,
            "molecule_chembl_id": "CHEMBL553",  # Duplicate compound
            "target_chembl_id": "CHEMBL203",
            "assay_chembl_id": "CHEMBL615118",
            "standard_type": "IC50",
            "standard_value": 5.1,
            "standard_units": "nM",
            "standard_relation": "=",
            "pchembl_value": 8.29,
            "document_chembl_id": "CHEMBL1153736",
        },
    ],
    "page_meta": {
        "total_count": 5,
        "limit": 3,
        "offset": 0,
        "next": "/activity.json?offset=3&limit=3",
    },
}

MOCK_ACTIVITIES_PAGE_2 = {
    "activities": [
        {
            "activity_id": 1004,
            "molecule_chembl_id": "CHEMBL1421",
            "target_chembl_id": "CHEMBL203",
            "assay_chembl_id": "CHEMBL615119",
            "standard_type": "EC50",
            "standard_value": 12.5,
            "standard_units": "nM",
            "standard_relation": "=",
            "pchembl_value": 7.90,
            "document_chembl_id": "CHEMBL1153737",
        },
        {
            "activity_id": 1005,
            "molecule_chembl_id": "CHEMBL1789",
            "target_chembl_id": "CHEMBL203",
            "assay_chembl_id": "CHEMBL615120",
            "standard_type": "IC50",
            "standard_value": 100.0,
            "standard_units": "nM",
            "standard_relation": ">",
            "pchembl_value": 7.00,
            "document_chembl_id": "CHEMBL1153738",
        },
    ],
    "page_meta": {
        "total_count": 5,
        "limit": 3,
        "offset": 3,
        "next": None,
    },
}

# Erlotinib - EGFR inhibitor (CHEMBL553)
MOCK_COMPOUND_ERLOTINIB = {
    "molecule_chembl_id": "CHEMBL553",
    "pref_name": "ERLOTINIB",
    "molecule_type": "Small molecule",
    "max_phase": 4,
    "therapeutic_flag": True,
    "oral": True,
    "natural_product": False,
    "first_approval": 2004,
    "molecule_structures": {
        "canonical_smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCOC",
        "standard_inchi": "InChI=1S/C22H23ClFN3O4/c1-28-17-6-15-14(7-18(17)29-3-5-31-2)22(26-11-25-15)27-13-4-12(23)8-16(24)9-13/h4,6-9,11H,3,5H2,1-2H3,(H,25,26,27)",
        "standard_inchi_key": "AAKJLRGGTJKAMG-UHFFFAOYSA-N",
    },
    "molecule_properties": {
        "full_mwt": 393.44,
        "full_molformula": "C22H23ClFN3O4",
        "alogp": 3.15,
        "hba": 7,
        "hbd": 1,
        "psa": 74.73,
        "rtb": 10,
        "num_ro5_violations": 0,
        "aromatic_rings": 3,
        "heavy_atoms": 31,
    },
    "cross_references": [
        {"xref_src": "PubChem", "xref_id": "176870"},
        {"xref_src": "DrugBank", "xref_id": "DB00530"},
    ],
}

# Gefitinib - EGFR inhibitor (CHEMBL939)
MOCK_COMPOUND_GEFITINIB = {
    "molecule_chembl_id": "CHEMBL939",
    "pref_name": "GEFITINIB",
    "molecule_type": "Small molecule",
    "max_phase": 4,
    "therapeutic_flag": True,
    "oral": True,
    "natural_product": False,
    "first_approval": 2003,
    "molecule_structures": {
        "canonical_smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1",
        "standard_inchi": "InChI=1S/C22H24ClFN4O3/c1-29-20-13-19-16(12-21(20)31-8-2-5-28-6-9-30-10-7-28)22(26-14-25-19)27-15-3-4-17(23)18(24)11-15/h3-4,11-14H,2,5-10H2,1H3,(H,25,26,27)",
        "standard_inchi_key": "XGALLCVXEZPNRQ-UHFFFAOYSA-N",
    },
    "molecule_properties": {
        "full_mwt": 446.90,
        "full_molformula": "C22H24ClFN4O3",
        "alogp": 3.75,
        "hba": 7,
        "hbd": 1,
        "psa": 68.74,
        "rtb": 8,
        "num_ro5_violations": 0,
        "aromatic_rings": 3,
        "heavy_atoms": 31,
    },
    "cross_references": [
        {"xref_src": "PubChem", "xref_id": "123631"},
        {"xref_src": "DrugBank", "xref_id": "DB00317"},
    ],
}

# Lapatinib (CHEMBL1421)
MOCK_COMPOUND_LAPATINIB = {
    "molecule_chembl_id": "CHEMBL1421",
    "pref_name": "LAPATINIB",
    "molecule_type": "Small molecule",
    "max_phase": 4,
    "therapeutic_flag": True,
    "oral": True,
    "molecule_structures": {
        "canonical_smiles": "CS(=O)(=O)CCNCc1ccc(-c2ccc3ncnc(Nc4ccc(OCc5cccc(F)c5)c(Cl)c4)c3c2)o1",
        "standard_inchi_key": "BCFGMOOMADDAQU-UHFFFAOYSA-N",
    },
    "molecule_properties": {
        "full_mwt": 581.06,
        "alogp": 5.05,
        "hba": 8,
        "hbd": 2,
        "psa": 105.04,
        "num_ro5_violations": 1,
    },
}

# Neratinib (CHEMBL1789)
MOCK_COMPOUND_NERATINIB = {
    "molecule_chembl_id": "CHEMBL1789",
    "pref_name": "NERATINIB",
    "molecule_type": "Small molecule",
    "max_phase": 4,
    "molecule_structures": {
        "canonical_smiles": "CCOc1cc2ncc(C#N)c(Nc3ccc(OCc4ccccn4)c(Cl)c3)c2cc1NC(=O)/C=C/CN(C)C",
        "standard_inchi_key": "HMDKFCWQHWKKGL-FNORWQNLSA-N",
    },
    "molecule_properties": {
        "full_mwt": 557.04,
        "alogp": 4.86,
        "hba": 9,
        "hbd": 2,
    },
}


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_http_response():
    """Factory for creating mock httpx responses."""

    def _create(status_code: int = 200, json_data: dict | None = None):
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code
        response.headers = {"Content-Type": "application/json"}

        if json_data is not None:
            response.json.return_value = json_data
        else:
            response.json.side_effect = ValueError("No JSON")

        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"HTTP {status_code}",
                request=MagicMock(),
                response=response,
            )
        else:
            response.raise_for_status.return_value = None

        return response

    return _create


@pytest.fixture
def chembl_client():
    """Create ChEMBL client with caching disabled."""
    client = ChEMBLClient(cache_enabled=False)
    client._redis_client = False  # Skip Redis
    return client


@pytest.fixture
def chembl_client_cached():
    """Create ChEMBL client with in-memory caching."""
    client = ChEMBLClient(cache_enabled=True)
    client._redis_client = False  # Force in-memory only
    return client


@pytest.fixture
def chembl_connector(chembl_client):
    """Create ChEMBL connector with non-cached client."""
    return ChEMBLConnector(client=chembl_client)


@pytest.fixture
def chembl_connector_cached(chembl_client_cached):
    """Create ChEMBL connector with cached client."""
    return ChEMBLConnector(client=chembl_client_cached)


# =============================================================================
# Test: search_compounds_by_target
# =============================================================================


class TestSearchCompoundsByTarget:
    """Tests for search_compounds_by_target returning normalized compounds."""

    async def test_returns_list_of_normalized_compounds(
        self, chembl_connector, mock_http_response
    ):
        """Should return a list of ChEMBLCompound objects."""
        # Mock activity endpoint returning compounds active against EGFR
        mock_activities = mock_http_response(200, MOCK_ACTIVITIES_PAGE_1)
        mock_erlotinib = mock_http_response(200, MOCK_COMPOUND_ERLOTINIB)
        mock_gefitinib = mock_http_response(200, MOCK_COMPOUND_GEFITINIB)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(
            side_effect=[mock_activities, mock_erlotinib, mock_gefitinib]
        )

        chembl_connector._client._client = mock_http_client

        result = await chembl_connector.search_compounds_by_target(
            "CHEMBL203", page_size=10
        )

        # Should return CompoundSearchResult with normalized compounds
        assert len(result.compounds) == 2  # 2 unique compounds (CHEMBL553 appears twice)
        assert all(isinstance(c, ChEMBLCompound) for c in result.compounds)

        # Check first compound is Erlotinib
        erlotinib = result.compounds[0]
        assert erlotinib.chembl_id == "CHEMBL553"
        assert erlotinib.pref_name == "ERLOTINIB"
        assert erlotinib.canonical_smiles is not None
        assert erlotinib.molecular_weight == Decimal("393.44")
        assert erlotinib.max_phase == 4
        assert erlotinib.therapeutic_flag is True

        # Check second compound is Gefitinib
        gefitinib = result.compounds[1]
        assert gefitinib.chembl_id == "CHEMBL939"
        assert gefitinib.pref_name == "GEFITINIB"
        assert gefitinib.molecular_weight == Decimal("446.90")

        await chembl_connector.close()

    async def test_resolves_uniprot_id_to_chembl_id(
        self, chembl_connector, mock_http_response
    ):
        """Should resolve UniProt ID (P00533) to ChEMBL ID (CHEMBL203)."""
        # Mock target lookup by UniProt ID
        mock_target_response = mock_http_response(
            200, {"targets": [MOCK_TARGET_EGFR]}
        )
        mock_activities = mock_http_response(200, MOCK_ACTIVITIES_PAGE_1)
        mock_erlotinib = mock_http_response(200, MOCK_COMPOUND_ERLOTINIB)
        mock_gefitinib = mock_http_response(200, MOCK_COMPOUND_GEFITINIB)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(
            side_effect=[mock_target_response, mock_activities, mock_erlotinib, mock_gefitinib]
        )

        chembl_connector._client._client = mock_http_client

        # Search using UniProt ID
        result = await chembl_connector.search_compounds_by_target(
            "P00533", page_size=10
        )

        assert len(result.compounds) >= 1
        # First call should be target lookup
        first_call = mock_http_client.get.call_args_list[0]
        assert "target_components__accession" in str(first_call)

        await chembl_connector.close()

    async def test_deduplicates_compounds_from_activities(
        self, chembl_connector, mock_http_response
    ):
        """Should return unique compounds even if they appear in multiple activities."""
        # CHEMBL553 appears twice in MOCK_ACTIVITIES_PAGE_1
        mock_activities = mock_http_response(200, MOCK_ACTIVITIES_PAGE_1)
        mock_erlotinib = mock_http_response(200, MOCK_COMPOUND_ERLOTINIB)
        mock_gefitinib = mock_http_response(200, MOCK_COMPOUND_GEFITINIB)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(
            side_effect=[mock_activities, mock_erlotinib, mock_gefitinib]
        )

        chembl_connector._client._client = mock_http_client

        result = await chembl_connector.search_compounds_by_target("CHEMBL203")

        # Should only have 2 unique compounds, not 3
        compound_ids = [c.chembl_id for c in result.compounds]
        assert len(compound_ids) == len(set(compound_ids))
        assert "CHEMBL553" in compound_ids
        assert "CHEMBL939" in compound_ids

        await chembl_connector.close()

    async def test_filters_by_min_pchembl(
        self, chembl_connector, mock_http_response
    ):
        """Should pass min_pchembl filter to API."""
        mock_activities = mock_http_response(200, {"activities": [], "page_meta": {"total_count": 0}})

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_activities)

        chembl_connector._client._client = mock_http_client

        await chembl_connector.search_compounds_by_target(
            "CHEMBL203",
            min_pchembl=7.0,
        )

        # Check that pchembl_value__gte was passed
        call_args = mock_http_client.get.call_args
        assert call_args[1]["params"]["pchembl_value__gte"] == 7.0

        await chembl_connector.close()

    async def test_filters_by_activity_types(
        self, chembl_connector, mock_http_response
    ):
        """Should pass activity_types filter to API."""
        mock_activities = mock_http_response(200, {"activities": [], "page_meta": {"total_count": 0}})

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_activities)

        chembl_connector._client._client = mock_http_client

        await chembl_connector.search_compounds_by_target(
            "CHEMBL203",
            activity_types=["IC50", "Ki"],
        )

        # Check that standard_type__in was passed
        call_args = mock_http_client.get.call_args
        assert call_args[1]["params"]["standard_type__in"] == "IC50,Ki"

        await chembl_connector.close()


# =============================================================================
# Test: get_bioactivities_by_target
# =============================================================================


class TestGetBioactivitiesByTarget:
    """Tests for get_bioactivities_by_target returning normalized results."""

    async def test_returns_normalized_bioactivities(
        self, chembl_connector, mock_http_response
    ):
        """Should return normalized ChEMBLBioactivity objects."""
        mock_activities = mock_http_response(200, MOCK_ACTIVITIES_PAGE_1)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_activities)

        chembl_connector._client._client = mock_http_client

        result = await chembl_connector.get_bioactivities_by_target("CHEMBL203")

        assert len(result.bioactivities) == 3
        assert all(isinstance(b, ChEMBLBioactivity) for b in result.bioactivities)

        await chembl_connector.close()

    async def test_bioactivity_has_value_and_unit(
        self, chembl_connector, mock_http_response
    ):
        """Should correctly normalize standard_value and standard_units."""
        mock_activities = mock_http_response(200, MOCK_ACTIVITIES_PAGE_1)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_activities)

        chembl_connector._client._client = mock_http_client

        result = await chembl_connector.get_bioactivities_by_target("CHEMBL203")

        # First activity: IC50 = 2.3 nM
        activity1 = result.bioactivities[0]
        assert activity1.activity_id == 1001
        assert activity1.molecule_chembl_id == "CHEMBL553"
        assert activity1.standard_type == BioactivityType.IC50
        assert activity1.standard_value == Decimal("2.3")
        assert activity1.standard_units == "nM"
        assert activity1.standard_relation == RelationshipType.EQUALS
        assert activity1.pchembl_value == Decimal("8.64")

        # Second activity: Ki < 0.5 nM
        activity2 = result.bioactivities[1]
        assert activity2.standard_type == BioactivityType.KI
        assert activity2.standard_value == Decimal("0.5")
        assert activity2.standard_relation == RelationshipType.LESS_THAN

        await chembl_connector.close()

    async def test_bioactivity_contains_assay_reference(
        self, chembl_connector, mock_http_response
    ):
        """Should include assay_chembl_id and target_chembl_id."""
        mock_activities = mock_http_response(200, MOCK_ACTIVITIES_PAGE_1)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_activities)

        chembl_connector._client._client = mock_http_client

        result = await chembl_connector.get_bioactivities_by_target("CHEMBL203")

        activity = result.bioactivities[0]
        assert activity.assay_chembl_id == "CHEMBL615116"
        assert activity.target_chembl_id == "CHEMBL203"
        assert activity.document_chembl_id == "CHEMBL1153734"

        await chembl_connector.close()

    async def test_returns_pagination_metadata(
        self, chembl_connector, mock_http_response
    ):
        """Should return correct pagination metadata."""
        mock_activities = mock_http_response(200, MOCK_ACTIVITIES_PAGE_1)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_activities)

        chembl_connector._client._client = mock_http_client

        result = await chembl_connector.get_bioactivities_by_target(
            "CHEMBL203", page=1, page_size=3
        )

        assert result.total_count == 5
        assert result.page == 1
        assert result.page_size == 3
        assert result.has_more is True

        await chembl_connector.close()


# =============================================================================
# Test: Pagination
# =============================================================================


class TestPagination:
    """Tests for pagination across multiple pages."""

    async def test_iter_bioactivities_merges_pages(
        self, chembl_connector, mock_http_response
    ):
        """iter_bioactivities_by_target should yield batches from all pages."""
        mock_page1 = mock_http_response(200, MOCK_ACTIVITIES_PAGE_1)
        mock_page2 = mock_http_response(200, MOCK_ACTIVITIES_PAGE_2)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_page1, mock_page2])

        chembl_connector._client._client = mock_http_client

        all_activities = []
        async for batch in chembl_connector.iter_bioactivities_by_target(
            "CHEMBL203", batch_size=3
        ):
            all_activities.extend(batch)

        # Should have all 5 activities from both pages
        assert len(all_activities) == 5
        activity_ids = [a.activity_id for a in all_activities]
        assert 1001 in activity_ids  # From page 1
        assert 1004 in activity_ids  # From page 2
        assert 1005 in activity_ids  # From page 2

        await chembl_connector.close()

    async def test_pagination_stops_at_max_results(
        self, chembl_connector, mock_http_response
    ):
        """Should stop iterating when max_results is reached."""
        mock_page1 = mock_http_response(200, MOCK_ACTIVITIES_PAGE_1)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_page1)

        chembl_connector._client._client = mock_http_client

        all_activities = []
        async for batch in chembl_connector.iter_bioactivities_by_target(
            "CHEMBL203", batch_size=10, max_results=2
        ):
            all_activities.extend(batch)

        # Should stop after max_results
        assert len(all_activities) <= 3  # One batch from page 1

        await chembl_connector.close()

    async def test_pagination_handles_empty_page(
        self, chembl_connector, mock_http_response
    ):
        """Should handle empty pages gracefully."""
        mock_empty = mock_http_response(
            200, {"activities": [], "page_meta": {"total_count": 0}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_empty)

        chembl_connector._client._client = mock_http_client

        all_activities = []
        async for batch in chembl_connector.iter_bioactivities_by_target("CHEMBL203"):
            all_activities.extend(batch)

        assert len(all_activities) == 0

        await chembl_connector.close()

    async def test_get_bioactivities_pages_correctly(
        self, chembl_connector, mock_http_response
    ):
        """get_bioactivities_by_target should correctly calculate offset for pages."""
        mock_activities = mock_http_response(
            200, {"activities": [], "page_meta": {"total_count": 0}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_activities)

        chembl_connector._client._client = mock_http_client

        # Request page 3 with page_size 25
        await chembl_connector.get_bioactivities_by_target(
            "CHEMBL203", page=3, page_size=25
        )

        # Check offset calculation: (page-1) * page_size = 2 * 25 = 50
        call_args = mock_http_client.get.call_args
        assert call_args[1]["params"]["offset"] == 50
        assert call_args[1]["params"]["limit"] == 25

        await chembl_connector.close()


# =============================================================================
# Test: Caching
# =============================================================================


class TestCaching:
    """Tests for caching behavior."""

    async def test_second_call_hits_cache(
        self, chembl_connector_cached, mock_http_response
    ):
        """Second call to same endpoint should hit cache."""
        mock_compound = mock_http_response(200, MOCK_COMPOUND_ERLOTINIB)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_compound)

        chembl_connector_cached._client._client = mock_http_client

        # First call - should hit HTTP
        result1 = await chembl_connector_cached.get_compound("CHEMBL553")
        assert result1.chembl_id == "CHEMBL553"
        assert mock_http_client.get.call_count == 1

        # Second call - should hit cache
        result2 = await chembl_connector_cached.get_compound("CHEMBL553")
        assert result2.chembl_id == "CHEMBL553"
        assert mock_http_client.get.call_count == 1  # Still 1, not 2

        await chembl_connector_cached.close()

    async def test_different_compounds_cached_separately(
        self, chembl_connector_cached, mock_http_response
    ):
        """Different compounds should have separate cache entries."""
        mock_erlotinib = mock_http_response(200, MOCK_COMPOUND_ERLOTINIB)
        mock_gefitinib = mock_http_response(200, MOCK_COMPOUND_GEFITINIB)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_erlotinib, mock_gefitinib])

        chembl_connector_cached._client._client = mock_http_client

        # Fetch two different compounds
        result1 = await chembl_connector_cached.get_compound("CHEMBL553")
        result2 = await chembl_connector_cached.get_compound("CHEMBL939")

        assert result1.pref_name == "ERLOTINIB"
        assert result2.pref_name == "GEFITINIB"
        assert mock_http_client.get.call_count == 2

        # Fetch again - both should hit cache
        await chembl_connector_cached.get_compound("CHEMBL553")
        await chembl_connector_cached.get_compound("CHEMBL939")
        assert mock_http_client.get.call_count == 2  # Still 2

        await chembl_connector_cached.close()

    async def test_bioactivities_are_cached(
        self, chembl_connector_cached, mock_http_response
    ):
        """Bioactivity results should be cached."""
        mock_activities = mock_http_response(200, MOCK_ACTIVITIES_PAGE_1)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_activities)

        chembl_connector_cached._client._client = mock_http_client

        # First call
        result1 = await chembl_connector_cached.get_bioactivities_by_target("CHEMBL203")
        assert len(result1.bioactivities) == 3
        assert mock_http_client.get.call_count == 1

        # Second call - should hit cache
        result2 = await chembl_connector_cached.get_bioactivities_by_target("CHEMBL203")
        assert len(result2.bioactivities) == 3
        assert mock_http_client.get.call_count == 1

        await chembl_connector_cached.close()

    async def test_target_resolution_is_cached(
        self, chembl_connector_cached, mock_http_response
    ):
        """UniProt to ChEMBL ID resolution should be cached."""
        mock_target = mock_http_response(200, {"targets": [MOCK_TARGET_EGFR]})
        mock_activities = mock_http_response(200, MOCK_ACTIVITIES_PAGE_1)

        # Track calls to determine which endpoints are hit
        call_count = {"target": 0, "activities": 0}

        async def mock_get(endpoint, **kwargs):
            if "target_components__accession" in str(kwargs.get("params", {})):
                call_count["target"] += 1
                return mock_target
            else:
                call_count["activities"] += 1
                return mock_activities

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = mock_get

        chembl_connector_cached._client._client = mock_http_client

        # First call with UniProt ID - resolves target then gets activities
        await chembl_connector_cached.get_bioactivities_by_target("P00533")
        assert call_count["target"] == 1  # Target lookup
        assert call_count["activities"] == 1  # Activities fetch

        # Second call - target resolution should be cached
        await chembl_connector_cached.get_bioactivities_by_target("P00533")
        assert call_count["target"] == 1  # Still 1 - cached!
        assert call_count["activities"] == 1  # Still 1 - activities also cached

        await chembl_connector_cached.close()

    async def test_cache_disabled_always_hits_http(
        self, chembl_connector, mock_http_response
    ):
        """With caching disabled, every call should hit HTTP."""
        mock_compound = mock_http_response(200, MOCK_COMPOUND_ERLOTINIB)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_compound)

        chembl_connector._client._client = mock_http_client

        await chembl_connector.get_compound("CHEMBL553")
        await chembl_connector.get_compound("CHEMBL553")
        await chembl_connector.get_compound("CHEMBL553")

        assert mock_http_client.get.call_count == 3

        await chembl_connector.close()


# =============================================================================
# Test: Compound Normalization Details
# =============================================================================


class TestCompoundNormalization:
    """Tests for detailed compound normalization."""

    async def test_normalizes_molecular_properties(
        self, chembl_connector, mock_http_response
    ):
        """Should correctly normalize all molecular properties."""
        mock_compound = mock_http_response(200, MOCK_COMPOUND_ERLOTINIB)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_compound)

        chembl_connector._client._client = mock_http_client

        compound = await chembl_connector.get_compound("CHEMBL553")

        # Molecular properties
        assert compound.molecular_formula == "C22H23ClFN3O4"
        assert compound.molecular_weight == Decimal("393.44")
        assert compound.alogp == Decimal("3.15")
        assert compound.hba == 7
        assert compound.hbd == 1
        assert compound.psa == Decimal("74.73")
        assert compound.rtb == 10
        assert compound.num_ro5_violations == 0
        assert compound.aromatic_rings == 3
        assert compound.heavy_atoms == 31

        await chembl_connector.close()

    async def test_normalizes_structure_identifiers(
        self, chembl_connector, mock_http_response
    ):
        """Should correctly normalize SMILES, InChI, InChIKey."""
        mock_compound = mock_http_response(200, MOCK_COMPOUND_ERLOTINIB)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_compound)

        chembl_connector._client._client = mock_http_client

        compound = await chembl_connector.get_compound("CHEMBL553")

        assert compound.canonical_smiles == "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCOC"
        assert compound.standard_inchi_key == "AAKJLRGGTJKAMG-UHFFFAOYSA-N"
        assert compound.standard_inchi is not None
        assert compound.standard_inchi.startswith("InChI=")

        await chembl_connector.close()

    async def test_normalizes_cross_references(
        self, chembl_connector, mock_http_response
    ):
        """Should extract PubChem and DrugBank cross-references."""
        mock_compound = mock_http_response(200, MOCK_COMPOUND_ERLOTINIB)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_compound)

        chembl_connector._client._client = mock_http_client

        compound = await chembl_connector.get_compound("CHEMBL553")

        assert compound.pubchem_cid == 176870
        assert compound.drugbank_id == "DB00530"

        await chembl_connector.close()

    async def test_normalizes_drug_properties(
        self, chembl_connector, mock_http_response
    ):
        """Should correctly normalize drug-related flags."""
        mock_compound = mock_http_response(200, MOCK_COMPOUND_ERLOTINIB)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_compound)

        chembl_connector._client._client = mock_http_client

        compound = await chembl_connector.get_compound("CHEMBL553")

        assert compound.max_phase == 4
        assert compound.therapeutic_flag is True
        assert compound.oral is True
        assert compound.natural_product is False
        assert compound.first_approval == 2004
        assert compound.molecule_type == "Small molecule"

        await chembl_connector.close()


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling scenarios."""

    async def test_not_found_raises_error(
        self, chembl_connector, mock_http_response
    ):
        """Should raise NotFoundError for non-existent compound."""
        from apps.api.connectors.chembl.client import NotFoundError

        mock_404 = mock_http_response(404, None)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_404)

        chembl_connector._client._client = mock_http_client

        with pytest.raises(NotFoundError):
            await chembl_connector.get_compound("CHEMBL_INVALID")

        await chembl_connector.close()

    async def test_search_compounds_by_target_handles_not_found_gracefully(
        self, chembl_connector, mock_http_response
    ):
        """Should skip compounds that can't be fetched."""
        mock_activities = mock_http_response(200, MOCK_ACTIVITIES_PAGE_1)
        mock_erlotinib = mock_http_response(200, MOCK_COMPOUND_ERLOTINIB)
        mock_404 = mock_http_response(404, None)  # Gefitinib not found

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(
            side_effect=[mock_activities, mock_erlotinib, mock_404]
        )

        chembl_connector._client._client = mock_http_client

        result = await chembl_connector.search_compounds_by_target("CHEMBL203")

        # Should only have 1 compound (Gefitinib was skipped)
        assert len(result.compounds) == 1
        assert result.compounds[0].chembl_id == "CHEMBL553"

        await chembl_connector.close()
