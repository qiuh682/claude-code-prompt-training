"""
Tests for PubChem connector with mocked API responses.

Tests:
1. search_compounds returns CIDs (handles empty/no results)
2. get_compound returns normalized Molecule (smiles/inchikey/name)
3. get_properties maps properties correctly
4. Cache and rate-limit handling work
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from apps.api.connectors.pubchem import (
    BadRequestError,
    CompoundProperties,
    NotFoundError,
    PubChemCompound,
    PubChemConnector,
    RateLimitError,
    SearchResult,
    SearchType,
)
from apps.api.connectors.pubchem.client import PubChemClient


# =============================================================================
# Mock JSON Fixtures - PubChem PUG REST API Response Format
# =============================================================================

# Search results - Aspirin search returns CIDs
MOCK_SEARCH_ASPIRIN = {
    "IdentifierList": {
        "CID": [2244, 71616526, 11560585, 135565953, 144204486]
    }
}

# Search results - No results
MOCK_SEARCH_NO_RESULTS = {
    "IdentifierList": {
        "CID": []
    }
}

# Aspirin (CID 2244) - Properties endpoint
MOCK_PROPERTIES_ASPIRIN = {
    "CID": 2244,
    "MolecularFormula": "C9H8O4",
    "MolecularWeight": 180.16,
    "CanonicalSMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "IsomericSMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "InChI": "InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)",
    "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
    "IUPACName": "2-acetyloxybenzoic acid",
    "Title": "Aspirin",
    "XLogP": 1.2,
    "ExactMass": 180.042259,
    "MonoisotopicMass": 180.042259,
    "TPSA": 63.6,
    "Complexity": 212,
    "Charge": 0,
    "HBondDonorCount": 1,
    "HBondAcceptorCount": 4,
    "RotatableBondCount": 3,
    "HeavyAtomCount": 13,
    "AtomStereoCount": 0,
    "DefinedAtomStereoCount": 0,
    "UndefinedAtomStereoCount": 0,
    "BondStereoCount": 0,
    "CovalentUnitCount": 1,
}

# Ibuprofen (CID 3672) - Properties endpoint
MOCK_PROPERTIES_IBUPROFEN = {
    "CID": 3672,
    "MolecularFormula": "C13H18O2",
    "MolecularWeight": 206.28,
    "CanonicalSMILES": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
    "IsomericSMILES": "CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O",
    "InChI": "InChI=1S/C13H18O2/c1-9(2)8-11-4-6-12(7-5-11)10(3)13(14)15/h4-7,9-10H,8H2,1-3H3,(H,14,15)",
    "InChIKey": "HEFNNWSXXWATRW-UHFFFAOYSA-N",
    "IUPACName": "2-(4-isobutylphenyl)propanoic acid",
    "Title": "Ibuprofen",
    "XLogP": 3.5,
    "ExactMass": 206.130681,
    "TPSA": 37.3,
    "Complexity": 181,
    "Charge": 0,
    "HBondDonorCount": 1,
    "HBondAcceptorCount": 2,
    "RotatableBondCount": 4,
    "HeavyAtomCount": 15,
}

# Batch properties response (multiple compounds)
MOCK_PROPERTIES_BATCH = {
    "PropertyTable": {
        "Properties": [
            MOCK_PROPERTIES_ASPIRIN,
            MOCK_PROPERTIES_IBUPROFEN,
        ]
    }
}

# Synonyms for Aspirin
MOCK_SYNONYMS_ASPIRIN = {
    "InformationList": {
        "Information": [
            {
                "CID": 2244,
                "Synonym": [
                    "Aspirin",
                    "ACETYLSALICYLIC ACID",
                    "50-78-2",
                    "2-Acetoxybenzoic acid",
                    "Acetosalic acid",
                    "Acylpyrin",
                    "Colfarit",
                    "Ecotrin",
                    "Endydol",
                    "Enterosarein",
                ]
            }
        ]
    }
}

# Compound with Lipinski violations (large molecule)
MOCK_PROPERTIES_LARGE_MOLECULE = {
    "CID": 99999,
    "MolecularFormula": "C40H50N10O8",
    "MolecularWeight": 802.89,  # > 500, violation
    "CanonicalSMILES": "CC(C)CC1NC(=O)C2CCCN2C(=O)C(CC3=CC=CC=C3)NC(=O)C(CC4=CC=C(O)C=C4)NC(=O)C(CC5=CNC6=CC=CC=C65)NC(=O)C(CC(C)C)NC1=O",
    "InChIKey": "AAAAAAAAAAAAAA-UHFFFAOYSA-N",
    "XLogP": 6.2,  # > 5, violation
    "HBondDonorCount": 7,  # > 5, violation
    "HBondAcceptorCount": 12,  # > 10, violation
    "RotatableBondCount": 15,
    "HeavyAtomCount": 58,
    "TPSA": 250.5,
}


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_http_response():
    """Factory for creating mock httpx responses."""

    def _create(
        status_code: int = 200,
        json_data: dict | None = None,
        headers: dict | None = None,
    ):
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code
        response.headers = {"Content-Type": "application/json", **(headers or {})}

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
def pubchem_client():
    """Create PubChem client with caching disabled."""
    client = PubChemClient(cache_enabled=False)
    client._redis_client = False
    return client


@pytest.fixture
def pubchem_client_cached():
    """Create PubChem client with in-memory caching."""
    client = PubChemClient(cache_enabled=True)
    client._redis_client = False
    return client


@pytest.fixture
def pubchem_connector(pubchem_client):
    """Create PubChem connector with non-cached client."""
    return PubChemConnector(client=pubchem_client)


@pytest.fixture
def pubchem_connector_cached(pubchem_client_cached):
    """Create PubChem connector with cached client."""
    return PubChemConnector(client=pubchem_client_cached)


# =============================================================================
# Test: search_compounds returns CIDs
# =============================================================================


class TestSearchCompounds:
    """Tests for search_compounds returning CIDs."""

    async def test_search_by_name_returns_cids(
        self, pubchem_connector, mock_http_response
    ):
        """Should return list of CIDs when searching by name."""
        mock_response = mock_http_response(200, MOCK_SEARCH_ASPIRIN)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_response)

        pubchem_connector._client._client = mock_http_client

        result = await pubchem_connector.search_compounds("aspirin")

        assert isinstance(result, SearchResult)
        assert result.query == "aspirin"
        assert result.search_type == SearchType.NAME
        assert len(result.cids) == 5
        assert 2244 in result.cids
        assert result.total_count == 5

        await pubchem_connector.close()

    async def test_search_returns_empty_list_when_no_results(
        self, pubchem_connector, mock_http_response
    ):
        """Should return empty CID list when no compounds found."""
        mock_response = mock_http_response(200, MOCK_SEARCH_NO_RESULTS)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_response)

        pubchem_connector._client._client = mock_http_client

        result = await pubchem_connector.search_compounds("nonexistent_compound_xyz123")

        assert result.cids == []
        assert result.total_count == 0

        await pubchem_connector.close()

    async def test_search_handles_invalid_query_gracefully(
        self, pubchem_connector, mock_http_response
    ):
        """Should return empty results for invalid queries (BadRequestError)."""
        # PubChem returns 400 for invalid SMILES etc.
        mock_400 = mock_http_response(400, {"Fault": {"Message": "Invalid SMILES"}})

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_400)

        pubchem_connector._client._client = mock_http_client

        result = await pubchem_connector.search_compounds(
            "invalid_smiles!!!", search_type=SearchType.SMILES
        )

        # Should not raise, just return empty
        assert result.cids == []
        assert result.total_count == 0

        await pubchem_connector.close()

    async def test_search_respects_max_results(
        self, pubchem_connector, mock_http_response
    ):
        """Should limit results to max_results."""
        mock_response = mock_http_response(200, MOCK_SEARCH_ASPIRIN)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_response)

        pubchem_connector._client._client = mock_http_client

        result = await pubchem_connector.search_compounds("aspirin", max_results=2)

        assert len(result.cids) == 2
        assert result.total_count == 2

        await pubchem_connector.close()

    async def test_search_by_smiles(
        self, pubchem_connector, mock_http_response
    ):
        """Should search by SMILES string."""
        mock_response = mock_http_response(200, {"IdentifierList": {"CID": [2244]}})

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_response)

        pubchem_connector._client._client = mock_http_client

        result = await pubchem_connector.search_compounds(
            "CC(=O)OC1=CC=CC=C1C(=O)O",
            search_type=SearchType.SMILES,
        )

        assert result.search_type == SearchType.SMILES
        assert 2244 in result.cids

        await pubchem_connector.close()

    async def test_search_by_inchikey(
        self, pubchem_connector, mock_http_response
    ):
        """Should search by InChIKey."""
        mock_response = mock_http_response(200, {"IdentifierList": {"CID": [2244]}})

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_response)

        pubchem_connector._client._client = mock_http_client

        result = await pubchem_connector.search_compounds(
            "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            search_type=SearchType.INCHIKEY,
        )

        assert result.search_type == SearchType.INCHIKEY
        assert 2244 in result.cids

        await pubchem_connector.close()


# =============================================================================
# Test: get_compound returns normalized Molecule
# =============================================================================


class TestGetCompound:
    """Tests for get_compound returning normalized PubChemCompound."""

    async def test_returns_normalized_compound(
        self, pubchem_connector, mock_http_response
    ):
        """Should return a normalized PubChemCompound with all fields."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )
        mock_synonyms = mock_http_response(200, MOCK_SYNONYMS_ASPIRIN)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_props, mock_synonyms])

        pubchem_connector._client._client = mock_http_client

        compound = await pubchem_connector.get_compound(2244)

        assert isinstance(compound, PubChemCompound)
        assert compound.cid == 2244

        await pubchem_connector.close()

    async def test_compound_has_smiles(
        self, pubchem_connector, mock_http_response
    ):
        """Should correctly extract canonical SMILES."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )
        mock_synonyms = mock_http_response(200, MOCK_SYNONYMS_ASPIRIN)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_props, mock_synonyms])

        pubchem_connector._client._client = mock_http_client

        compound = await pubchem_connector.get_compound(2244)

        assert compound.canonical_smiles == "CC(=O)OC1=CC=CC=C1C(=O)O"
        assert compound.isomeric_smiles == "CC(=O)OC1=CC=CC=C1C(=O)O"

        await pubchem_connector.close()

    async def test_compound_has_inchikey(
        self, pubchem_connector, mock_http_response
    ):
        """Should correctly extract InChIKey."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )
        mock_synonyms = mock_http_response(200, MOCK_SYNONYMS_ASPIRIN)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_props, mock_synonyms])

        pubchem_connector._client._client = mock_http_client

        compound = await pubchem_connector.get_compound(2244)

        assert compound.inchikey == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
        assert compound.inchi is not None
        assert compound.inchi.startswith("InChI=")

        await pubchem_connector.close()

    async def test_compound_has_name_and_synonyms(
        self, pubchem_connector, mock_http_response
    ):
        """Should extract IUPAC name and synonyms."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )
        mock_synonyms = mock_http_response(200, MOCK_SYNONYMS_ASPIRIN)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_props, mock_synonyms])

        pubchem_connector._client._client = mock_http_client

        compound = await pubchem_connector.get_compound(2244)

        assert compound.iupac_name == "2-acetyloxybenzoic acid"
        assert compound.title == "Aspirin"
        assert "Aspirin" in compound.synonyms
        assert "ACETYLSALICYLIC ACID" in compound.synonyms

        await pubchem_connector.close()

    async def test_compound_not_found_raises_error(
        self, pubchem_connector, mock_http_response
    ):
        """Should raise NotFoundError for non-existent CID."""
        mock_404 = mock_http_response(404, {"Fault": {"Code": "PUGREST.NotFound"}})

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_404)

        pubchem_connector._client._client = mock_http_client

        with pytest.raises(NotFoundError):
            await pubchem_connector.get_compound(999999999)

        await pubchem_connector.close()

    async def test_get_compound_without_synonyms(
        self, pubchem_connector, mock_http_response
    ):
        """Should work without fetching synonyms."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_props)

        pubchem_connector._client._client = mock_http_client

        compound = await pubchem_connector.get_compound(2244, include_synonyms=False)

        assert compound.cid == 2244
        assert compound.canonical_smiles is not None
        # Only 1 call (properties), not 2 (properties + synonyms)
        assert mock_http_client.get.call_count == 1

        await pubchem_connector.close()


