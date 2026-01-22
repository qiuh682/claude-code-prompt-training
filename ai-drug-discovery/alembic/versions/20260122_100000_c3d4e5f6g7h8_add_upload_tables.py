"""Add upload tables for molecule data ingestion

Creates tables for the Custom Data Upload System:
- uploads: Main upload job records with state machine
- upload_files: File storage references
- upload_progress: Real-time progress tracking
- upload_row_errors: Per-row validation errors
- upload_result_summaries: Final processing statistics

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-01-22 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6g7h8"
down_revision: str | None = "b2c3d4e5f6g7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    # ==========================================================================
    # CREATE UPLOADS TABLE
    # ==========================================================================
    op.create_table(
        "uploads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, comment="User-provided upload name"),
        sa.Column(
            "file_type",
            sa.Enum("sdf", "csv", "smiles_list", name="filetype"),
            nullable=False,
            comment="sdf, csv, or smiles_list",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "initiated",
                "validating",
                "validation_failed",
                "awaiting_confirm",
                "cancelled",
                "processing",
                "completed",
                "failed",
                name="uploadstatus",
            ),
            nullable=False,
        ),
        sa.Column(
            "duplicate_action",
            sa.Enum("skip", "update", "error", name="duplicateaction"),
            nullable=False,
        ),
        sa.Column(
            "similarity_threshold",
            sa.Numeric(precision=4, scale=3),
            nullable=True,
            comment="Tanimoto threshold for similarity-based duplicate detection",
        ),
        sa.Column(
            "column_mapping",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='{"smiles": "SMILES_COL", "name": "Compound_Name", ...}',
        ),
        sa.Column("error_message", sa.Text(), nullable=True, comment="High-level error message if failed"),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Auto-cancel unconfirmed uploads after this time",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_uploads_created_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_uploads_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Molecule upload job records",
    )
    op.create_index("ix_uploads_created_by", "uploads", ["created_by"])
    op.create_index("ix_uploads_org_created", "uploads", ["organization_id", "created_at"])
    op.create_index("ix_uploads_org_status", "uploads", ["organization_id", "status"])
    op.create_index("ix_uploads_organization_id", "uploads", ["organization_id"])
    op.create_index("ix_uploads_status", "uploads", ["status"])

    # ==========================================================================
    # CREATE UPLOAD_FILES TABLE
    # ==========================================================================
    op.create_table(
        "upload_files",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("upload_id", sa.UUID(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_backend", sa.String(length=20), nullable=False, comment="local or s3"),
        sa.Column(
            "storage_path",
            sa.String(length=500),
            nullable=False,
            comment="Relative path (local) or S3 key",
        ),
        sa.Column(
            "sha256_hash",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 hash for integrity verification",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["uploads.id"],
            name="fk_upload_files_upload_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upload_id", name="uq_upload_files_upload_id"),
        comment="Uploaded file storage references",
    )
    op.create_index("ix_upload_files_hash", "upload_files", ["sha256_hash"])

    # ==========================================================================
    # CREATE UPLOAD_PROGRESS TABLE
    # ==========================================================================
    op.create_table(
        "upload_progress",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("upload_id", sa.UUID(), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "duplicate_exact",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="InChIKey exact matches",
        ),
        sa.Column(
            "duplicate_similar",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Tanimoto similarity matches",
        ),
        sa.Column(
            "phase",
            sa.String(length=50),
            nullable=False,
            server_default="initializing",
            comment="parsing, validating, checking_duplicates, inserting",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["uploads.id"],
            name="fk_upload_progress_upload_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upload_id", name="uq_upload_progress_upload_id"),
        comment="Real-time upload progress tracking",
    )

    # ==========================================================================
    # CREATE UPLOAD_ROW_ERRORS TABLE
    # ==========================================================================
    op.create_table(
        "upload_row_errors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("upload_id", sa.UUID(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False, comment="1-based row number in source file"),
        sa.Column("error_code", sa.String(length=50), nullable=False, comment="Structured error code"),
        sa.Column("error_message", sa.Text(), nullable=False, comment="Human-readable error message"),
        sa.Column(
            "raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Truncated row data for debugging",
        ),
        sa.Column(
            "field_name",
            sa.String(length=100),
            nullable=True,
            comment="Which field caused the error",
        ),
        sa.Column(
            "duplicate_inchi_key",
            sa.String(length=27),
            nullable=True,
            comment="InChIKey of existing duplicate molecule",
        ),
        sa.Column(
            "duplicate_similarity",
            sa.Numeric(precision=4, scale=3),
            nullable=True,
            comment="Tanimoto similarity score for similar duplicates",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["uploads.id"],
            name="fk_upload_row_errors_upload_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upload_id", "row_number", name="uq_upload_row_error"),
        comment="Per-row validation errors",
    )
    op.create_index("ix_upload_row_errors_code", "upload_row_errors", ["upload_id", "error_code"])
    op.create_index("ix_upload_row_errors_upload_id", "upload_row_errors", ["upload_id"])

    # ==========================================================================
    # CREATE UPLOAD_RESULT_SUMMARIES TABLE
    # ==========================================================================
    op.create_table(
        "upload_result_summaries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("upload_id", sa.UUID(), nullable=False),
        sa.Column("molecules_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("molecules_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("molecules_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exact_duplicates_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("similar_duplicates_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processing_duration_seconds", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["uploads.id"],
            name="fk_upload_result_summaries_upload_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upload_id", name="uq_upload_result_summaries_upload_id"),
        comment="Final upload processing statistics",
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_table("upload_result_summaries")
    op.drop_index("ix_upload_row_errors_upload_id", table_name="upload_row_errors")
    op.drop_index("ix_upload_row_errors_code", table_name="upload_row_errors")
    op.drop_table("upload_row_errors")
    op.drop_table("upload_progress")
    op.drop_index("ix_upload_files_hash", table_name="upload_files")
    op.drop_table("upload_files")
    op.drop_index("ix_uploads_status", table_name="uploads")
    op.drop_index("ix_uploads_organization_id", table_name="uploads")
    op.drop_index("ix_uploads_org_status", table_name="uploads")
    op.drop_index("ix_uploads_org_created", table_name="uploads")
    op.drop_index("ix_uploads_created_by", table_name="uploads")
    op.drop_table("uploads")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS uploadstatus")
    op.execute("DROP TYPE IF EXISTS filetype")
    op.execute("DROP TYPE IF EXISTS duplicateaction")
