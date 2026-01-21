"""Tests for molecular similarity calculations."""

import pytest

from packages.chemistry.features import (
    FingerprintType,
    calculate_fingerprint,
    calculate_morgan_fingerprint,
)
from packages.chemistry.similarity import (
    FingerprintIndex,
    SimilarityResult,
    SimilaritySearchResult,
    bulk_tanimoto,
    cluster_by_similarity,
    dice_similarity,
    dice_similarity_bytes,
    find_similar_molecules,
    similarity_matrix,
    tanimoto_from_smiles,
    tanimoto_similarity,
    tanimoto_similarity_bytes,
)


# ============================================================================
# Test data
# ============================================================================

ETHANOL = "CCO"
METHANOL = "CO"
PROPANOL = "CCCO"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
CAFFEINE = "Cn1cnc2c1c(=O)n(c(=O)n2C)C"
BENZENE = "c1ccccc1"
TOLUENE = "Cc1ccccc1"
PHENOL = "Oc1ccccc1"


class TestTanimotoSimilarityBytes:
    """Tests for raw byte-based Tanimoto calculation."""

    def test_identical_fingerprints(self):
        """Test similarity of identical fingerprints."""
        fp = b"\xff\xff\xff\xff"  # All ones
        sim = tanimoto_similarity_bytes(fp, fp)
        assert sim == 1.0

    def test_completely_different(self):
        """Test similarity of non-overlapping fingerprints."""
        fp1 = b"\xf0\xf0\xf0\xf0"  # 11110000 pattern
        fp2 = b"\x0f\x0f\x0f\x0f"  # 00001111 pattern
        sim = tanimoto_similarity_bytes(fp1, fp2)
        assert sim == 0.0

    def test_partial_overlap(self):
        """Test similarity with partial overlap."""
        fp1 = b"\xff\x00"  # 8 bits on
        fp2 = b"\xff\xff"  # 16 bits on
        sim = tanimoto_similarity_bytes(fp1, fp2)
        # Tanimoto = 8 / (8 + 16 - 8) = 8/16 = 0.5
        assert sim == 0.5

    def test_empty_fingerprints(self):
        """Test similarity of empty fingerprints."""
        fp = b"\x00\x00\x00\x00"
        sim = tanimoto_similarity_bytes(fp, fp)
        assert sim == 1.0  # Both empty = identical

    def test_different_lengths_raises(self):
        """Test that different length fingerprints raise error."""
        fp1 = b"\xff\xff"
        fp2 = b"\xff\xff\xff"
        with pytest.raises(ValueError, match="same length"):
            tanimoto_similarity_bytes(fp1, fp2)


class TestTanimotoSimilarity:
    """Tests for Fingerprint object-based Tanimoto calculation."""

    def test_identical_molecules(self):
        """Test similarity of identical molecules."""
        fp1 = calculate_morgan_fingerprint(ASPIRIN)
        fp2 = calculate_morgan_fingerprint(ASPIRIN)
        sim = tanimoto_similarity(fp1, fp2)
        assert sim == 1.0

    def test_similar_molecules(self):
        """Test similarity of similar molecules."""
        fp_benzene = calculate_morgan_fingerprint(BENZENE)
        fp_toluene = calculate_morgan_fingerprint(TOLUENE)
        sim = tanimoto_similarity(fp_benzene, fp_toluene)

        # Benzene and toluene share structural similarity (but Morgan radius 2 gives ~0.27)
        assert 0.2 < sim < 1.0

    def test_different_molecules(self):
        """Test similarity of different molecules."""
        fp_ethanol = calculate_morgan_fingerprint(ETHANOL)
        fp_caffeine = calculate_morgan_fingerprint(CAFFEINE)
        sim = tanimoto_similarity(fp_ethanol, fp_caffeine)

        # Ethanol and caffeine are quite different
        assert sim < 0.5

    def test_mismatched_types_raises(self):
        """Test that different fingerprint types raise error."""
        fp_morgan = calculate_fingerprint(ASPIRIN, FingerprintType.MORGAN)
        fp_maccs = calculate_fingerprint(ASPIRIN, FingerprintType.MACCS)

        with pytest.raises(ValueError, match="types must match"):
            tanimoto_similarity(fp_morgan, fp_maccs)

    def test_symmetry(self):
        """Test that similarity is symmetric."""
        fp1 = calculate_morgan_fingerprint(ASPIRIN)
        fp2 = calculate_morgan_fingerprint(CAFFEINE)

        sim12 = tanimoto_similarity(fp1, fp2)
        sim21 = tanimoto_similarity(fp2, fp1)

        assert sim12 == sim21


