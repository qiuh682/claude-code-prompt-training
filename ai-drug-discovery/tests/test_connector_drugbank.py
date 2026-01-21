"""
Tests for the DrugBank connector.

Tests cover:
1. Not configured mode (no API key / no local dataset):
   - Methods raise NotConfiguredError
   - Status shows not configured
2. Mocked configured mode:
   - get_drug returns normalized DrugBankDrug (Molecule-like record)
   - get_drug_targets returns DTI records linked to Target identifiers
   - Search functionality
   - Caching behavior
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from apps.api.connectors.drugbank import (
    DrugBankConnector,
    DrugBankClient,
    DrugBankNormalizer,
    DrugBankDrug,
    DrugTargetInteraction,
    DTISearchResult,
    DrugSearchResult,
    DrugBankMode,
    DrugBankStatus,
    NotConfiguredError,
    NotFoundError,
    DrugType,
    DrugGroup,
    TargetAction,
    TargetType,
)


# =============================================================================
# Mock Data Fixtures - Aspirin (DB00945) as primary test case
# =============================================================================

@pytest.fixture
def mock_aspirin_raw_response():
    """Raw DrugBank API response for Aspirin (DB00945)."""
    return {
        "drugbank_id": "DB00945",
        "primary_id": "DB00945",
        "secondary_ids": ["APRD00264"],
        "name": "Aspirin",
        "description": "Acetylsalicylic acid is a salicylate drug.",
        "type": "small molecule",
        "groups": ["approved", "vet_approved"],
        "cas_number": "50-78-2",
        "unii": "R16CO5Y76E",
        "smiles": "CC(=O)OC1=CC=CC=C1C(O)=O",
        "inchi": "InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)",
        "inchikey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
        "molecular_formula": "C9H8O4",
        "molecular_weight": "180.157",
        "average_mass": "180.1574",
        "monoisotopic_mass": "180.042258736",
        "state": "Solid",
        "indication": "For use in the temporary relief of various forms of pain, inflammation associated with various conditions.",
        "pharmacodynamics": "Aspirin inhibits prostaglandin synthesis by irreversibly inactivating cyclooxygenase (COX).",
        "mechanism_of_action": "The analgesic, antipyretic, and anti-inflammatory effects of aspirin are due to actions by both the acetyl and salicylate portions.",
        "absorption": "Rapidly absorbed from the stomach and upper small intestine.",
        "half_life": "The half-life of aspirin is 15-20 minutes.",
        "protein_binding": "High protein binding (80-90%)",
        "metabolism": "Aspirin is rapidly hydrolyzed primarily in plasma to salicylic acid.",
        "route_of_elimination": "Renal excretion is the major route of elimination.",
        "toxicity": "Oral, rat LD50: 200 mg/kg.",
        "synonyms": [
            {"name": "Acetylsalicylic acid", "language": "English"},
            {"name": "ASA", "language": "English"},
            {"name": "2-Acetoxybenzoic acid", "language": "English"}
        ],
        "brands": ["Bayer Aspirin", "Ecotrin", "Bufferin"],
        "categories": [
            {"category": "Analgesics", "mesh_id": "D000700"},
            {"category": "Anti-Inflammatory Agents", "mesh_id": "D000893"},
            {"category": "Platelet Aggregation Inhibitors", "mesh_id": "D010975"}
        ],
        "atc_codes": ["B01AC06", "N02BA01"],
        "external_identifiers": [
            {"resource": "ChEMBL", "identifier": "CHEMBL25"},
            {"resource": "PubChem Compound", "identifier": "2244"},
            {"resource": "KEGG Drug", "identifier": "D00109"},
            {"resource": "ChEBI", "identifier": "15365"},
            {"resource": "PDB", "identifier": "AIN"}
        ],
        "drug_interactions": [
            {
                "drugbank_id": "DB00945",
                "name": "Warfarin",
                "description": "May increase the anticoagulant effect."
            }
        ],
        "food_interactions": [
            "Avoid alcohol",
            "Take with food to reduce stomach irritation"
        ],
        "targets": [
            {"id": "BE0000262", "name": "COX-1", "uniprot_id": "P23219"}
        ],
        "enzymes": [
            {"id": "BE0002363", "name": "CYP2C9", "uniprot_id": "P11712"}
        ],
        "carriers": [],
        "transporters": [],
        "calculated_properties": {
            "SMILES": "CC(=O)OC1=CC=CC=C1C(O)=O",
            "InChI": "InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)",
            "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            "Molecular Weight": "180.157",
            "Molecular Formula": "C9H8O4",
            "logP": "1.19",
            "Polar Surface Area (PSA)": "63.6",
            "H Bond Donor Count": "1",
            "H Bond Acceptor Count": "4",
            "Rotatable Bond Count": "3"
        }
    }


@pytest.fixture
def mock_imatinib_raw_response():
    """Raw DrugBank API response for Imatinib (DB00619) - secondary test case."""
    return {
        "drugbank_id": "DB00619",
        "primary_id": "DB00619",
        "name": "Imatinib",
        "description": "Imatinib is a tyrosine kinase inhibitor used in the treatment of multiple cancers.",
        "type": "small molecule",
        "groups": ["approved"],
        "cas_number": "152459-95-5",
        "smiles": "CN1CCN(CC1)CC2=CC=C(C=C2)C(=O)NC3=CC(=C(C=C3)NC4=NC=CC(=N4)C5=CN=CC=C5)C",
        "inchikey": "KTUFNOKKBVMGRW-UHFFFAOYSA-N",
        "molecular_weight": "493.603",
        "indication": "Treatment of chronic myeloid leukemia (CML) and gastrointestinal stromal tumors (GIST).",
        "mechanism_of_action": "Imatinib inhibits the BCR-ABL tyrosine kinase.",
        "targets": [
            {"id": "BE0000048", "name": "BCR-ABL", "uniprot_id": "P00519"},
            {"id": "BE0000083", "name": "KIT", "uniprot_id": "P10721"}
        ],
        "enzymes": [
            {"id": "BE0002433", "name": "CYP3A4", "uniprot_id": "P08684"}
        ],
        "carriers": [],
        "transporters": []
    }


@pytest.fixture
def mock_aspirin_targets_response():
    """Raw DrugBank API response for Aspirin targets."""
    return [
        {
            "id": "BE0000262",
            "name": "Prostaglandin G/H synthase 1",
            "target_type": "target",
            "gene_name": "PTGS1",
            "uniprot_id": "P23219",
            "organism": "Humans",
            "actions": ["inhibitor"],
            "known_action": True,
            "polypeptide_name": "Cyclooxygenase-1",
            "references": ["PMID:1234567"]
        },
        {
            "id": "BE0000263",
            "name": "Prostaglandin G/H synthase 2",
            "target_type": "target",
            "gene_name": "PTGS2",
            "uniprot_id": "P35354",
            "organism": "Humans",
            "actions": ["inhibitor"],
            "known_action": True,
            "polypeptide_name": "Cyclooxygenase-2",
            "references": ["PMID:7654321"]
        }
    ]


@pytest.fixture
def mock_aspirin_enzymes_response():
    """Raw DrugBank API response for Aspirin metabolizing enzymes."""
    return [
        {
            "id": "BE0002363",
            "name": "Cytochrome P450 2C9",
            "target_type": "enzyme",
            "gene_name": "CYP2C9",
            "uniprot_id": "P11712",
            "organism": "Humans",
            "actions": ["substrate"],
            "known_action": True
        }
    ]


@pytest.fixture
def mock_search_response():
    """Mock search results response."""
    return {
        "drugs": [
            {
                "drugbank_id": "DB00945",
                "name": "Aspirin",
                "type": "small molecule",
                "groups": ["approved"],
                "cas_number": "50-78-2",
                "molecular_weight": "180.157"
            },
            {
                "drugbank_id": "DB01294",
                "name": "Bismuth subsalicylate",
                "type": "small molecule",
                "groups": ["approved"],
                "cas_number": "14882-18-9",
                "molecular_weight": "362.093"
            }
        ],
        "total": 2
    }


@pytest.fixture
def mock_empty_search_response():
    """Mock empty search results."""
    return {"drugs": [], "total": 0}


@pytest.fixture
def mock_response_factory():
    """Factory for creating mock HTTP responses."""
    def _create(status_code=200, json_data=None, text="", headers=None):
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code

        default_headers = {}
        if json_data is not None:
            default_headers["Content-Type"] = "application/json"
        response.headers = {**default_headers, **(headers or {})}

        if json_data is not None:
            response.json.return_value = json_data
        response.text = text

        response.raise_for_status = MagicMock()
        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"HTTP {status_code}",
                request=MagicMock(),
                response=response,
            )

        return response
    return _create


# =============================================================================
# Part 1: Not Configured Mode Tests
# =============================================================================

class TestDrugBankNotConfiguredMode:
    """Tests for DrugBank connector when not configured (no API key, no local data)."""

    def test_mode_is_not_configured_with_no_credentials(self):
        """Connector mode is NOT_CONFIGURED when no API key or data path provided."""
        connector = DrugBankConnector(api_key=None, data_path=None)

        assert connector.mode == DrugBankMode.NOT_CONFIGURED
        assert connector.is_configured is False

    @pytest.mark.asyncio
    async def test_get_status_shows_not_configured(self):
        """get_status returns proper status when not configured."""
        connector = DrugBankConnector(api_key=None, data_path=None)

        status = await connector.get_status()

        assert isinstance(status, DrugBankStatus)
        assert status.mode == DrugBankMode.NOT_CONFIGURED
        assert status.is_configured is False
        assert status.api_available is False
        assert status.local_data_available is False
        assert status.message is not None
        assert "not configured" in status.message.lower()

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_drug_raises_not_configured_error(self):
        """get_drug raises NotConfiguredError when not configured."""
        connector = DrugBankConnector(api_key=None, data_path=None)

        with pytest.raises(NotConfiguredError):
            await connector.get_drug("DB00945")

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_drug_targets_raises_not_configured_error(self):
        """get_drug_targets raises NotConfiguredError when not configured."""
        connector = DrugBankConnector(api_key=None, data_path=None)

        with pytest.raises(NotConfiguredError):
            await connector.get_drug_targets("DB00945")

        await connector.close()

    @pytest.mark.asyncio
    async def test_search_drugs_raises_not_configured_error(self):
        """search_drugs raises NotConfiguredError when not configured."""
        connector = DrugBankConnector(api_key=None, data_path=None)

        with pytest.raises(NotConfiguredError):
            await connector.search_drugs("aspirin")

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_drugs_batch_raises_not_configured_error(self):
        """get_drugs_batch raises NotConfiguredError when not configured."""
        connector = DrugBankConnector(api_key=None, data_path=None)

        with pytest.raises(NotConfiguredError):
            await connector.get_drugs_batch(["DB00945", "DB00619"])

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_admet_raises_not_configured_error(self):
        """get_admet raises NotConfiguredError when not configured."""
        connector = DrugBankConnector(api_key=None, data_path=None)

        with pytest.raises(NotConfiguredError):
            await connector.get_admet("DB00945")

        await connector.close()


class TestDrugBankClientNotConfigured:
    """Tests for DrugBankClient when API key is not set."""

    def test_client_is_configured_false_without_api_key(self):
        """Client reports not configured when no API key."""
        client = DrugBankClient(api_key=None)

        assert client.is_configured is False

    def test_client_is_configured_true_with_api_key(self):
        """Client reports configured when API key is set."""
        client = DrugBankClient(api_key="test_api_key")

        assert client.is_configured is True

    @pytest.mark.asyncio
    async def test_get_drug_raises_not_configured_without_api_key(self):
        """get_drug raises NotConfiguredError without API key."""
        client = DrugBankClient(api_key=None)

        with pytest.raises(NotConfiguredError):
            await client.get_drug("DB00945")

        await client.close()

    @pytest.mark.asyncio
    async def test_search_drugs_raises_not_configured_without_api_key(self):
        """search_drugs raises NotConfiguredError without API key."""
        client = DrugBankClient(api_key=None)

        with pytest.raises(NotConfiguredError):
            await client.search_drugs("aspirin")

        await client.close()


# =============================================================================
# Part 2: Mocked Configured Mode Tests
# =============================================================================

class TestDrugBankConnectorGetDrug:
    """Tests for DrugBankConnector.get_drug() in configured mode."""

    @pytest.mark.asyncio
    async def test_get_drug_returns_normalized_drug(
        self, mock_aspirin_raw_response, mock_response_factory
    ):
        """get_drug returns fully normalized DrugBankDrug."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        mock_response = mock_response_factory(json_data=mock_aspirin_raw_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            drug = await connector.get_drug("DB00945")

            assert isinstance(drug, DrugBankDrug)
            assert drug.drugbank_id == "DB00945"
            assert drug.name == "Aspirin"

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_drug_has_molecule_like_fields(
        self, mock_aspirin_raw_response, mock_response_factory
    ):
        """get_drug returns drug with Molecule-like fields (smiles, inchikey, mw)."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        mock_response = mock_response_factory(json_data=mock_aspirin_raw_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            drug = await connector.get_drug("DB00945")

            # SMILES - essential for chemistry
            assert drug.canonical_smiles is not None
            assert "CC(=O)O" in drug.canonical_smiles

            # InChIKey - standard identifier
            assert drug.inchikey == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"

            # Molecular weight
            assert drug.molecular_weight is not None
            assert float(drug.molecular_weight) == pytest.approx(180.157, rel=0.01)

            # InChI
            assert drug.inchi is not None
            assert drug.inchi.startswith("InChI=")

            # Molecular formula
            assert drug.molecular_formula == "C9H8O4"

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_drug_has_drug_specific_fields(
        self, mock_aspirin_raw_response, mock_response_factory
    ):
        """get_drug returns drug with DrugBank-specific fields."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        mock_response = mock_response_factory(json_data=mock_aspirin_raw_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            drug = await connector.get_drug("DB00945")

            # Drug type
            assert drug.drug_type == DrugType.SMALL_MOLECULE

            # Groups/Status
            assert DrugGroup.APPROVED in drug.groups
            assert drug.is_approved is True

            # CAS number
            assert drug.cas_number == "50-78-2"

            # Indication
            assert drug.indication is not None
            assert "pain" in drug.indication.lower() or "relief" in drug.indication.lower()

            # Mechanism of action
            assert drug.mechanism_of_action is not None

            # ATC codes (drug classification)
            assert len(drug.atc_codes) > 0
            assert "N02BA01" in drug.atc_codes or "B01AC06" in drug.atc_codes

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_drug_has_cross_references(
        self, mock_aspirin_raw_response, mock_response_factory
    ):
        """get_drug returns drug with cross-references to other databases."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        mock_response = mock_response_factory(json_data=mock_aspirin_raw_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            drug = await connector.get_drug("DB00945")

            # ChEMBL reference
            assert drug.chembl_id == "CHEMBL25"

            # PubChem reference
            assert drug.pubchem_cid == 2244

            # KEGG reference
            assert drug.kegg_id == "D00109"

            # PDB reference
            assert "AIN" in drug.pdb_ids

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_drug_has_admet_properties(
        self, mock_aspirin_raw_response, mock_response_factory
    ):
        """get_drug returns drug with ADMET properties."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        mock_response = mock_response_factory(json_data=mock_aspirin_raw_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            drug = await connector.get_drug("DB00945")

            # ADMET properties
            assert drug.admet is not None
            assert drug.admet.absorption is not None
            assert "stomach" in drug.admet.absorption.lower() or "absorb" in drug.admet.absorption.lower()
            assert drug.admet.half_life is not None
            assert drug.admet.metabolism is not None
            assert drug.admet.protein_binding is not None
            assert drug.admet.toxicity is not None

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_drug_not_found_raises_error(self, mock_response_factory):
        """get_drug raises NotFoundError for invalid DrugBank ID."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        mock_response = mock_response_factory(status_code=404, text="Not found")

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            with pytest.raises(NotFoundError) as exc_info:
                await connector.get_drug("DB99999")

            assert exc_info.value.status_code == 404

        await connector.close()


class TestDrugBankConnectorGetDrugTargets:
    """Tests for DrugBankConnector.get_drug_targets() returning DTI records."""

    @pytest.mark.asyncio
    async def test_get_drug_targets_returns_dti_result(
        self,
        mock_aspirin_raw_response,
        mock_aspirin_targets_response,
        mock_aspirin_enzymes_response,
        mock_response_factory
    ):
        """get_drug_targets returns DTISearchResult with interactions."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        drug_response = mock_response_factory(json_data=mock_aspirin_raw_response)
        targets_response = mock_response_factory(json_data=mock_aspirin_targets_response)
        enzymes_response = mock_response_factory(json_data=mock_aspirin_enzymes_response)
        empty_response = mock_response_factory(json_data=[])

        async def mock_get(endpoint, **kwargs):
            if endpoint == "/drugs/DB00945":
                return drug_response
            elif endpoint == "/drugs/DB00945/targets":
                return targets_response
            elif endpoint == "/drugs/DB00945/enzymes":
                return enzymes_response
            else:
                return empty_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            result = await connector.get_drug_targets("DB00945")

            assert isinstance(result, DTISearchResult)
            assert result.drugbank_id == "DB00945"
            assert result.drug_name == "Aspirin"
            assert result.total_count > 0
            assert len(result.interactions) > 0

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_drug_targets_contains_target_identifiers(
        self,
        mock_aspirin_raw_response,
        mock_aspirin_targets_response,
        mock_aspirin_enzymes_response,
        mock_response_factory
    ):
        """DTI records contain target identifiers (UniProt ID, gene name)."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        drug_response = mock_response_factory(json_data=mock_aspirin_raw_response)
        targets_response = mock_response_factory(json_data=mock_aspirin_targets_response)
        enzymes_response = mock_response_factory(json_data=mock_aspirin_enzymes_response)
        empty_response = mock_response_factory(json_data=[])

        async def mock_get(endpoint, **kwargs):
            if endpoint == "/drugs/DB00945":
                return drug_response
            elif endpoint == "/drugs/DB00945/targets":
                return targets_response
            elif endpoint == "/drugs/DB00945/enzymes":
                return enzymes_response
            else:
                return empty_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            result = await connector.get_drug_targets("DB00945")

            # Find COX-1 target
            cox1_targets = [
                dti for dti in result.interactions
                if dti.uniprot_id == "P23219"
            ]
            assert len(cox1_targets) > 0

            dti = cox1_targets[0]
            assert isinstance(dti, DrugTargetInteraction)

            # UniProt ID - essential for linking to Target
            assert dti.uniprot_id == "P23219"

            # Gene name
            assert dti.gene_name == "PTGS1"

            # Target name
            assert dti.target_name is not None
            assert "synthase" in dti.target_name.lower() or "COX" in str(dti.target_name)

            # Drug info in DTI
            assert dti.drugbank_id == "DB00945"
            assert dti.drug_name == "Aspirin"

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_drug_targets_has_action_info(
        self,
        mock_aspirin_raw_response,
        mock_aspirin_targets_response,
        mock_aspirin_enzymes_response,
        mock_response_factory
    ):
        """DTI records contain action information (inhibitor, agonist, etc.)."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        drug_response = mock_response_factory(json_data=mock_aspirin_raw_response)
        targets_response = mock_response_factory(json_data=mock_aspirin_targets_response)
        enzymes_response = mock_response_factory(json_data=mock_aspirin_enzymes_response)
        empty_response = mock_response_factory(json_data=[])

        async def mock_get(endpoint, **kwargs):
            if endpoint == "/drugs/DB00945":
                return drug_response
            elif endpoint == "/drugs/DB00945/targets":
                return targets_response
            elif endpoint == "/drugs/DB00945/enzymes":
                return enzymes_response
            else:
                return empty_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            result = await connector.get_drug_targets("DB00945")

            # Aspirin is an inhibitor of COX
            targets_with_inhibitor = [
                dti for dti in result.interactions
                if dti.action == TargetAction.INHIBITOR
            ]
            assert len(targets_with_inhibitor) > 0

            dti = targets_with_inhibitor[0]
            assert dti.action == TargetAction.INHIBITOR
            assert "inhibitor" in dti.actions

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_drug_targets_includes_enzymes(
        self,
        mock_aspirin_raw_response,
        mock_aspirin_targets_response,
        mock_aspirin_enzymes_response,
        mock_response_factory
    ):
        """get_drug_targets includes metabolizing enzymes by default."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        drug_response = mock_response_factory(json_data=mock_aspirin_raw_response)
        targets_response = mock_response_factory(json_data=mock_aspirin_targets_response)
        enzymes_response = mock_response_factory(json_data=mock_aspirin_enzymes_response)
        empty_response = mock_response_factory(json_data=[])

        async def mock_get(endpoint, **kwargs):
            if endpoint == "/drugs/DB00945":
                return drug_response
            elif endpoint == "/drugs/DB00945/targets":
                return targets_response
            elif endpoint == "/drugs/DB00945/enzymes":
                return enzymes_response
            else:
                return empty_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            result = await connector.get_drug_targets("DB00945")

            # Find CYP2C9 enzyme
            enzymes = [
                dti for dti in result.interactions
                if dti.target_type == TargetType.ENZYME
            ]
            assert len(enzymes) > 0

            cyp_enzyme = next(
                (e for e in enzymes if e.uniprot_id == "P11712"),
                None
            )
            assert cyp_enzyme is not None
            assert cyp_enzyme.gene_name == "CYP2C9"
            assert cyp_enzyme.target_type == TargetType.ENZYME

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_drug_targets_exclude_enzymes(
        self,
        mock_aspirin_raw_response,
        mock_aspirin_targets_response,
        mock_response_factory
    ):
        """get_drug_targets can exclude enzymes."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        drug_response = mock_response_factory(json_data=mock_aspirin_raw_response)
        targets_response = mock_response_factory(json_data=mock_aspirin_targets_response)
        empty_response = mock_response_factory(json_data=[])

        async def mock_get(endpoint, **kwargs):
            if endpoint == "/drugs/DB00945":
                return drug_response
            elif endpoint == "/drugs/DB00945/targets":
                return targets_response
            else:
                return empty_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            result = await connector.get_drug_targets(
                "DB00945",
                include_enzymes=False,
                include_carriers=False,
                include_transporters=False
            )

            # Should only have targets, no enzymes
            enzyme_count = sum(
                1 for dti in result.interactions
                if dti.target_type == TargetType.ENZYME
            )
            assert enzyme_count == 0

        await connector.close()


