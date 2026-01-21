"""Add fingerprint storage and extended descriptors

Adds:
- Extended descriptor columns to molecules table (num_rings, num_aromatic_rings,
  num_heavy_atoms, fraction_sp3, lipinski_violations)
- fingerprint_rdkit column to molecules table
- molecule_fingerprints table for detailed fingerprint storage with metadata
- Indexes for similarity search preparation

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-21 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6g7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    # ==========================================================================
    # ADD EXTENDED DESCRIPTOR COLUMNS TO MOLECULES
    # ==========================================================================
    op.add_column(
        "molecules",
        sa.Column(
            "num_rings",
            sa.SmallInteger(),
            nullable=True,
            comment="Total ring count",
        ),
    )
    op.add_column(
        "molecules",
        sa.Column(
            "num_aromatic_rings",
            sa.SmallInteger(),
            nullable=True,
            comment="Aromatic ring count",
        ),
    )
    op.add_column(
        "molecules",
        sa.Column(
            "num_heavy_atoms",
            sa.SmallInteger(),
            nullable=True,
            comment="Heavy atom count (non-hydrogen)",
        ),
    )
    op.add_column(
        "molecules",
        sa.Column(
            "fraction_sp3",
            sa.Numeric(precision=5, scale=4),
            nullable=True,
            comment="Fraction of sp3 carbons (0.0000-1.0000)",
        ),
    )
    op.add_column(
        "molecules",
        sa.Column(
            "lipinski_violations",
            sa.SmallInteger(),
            nullable=True,
            comment="Number of Lipinski Rule of 5 violations (0-4)",
        ),
    )

    # ==========================================================================
    # ADD RDKIT FINGERPRINT COLUMN TO MOLECULES
    # ==========================================================================
    op.add_column(
        "molecules",
        sa.Column(
            "fingerprint_rdkit",
            sa.LargeBinary(),
            nullable=True,
            comment="RDKit topological fingerprint (2048 bits)",
        ),
    )

    # Update comment on existing fingerprint columns for clarity
    # (This is informational - actual column comments would need ALTER COLUMN)

    # ==========================================================================
    # CREATE MOLECULE_FINGERPRINTS TABLE
    # ==========================================================================
    op.create_table(
        "molecule_fingerprints",
        # Primary key
        sa.Column("id", sa.UUID(), nullable=False),
        # Foreign key to molecule
        sa.Column("molecule_id", sa.UUID(), nullable=False),
        # Fingerprint type
        sa.Column(
            "fingerprint_type",
            sa.String(length=50),
            nullable=False,
            comment="morgan, maccs, rdkit, ecfp4, fcfp4, etc.",
        ),
        # Fingerprint data
        sa.Column(
            "fingerprint_bytes",
            sa.LargeBinary(),
            nullable=False,
            comment="Raw fingerprint bytes",
        ),
        sa.Column(
            "fingerprint_base64",
            sa.Text(),
            nullable=True,
            comment="Base64 encoded for JSON APIs",
        ),
        sa.Column(
            "fingerprint_hex",
            sa.Text(),
            nullable=True,
            comment="Hex encoded for debugging",
        ),
        # Generation parameters
        sa.Column(
            "num_bits",
            sa.SmallInteger(),
            nullable=False,
            comment="Number of bits in fingerprint",
        ),
        sa.Column(
            "radius",
            sa.SmallInteger(),
            nullable=True,
            comment="Radius for circular fingerprints (Morgan)",
        ),
        sa.Column(
            "use_features",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Feature-based (FCFP) vs atom-based (ECFP)",
        ),
        # Statistics
        sa.Column(
            "num_on_bits",
            sa.SmallInteger(),
            nullable=True,
            comment="Number of bits set to 1",
        ),
        # External index reference
        sa.Column(
            "external_index_id",
            sa.String(length=255),
            nullable=True,
            comment="ID in external vector DB (e.g., Pinecone vector ID)",
        ),
        sa.Column(
            "external_index_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When last synced to external index",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["molecule_id"], ["molecules.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "molecule_id", "fingerprint_type", name="uq_molecule_fingerprint_type"
        ),
        comment="Molecular fingerprints for similarity search",
    )

    # Indexes for molecule_fingerprints
    op.create_index(
        "ix_molecule_fp_molecule_id",
        "molecule_fingerprints",
        ["molecule_id"],
    )
    op.create_index(
        "ix_molecule_fp_type",
        "molecule_fingerprints",
        ["fingerprint_type"],
    )
    op.create_index(
        "ix_molecule_fp_external_id",
        "molecule_fingerprints",
        ["external_index_id"],
    )

    # ==========================================================================
    # FINGERPRINT INDEX PLACEHOLDERS
    # ==========================================================================
    # Note: Actual fingerprint similarity indexes require extensions.
    #
    # Option 1: PostgreSQL RDKit Cartridge
    # ------------------------------------
    # Requires installing RDKit PostgreSQL extension:
    #   CREATE EXTENSION IF NOT EXISTS rdkit;
    #
    # Then create GiST index:
    #   CREATE INDEX idx_mol_morgan_gist ON molecules
    #       USING gist(fingerprint_morgan gist_bfp_ops);
    #
    # Query with:
    #   SELECT id, tanimoto_sml(fingerprint_morgan, :query_fp) as sim
    #   FROM molecules
    #   WHERE fingerprint_morgan % :query_fp
    #   ORDER BY fingerprint_morgan <%> :query_fp
    #   LIMIT 100;
    #
    # Option 2: pgvector Extension
    # ----------------------------
    # Requires installing pgvector:
    #   CREATE EXTENSION IF NOT EXISTS vector;
    #
    # Add vector column (convert binary fingerprint to float vector):
    #   ALTER TABLE molecule_fingerprints
    #       ADD COLUMN fingerprint_vector vector(2048);
    #
    # Create IVFFlat or HNSW index:
    #   CREATE INDEX idx_fp_vector_ivf ON molecule_fingerprints
    #       USING ivfflat (fingerprint_vector vector_cosine_ops)
    #       WITH (lists = 100);
    #
    # Option 3: External Vector DB (Pinecone, Milvus, Weaviate)
    # ---------------------------------------------------------
    # Store fingerprints in molecule_fingerprints table.
    # Sync to external vector DB using external_index_id.
    # See packages/chemistry/fingerprint_index.py for adapter interface.
    #
    # ==========================================================================


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop molecule_fingerprints table
    op.drop_index("ix_molecule_fp_external_id", table_name="molecule_fingerprints")
    op.drop_index("ix_molecule_fp_type", table_name="molecule_fingerprints")
    op.drop_index("ix_molecule_fp_molecule_id", table_name="molecule_fingerprints")
    op.drop_table("molecule_fingerprints")

    # Remove columns from molecules
    op.drop_column("molecules", "fingerprint_rdkit")
    op.drop_column("molecules", "lipinski_violations")
    op.drop_column("molecules", "fraction_sp3")
    op.drop_column("molecules", "num_heavy_atoms")
    op.drop_column("molecules", "num_aromatic_rings")
    op.drop_column("molecules", "num_rings")