class TestDiceSimilarity:
    """Tests for Dice similarity coefficient."""

    def test_identical_fingerprints(self):
        """Test Dice similarity of identical fingerprints."""
        fp = b"\xff\xff\xff\xff"
        sim = dice_similarity_bytes(fp, fp)
        assert sim == 1.0

    def test_partial_overlap(self):
        """Test Dice with partial overlap."""
        fp1 = b"\xff\x00"  # 8 bits on
        fp2 = b"\xff\xff"  # 16 bits on
        sim = dice_similarity_bytes(fp1, fp2)
        # Dice = 2*8 / (8 + 16) = 16/24 = 0.666...
        assert abs(sim - 2 / 3) < 0.001

    def test_dice_vs_tanimoto(self):
        """Test relationship between Dice and Tanimoto."""
        fp1 = calculate_morgan_fingerprint(BENZENE)
        fp2 = calculate_morgan_fingerprint(TOLUENE)

        tan = tanimoto_similarity(fp1, fp2)
        dice = dice_similarity(fp1, fp2)

        # Dice >= Tanimoto always
        assert dice >= tan


class TestTanimotoFromSmiles:
    """Tests for SMILES-based similarity calculation."""

    def test_tanimoto_from_smiles_basic(self):
        """Test direct SMILES comparison."""
        sim = tanimoto_from_smiles(BENZENE, TOLUENE)
        # Benzene and toluene similarity with Morgan radius 2 is ~0.27
        assert 0.2 < sim < 1.0

    def test_tanimoto_from_smiles_identical(self):
        """Test identical SMILES."""
        sim = tanimoto_from_smiles(ASPIRIN, ASPIRIN)
        assert sim == 1.0

    def test_tanimoto_from_smiles_with_type(self):
        """Test with different fingerprint type."""
        sim_morgan = tanimoto_from_smiles(BENZENE, PHENOL, fp_type=FingerprintType.MORGAN)
        sim_maccs = tanimoto_from_smiles(BENZENE, PHENOL, fp_type=FingerprintType.MACCS)

        # Both should be positive
        assert sim_morgan > 0
        assert sim_maccs > 0


class TestBulkTanimoto:
    """Tests for bulk similarity calculations."""

    def test_bulk_tanimoto_basic(self):
        """Test bulk similarity search."""
        database = [ETHANOL, METHANOL, PROPANOL, ASPIRIN, CAFFEINE]
        results = bulk_tanimoto(ETHANOL, database)

        assert len(results) == 5
        # Results should be sorted by similarity descending
        assert all(results[i][1] >= results[i + 1][1] for i in range(len(results) - 1))
        # First result should be identical match (ETHANOL)
        assert results[0][1] == 1.0
        assert results[0][0] == 0

    def test_bulk_tanimoto_with_threshold(self):
        """Test bulk search with threshold."""
        database = [ETHANOL, ASPIRIN, CAFFEINE, BENZENE]
        results = bulk_tanimoto(ETHANOL, database, threshold=0.5)

        # Only molecules above threshold
        assert all(r[1] >= 0.5 for r in results)

    def test_bulk_tanimoto_with_fingerprints(self):
        """Test bulk search with pre-computed fingerprints."""
        database_fps = [calculate_morgan_fingerprint(s) for s in [BENZENE, TOLUENE, PHENOL]]
        query_fp = calculate_morgan_fingerprint(TOLUENE)

        results = bulk_tanimoto(query_fp, database_fps)
        # Toluene should match itself perfectly
        assert results[0][0] == 1  # Index of TOLUENE
        assert results[0][1] == 1.0


class TestSimilarityMatrix:
    """Tests for pairwise similarity matrix."""

    def test_similarity_matrix_basic(self):
        """Test pairwise similarity matrix."""
        molecules = [BENZENE, TOLUENE, PHENOL]
        matrix = similarity_matrix(molecules)

        assert len(matrix) == 3
        assert all(len(row) == 3 for row in matrix)
        # Diagonal should be 1.0
        assert matrix[0][0] == 1.0
        assert matrix[1][1] == 1.0
        assert matrix[2][2] == 1.0
        # Should be symmetric
        assert matrix[0][1] == matrix[1][0]
        assert matrix[0][2] == matrix[2][0]

    def test_similarity_matrix_single(self):
        """Test matrix with single molecule."""
        matrix = similarity_matrix([ASPIRIN])
        assert matrix == [[1.0]]


class TestFindSimilarMolecules:
    """Tests for similarity search function."""

    def test_find_similar_basic(self):
        """Test finding similar molecules."""
        database = [ETHANOL, METHANOL, PROPANOL, ASPIRIN, BENZENE]
        result = find_similar_molecules(ETHANOL, database, threshold=0.3)

        assert isinstance(result, SimilaritySearchResult)
        assert result.query_smiles == ETHANOL
        assert result.threshold == 0.3
        assert len(result.matches) > 0
        # First match should be exact
        assert result.matches[0][1] == 1.0

    def test_find_similar_top_n(self):
        """Test limiting results."""
        database = [ETHANOL, METHANOL, PROPANOL, BENZENE, TOLUENE]
        result = find_similar_molecules(ETHANOL, database, threshold=0.0, top_n=3)

        assert len(result.matches) == 3

    def test_find_similar_high_threshold(self):
        """Test with very high threshold."""
        database = [ETHANOL, ASPIRIN, CAFFEINE]
        result = find_similar_molecules(ETHANOL, database, threshold=0.99)

        # Only exact match should pass
        assert len(result.matches) == 1
        assert result.matches[0][1] >= 0.99