class TestDrugBankConnectorSearch:
    """Tests for DrugBankConnector search functionality."""

    @pytest.mark.asyncio
    async def test_search_drugs_returns_results(
        self, mock_search_response, mock_response_factory
    ):
        """search_drugs returns DrugSearchResult."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        mock_response = mock_response_factory(json_data=mock_search_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            result = await connector.search_drugs("aspirin")

            assert isinstance(result, DrugSearchResult)
            assert result.query == "aspirin"
            assert len(result.hits) == 2
            assert result.total_count == 2

            # First hit should be Aspirin
            hit = result.hits[0]
            assert hit.drugbank_id == "DB00945"
            assert hit.name == "Aspirin"
            assert hit.drug_type == DrugType.SMALL_MOLECULE

        await connector.close()

    @pytest.mark.asyncio
    async def test_search_drugs_empty_results(
        self, mock_empty_search_response, mock_response_factory
    ):
        """search_drugs returns empty result when no matches."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        mock_response = mock_response_factory(json_data=mock_empty_search_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            result = await connector.search_drugs("nonexistent_xyz_12345")

            assert isinstance(result, DrugSearchResult)
            assert len(result.hits) == 0
            assert result.total_count == 0

        await connector.close()


class TestDrugBankConnectorCaching:
    """Tests for DrugBankConnector caching behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit_on_repeat_call(
        self, mock_aspirin_raw_response, mock_response_factory
    ):
        """Second call to get_drug uses cache."""
        client = DrugBankClient(api_key="test_key", cache_enabled=True)
        client._redis_client = False  # Force in-memory cache
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        mock_response = mock_response_factory(json_data=mock_aspirin_raw_response)
        call_count = {"value": 0}

        async def mock_get(*args, **kwargs):
            call_count["value"] += 1
            return mock_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            # First call
            drug1 = await connector.get_drug("DB00945")
            assert call_count["value"] == 1

            # Second call - should use cache
            drug2 = await connector.get_drug("DB00945")
            assert call_count["value"] == 1  # No additional HTTP call

            assert drug1.drugbank_id == drug2.drugbank_id

        await connector.close()

    @pytest.mark.asyncio
    async def test_cache_disabled_makes_multiple_requests(
        self, mock_aspirin_raw_response, mock_response_factory
    ):
        """With cache disabled, each call makes HTTP request."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        mock_response = mock_response_factory(json_data=mock_aspirin_raw_response)
        call_count = {"value": 0}

        async def mock_get(*args, **kwargs):
            call_count["value"] += 1
            return mock_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            await connector.get_drug("DB00945")
            await connector.get_drug("DB00945")

            assert call_count["value"] == 2

        await connector.close()


