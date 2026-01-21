# Molecular Fingerprint Indexing Strategy

This document describes the fingerprint storage and similarity search architecture
for the AI Drug Discovery platform.

## Overview

Molecular similarity search is a core capability for drug discovery workflows:
- Finding analogs of hit compounds
- Clustering chemical libraries
- Identifying potential activity cliffs
- Virtual screening

The platform supports three indexing strategies with different tradeoffs.

## Storage Architecture

### Inline Storage (molecules table)

For quick access, fingerprints are stored directly on the `molecules` table:

```sql
fingerprint_morgan  BYTEA  -- Morgan/ECFP (2048 bits, radius 2)
fingerprint_maccs   BYTEA  -- MACCS keys (167 bits)
fingerprint_rdkit   BYTEA  -- RDKit topological (2048 bits)
```

**Use cases:**
- Exact fingerprint retrieval for a known molecule
- Small-scale similarity calculations (<1000 molecules)
- Exporting fingerprints via API

### Extended Storage (molecule_fingerprints table)

For flexibility and external index integration:

```sql
molecule_fingerprints
├── molecule_id         UUID FK
├── fingerprint_type    VARCHAR(50)    -- 'morgan', 'maccs', 'rdkit', etc.
├── fingerprint_bytes   BYTEA          -- Raw binary
├── fingerprint_base64  TEXT           -- For JSON APIs
├── fingerprint_hex     TEXT           -- For debugging
├── num_bits           SMALLINT        -- e.g., 2048
├── radius             SMALLINT        -- For Morgan (2=ECFP4, 3=ECFP6)
├── use_features       BOOLEAN         -- ECFP vs FCFP
├── num_on_bits        SMALLINT        -- Density metric
├── external_index_id  VARCHAR(255)    -- Pinecone/Milvus vector ID
└── external_index_synced_at TIMESTAMP
```

**Use cases:**
- Storing multiple fingerprint variants
- Tracking generation parameters for reproducibility
- Syncing with external vector databases

## Indexing Strategies

### Strategy 1: PostgreSQL pg_similarity / RDKit Cartridge

**Setup:**
```sql
-- Install RDKit PostgreSQL extension
CREATE EXTENSION IF NOT EXISTS rdkit;

-- Create GiST index on fingerprint column
CREATE INDEX idx_mol_morgan_gist ON molecules
    USING gist(fingerprint_morgan gist_bfp_ops);
```

**Query:**
```sql
-- Find molecules with Tanimoto > 0.7
SELECT id, canonical_smiles,
       tanimoto_sml(fingerprint_morgan, :query_fp) as similarity
FROM molecules
WHERE fingerprint_morgan % :query_fp  -- Uses GiST index
  AND tanimoto_sml(fingerprint_morgan, :query_fp) > 0.7
ORDER BY fingerprint_morgan <%> :query_fp  -- Distance operator
LIMIT 100;
```

**Tradeoffs:**

| Pros | Cons |
|------|------|
| Native PostgreSQL, no external services | Requires RDKit extension installation |
| Exact Tanimoto calculation | Complex extension compilation |
| Transactional consistency | Limited scalability (~500K-1M molecules) |
| No network latency | O(n) without proper indexing |

**Best for:** Small-medium datasets (<500K molecules), on-premise deployments

### Strategy 2: PostgreSQL pgvector

**Setup:**
```sql
-- Install pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add vector column (convert binary to float)
ALTER TABLE molecule_fingerprints
    ADD COLUMN fingerprint_vector vector(2048);

-- Create IVFFlat index (good balance of speed/accuracy)
CREATE INDEX idx_fp_vector_ivf ON molecule_fingerprints
    USING ivfflat (fingerprint_vector vector_cosine_ops)
    WITH (lists = 100);

-- Or HNSW index (faster queries, more memory)
CREATE INDEX idx_fp_vector_hnsw ON molecule_fingerprints
    USING hnsw (fingerprint_vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

**Query:**
```sql
-- Convert query fingerprint to vector and search
SELECT molecule_id,
       1 - (fingerprint_vector <=> :query_vector) as similarity