# =============================================================================
# Test: get_properties maps properties correctly
# =============================================================================


class TestGetProperties:
    """Tests for get_properties mapping correctly."""

    async def test_maps_molecular_weight(
        self, pubchem_connector, mock_http_response
    ):
        """Should correctly map MolecularWeight."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_props)

        pubchem_connector._client._client = mock_http_client

        props = await pubchem_connector.get_properties(2244)

        assert isinstance(props, CompoundProperties)
        assert props.cid == 2244
        assert props.molecular_weight == Decimal("180.16")

        await pubchem_connector.close()

    async def test_maps_logp(
        self, pubchem_connector, mock_http_response
    ):
        """Should correctly map XLogP."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_props)

        pubchem_connector._client._client = mock_http_client

        props = await pubchem_connector.get_properties(2244)

        assert props.xlogp == Decimal("1.2")

        await pubchem_connector.close()

    async def test_maps_tpsa(
        self, pubchem_connector, mock_http_response
    ):
        """Should correctly map TPSA."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_props)

        pubchem_connector._client._client = mock_http_client

        props = await pubchem_connector.get_properties(2244)

        assert props.tpsa == Decimal("63.6")

        await pubchem_connector.close()

    async def test_maps_hydrogen_bond_counts(
        self, pubchem_connector, mock_http_response
    ):
        """Should correctly map HBD and HBA."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_props)

        pubchem_connector._client._client = mock_http_client

        props = await pubchem_connector.get_properties(2244)

        assert props.hbond_donor_count == 1
        assert props.hbond_acceptor_count == 4

        await pubchem_connector.close()

    async def test_maps_rotatable_bonds(
        self, pubchem_connector, mock_http_response
    ):
        """Should correctly map rotatable bond count."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_props)

        pubchem_connector._client._client = mock_http_client

        props = await pubchem_connector.get_properties(2244)

        assert props.rotatable_bond_count == 3

        await pubchem_connector.close()

    async def test_computes_ro5_violations_zero(
        self, pubchem_connector, mock_http_response
    ):
        """Should compute 0 RO5 violations for Aspirin."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_props)

        pubchem_connector._client._client = mock_http_client

        props = await pubchem_connector.get_properties(2244)

        # Aspirin: MW=180 (<500), LogP=1.2 (<5), HBD=1 (<5), HBA=4 (<10)
        assert props.ro5_violations == 0

        await pubchem_connector.close()

    async def test_computes_ro5_violations_multiple(
        self, pubchem_connector, mock_http_response
    ):
        """Should compute multiple RO5 violations for large molecule."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_LARGE_MOLECULE]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_props)

        pubchem_connector._client._client = mock_http_client

        props = await pubchem_connector.get_properties(99999)

        # Large molecule: MW=802 (>500), LogP=6.2 (>5), HBD=7 (>5), HBA=12 (>10)
        assert props.ro5_violations == 4

        await pubchem_connector.close()

    async def test_maps_complexity(
        self, pubchem_connector, mock_http_response
    ):
        """Should correctly map molecular complexity."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_props)

        pubchem_connector._client._client = mock_http_client

        props = await pubchem_connector.get_properties(2244)

        assert props.complexity == Decimal("212")

        await pubchem_connector.close()

    async def test_maps_exact_mass(
        self, pubchem_connector, mock_http_response
    ):
        """Should correctly map exact mass."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_props)

        pubchem_connector._client._client = mock_http_client

        props = await pubchem_connector.get_properties(2244)

        assert props.exact_mass == Decimal("180.042259")

        await pubchem_connector.close()


# =============================================================================
# Test: Caching
# =============================================================================


class TestCaching:
    """Tests for caching behavior."""

    async def test_second_call_hits_cache(
        self, pubchem_connector_cached, mock_http_response
    ):
        """Second call to same endpoint should hit cache."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_props)

        pubchem_connector_cached._client._client = mock_http_client

        # First call - hits HTTP
        props1 = await pubchem_connector_cached.get_properties(2244)
        assert props1.cid == 2244
        assert mock_http_client.get.call_count == 1

        # Second call - hits cache
        props2 = await pubchem_connector_cached.get_properties(2244)
        assert props2.cid == 2244
        assert mock_http_client.get.call_count == 1  # Still 1

        await pubchem_connector_cached.close()

    async def test_different_cids_cached_separately(
        self, pubchem_connector_cached, mock_http_response
    ):
        """Different CIDs should have separate cache entries."""
        mock_aspirin = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )
        mock_ibuprofen = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_IBUPROFEN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_aspirin, mock_ibuprofen])

        pubchem_connector_cached._client._client = mock_http_client

        props1 = await pubchem_connector_cached.get_properties(2244)
        props2 = await pubchem_connector_cached.get_properties(3672)

        assert props1.cid == 2244
        assert props2.cid == 3672
        assert mock_http_client.get.call_count == 2

        # Both should be cached now
        await pubchem_connector_cached.get_properties(2244)
        await pubchem_connector_cached.get_properties(3672)
        assert mock_http_client.get.call_count == 2  # Still 2

        await pubchem_connector_cached.close()

    async def test_search_results_are_cached(
        self, pubchem_connector_cached, mock_http_response
    ):
        """Search results should be cached."""
        mock_search = mock_http_response(200, MOCK_SEARCH_ASPIRIN)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_search)

        pubchem_connector_cached._client._client = mock_http_client

        result1 = await pubchem_connector_cached.search_compounds("aspirin")
        assert len(result1.cids) == 5
        assert mock_http_client.get.call_count == 1

        result2 = await pubchem_connector_cached.search_compounds("aspirin")
        assert len(result2.cids) == 5
        assert mock_http_client.get.call_count == 1  # Cached

        await pubchem_connector_cached.close()

    async def test_cache_disabled_always_hits_http(
        self, pubchem_connector, mock_http_response
    ):
        """With caching disabled, every call should hit HTTP."""
        mock_props = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_props)

        pubchem_connector._client._client = mock_http_client

        await pubchem_connector.get_properties(2244)
        await pubchem_connector.get_properties(2244)
        await pubchem_connector.get_properties(2244)

        assert mock_http_client.get.call_count == 3

        await pubchem_connector.close()