class TestClusterBySimilarity:
    """Tests for similarity-based clustering."""

    def test_cluster_basic(self):
        """Test basic clustering."""
        molecules = [BENZENE, TOLUENE, PHENOL, ETHANOL, METHANOL]
        clusters = cluster_by_similarity(molecules, threshold=0.5)

        # Should have at least one cluster
        assert len(clusters) > 0
        # All molecules should be assigned
        all_indices = set()
        for cluster in clusters:
            all_indices.update(cluster)
        assert all_indices == {0, 1, 2, 3, 4}

    def test_cluster_identical(self):
        """Test clustering identical molecules."""
        molecules = [ASPIRIN, ASPIRIN, ASPIRIN]
        clusters = cluster_by_similarity(molecules, threshold=0.9)

        # All should be in one cluster
        assert len(clusters) == 1
        assert set(clusters[0]) == {0, 1, 2}

    def test_cluster_very_different(self):
        """Test clustering very different molecules."""
        # These are quite different
        molecules = [ETHANOL, CAFFEINE]
        clusters = cluster_by_similarity(molecules, threshold=0.9)

        # Should be in separate clusters
        assert len(clusters) == 2


class TestFingerprintIndex:
    """Tests for FingerprintIndex in-memory search structure."""

    def test_index_add_and_search(self):
        """Test adding molecules and searching."""
        index = FingerprintIndex()
        index.add(BENZENE, "mol1")
        index.add(TOLUENE, "mol2")
        index.add(PHENOL, "mol3")
        index.add(ASPIRIN, "mol4")

        results = index.search(BENZENE, threshold=0.7)

        # Should find at least benzene itself
        assert len(results) > 0
        # First result should be benzene (exact match)
        assert results[0][0] == "mol1"
        assert results[0][2] == 1.0

    def test_index_add_many(self):
        """Test adding multiple molecules at once."""
        index = FingerprintIndex()
        smiles_list = [ETHANOL, METHANOL, PROPANOL]
        ids = ["eth", "meth", "prop"]

        indices = index.add_many(smiles_list, ids)

        assert len(indices) == 3
        assert len(index) == 3

    def test_index_search_top_n(self):
        """Test limiting search results."""
        index = FingerprintIndex()
        index.add_many([BENZENE, TOLUENE, PHENOL, ASPIRIN, CAFFEINE])

        results = index.search(BENZENE, threshold=0.0, top_n=2)
        assert len(results) == 2

    def test_index_without_ids(self):
        """Test index without explicit IDs."""
        index = FingerprintIndex()
        index.add(ETHANOL)
        index.add(METHANOL)

        results = index.search(ETHANOL)
        # IDs should be numeric indices
        assert results[0][0] == 0

    def test_index_custom_fingerprint(self):
        """Test index with custom fingerprint parameters."""
        index = FingerprintIndex(fp_type=FingerprintType.MORGAN, radius=3, num_bits=1024)
        index.add(ASPIRIN, "aspirin")
        index.add(CAFFEINE, "caffeine")

        results = index.search(ASPIRIN)
        assert len(results) >= 1


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_database_search(self):
        """Test searching empty database."""
        results = bulk_tanimoto(ETHANOL, [])
        assert results == []

    def test_single_molecule_matrix(self):
        """Test similarity matrix with one molecule."""
        matrix = similarity_matrix([ASPIRIN])
        assert matrix == [[1.0]]

    def test_cluster_single_molecule(self):
        """Test clustering single molecule."""
        clusters = cluster_by_similarity([ASPIRIN])
        assert clusters == [[0]]

    def test_charged_molecules(self):
        """Test similarity of charged molecules."""
        sim = tanimoto_from_smiles("[NH4+]", "[NH3]")
        assert 0 <= sim <= 1

    def test_stereoisomers(self):
        """Test similarity of stereoisomers."""
        l_ala = "N[C@@H](C)C(=O)O"
        d_ala = "N[C@H](C)C(=O)O"
        sim = tanimoto_from_smiles(l_ala, d_ala)
        # Morgan fingerprints don't distinguish by default
        assert sim == 1.0


class TestDeterminism:
    """Tests to ensure deterministic behavior."""

    def test_tanimoto_deterministic(self):
        """Test that Tanimoto calculation is deterministic."""
        for _ in range(10):
            sim = tanimoto_from_smiles(ASPIRIN, CAFFEINE)
            assert sim == tanimoto_from_smiles(ASPIRIN, CAFFEINE)

    def test_bulk_search_deterministic(self):
        """Test that bulk search is deterministic."""
        database = [ETHANOL, ASPIRIN, BENZENE]
        r1 = bulk_tanimoto(ETHANOL, database)
        r2 = bulk_tanimoto(ETHANOL, database)
        assert r1 == r2

    def test_matrix_deterministic(self):
        """Test that matrix calculation is deterministic."""
        molecules = [BENZENE, TOLUENE, PHENOL]
        m1 = similarity_matrix(molecules)
        m2 = similarity_matrix(molecules)
        assert m1 == m2