FROM molecule_fingerprints
WHERE fingerprint_type = 'morgan'
ORDER BY fingerprint_vector <=> :query_vector
LIMIT 100;
```

**Tradeoffs:**

| Pros | Cons |
|------|------|
| Simple extension installation | Approximate results (may miss some) |
| Good scalability (~5M molecules) | Binary→float conversion loses precision |
| IVFFlat/HNSW approximate search | Cosine ≈ Tanimoto only for normalized vectors |
| Native PostgreSQL | Requires index parameter tuning |

**Best for:** Medium datasets (100K-5M molecules), cloud PostgreSQL (Supabase, Neon)

### Strategy 3: External Vector Database (Pinecone)

**Setup:**
```python
import pinecone

pinecone.init(api_key="...", environment="us-east1-gcp")
pinecone.create_index(
    "molecules",
    dimension=2048,
    metric="cosine",
    pod_type="s1.x1"  # or p1 for higher throughput
)
```

**Usage:**
```python
from packages.chemistry.fingerprint_index import PineconeFingerprintIndex

index = PineconeFingerprintIndex(
    api_key="...",
    environment="us-east1-gcp",
    index_name="molecules"
)

# Index a molecule
await index.index_molecule(molecule_id, fingerprint_bytes, "morgan")

# Search
results = await index.search_similar(
    query_fingerprint,
    threshold=0.7,
    limit=100
)
```

**Tradeoffs:**

| Pros | Cons |
|------|------|
| Highly scalable (10M+ molecules) | External dependency |
| Managed service, no infra | Network latency (~10-50ms) |
| Tunable recall/speed | Additional cost |
| Multiple index types | Eventual consistency with PostgreSQL |

**Best for:** Large datasets (>1M molecules), cloud-native architecture

## Recommendation Matrix

| Dataset Size | Recommended Strategy | Estimated Query Time |
|-------------|---------------------|---------------------|
| < 10K | In-memory (Python) | < 10ms |
| 10K - 100K | PostgreSQL + Python Tanimoto | 50-200ms |
| 100K - 1M | pgvector (IVFFlat) | 10-50ms |
| 1M - 10M | pgvector (HNSW) or Pinecone | 10-30ms |
| > 10M | Pinecone or Milvus | 10-30ms |

## Implementation Notes

### Binary to Vector Conversion

For pgvector and Pinecone, binary fingerprints must be converted to float vectors:

```python
def fingerprint_to_vector(fp_bytes: bytes) -> list[float]:
    """Convert fingerprint bytes to normalized float vector."""
    bits = []
    for byte in fp_bytes:
        for i in range(8):
            bits.append(1.0 if (byte >> i) & 1 else 0.0)

    # Normalize to unit length (required for cosine similarity)
    norm = sum(b * b for b in bits) ** 0.5
    if norm > 0:
        bits = [b / norm for b in bits]

    return bits
```

### Tanimoto vs Cosine Similarity

For binary fingerprints:
- **Tanimoto**: |A ∩ B| / |A ∪ B|
- **Cosine**: A · B / (|A| × |B|)

For normalized binary vectors, cosine similarity approximates Tanimoto but is not identical.
The correlation is typically > 0.95 for drug-like molecules.

### Sync Strategy for External Indexes

When using Pinecone, maintain sync with PostgreSQL:

```python
# On molecule insert/update
async def sync_fingerprint(molecule_id, fp_bytes, fp_type):
    # 1. Store in PostgreSQL
    await repo.store_fingerprint(molecule_id, fp_bytes, fp_type)

    # 2. Sync to Pinecone (async, can be queued)
    await pinecone_index.index_molecule(molecule_id, fp_bytes, fp_type)

    # 3. Update sync timestamp
    await repo.update_sync_timestamp(molecule_id, fp_type)
```

Consider using a message queue (Redis, RabbitMQ) for reliable sync.

## Files

- `db/models/discovery.py` - Molecule and MoleculeFingerprint models
- `packages/chemistry/fingerprint_index.py` - Index adapter interfaces
- `packages/chemistry/molecule_repository.py` - Repository with upsert
- `alembic/versions/*_add_fingerprint_storage.py` - Migration

## Future Enhancements

1. **Substructure Search**: Add RDKit cartridge for SMARTS-based substructure queries
2. **Scaffold Clustering**: Implement Murcko scaffold extraction and clustering
3. **Activity Cliffs**: Detect structurally similar molecules with different activity
4. **Diversity Selection**: MaxMin or clustering-based diverse subset selection
