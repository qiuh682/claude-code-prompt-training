"""
Fingerprint Index Adapters for Molecular Similarity Search.

This module provides abstract interfaces and concrete implementations for
storing and searching molecular fingerprints using different backends:

1. PostgreSQL (pg_similarity / RDKit cartridge)
   - Uses BIT columns and Tanimoto operators from RDKit extension
   - Good for small-medium datasets (<1M molecules)
   - No external dependencies beyond PostgreSQL

2. PostgreSQL with pgvector
   - Converts fingerprints to float vectors
   - Uses IVFFlat or HNSW indexes for approximate nearest neighbor
   - Better scalability than raw BIT operations

3. Pinecone (external vector database)
   - Cloud-hosted vector similarity search
   - Best for large datasets (>1M molecules)
   - Requires API key and network access

INDEXING TRADEOFFS:
==================

PostgreSQL pg_similarity / RDKit Cartridge:
+ Native PostgreSQL, no external services
+ Exact Tanimoto calculation
+ Transactional consistency
- Requires RDKit PostgreSQL extension (installation can be complex)
- O(n) scan for similarity search without GiST index
- Limited scalability (practical limit ~500K-1M molecules)

PostgreSQL pgvector:
+ Native PostgreSQL with simple extension
+ Approximate nearest neighbor with IVFFlat/HNSW
+ Better scalability than pg_similarity (~5M molecules)
- Converts binary fingerprints to float vectors (some precision loss)
- Approximate results (may miss some similar molecules)
- Requires tuning index parameters (lists, probes)

Pinecone / External Vector DB:
+ Highly scalable (10M+ molecules)
+ Managed service, no infrastructure overhead
+ Fast approximate search with tunable recall
- External dependency and network latency
- Additional cost (Pinecone pricing)
- Eventual consistency with main database
- Requires sync mechanism to keep fingerprints up to date

RECOMMENDATION:
- < 100K molecules: PostgreSQL with simple BYTEA and in-memory search
- 100K - 1M molecules: PostgreSQL with pgvector (IVFFlat index)
- > 1M molecules: Pinecone or similar vector database

Usage:
    # PostgreSQL adapter (in-memory search for small datasets)
    adapter = PostgresFingerprintIndex(session)
    await adapter.index_molecule(molecule_id, fingerprint_bytes)
    results = await adapter.search_similar(query_fp, threshold=0.7, limit=100)

    # Pinecone adapter
    adapter = PineconeFingerprintIndex(api_key="...", index_name="molecules")
    await adapter.index_molecule(molecule_id, fingerprint_bytes)
    results = await adapter.search_similar(query_fp, threshold=0.7, limit=100)
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, Sequence
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class SimilarityMatch:
    """Result of a similarity search."""

    molecule_id: UUID
    similarity: float  # Tanimoto coefficient (0.0 - 1.0)
    fingerprint_type: str


@dataclass(frozen=True)
class IndexStats:
    """Statistics about the fingerprint index."""

    total_indexed: int
    fingerprint_type: str
    last_updated: datetime | None
    backend: str
    metadata: dict[str, Any]


class FingerprintIndexAdapter(ABC):
    """
    Abstract interface for fingerprint similarity search backends.

    Implementations should provide:
    - index_molecule: Add/update a molecule's fingerprint in the index
    - remove_molecule: Remove a molecule from the index
    - search_similar: Find molecules similar to a query fingerprint
    - bulk_index: Efficiently index multiple molecules
    - get_stats: Return index statistics
    """

    @abstractmethod
    async def index_molecule(
        self,
        molecule_id: UUID,
        fingerprint_bytes: bytes,
        fingerprint_type: str = "morgan",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Add or update a molecule's fingerprint in the index.

        Args:
            molecule_id: Unique molecule identifier
            fingerprint_bytes: Raw fingerprint bytes
            fingerprint_type: Type of fingerprint (morgan, maccs, rdkit)
            metadata: Optional metadata to store with the fingerprint

        Returns:
            True if indexed successfully
        """
        pass

    @abstractmethod
    async def remove_molecule(
        self,
        molecule_id: UUID,
        fingerprint_type: str = "morgan",
    ) -> bool:
        """
        Remove a molecule from the index.

        Args:
            molecule_id: Unique molecule identifier
            fingerprint_type: Type of fingerprint to remove

        Returns:
            True if removed successfully
        """
        pass

    @abstractmethod
    async def search_similar(
        self,
        query_fingerprint: bytes,
        fingerprint_type: str = "morgan",
        threshold: float = 0.7,
        limit: int = 100,
        exclude_ids: Sequence[UUID] | None = None,
    ) -> list[SimilarityMatch]:
        """
        Search for molecules similar to the query fingerprint.

        Args:
            query_fingerprint: Query fingerprint bytes
            fingerprint_type: Type of fingerprint to search
            threshold: Minimum Tanimoto similarity (0.0 - 1.0)
            limit: Maximum number of results
            exclude_ids: Molecule IDs to exclude from results

        Returns:
            List of SimilarityMatch sorted by similarity descending
        """
        pass

    @abstractmethod
    async def bulk_index(
        self,
        molecules: Sequence[tuple[UUID, bytes]],
        fingerprint_type: str = "morgan",
    ) -> int:
        """
        Efficiently index multiple molecules.

        Args:
            molecules: Sequence of (molecule_id, fingerprint_bytes) tuples
            fingerprint_type: Type of fingerprint

        Returns:
            Number of molecules successfully indexed
        """
        pass

    @abstractmethod
    async def get_stats(self, fingerprint_type: str = "morgan") -> IndexStats:
        """Get statistics about the index."""
        pass


