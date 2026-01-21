"""
Molecular similarity calculations for substructure and similarity search.

This module provides:
- Tanimoto similarity calculation (in-memory)
- Bulk similarity search
- Fingerprint-based similarity matrix
- Dice similarity (alternative metric)

Designed for deterministic results in tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

from packages.chemistry.features import (
    Fingerprint,
    FingerprintType,
    calculate_fingerprint,
    calculate_morgan_fingerprint,
)

if TYPE_CHECKING:
    from rdkit.Chem import Mol


@dataclass(frozen=True)
class SimilarityResult:
    """Result of a similarity comparison."""

    query_index: int
    target_index: int
    similarity: float
    fp_type: FingerprintType


@dataclass(frozen=True)
class SimilaritySearchResult:
    """Result of a similarity search against a database."""

    query_smiles: str
    matches: list[tuple[int, float]]  # (index, similarity) pairs sorted by similarity desc
    fp_type: FingerprintType
    threshold: float


def tanimoto_similarity_bytes(fp1_bytes: bytes, fp2_bytes: bytes) -> float:
    """
    Calculate Tanimoto similarity between two fingerprints represented as bytes.

    Tanimoto coefficient = |A ∩ B| / |A ∪ B|
                        = (bits in common) / (bits in A + bits in B - bits in common)

    Args:
        fp1_bytes: First fingerprint as bytes
        fp2_bytes: Second fingerprint as bytes

    Returns:
        Tanimoto similarity coefficient (0.0 to 1.0)
    """
    if len(fp1_bytes) != len(fp2_bytes):
        raise ValueError(
            f"Fingerprints must have same length: {len(fp1_bytes)} vs {len(fp2_bytes)}"
        )

    # Count bits
    bits_a = sum(bin(b).count("1") for b in fp1_bytes)
    bits_b = sum(bin(b).count("1") for b in fp2_bytes)

    # Count common bits (AND operation)
    common_bits = sum(bin(a & b).count("1") for a, b in zip(fp1_bytes, fp2_bytes))

    # Tanimoto formula
    union_bits = bits_a + bits_b - common_bits
    if union_bits == 0:
        return 1.0  # Both fingerprints are empty, consider identical

    return common_bits / union_bits


def tanimoto_similarity(fp1: Fingerprint, fp2: Fingerprint) -> float:
    """
    Calculate Tanimoto similarity between two Fingerprint objects.

    Args:
        fp1: First fingerprint
        fp2: Second fingerprint

    Returns:
        Tanimoto similarity coefficient (0.0 to 1.0)
    """
    if fp1.fp_type != fp2.fp_type:
        raise ValueError(
            f"Fingerprint types must match: {fp1.fp_type} vs {fp2.fp_type}"
        )
    return tanimoto_similarity_bytes(fp1.bytes_data, fp2.bytes_data)


def dice_similarity_bytes(fp1_bytes: bytes, fp2_bytes: bytes) -> float:
    """
    Calculate Dice similarity between two fingerprints.

    Dice coefficient = 2 * |A ∩ B| / (|A| + |B|)

    Args:
        fp1_bytes: First fingerprint as bytes
        fp2_bytes: Second fingerprint as bytes

    Returns:
        Dice similarity coefficient (0.0 to 1.0)
    """
    if len(fp1_bytes) != len(fp2_bytes):
        raise ValueError(
            f"Fingerprints must have same length: {len(fp1_bytes)} vs {len(fp2_bytes)}"
        )

    bits_a = sum(bin(b).count("1") for b in fp1_bytes)
    bits_b = sum(bin(b).count("1") for b in fp2_bytes)
    common_bits = sum(bin(a & b).count("1") for a, b in zip(fp1_bytes, fp2_bytes))

    total_bits = bits_a + bits_b
    if total_bits == 0:
        return 1.0

    return (2 * common_bits) / total_bits


def dice_similarity(fp1: Fingerprint, fp2: Fingerprint) -> float:
    """
    Calculate Dice similarity between two Fingerprint objects.

    Args:
        fp1: First fingerprint
        fp2: Second fingerprint

    Returns:
        Dice similarity coefficient (0.0 to 1.0)
    """
    if fp1.fp_type != fp2.fp_type:
        raise ValueError(
            f"Fingerprint types must match: {fp1.fp_type} vs {fp2.fp_type}"
        )
    return dice_similarity_bytes(fp1.bytes_data, fp2.bytes_data)


def tanimoto_from_smiles(
    smiles1: str,
    smiles2: str,
    fp_type: FingerprintType = FingerprintType.MORGAN,
    **fp_kwargs,
) -> float:
    """
    Calculate Tanimoto similarity between two molecules given as SMILES.

    Args:
        smiles1: First SMILES string
        smiles2: Second SMILES string
        fp_type: Fingerprint type to use
        **fp_kwargs: Additional fingerprint parameters

    Returns:
        Tanimoto similarity coefficient (0.0 to 1.0)
    """
    fp1 = calculate_fingerprint(smiles1, fp_type, **fp_kwargs)
    fp2 = calculate_fingerprint(smiles2, fp_type, **fp_kwargs)
    return tanimoto_similarity(fp1, fp2)


def bulk_tanimoto(
    query: Fingerprint | str,
    targets: Sequence[Fingerprint | str],
    threshold: float = 0.0,
    fp_type: FingerprintType = FingerprintType.MORGAN,
    **fp_kwargs,
) -> list[tuple[int, float]]:
    """
    Calculate Tanimoto similarity of a query against multiple targets.

    Args:
        query: Query fingerprint or SMILES
        targets: List of target fingerprints or SMILES
        threshold: Minimum similarity threshold (0.0 to 1.0)
        fp_type: Fingerprint type (used if inputs are SMILES)
        **fp_kwargs: Additional fingerprint parameters

    Returns:
        List of (index, similarity) tuples for targets above threshold,
        sorted by similarity descending
    """
    # Convert query to fingerprint if needed
    if isinstance(query, str):
        query_fp = calculate_fingerprint(query, fp_type, **fp_kwargs)
    else:
        query_fp = query

    results = []
    for i, target in enumerate(targets):
        # Convert target to fingerprint if needed
        if isinstance(target, str):
            target_fp = calculate_fingerprint(target, fp_type, **fp_kwargs)
        else:
            target_fp = target

        sim = tanimoto_similarity(query_fp, target_fp)
        if sim >= threshold:
            results.append((i, sim))

    # Sort by similarity descending
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def similarity_matrix(
    molecules: Sequence[Fingerprint | str],
    fp_type: FingerprintType = FingerprintType.MORGAN,
    **fp_kwargs,
) -> list[list[float]]:
    """
    Calculate pairwise Tanimoto similarity matrix.

    Args:
        molecules: List of fingerprints or SMILES
        fp_type: Fingerprint type (used if inputs are SMILES)
        **fp_kwargs: Additional fingerprint parameters

    Returns:
        2D list where result[i][j] is similarity between molecule i and j
    """
    # Convert all to fingerprints
    fps = []
    for mol in molecules:
        if isinstance(mol, str):
            fps.append(calculate_fingerprint(mol, fp_type, **fp_kwargs))
        else:
            fps.append(mol)

    n = len(fps)
    matrix = [[0.0] * n for _ in range(n)]

    for i in range(n):
        matrix[i][i] = 1.0  # Self-similarity
        for j in range(i + 1, n):
            sim = tanimoto_similarity(fps[i], fps[j])
            matrix[i][j] = sim
            matrix[j][i] = sim  # Symmetric

    return matrix


def find_similar_molecules(
    query_smiles: str,
    database_smiles: list[str],
    threshold: float = 0.7,
    top_n: int | None = None,
    fp_type: FingerprintType = FingerprintType.MORGAN,
    **fp_kwargs,
) -> SimilaritySearchResult:
    """
    Search for similar molecules in a database.

    Args:
        query_smiles: Query molecule SMILES
        database_smiles: List of database molecule SMILES
        threshold: Minimum similarity threshold
        top_n: Maximum number of results (None = all above threshold)
        fp_type: Fingerprint type to use
        **fp_kwargs: Additional fingerprint parameters

    Returns:
        SimilaritySearchResult with matches
    """
    query_fp = calculate_fingerprint(query_smiles, fp_type, **fp_kwargs)

    matches = bulk_tanimoto(
        query_fp,
        database_smiles,
        threshold=threshold,
        fp_type=fp_type,
        **fp_kwargs,
    )

    if top_n is not None:
        matches = matches[:top_n]

    return SimilaritySearchResult(
        query_smiles=query_smiles,
        matches=matches,
        fp_type=fp_type,
        threshold=threshold,
    )


def cluster_by_similarity(
    molecules: list[str],
    threshold: float = 0.7,
    fp_type: FingerprintType = FingerprintType.MORGAN,
    **fp_kwargs,
) -> list[list[int]]:
    """
    Cluster molecules by Tanimoto similarity using single-linkage clustering.

    Args:
        molecules: List of SMILES strings
        threshold: Similarity threshold for clustering
        fp_type: Fingerprint type to use
        **fp_kwargs: Additional fingerprint parameters

    Returns:
        List of clusters, where each cluster is a list of molecule indices
    """
    # Calculate fingerprints
    fps = [calculate_fingerprint(s, fp_type, **fp_kwargs) for s in molecules]
    n = len(fps)

    # Track which molecules have been assigned to clusters
    assigned = [False] * n
    clusters = []

    for i in range(n):
        if assigned[i]:
            continue

        # Start new cluster with this molecule
        cluster = [i]
        assigned[i] = True

        # Find all molecules similar to any member of this cluster
        j = 0
        while j < len(cluster):
            current = cluster[j]
            for k in range(n):
                if not assigned[k]:
                    sim = tanimoto_similarity(fps[current], fps[k])
                    if sim >= threshold:
                        cluster.append(k)
                        assigned[k] = True
            j += 1

        clusters.append(sorted(cluster))

    return clusters


class FingerprintIndex:
    """
    In-memory index for fast similarity search.

    This is a simple implementation for testing. For production use,
    consider specialized libraries like chemfp or database extensions.
    """

    def __init__(
        self,
        fp_type: FingerprintType = FingerprintType.MORGAN,
        **fp_kwargs,
    ):
        self.fp_type = fp_type
        self.fp_kwargs = fp_kwargs
        self._fingerprints: list[Fingerprint] = []
        self._smiles: list[str] = []
        self._ids: list[str | int] = []

    def add(self, smiles: str, mol_id: str | int | None = None) -> int:
        """
        Add a molecule to the index.

        Args:
            smiles: SMILES string
            mol_id: Optional identifier

        Returns:
            Index of added molecule
        """
        fp = calculate_fingerprint(smiles, self.fp_type, **self.fp_kwargs)
        idx = len(self._fingerprints)
        self._fingerprints.append(fp)
        self._smiles.append(smiles)
        self._ids.append(mol_id if mol_id is not None else idx)
        return idx

    def add_many(
        self, smiles_list: list[str], ids: list[str | int] | None = None
    ) -> list[int]:
        """Add multiple molecules to the index."""
        if ids is None:
            ids = [None] * len(smiles_list)  # type: ignore
        return [self.add(s, i) for s, i in zip(smiles_list, ids)]

    def search(
        self,
        query_smiles: str,
        threshold: float = 0.7,
        top_n: int | None = None,
    ) -> list[tuple[str | int, str, float]]:
        """
        Search for similar molecules.

        Args:
            query_smiles: Query SMILES
            threshold: Minimum similarity
            top_n: Maximum results

        Returns:
            List of (id, smiles, similarity) tuples
        """
        query_fp = calculate_fingerprint(
            query_smiles, self.fp_type, **self.fp_kwargs
        )

        results = []
        for i, fp in enumerate(self._fingerprints):
            sim = tanimoto_similarity(query_fp, fp)
            if sim >= threshold:
                results.append((self._ids[i], self._smiles[i], sim))

        results.sort(key=lambda x: x[2], reverse=True)
        if top_n is not None:
            results = results[:top_n]

        return results

    def __len__(self) -> int:
        return len(self._fingerprints)