# =============================================================================
# Test: Rate Limiting
# =============================================================================


class TestRateLimiting:
    """Tests for rate limit handling."""

    async def test_retries_on_503_rate_limit(
        self, pubchem_client, mock_http_response
    ):
        """Should retry on 503 (PubChem rate limit) with backoff."""
        # PubChem returns 503 when rate limited
        mock_503 = mock_http_response(
            503, {"Fault": {"Message": "Server busy"}}, headers={"Retry-After": "1"}
        )
        mock_success = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_503, mock_success])

        pubchem_client._client = mock_http_client

        # Should succeed after retry
        result = await pubchem_client.get_properties(2244)

        assert result["CID"] == 2244
        assert mock_http_client.get.call_count == 2

        await pubchem_client.close()

    async def test_raises_rate_limit_error_after_max_retries(
        self, pubchem_client, mock_http_response
    ):
        """Should raise RateLimitError after max retries."""
        mock_503 = mock_http_response(
            503, {"Fault": {"Message": "Server busy"}}, headers={"Retry-After": "1"}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_503)

        pubchem_client._client = mock_http_client
        pubchem_client.max_retries = 2  # Reduce for faster test

        with pytest.raises(RateLimitError):
            await pubchem_client.get_properties(2244)

        # Should have tried max_retries + 1 times
        assert mock_http_client.get.call_count == 3

        await pubchem_client.close()

    async def test_retries_on_5xx_server_error(
        self, pubchem_client, mock_http_response
    ):
        """Should retry on 5xx server errors."""
        mock_500 = mock_http_response(500, {"Fault": {"Message": "Internal error"}})
        mock_success = mock_http_response(
            200, {"PropertyTable": {"Properties": [MOCK_PROPERTIES_ASPIRIN]}}
        )

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(side_effect=[mock_500, mock_success])

        pubchem_client._client = mock_http_client

        result = await pubchem_client.get_properties(2244)

        assert result["CID"] == 2244
        assert mock_http_client.get.call_count == 2

        await pubchem_client.close()