class TestDrugBankConnectorBatch:
    """Tests for DrugBankConnector batch operations."""

    @pytest.mark.asyncio
    async def test_get_drugs_batch(
        self, mock_aspirin_raw_response, mock_imatinib_raw_response, mock_response_factory
    ):
        """get_drugs_batch retrieves multiple drugs."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        aspirin_response = mock_response_factory(json_data=mock_aspirin_raw_response)
        imatinib_response = mock_response_factory(json_data=mock_imatinib_raw_response)

        async def mock_get(endpoint, **kwargs):
            if "DB00945" in endpoint:
                return aspirin_response
            elif "DB00619" in endpoint:
                return imatinib_response
            return mock_response_factory(status_code=404)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            drugs = await connector.get_drugs_batch(["DB00945", "DB00619"])

            assert len(drugs) == 2
            ids = {d.drugbank_id for d in drugs}
            assert "DB00945" in ids
            assert "DB00619" in ids

        await connector.close()


class TestDrugBankNormalizerUnit:
    """Unit tests for DrugBankNormalizer."""

    def test_normalize_drug_basic_fields(self, mock_aspirin_raw_response):
        """Normalizer extracts basic drug fields."""
        normalizer = DrugBankNormalizer()

        drug = normalizer.normalize_drug(mock_aspirin_raw_response)

        assert drug.drugbank_id == "DB00945"
        assert drug.name == "Aspirin"
        assert drug.drug_type == DrugType.SMALL_MOLECULE
        assert DrugGroup.APPROVED in drug.groups

    def test_normalize_drug_molecule_fields(self, mock_aspirin_raw_response):
        """Normalizer extracts molecule-like fields."""
        normalizer = DrugBankNormalizer()

        drug = normalizer.normalize_drug(mock_aspirin_raw_response)

        assert drug.canonical_smiles is not None
        assert drug.inchikey == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
        assert drug.molecular_weight == Decimal("180.157")

    def test_normalize_dti(self, mock_aspirin_targets_response):
        """Normalizer creates DTI with target identifiers."""
        normalizer = DrugBankNormalizer()

        raw_target = mock_aspirin_targets_response[0]
        dti = normalizer.normalize_dti(raw_target, "DB00945", "Aspirin")

        assert dti.drugbank_id == "DB00945"
        assert dti.drug_name == "Aspirin"
        assert dti.uniprot_id == "P23219"
        assert dti.gene_name == "PTGS1"
        assert dti.action == TargetAction.INHIBITOR

    def test_normalize_search_hit(self):
        """Normalizer creates search hit."""
        normalizer = DrugBankNormalizer()

        raw = {
            "drugbank_id": "DB00945",
            "name": "Aspirin",
            "type": "small molecule",
            "groups": ["approved"],
            "molecular_weight": "180.157"
        }

        hit = normalizer.normalize_search_hit(raw)

        assert hit.drugbank_id == "DB00945"
        assert hit.name == "Aspirin"
        assert hit.drug_type == DrugType.SMALL_MOLECULE
        assert DrugGroup.APPROVED in hit.groups


class TestDrugBankConnectorModeDetection:
    """Tests for DrugBankConnector mode detection."""

    def test_mode_is_api_with_api_key(self):
        """Connector uses API mode when API key is set."""
        connector = DrugBankConnector(api_key="test_api_key", data_path=None)

        assert connector.mode == DrugBankMode.API
        assert connector.is_configured is True

    def test_mode_prefers_api_when_api_key_available(self):
        """Connector uses API mode when API key is available (API is preferred)."""
        # When API key is set and prefer_api is True (default), API mode is used
        connector = DrugBankConnector(api_key="test_key", data_path=None, prefer_api=True)

        assert connector.mode == DrugBankMode.API
        assert connector.is_configured is True

    @pytest.mark.asyncio
    async def test_get_status_returns_api_mode(self):
        """get_status shows API mode when API key is set."""
        connector = DrugBankConnector(api_key="test_api_key", data_path=None)

        status = await connector.get_status()

        assert status.mode == DrugBankMode.API
        assert status.is_configured is True
        assert status.api_available is True

        await connector.close()


class TestDrugBankErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_authentication_error_on_401(self, mock_response_factory):
        """Client raises AuthenticationError on 401 response."""
        from apps.api.connectors.drugbank import AuthenticationError

        client = DrugBankClient(api_key="invalid_key", cache_enabled=False)

        mock_response = mock_response_factory(status_code=401, text="Unauthorized")

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            with pytest.raises(AuthenticationError):
                await client.get_drug("DB00945")

        await client.close()

    @pytest.mark.asyncio
    async def test_rate_limit_error_on_429(self, mock_response_factory):
        """Client raises RateLimitError on 429 response."""
        from apps.api.connectors.drugbank import RateLimitError

        client = DrugBankClient(api_key="test_key", cache_enabled=False, max_retries=0)

        mock_response = mock_response_factory(
            status_code=429,
            text="Rate limited",
            headers={"Retry-After": "60"}
        )

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            with pytest.raises(RateLimitError) as exc_info:
                await client.get_drug("DB00945")

            assert exc_info.value.retry_after == 60

        await client.close()


class TestDrugBankIntegration:
    """Integration-style tests using the full connector stack."""

    @pytest.mark.asyncio
    async def test_full_workflow_get_drug_then_targets(
        self,
        mock_aspirin_raw_response,
        mock_aspirin_targets_response,
        mock_aspirin_enzymes_response,
        mock_response_factory
    ):
        """Full workflow: get drug, then get its targets."""
        client = DrugBankClient(api_key="test_key", cache_enabled=False)
        connector = DrugBankConnector(api_key="test_key")
        connector._client = client
        connector._mode = DrugBankMode.API

        drug_response = mock_response_factory(json_data=mock_aspirin_raw_response)
        targets_response = mock_response_factory(json_data=mock_aspirin_targets_response)
        enzymes_response = mock_response_factory(json_data=mock_aspirin_enzymes_response)
        empty_response = mock_response_factory(json_data=[])

        async def mock_get(endpoint, **kwargs):
            if endpoint == "/drugs/DB00945":
                return drug_response
            elif endpoint == "/drugs/DB00945/targets":
                return targets_response
            elif endpoint == "/drugs/DB00945/enzymes":
                return enzymes_response
            else:
                return empty_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            # Step 1: Get drug
            drug = await connector.get_drug("DB00945")
            assert drug.drugbank_id == "DB00945"
            assert drug.name == "Aspirin"
            assert drug.canonical_smiles is not None

            # Step 2: Get targets
            dti_result = await connector.get_drug_targets("DB00945")
            assert dti_result.drugbank_id == "DB00945"
            assert len(dti_result.interactions) > 0

            # Verify link between drug and target
            target_uniprots = {dti.uniprot_id for dti in dti_result.interactions if dti.uniprot_id}
            assert "P23219" in target_uniprots  # COX-1

        await connector.close()