def _tanimoto_from_bytes(fp1: bytes, fp2: bytes) -> float:
    """Calculate Tanimoto similarity between two fingerprints."""
    if len(fp1) != len(fp2):
        raise ValueError(f"Fingerprint length mismatch: {len(fp1)} vs {len(fp2)}")

    bits_a = sum(bin(b).count("1") for b in fp1)
    bits_b = sum(bin(b).count("1") for b in fp2)
    common = sum(bin(a & b).count("1") for a, b in zip(fp1, fp2))

    union = bits_a + bits_b - common
    if union == 0:
        return 1.0
    return common / union


class PostgresFingerprintIndex(FingerprintIndexAdapter):
    """
    PostgreSQL-based fingerprint index using in-memory Tanimoto calculation.

    This is a simple implementation that stores fingerprints in the
    molecule_fingerprints table and performs similarity search by
    scanning and computing Tanimoto coefficients in Python.

    For production with >100K molecules, consider:
    - Adding RDKit cartridge for native BIT Tanimoto operators
    - Using pgvector extension for approximate nearest neighbor
    - Moving to Pinecone or similar vector database

    The PostgreSQL RDKit cartridge provides:
    - mol and fp data types
    - tanimoto_sml() and dice_sml() functions
    - GiST indexes for similarity search

    Example SQL with RDKit cartridge (not implemented here):
        CREATE INDEX idx_mol_morgan ON molecule_fingerprints
            USING gist(fingerprint_bytes gist_bfp_ops);

        SELECT molecule_id, tanimoto_sml(fingerprint_bytes, :query_fp) as sim
        FROM molecule_fingerprints
        WHERE fingerprint_bytes % :query_fp  -- uses GiST index
        ORDER BY sim DESC
        LIMIT 100;
    """

    def __init__(self, session: "AsyncSession"):
        self.session = session
        self._cache: dict[str, dict[UUID, bytes]] = {}

    async def index_molecule(
        self,
        molecule_id: UUID,
        fingerprint_bytes: bytes,
        fingerprint_type: str = "morgan",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Add fingerprint to the molecule_fingerprints table."""
        from sqlalchemy import select, update
        from sqlalchemy.dialects.postgresql import insert

        from db.models import MoleculeFingerprint

        # Upsert fingerprint
        stmt = insert(MoleculeFingerprint).values(
            molecule_id=molecule_id,
            fingerprint_type=fingerprint_type,
            fingerprint_bytes=fingerprint_bytes,
            fingerprint_base64=base64.b64encode(fingerprint_bytes).decode("ascii"),
            fingerprint_hex=fingerprint_bytes.hex(),
            num_bits=len(fingerprint_bytes) * 8,
            num_on_bits=sum(bin(b).count("1") for b in fingerprint_bytes),
            radius=metadata.get("radius") if metadata else None,
            use_features=metadata.get("use_features", False) if metadata else False,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_molecule_fingerprint_type",
            set_={
                "fingerprint_bytes": fingerprint_bytes,
                "fingerprint_base64": base64.b64encode(fingerprint_bytes).decode("ascii"),
                "fingerprint_hex": fingerprint_bytes.hex(),
                "num_on_bits": sum(bin(b).count("1") for b in fingerprint_bytes),
                "updated_at": datetime.utcnow(),
            },
        )
        await self.session.execute(stmt)

        # Invalidate cache
        if fingerprint_type in self._cache:
            self._cache[fingerprint_type][molecule_id] = fingerprint_bytes

        return True

    async def remove_molecule(
        self,
        molecule_id: UUID,
        fingerprint_type: str = "morgan",
    ) -> bool:
        """Remove fingerprint from the table."""
        from sqlalchemy import delete

        from db.models import MoleculeFingerprint

        stmt = delete(MoleculeFingerprint).where(
            MoleculeFingerprint.molecule_id == molecule_id,
            MoleculeFingerprint.fingerprint_type == fingerprint_type,
        )
        result = await self.session.execute(stmt)

        # Invalidate cache
        if fingerprint_type in self._cache:
            self._cache[fingerprint_type].pop(molecule_id, None)

        return result.rowcount > 0

    async def search_similar(
        self,
        query_fingerprint: bytes,
        fingerprint_type: str = "morgan",
        threshold: float = 0.7,
        limit: int = 100,
        exclude_ids: Sequence[UUID] | None = None,
    ) -> list[SimilarityMatch]:
        """
        Search for similar fingerprints using in-memory Tanimoto calculation.

        Note: For large datasets, this scans all fingerprints. Consider using
        RDKit cartridge or pgvector for better performance.
        """
        from sqlalchemy import select

        from db.models import MoleculeFingerprint

        # Load fingerprints (with caching for repeated searches)
        if fingerprint_type not in self._cache:
            stmt = select(
                MoleculeFingerprint.molecule_id,
                MoleculeFingerprint.fingerprint_bytes,
            ).where(MoleculeFingerprint.fingerprint_type == fingerprint_type)

            result = await self.session.execute(stmt)
            self._cache[fingerprint_type] = {
                row.molecule_id: row.fingerprint_bytes for row in result.fetchall()
            }

        # Calculate similarities
        exclude_set = set(exclude_ids) if exclude_ids else set()
        matches = []

        for mol_id, fp_bytes in self._cache[fingerprint_type].items():
            if mol_id in exclude_set:
                continue

            try:
                sim = _tanimoto_from_bytes(query_fingerprint, fp_bytes)
                if sim >= threshold:
                    matches.append(SimilarityMatch(
                        molecule_id=mol_id,
                        similarity=sim,
                        fingerprint_type=fingerprint_type,
                    ))
            except ValueError:
                # Skip fingerprints with mismatched length
                continue

        # Sort by similarity descending and limit
        matches.sort(key=lambda m: m.similarity, reverse=True)
        return matches[:limit]

    async def bulk_index(
        self,
        molecules: Sequence[tuple[UUID, bytes]],
        fingerprint_type: str = "morgan",
    ) -> int:
        """Bulk insert fingerprints."""
        from sqlalchemy.dialects.postgresql import insert

        from db.models import MoleculeFingerprint

        if not molecules:
            return 0

        values = [
            {
                "molecule_id": mol_id,
                "fingerprint_type": fingerprint_type,
                "fingerprint_bytes": fp_bytes,
                "fingerprint_base64": base64.b64encode(fp_bytes).decode("ascii"),
                "fingerprint_hex": fp_bytes.hex(),
                "num_bits": len(fp_bytes) * 8,
                "num_on_bits": sum(bin(b).count("1") for b in fp_bytes),
                "use_features": False,
            }
            for mol_id, fp_bytes in molecules
        ]

        stmt = insert(MoleculeFingerprint).values(values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_molecule_fingerprint_type",
            set_={
                "fingerprint_bytes": stmt.excluded.fingerprint_bytes,
                "fingerprint_base64": stmt.excluded.fingerprint_base64,
                "num_on_bits": stmt.excluded.num_on_bits,
                "updated_at": datetime.utcnow(),
            },
        )
        await self.session.execute(stmt)

        # Invalidate cache
        self._cache.pop(fingerprint_type, None)

        return len(molecules)

    async def get_stats(self, fingerprint_type: str = "morgan") -> IndexStats:
        """Get index statistics."""
        from sqlalchemy import func, select

        from db.models import MoleculeFingerprint

        stmt = select(
            func.count(MoleculeFingerprint.id),
            func.max(MoleculeFingerprint.updated_at),
        ).where(MoleculeFingerprint.fingerprint_type == fingerprint_type)

        result = await self.session.execute(stmt)
        row = result.fetchone()

        return IndexStats(
            total_indexed=row[0] if row else 0,
            fingerprint_type=fingerprint_type,
            last_updated=row[1] if row else None,
            backend="postgresql",
            metadata={"cache_size": len(self._cache.get(fingerprint_type, {}))},
        )

    def clear_cache(self) -> None:
        """Clear the fingerprint cache."""
        self._cache.clear()


class PineconeFingerprintIndex(FingerprintIndexAdapter):
    """
    Pinecone-based fingerprint index for large-scale similarity search.

    This is a placeholder implementation. To use Pinecone:
    1. Install pinecone-client: pip install pinecone-client
    2. Create a Pinecone index with appropriate dimensions
    3. Set PINECONE_API_KEY and PINECONE_ENVIRONMENT

    Pinecone Configuration:
    - Dimension: Typically 2048 for Morgan fingerprints
    - Metric: "cosine" (approximates Tanimoto for normalized vectors)
    - Pod type: s1 or p1 depending on scale and budget

    Converting fingerprints to vectors:
    - Binary fingerprints are converted to float vectors [0.0, 1.0]
    - Normalize to unit length for cosine similarity
    - Cosine on normalized binary vectors approximates Tanimoto

    Example Pinecone setup:
        import pinecone
        pinecone.init(api_key="...", environment="...")
        pinecone.create_index(
            "molecules",
            dimension=2048,
            metric="cosine",
            pod_type="s1.x1"
        )
    """

    def __init__(
        self,
        api_key: str | None = None,
        environment: str | None = None,
        index_name: str = "molecules",
    ):
        self.api_key = api_key
        self.environment = environment
        self.index_name = index_name
        self._index = None

        # Placeholder - real implementation would initialize Pinecone
        if api_key and environment:
            self._init_pinecone()

    def _init_pinecone(self) -> None:
        """Initialize Pinecone connection."""
        # Placeholder - would do:
        # import pinecone
        # pinecone.init(api_key=self.api_key, environment=self.environment)
        # self._index = pinecone.Index(self.index_name)
        pass

    def _fp_to_vector(self, fp_bytes: bytes) -> list[float]:
        """Convert fingerprint bytes to float vector."""
        # Expand bytes to bits, normalize
        bits = []
        for byte in fp_bytes:
            for i in range(8):
                bits.append(1.0 if (byte >> i) & 1 else 0.0)
        # Normalize to unit length
        norm = sum(b * b for b in bits) ** 0.5
        if norm > 0:
            bits = [b / norm for b in bits]
        return bits

    async def index_molecule(
        self,
        molecule_id: UUID,
        fingerprint_bytes: bytes,
        fingerprint_type: str = "morgan",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Add fingerprint to Pinecone index."""
        if not self._index:
            raise RuntimeError("Pinecone not initialized. Provide api_key and environment.")

        vector = self._fp_to_vector(fingerprint_bytes)
        meta = {
            "fingerprint_type": fingerprint_type,
            **(metadata or {}),
        }

        # Placeholder - would do:
        # self._index.upsert(vectors=[
        #     (str(molecule_id), vector, meta)
        # ])

        return True

    async def remove_molecule(
        self,
        molecule_id: UUID,
        fingerprint_type: str = "morgan",
    ) -> bool:
        """Remove molecule from Pinecone index."""
        if not self._index:
            raise RuntimeError("Pinecone not initialized.")

        # Placeholder - would do:
        # self._index.delete(ids=[str(molecule_id)])

        return True

    async def search_similar(
        self,
        query_fingerprint: bytes,
        fingerprint_type: str = "morgan",
        threshold: float = 0.7,
        limit: int = 100,
        exclude_ids: Sequence[UUID] | None = None,
    ) -> list[SimilarityMatch]:
        """Search Pinecone for similar fingerprints."""
        if not self._index:
            raise RuntimeError("Pinecone not initialized.")

        vector = self._fp_to_vector(query_fingerprint)

        # Placeholder - would do:
        # results = self._index.query(
        #     vector=vector,
        #     top_k=limit,
        #     filter={"fingerprint_type": fingerprint_type},
        #     include_metadata=True,
        # )
        # matches = [
        #     SimilarityMatch(
        #         molecule_id=UUID(m.id),
        #         similarity=m.score,  # cosine similarity
        #         fingerprint_type=fingerprint_type,
        #     )
        #     for m in results.matches
        #     if m.score >= threshold
        # ]

        return []

    async def bulk_index(
        self,
        molecules: Sequence[tuple[UUID, bytes]],
        fingerprint_type: str = "morgan",
    ) -> int:
        """Bulk upsert to Pinecone."""
        if not self._index:
            raise RuntimeError("Pinecone not initialized.")

        # Placeholder - would batch upsert:
        # vectors = [
        #     (str(mol_id), self._fp_to_vector(fp), {"fingerprint_type": fingerprint_type})
        #     for mol_id, fp in molecules
        # ]
        # for batch in chunks(vectors, 100):
        #     self._index.upsert(vectors=batch)

        return len(molecules)

    async def get_stats(self, fingerprint_type: str = "morgan") -> IndexStats:
        """Get Pinecone index statistics."""
        # Placeholder - would do:
        # stats = self._index.describe_index_stats()

        return IndexStats(
            total_indexed=0,
            fingerprint_type=fingerprint_type,
            last_updated=None,
            backend="pinecone",
            metadata={"index_name": self.index_name},
        )


def get_fingerprint_index(
    backend: str,
    session: "AsyncSession | None" = None,
    **kwargs,
) -> FingerprintIndexAdapter:
    """
    Factory function to get appropriate fingerprint index adapter.

    Args:
        backend: "postgres" or "pinecone"
        session: SQLAlchemy async session (required for postgres)
        **kwargs: Backend-specific configuration

    Returns:
        Configured FingerprintIndexAdapter
    """
    if backend == "postgres":
        if session is None:
            raise ValueError("PostgreSQL backend requires session parameter")
        return PostgresFingerprintIndex(session)
    elif backend == "pinecone":
        return PineconeFingerprintIndex(
            api_key=kwargs.get("api_key"),
            environment=kwargs.get("environment"),
            index_name=kwargs.get("index_name", "molecules"),
        )
    else:
        raise ValueError(f"Unknown backend: {backend}. Use 'postgres' or 'pinecone'")
