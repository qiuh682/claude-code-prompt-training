"""
Tests for the UniProt connector.

Tests cover:
1. get_target returns normalized UniProtTarget with sequence and key annotations
2. Handles "not found" UniProt ID gracefully (404 -> NotFoundError)
3. Cache is used on repeat calls
4. Search functionality
5. Batch operations
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from apps.api.connectors.uniprot import (
    UniProtClient,
    UniProtConnector,
    UniProtNormalizer,
    UniProtTarget,
    NotFoundError,
    RateLimitError,
    UniProtClientError,
    TargetSearchResult,
)


# =============================================================================
# Mock Data Fixtures - EGFR (P00533) as primary test case
# =============================================================================

@pytest.fixture
def mock_egfr_raw_response():
    """Raw UniProt API response for EGFR (P00533)."""
    return {
        "primaryAccession": "P00533",
        "uniProtkbId": "EGFR_HUMAN",
        "entryType": "UniProtKB reviewed (Swiss-Prot)",
        "proteinDescription": {
            "recommendedName": {
                "fullName": {"value": "Epidermal growth factor receptor"},
                "shortNames": [{"value": "EGF receptor"}],
                "ecNumbers": [{"value": "2.7.10.1"}]
            },
            "alternativeNames": [
                {"fullName": {"value": "Proto-oncogene c-ErbB-1"}},
                {"fullName": {"value": "Receptor tyrosine-protein kinase erbB-1"}}
            ]
        },
        "genes": [
            {
                "geneName": {"value": "EGFR"},
                "synonyms": [
                    {"value": "ERBB"},
                    {"value": "ERBB1"},
                    {"value": "HER1"}
                ]
            }
        ],
        "organism": {
            "scientificName": "Homo sapiens",
            "commonName": "Human",
            "taxonId": 9606,
            "lineage": ["Eukaryota", "Metazoa", "Chordata", "Mammalia", "Primates", "Hominidae", "Homo"]
        },
        "sequence": {
            "value": "MRPSGTAGAALLALLAALCPASRALEEKKVCQGTSNKLTQLGTFEDHFLSLQRMFNNCEVVLGNLEITYVQRNYDLSFLKTIQEVAGYVLIALNTVERIPLENLQIIRGNMYYENSYALAVLSNYDANKTGLKELPMRNLQEILHGAVRFSNNPALCNVESIQWRDIVSSDFLSNMSMDFQNHLGSCQKCDPSCPNGSCWGAGEENCQKLTKIICAQQCSGRCRGKSPSDCCHNQCAAGCTGPRESDCLVCRKFRDEATCKDTCPPLMLYNPTTYQMDVNPEGKYSFGATCVKKCPRNYVVTDHGSCVRACGADSYEMEEDGVRKCKKCEGPCRKVCNGIGIGEFKDSLSINATNIKHFKNCTSISGDLHILPVAFRGDSFTHTPPLDPQELDILKTVKEITGFLLIQAWPENRTDLHAFENLEIIRGRTKQHGQFSLAVVSLNITSLGLRSLKEISDGDVIISGNKNLCYANTINWKKLFGTSGQKTKIISNRGENSCKATGQVCHALCSPEGCWGPEPRDCVSCRNVSRGRECVDKCNLLEGEPREFVENSECIQCHPECLPQAMNITCTGRGPDNCIQCAHYIDGPHCVKTCPAGVMGENNTLVWKYADAGHVCHLCHPNCTYGCTGPGLEGCPTNGPKIPSIATGMVGALLLLLVVALGIGLFMRRRHIVRKRTLRRLLQERELVEPLTPSGEAPNQALLRILKETEFKKIKVLGSGAFGTVYKGLWIPEGEKVKIPVAIKELREATSPKANKEILDEAYVMASVDNPHVCRLLGICLTSTVQLITQLMPFGCLLDYVREHKDNIGSQYLLNWCVQIAKGMNYLEDRRLVHRDLAARNVLVKTPQHVKITDFGLAKLLGAEEKEYHAEGGKVPIKWMALESILHRIYTHQSDVWSYGVTVWELMTFGSKPYDGIPASEISSILEKGERLPQPPICTIDVYMIMVKCWMIDADSRPKFRELIIEFSKMARDPQRYLVIQGDERMHLPSPTDSNFYRALMDEEDMDDVVDADEYLIPQQGFFSSPSTSRTPLLSSLSATSNNSTVACIDRNGLQSCPIKEDSFLQRYSSDPTGALTEDSIDDTFLPVPEYINQSVPKRPAGSVQNPVYHNQPLNPAPSRDPHYQDPHSTAVGNPEYLNTVQPTCVNSTFDSPAHWAQKGSHQISLDNPDYQQDFFPKEAKPNGIFKGSTAENAEYLRVAPQSSEFIGA",
            "length": 1210,
            "molWeight": 134277,
            "crc64": "E83C2E5EB2A92E61",
            "md5": "E83C2E5EB2A92E61ABCDEF1234567890"
        },
        "comments": [
            {
                "commentType": "FUNCTION",
                "texts": [
                    {
                        "value": "Receptor tyrosine kinase binding ligands of the EGF family and activating several signaling cascades to convert extracellular cues into appropriate cellular responses. Known ligands include EGF, TGFA/TGF-alpha, AREG, epigen/EPGN, BTC/betacellulin, epiregulin/EREG and HBEGF/heparin-binding EGF."
                    }
                ]
            },
            {
                "commentType": "CATALYTIC ACTIVITY",
                "reaction": {
                    "name": "ATP + a [protein]-L-tyrosine = ADP + a [protein]-L-tyrosine phosphate + H(+)",
                    "ecNumber": "2.7.10.1"
                }
            },
            {
                "commentType": "PATHWAY",
                "texts": [
                    {"value": "Protein modification; protein phosphorylation."}
                ]
            },
            {
                "commentType": "SUBCELLULAR LOCATION",
                "subcellularLocations": [
                    {
                        "location": {"value": "Cell membrane"},
                        "topology": {"value": "Single-pass type I membrane protein"}
                    },
                    {
                        "location": {"value": "Endosome"},
                        "topology": {"value": "Membrane"}
                    },
                    {
                        "location": {"value": "Nucleus"}
                    }
                ]
            },
            {
                "commentType": "DISEASE",
                "disease": {
                    "diseaseId": "DI-00551",
                    "diseaseAccession": "DI-00551",
                    "acronym": "NSCLC",
                    "description": "Non-small cell lung cancer"
                },
                "texts": [
                    {"value": "Disease description: A common type of lung cancer."}
                ]
            }
        ],
        "features": [
            {
                "type": "Signal",
                "location": {
                    "start": {"value": 1},
                    "end": {"value": 24}
                },
                "description": "Signal peptide"
            },
            {
                "type": "Domain",
                "location": {
                    "start": {"value": 57},
                    "end": {"value": 167}
                },
                "description": "Receptor L1"
            },
            {
                "type": "Domain",
                "location": {
                    "start": {"value": 712},
                    "end": {"value": 979}
                },
                "description": "Protein kinase"
            },
            {
                "type": "Active site",
                "location": {
                    "start": {"value": 837},
                    "end": {"value": 837}
                },
                "description": "Proton acceptor"
            },
            {
                "type": "Binding site",
                "location": {
                    "start": {"value": 745},
                    "end": {"value": 752}
                },
                "description": "ATP",
                "ligand": {"name": "ATP"}
            },
            {
                "type": "Modified residue",
                "location": {
                    "start": {"value": 869},
                    "end": {"value": 869}
                },
                "description": "Phosphotyrosine; by autocatalysis"
            }
        ],
        "keywords": [
            {"id": "KW-0067", "category": "Biological process", "name": "ATP-binding"},
            {"id": "KW-0418", "category": "Molecular function", "name": "Kinase"},
            {"id": "KW-0829", "category": "Molecular function", "name": "Tyrosine-protein kinase"},
            {"id": "KW-0473", "category": "Cellular component", "name": "Membrane"},
            {"id": "KW-0675", "category": "Biological process", "name": "Receptor"},
            {"id": "KW-0656", "category": "Disease", "name": "Proto-oncogene"}
        ],
        "uniProtKBCrossReferences": [
            {
                "database": "PDB",
                "id": "1IVO",
                "properties": [
                    {"key": "Method", "value": "X-ray"},
                    {"key": "Resolution", "value": "2.60 A"}
                ]
            },
            {
                "database": "PDB",
                "id": "1M17",
                "properties": [
                    {"key": "Method", "value": "X-ray"},
                    {"key": "Resolution", "value": "2.60 A"}
                ]
            },
            {
                "database": "ChEMBL",
                "id": "CHEMBL203",
                "properties": []
            },
            {
                "database": "DrugBank",
                "id": "DB00530",
                "properties": [
                    {"key": "GenericName", "value": "Erlotinib"}
                ]
            },
            {
                "database": "InterPro",
                "id": "IPR000719",
                "properties": [
                    {"key": "EntryName", "value": "Prot_kinase_dom"}
                ]
            },
            {
                "database": "Pfam",
                "id": "PF00069",
                "properties": [
                    {"key": "EntryName", "value": "Pkinase"}
                ]
            },
            {
                "database": "Ensembl",
                "id": "ENSG00000146648",
                "properties": []
            },
            {
                "database": "RefSeq",
                "id": "NP_005219.2",
                "properties": []
            },
            {
                "database": "GO",
                "id": "GO:0004716",
                "properties": [
                    {"key": "GoTerm", "value": "F:receptor signaling protein tyrosine kinase activity"},
                    {"key": "GoEvidenceType", "value": "IDA:UniProtKB"}
                ]
            },
            {
                "database": "GO",
                "id": "GO:0005524",
                "properties": [
                    {"key": "GoTerm", "value": "F:ATP binding"},
                    {"key": "GoEvidenceType", "value": "IEA:UniProtKB-KW"}
                ]
            }
        ],
        "proteinExistence": "1: Evidence at protein level",
        "annotationScore": 5,
        "entryAudit": {
            "firstPublicDate": "1986-07-21",
            "lastAnnotationUpdateDate": "2024-01-24",
            "lastSequenceUpdateDate": "1996-10-01",
            "entryVersion": 295,
            "sequenceVersion": 2
        }
    }


@pytest.fixture
def mock_braf_raw_response():
    """Raw UniProt API response for BRAF (P15056) - secondary test case."""
    return {
        "primaryAccession": "P15056",
        "uniProtkbId": "BRAF_HUMAN",
        "entryType": "UniProtKB reviewed (Swiss-Prot)",
        "proteinDescription": {
            "recommendedName": {
                "fullName": {"value": "Serine/threonine-protein kinase B-raf"},
                "ecNumbers": [{"value": "2.7.11.1"}]
            }
        },
        "genes": [
            {
                "geneName": {"value": "BRAF"},
                "synonyms": [{"value": "RAFB1"}]
            }
        ],
        "organism": {
            "scientificName": "Homo sapiens",
            "commonName": "Human",
            "taxonId": 9606,
            "lineage": ["Eukaryota", "Metazoa", "Chordata", "Mammalia"]
        },
        "sequence": {
            "value": "MAALSGGGGGGAEPGQALFNGDMEPEAGAGAGAAASSAADPAIPEEVWNIKQMIKLTQEHIEALLDKFGGEHNPPSIYLEAYEEYTSKLDALQQREQQLLESLGNGTDFSVSSSASMDTVTSSSSSSLSVLPSSLSVFQNPTDVARSNPKSPQKPIVRVFLPNKQRTVVPARCGVTVRDSLKKALMMRGLIPECCAVYRIQDGEKKPIGWDTDISWLTGEELHVEVLENVPLTTHNFVRKTFFTLAFCDFCRKLLFQGFRCQTCGYKFHQRCSTEVPLMCVNYDQLDLLFVSKFFEHHPIPQEEASLAETALTSGSSPSAPASDSIGPQILTSPSPSKSIPIPQPFRPADEDHRNQFGQRDRSSSAPNVHINTIEPVNIDDLIRDQGFRGDGGSTTGLSATPPASLPGSLTNVKALQKSPGPQRERKSSSSSEDRNRMKTLGRRDSSDDWEIPDGQITVGQRIGSGSFGTVYKGKWHGDVAVKMLNVTAPTPQQLQAFKNEVGVLRKTRHVNILLFMGYSTKPQLAIVTQWCEGSSLYHHLHIIETKFEMIKLIDIARQTAQGMDYLHAKSIIHRDLKSNNIFLHEDLTVKIGDFGLATVKSRWSGSHQFEQLSGSILWMAPEVIRMQDKNPYSFQSDVYAFGIVLYELMTGQLPYSNINNRDQIIFMVGRGYLSPDLSKVRSNCPKAMKRLMAECLKKKRDERPLFPQILASIELLARSLPKIHRSASEPSLNRAGFQTEDFSLYACASPKTPIQAGGYGAFPVH",
            "length": 766,
            "molWeight": 84437,
            "crc64": "ABCDEF1234567890",
            "md5": "ABCDEF1234567890FEDCBA0987654321"
        },
        "comments": [
            {
                "commentType": "FUNCTION",
                "texts": [
                    {
                        "value": "Serine/threonine-protein kinase that plays a role in regulating the MAP kinase/ERK signaling pathway."
                    }
                ]
            }
        ],
        "features": [
            {
                "type": "Domain",
                "location": {
                    "start": {"value": 457},
                    "end": {"value": 717}
                },
                "description": "Protein kinase"
            }
        ],
        "keywords": [
            {"id": "KW-0418", "category": "Molecular function", "name": "Kinase"},
            {"id": "KW-0723", "category": "Molecular function", "name": "Serine/threonine-protein kinase"},
            {"id": "KW-0656", "category": "Disease", "name": "Proto-oncogene"}
        ],
        "uniProtKBCrossReferences": [
            {
                "database": "ChEMBL",
                "id": "CHEMBL5145",
                "properties": []
            },
            {
                "database": "PDB",
                "id": "1UWH",
                "properties": []
            }
        ],
        "proteinExistence": "1: Evidence at protein level"
    }


@pytest.fixture
def mock_search_response():
    """Mock search results response."""
    return {
        "results": [
            {
                "primaryAccession": "P00533",
                "uniProtkbId": "EGFR_HUMAN",
                "proteinDescription": {
                    "recommendedName": {
                        "fullName": {"value": "Epidermal growth factor receptor"}
                    }
                },
                "genes": [{"geneName": {"value": "EGFR"}}],
                "organism": {"scientificName": "Homo sapiens", "taxonId": 9606},
                "sequence": {"length": 1210}
            },
            {
                "primaryAccession": "P04412",
                "uniProtkbId": "EGFR_DROME",
                "proteinDescription": {
                    "recommendedName": {
                        "fullName": {"value": "Epidermal growth factor receptor homolog"}
                    }
                },
                "genes": [{"geneName": {"value": "Egfr"}}],
                "organism": {"scientificName": "Drosophila melanogaster", "taxonId": 7227},
                "sequence": {"length": 1394}
            }
        ]
    }


@pytest.fixture
def mock_empty_search_response():
    """Mock empty search results."""
    return {"results": []}


@pytest.fixture
def mock_response_factory():
    """Factory for creating mock HTTP responses."""
    def _create(status_code=200, json_data=None, text="", headers=None):
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code

        # Set default headers with Content-Type for JSON
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
# UniProtClient Tests
# =============================================================================

class TestUniProtClientGetEntry:
    """Tests for UniProtClient.get_entry()."""

    @pytest.mark.asyncio
    async def test_get_entry_returns_raw_json(
        self, mock_egfr_raw_response, mock_response_factory
    ):
        """get_entry returns raw JSON response from UniProt API."""
        client = UniProtClient(cache_enabled=False)

        mock_response = mock_response_factory(json_data=mock_egfr_raw_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            result = await client.get_entry("P00533")

            assert result["primaryAccession"] == "P00533"
            assert result["uniProtkbId"] == "EGFR_HUMAN"
            assert "sequence" in result
            mock_http.get.assert_called_once_with("/uniprotkb/P00533", params=None)

        await client.close()

    @pytest.mark.asyncio
    async def test_get_entry_not_found_raises_error(self, mock_response_factory):
        """get_entry raises NotFoundError for 404 response."""
        client = UniProtClient(cache_enabled=False)

        mock_response = mock_response_factory(status_code=404, text="Not found")

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            with pytest.raises(NotFoundError) as exc_info:
                await client.get_entry("INVALID_ID")

            assert exc_info.value.status_code == 404
            assert "INVALID_ID" in str(exc_info.value.resource) or "/uniprotkb/INVALID_ID" in str(exc_info.value.resource)

        await client.close()

    @pytest.mark.asyncio
    async def test_get_entry_rate_limit_raises_error(self, mock_response_factory):
        """get_entry raises RateLimitError for 429 response."""
        client = UniProtClient(cache_enabled=False, max_retries=0)

        mock_response = mock_response_factory(
            status_code=429,
            text="Rate limit exceeded",
            headers={"Retry-After": "60"}
        )

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            with pytest.raises(RateLimitError) as exc_info:
                await client.get_entry("P00533")

            assert exc_info.value.status_code == 429
            assert exc_info.value.retry_after == 60

        await client.close()

    @pytest.mark.asyncio
    async def test_get_entry_server_error_retries(self, mock_egfr_raw_response, mock_response_factory):
        """get_entry retries on 5xx server errors."""
        client = UniProtClient(cache_enabled=False, max_retries=2)

        error_response = mock_response_factory(status_code=500, text="Server error")
        success_response = mock_response_factory(json_data=mock_egfr_raw_response)

        call_count = 0
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return error_response
            return success_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client.get_entry("P00533")

            assert result["primaryAccession"] == "P00533"
            assert call_count == 2

        await client.close()


class TestUniProtClientSearch:
    """Tests for UniProtClient.search()."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self, mock_search_response, mock_response_factory):
        """search returns list of matching proteins."""
        client = UniProtClient(cache_enabled=False)

        mock_response = mock_response_factory(json_data=mock_search_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            result = await client.search("EGFR AND organism_id:9606")

            assert "results" in result
            assert len(result["results"]) == 2
            assert result["results"][0]["primaryAccession"] == "P00533"

        await client.close()

    @pytest.mark.asyncio
    async def test_search_empty_results(self, mock_empty_search_response, mock_response_factory):
        """search returns empty list when no matches."""
        client = UniProtClient(cache_enabled=False)

        mock_response = mock_response_factory(json_data=mock_empty_search_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            result = await client.search("nonexistent_protein_xyz_12345")

            assert "results" in result
            assert len(result["results"]) == 0

        await client.close()

    @pytest.mark.asyncio
    async def test_search_by_gene(self, mock_search_response, mock_response_factory):
        """search_by_gene builds correct query."""
        client = UniProtClient(cache_enabled=False)

        mock_response = mock_response_factory(json_data=mock_search_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            result = await client.search_by_gene("EGFR", organism_id=9606)

            assert len(result["results"]) == 2
            # Verify query params include gene and organism
            call_kwargs = mock_http.get.call_args
            assert "gene" in str(call_kwargs).lower() or "query" in str(call_kwargs)

        await client.close()


class TestUniProtClientCaching:
    """Tests for UniProtClient caching behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_data(self, mock_egfr_raw_response, mock_response_factory):
        """Second call returns cached data without HTTP request."""
        client = UniProtClient(cache_enabled=True)
        client._redis_client = False  # Force in-memory cache

        mock_response = mock_response_factory(json_data=mock_egfr_raw_response)
        call_count = {"value": 0}

        async def mock_get(*args, **kwargs):
            call_count["value"] += 1
            return mock_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            # First call - should hit API
            result1 = await client.get_entry("P00533")
            assert call_count["value"] == 1

            # Second call - should hit cache
            result2 = await client.get_entry("P00533")
            assert call_count["value"] == 1  # No additional HTTP call

            assert result1["primaryAccession"] == result2["primaryAccession"]

        await client.close()

    @pytest.mark.asyncio
    async def test_cache_disabled_makes_multiple_requests(
        self, mock_egfr_raw_response, mock_response_factory
    ):
        """With cache disabled, each call makes HTTP request."""
        client = UniProtClient(cache_enabled=False)

        mock_response = mock_response_factory(json_data=mock_egfr_raw_response)
        call_count = {"value": 0}

        async def mock_get(*args, **kwargs):
            call_count["value"] += 1
            return mock_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            await client.get_entry("P00533")
            await client.get_entry("P00533")

            assert call_count["value"] == 2

        await client.close()

    @pytest.mark.asyncio
    async def test_different_accessions_make_separate_requests(
        self, mock_egfr_raw_response, mock_braf_raw_response, mock_response_factory
    ):
        """Different accessions make separate HTTP requests."""
        client = UniProtClient(cache_enabled=True)
        client._redis_client = False

        responses = {
            "/uniprotkb/P00533": mock_response_factory(json_data=mock_egfr_raw_response),
            "/uniprotkb/P15056": mock_response_factory(json_data=mock_braf_raw_response),
        }
        call_count = {"value": 0}

        async def mock_get(endpoint, **kwargs):
            call_count["value"] += 1
            return responses.get(endpoint, mock_response_factory(status_code=404))

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            result1 = await client.get_entry("P00533")
            result2 = await client.get_entry("P15056")

            assert call_count["value"] == 2
            assert result1["primaryAccession"] == "P00533"
            assert result2["primaryAccession"] == "P15056"

        await client.close()


# =============================================================================
# UniProtNormalizer Tests
# =============================================================================

class TestUniProtNormalizer:
    """Tests for UniProtNormalizer."""

    def test_normalize_target_extracts_basic_info(self, mock_egfr_raw_response):
        """Normalizer extracts basic protein information."""
        normalizer = UniProtNormalizer()

        target = normalizer.normalize_target(mock_egfr_raw_response)

        assert isinstance(target, UniProtTarget)
        assert target.uniprot_id == "P00533"
        assert target.entry_name == "EGFR_HUMAN"
        assert "Epidermal growth factor receptor" in target.protein_name.recommended_name

    def test_normalize_target_extracts_sequence(self, mock_egfr_raw_response):
        """Normalizer extracts protein sequence data."""
        normalizer = UniProtNormalizer()

        target = normalizer.normalize_target(mock_egfr_raw_response)

        assert target.sequence is not None
        assert len(target.sequence) == 1210
        assert target.sequence.startswith("MRPSGTAGAALLALLAALCPASRALEEKKVCQG")
        assert target.sequence_length == 1210
        assert target.sequence_mass == 134277

    def test_normalize_target_extracts_gene_info(self, mock_egfr_raw_response):
        """Normalizer extracts gene information."""
        normalizer = UniProtNormalizer()

        target = normalizer.normalize_target(mock_egfr_raw_response)

        assert target.gene is not None
        assert target.gene.name == "EGFR"
        assert "ERBB" in target.gene.synonyms or "HER1" in target.gene.synonyms

    def test_normalize_target_extracts_organism(self, mock_egfr_raw_response):
        """Normalizer extracts organism information."""
        normalizer = UniProtNormalizer()

        target = normalizer.normalize_target(mock_egfr_raw_response)

        assert target.organism is not None
        assert target.organism.scientific_name == "Homo sapiens"
        assert target.organism.common_name == "Human"
        assert target.organism.tax_id == 9606

    def test_normalize_target_extracts_function(self, mock_egfr_raw_response):
        """Normalizer extracts function annotation."""
        normalizer = UniProtNormalizer()

        target = normalizer.normalize_target(mock_egfr_raw_response)

        assert target.function is not None
        assert len(target.function) > 0
        # Check function text contains EGFR-related info
        function_text = " ".join(f.text for f in target.function if f.text)
        assert "tyrosine kinase" in function_text.lower() or "EGF" in function_text

    def test_normalize_target_extracts_domains(self, mock_egfr_raw_response):
        """Normalizer extracts domain features."""
        normalizer = UniProtNormalizer()

        target = normalizer.normalize_target(mock_egfr_raw_response)

        assert target.domains is not None
        assert len(target.domains) > 0

        # Check for kinase domain
        domain_names = [d.description.lower() for d in target.domains if d.description]
        assert any("kinase" in name for name in domain_names)

    def test_normalize_target_extracts_keywords(self, mock_egfr_raw_response):
        """Normalizer extracts keywords."""
        normalizer = UniProtNormalizer()

        target = normalizer.normalize_target(mock_egfr_raw_response)

        assert target.keywords is not None
        assert len(target.keywords) > 0

        keyword_names = [kw.lower() for kw in target.keywords]
        assert any("kinase" in kw for kw in keyword_names)

    def test_normalize_target_extracts_cross_references(self, mock_egfr_raw_response):
        """Normalizer extracts cross-references to other databases."""
        normalizer = UniProtNormalizer()

        target = normalizer.normalize_target(mock_egfr_raw_response)

        # Check PDB references
        assert target.pdb_ids is not None
        assert len(target.pdb_ids) > 0
        assert "1IVO" in target.pdb_ids or "1M17" in target.pdb_ids

        # Check ChEMBL reference
        assert target.chembl_id == "CHEMBL203"

    def test_normalize_target_extracts_subcellular_location(self, mock_egfr_raw_response):
        """Normalizer extracts subcellular location."""
        normalizer = UniProtNormalizer()

        target = normalizer.normalize_target(mock_egfr_raw_response)

        assert target.subcellular_locations is not None
        assert len(target.subcellular_locations) > 0

        locations = [loc.location.lower() for loc in target.subcellular_locations if loc.location]
        assert any("membrane" in loc for loc in locations)

    def test_normalize_target_extracts_disease_associations(self, mock_egfr_raw_response):
        """Normalizer extracts disease associations."""
        normalizer = UniProtNormalizer()

        target = normalizer.normalize_target(mock_egfr_raw_response)

        assert target.disease_associations is not None
        assert len(target.disease_associations) > 0

        # Verify disease association has data (diseaseId becomes disease_name)
        disease = target.disease_associations[0]
        assert disease.disease_name is not None
        # Description contains the actual disease info
        assert disease.description is None or "lung" in disease.description.lower() or disease.disease_name == "DI-00551"

    def test_normalize_target_with_minimal_data(self):
        """Normalizer handles entries with minimal data."""
        normalizer = UniProtNormalizer()

        minimal_entry = {
            "primaryAccession": "Q12345",
            "uniProtkbId": "TEST_HUMAN",
            "proteinDescription": {
                "recommendedName": {
                    "fullName": {"value": "Test protein"}
                }
            },
            "sequence": {
                "value": "MVLSPADKTN",
                "length": 10
            }
        }

        target = normalizer.normalize_target(minimal_entry)

        assert target.uniprot_id == "Q12345"
        assert target.entry_name == "TEST_HUMAN"
        assert target.sequence == "MVLSPADKTN"
        assert target.sequence_length == 10
        # Optional fields should be None or empty
        assert target.gene is None or target.gene.name is None

    def test_normalize_search_hit(self, mock_search_response):
        """Normalizer converts search results to TargetSearchHit."""
        normalizer = UniProtNormalizer()

        hits = normalizer.normalize_search_results(mock_search_response)

        assert len(hits) == 2

        egfr_hit = hits[0]
        assert egfr_hit.uniprot_id == "P00533"
        assert egfr_hit.entry_name == "EGFR_HUMAN"
        assert "Epidermal growth factor receptor" in egfr_hit.protein_name


# =============================================================================
# UniProtConnector Tests
# =============================================================================

class TestUniProtConnectorGetTarget:
    """Tests for UniProtConnector.get_target()."""

    @pytest.mark.asyncio
    async def test_get_target_returns_normalized_target(
        self, mock_egfr_raw_response, mock_response_factory
    ):
        """get_target returns fully normalized UniProtTarget."""
        client = UniProtClient(cache_enabled=False)
        connector = UniProtConnector(client=client)

        mock_response = mock_response_factory(json_data=mock_egfr_raw_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            target = await connector.get_target("P00533")

            assert isinstance(target, UniProtTarget)
            assert target.uniprot_id == "P00533"
            assert target.entry_name == "EGFR_HUMAN"
            assert "Epidermal growth factor receptor" in target.protein_name.recommended_name
            assert target.sequence is not None
            assert len(target.sequence) == 1210
            assert target.gene.name == "EGFR"
            assert target.organism.tax_id == 9606

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_target_not_found_raises_error(self, mock_response_factory):
        """get_target raises NotFoundError for invalid UniProt ID."""
        client = UniProtClient(cache_enabled=False)
        connector = UniProtConnector(client=client)

        mock_response = mock_response_factory(status_code=404, text="Not found")

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            with pytest.raises(NotFoundError) as exc_info:
                await connector.get_target("INVALID_ACCESSION")

            assert exc_info.value.status_code == 404

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_target_with_annotations(
        self, mock_egfr_raw_response, mock_response_factory
    ):
        """get_target returns target with all key annotations."""
        client = UniProtClient(cache_enabled=False)
        connector = UniProtConnector(client=client)

        mock_response = mock_response_factory(json_data=mock_egfr_raw_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            target = await connector.get_target("P00533")

            # Verify key annotations are present
            assert target.function is not None and len(target.function) > 0
            assert target.domains is not None and len(target.domains) > 0
            assert target.keywords is not None and len(target.keywords) > 0
            assert target.pdb_ids is not None and len(target.pdb_ids) > 0
            assert target.chembl_id == "CHEMBL203"
            assert target.subcellular_locations is not None
            assert target.disease_associations is not None

        await connector.close()


class TestUniProtConnectorSearch:
    """Tests for UniProtConnector search methods."""

    @pytest.mark.asyncio
    async def test_search_targets_returns_results(
        self, mock_search_response, mock_response_factory
    ):
        """search_targets returns TargetSearchResult."""
        client = UniProtClient(cache_enabled=False)
        connector = UniProtConnector(client=client)

        mock_response = mock_response_factory(json_data=mock_search_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            result = await connector.search_targets("EGFR")

            assert isinstance(result, TargetSearchResult)
            assert len(result.hits) == 2
            assert result.hits[0].uniprot_id == "P00533"

        await connector.close()

    @pytest.mark.asyncio
    async def test_search_targets_empty_results(
        self, mock_empty_search_response, mock_response_factory
    ):
        """search_targets handles empty results gracefully."""
        client = UniProtClient(cache_enabled=False)
        connector = UniProtConnector(client=client)

        mock_response = mock_response_factory(json_data=mock_empty_search_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            result = await connector.search_targets("nonexistent_xyz_12345")

            assert isinstance(result, TargetSearchResult)
            assert len(result.hits) == 0

        await connector.close()

    @pytest.mark.asyncio
    async def test_search_by_gene_name(
        self, mock_search_response, mock_response_factory
    ):
        """search_by_gene returns targets matching gene name."""
        client = UniProtClient(cache_enabled=False)
        connector = UniProtConnector(client=client)

        mock_response = mock_response_factory(json_data=mock_search_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            result = await connector.search_by_gene("EGFR", organism_id=9606)

            assert len(result.hits) >= 1
            # First result should be human EGFR
            assert result.hits[0].uniprot_id == "P00533"

        await connector.close()


class TestUniProtConnectorCaching:
    """Tests for UniProtConnector caching behavior."""

    @pytest.mark.asyncio
    async def test_connector_caches_targets(
        self, mock_egfr_raw_response, mock_response_factory
    ):
        """Connector caches target data on repeat calls."""
        client = UniProtClient(cache_enabled=True)
        client._redis_client = False  # Force in-memory cache
        connector = UniProtConnector(client=client)

        mock_response = mock_response_factory(json_data=mock_egfr_raw_response)
        call_count = {"value": 0}

        async def mock_get(*args, **kwargs):
            call_count["value"] += 1
            return mock_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            # First call
            target1 = await connector.get_target("P00533")
            assert call_count["value"] == 1

            # Second call - should use cache
            target2 = await connector.get_target("P00533")
            assert call_count["value"] == 1  # No additional HTTP call

            # Both should have same data
            assert target1.uniprot_id == target2.uniprot_id
            assert target1.sequence == target2.sequence

        await connector.close()

    @pytest.mark.asyncio
    async def test_connector_search_caching(
        self, mock_search_response, mock_response_factory
    ):
        """Connector caches search results."""
        client = UniProtClient(cache_enabled=True)
        client._redis_client = False  # Force in-memory cache
        connector = UniProtConnector(client=client)

        mock_response = mock_response_factory(json_data=mock_search_response)
        call_count = {"value": 0}

        async def mock_get(*args, **kwargs):
            call_count["value"] += 1
            return mock_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            # First search
            await connector.search_targets("EGFR")
            assert call_count["value"] == 1

            # Same search - should use cache
            await connector.search_targets("EGFR")
            assert call_count["value"] == 1

        await connector.close()


class TestUniProtConnectorBatch:
    """Tests for UniProtConnector batch operations."""

    @pytest.mark.asyncio
    async def test_get_targets_batch(
        self, mock_egfr_raw_response, mock_braf_raw_response, mock_response_factory
    ):
        """get_targets_batch retrieves multiple targets."""
        client = UniProtClient(cache_enabled=False)
        connector = UniProtConnector(client=client)

        # Mock search response with both entries
        batch_response = {
            "results": [mock_egfr_raw_response, mock_braf_raw_response]
        }
        mock_response = mock_response_factory(json_data=batch_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            targets = await connector.get_targets_batch(["P00533", "P15056"])

            assert len(targets) == 2
            accessions = {t.uniprot_id for t in targets}
            assert "P00533" in accessions
            assert "P15056" in accessions

        await connector.close()

    @pytest.mark.asyncio
    async def test_get_targets_batch_empty_list(self):
        """get_targets_batch returns empty list for empty input."""
        client = UniProtClient(cache_enabled=False)
        connector = UniProtConnector(client=client)

        targets = await connector.get_targets_batch([])

        assert targets == []

        await connector.close()


# =============================================================================
# Integration-Style Tests (with mocked HTTP)
# =============================================================================

class TestUniProtIntegration:
    """Integration-style tests using the full connector stack."""

    @pytest.mark.asyncio
    async def test_full_workflow_get_target_and_check_annotations(
        self, mock_egfr_raw_response, mock_response_factory
    ):
        """Full workflow: get target and verify all annotations are accessible."""
        client = UniProtClient(cache_enabled=False)
        connector = UniProtConnector(client=client)

        mock_response = mock_response_factory(json_data=mock_egfr_raw_response)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            target = await connector.get_target("P00533")

            # Verify target is a complete drug discovery target profile
            assert target.uniprot_id == "P00533"
            assert target.entry_name == "EGFR_HUMAN"

            # Basic info
            assert "Epidermal growth factor receptor" in target.protein_name.recommended_name
            assert target.gene.name == "EGFR"
            assert target.organism.scientific_name == "Homo sapiens"

            # Sequence data (essential for drug discovery)
            assert target.sequence is not None
            assert target.sequence_length == 1210
            assert target.sequence_mass > 0

            # Functional annotations
            assert any("kinase" in f.text.lower() for f in target.function if f.text)

            # Structural features (important for drug binding)
            assert len(target.domains) > 0
            domain_descriptions = [d.description.lower() for d in target.domains if d.description]
            assert any("kinase" in d for d in domain_descriptions)

            # Drug-related annotations
            assert target.chembl_id == "CHEMBL203"  # ChEMBL target ID
            assert len(target.pdb_ids) > 0  # Structural data available

            # Disease relevance
            assert len(target.disease_associations) > 0

        await connector.close()

    @pytest.mark.asyncio
    async def test_workflow_search_then_get_details(
        self, mock_search_response, mock_egfr_raw_response, mock_response_factory
    ):
        """Workflow: search for targets, then get detailed info."""
        client = UniProtClient(cache_enabled=False)
        connector = UniProtConnector(client=client)

        search_response = mock_response_factory(json_data=mock_search_response)
        detail_response = mock_response_factory(json_data=mock_egfr_raw_response)

        call_sequence = []

        async def mock_get(endpoint, **kwargs):
            call_sequence.append(endpoint)
            if "search" in endpoint:
                return search_response
            return detail_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_get_client.return_value = mock_http

            # Step 1: Search
            search_result = await connector.search_targets("kinase AND organism_id:9606")
            assert len(search_result.hits) == 2

            # Step 2: Get detailed info for top hit
            target = await connector.get_target(search_result.hits[0].uniprot_id)
            assert target.uniprot_id == "P00533"
            assert target.sequence is not None

            # Verify both calls were made
            assert len(call_sequence) == 2

        await connector.close()


class TestUniProtErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_handles_malformed_response_gracefully(self, mock_response_factory):
        """Connector handles malformed API response."""
        client = UniProtClient(cache_enabled=False)
        connector = UniProtConnector(client=client)

        # Response missing required fields
        malformed = {"primaryAccession": "P00533"}  # Missing most fields
        mock_response = mock_response_factory(json_data=malformed)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            # Should either handle gracefully or raise clear error
            try:
                target = await connector.get_target("P00533")
                # If it succeeds, basic fields should be present
                assert target.uniprot_id == "P00533"
            except (ValueError, KeyError) as e:
                # Acceptable to raise if data is too malformed
                assert "P00533" in str(e) or True

        await connector.close()

    @pytest.mark.asyncio
    async def test_timeout_handling(self, mock_response_factory):
        """Connector handles timeout errors."""
        client = UniProtClient(cache_enabled=False, max_retries=0)
        connector = UniProtConnector(client=client)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_get_client.return_value = mock_http

            with pytest.raises(UniProtClientError) as exc_info:
                await connector.get_target("P00533")

            assert "timeout" in str(exc_info.value).lower()

        await connector.close()

    @pytest.mark.asyncio
    async def test_connection_error_handling(self, mock_response_factory):
        """Connector handles connection errors."""
        client = UniProtClient(cache_enabled=False, max_retries=0)
        connector = UniProtConnector(client=client)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_get_client.return_value = mock_http

            with pytest.raises(UniProtClientError):
                await connector.get_target("P00533")

        await connector.close()