# =============================================================================
# Test: Batch Operations
# =============================================================================


class TestBatchOperations:
    """Tests for batch compound fetching."""

    async def test_get_compounds_batch(
        self, pubchem_connector, mock_http_response
    ):
        """Should fetch multiple compounds in batch."""
        mock_batch = mock_http_response(200, MOCK_PROPERTIES_BATCH)

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(return_value=mock_batch)

        pubchem_connector._client._client = mock_http_client

        compounds = await pubchem_connector.get_compounds_batch([2244, 3672])

        assert len(compounds) == 2
        cids = [c.cid for c in compounds]
        assert 2244 in cids
        assert 3672 in cids

        await pubchem_connector.close()

    async def test_get_compounds_batch_empty_list(
        self, pubchem_connector, mock_http_response
    ):
        """Should handle empty CID list."""
        compounds = await pubchem_connector.get_compounds_batch([])

        assert compounds == []

        await pubchem_connector.close()


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling scenarios."""

    async def test_handles_network_error(
        self, pubchem_client, mock_http_response
    ):
        """Should wrap network errors in PubChemClientError."""
        from apps.api.connectors.pubchem.client import PubChemClientError

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        pubchem_client._client = mock_http_client
        pubchem_client.max_retries = 0  # No retries for this test

        with pytest.raises(PubChemClientError) as exc_info:
            await pubchem_client.get_properties(2244)

        assert "Connection refused" in str(exc_info.value) or "Request error" in str(exc_info.value)

        await pubchem_client.close()

    async def test_handles_timeout(
        self, pubchem_client, mock_http_response
    ):
        """Should handle timeout errors."""
        from apps.api.connectors.pubchem.client import PubChemClientError

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get = AsyncMock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        pubchem_client._client = mock_http_client
        pubchem_client.max_retries = 0

        with pytest.raises(PubChemClientError) as exc_info:
            await pubchem_client.get_properties(2244)

        assert "timeout" in str(exc_info.value).lower()

        await pubchem_client.close()
