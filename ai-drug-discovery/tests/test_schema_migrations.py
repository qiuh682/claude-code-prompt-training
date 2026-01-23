"""
Tests for Task 1.3 schema migrations.

Verifies that Alembic migrations correctly create:
- Discovery domain tables (molecules, targets, assays, projects, predictions)
- Association tables (molecule_targets, project_molecules, project_targets)
- Key constraints (unique inchikey, unique uniprot_id)
- Chemical search indexes (canonical_smiles, inchi_key)

Usage:
    DATABASE_URL_TEST=postgresql://postgres:postgres@localhost:5433/drugdiscovery_test \
    pytest tests/test_schema_migrations.py -v
"""

import os
import subprocess

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError


# =============================================================================
# Configuration
# =============================================================================


def get_test_database_url() -> str:
    """Get test database URL from environment."""
    url = os.getenv("DATABASE_URL_TEST")
    if not url:
        pytest.skip("DATABASE_URL_TEST not set")
    return url


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def db_engine() -> Engine:
    """Create a SQLAlchemy engine for the test database."""
    url = get_test_database_url()
    engine = create_engine(url, pool_pre_ping=True)

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as e:
        pytest.skip(f"Cannot connect to test database: {e}")

    return engine


@pytest.fixture(scope="module")
def clean_database(db_engine: Engine) -> Engine:
    """Drop all tables to ensure a clean slate for schema tests."""
    with db_engine.connect() as conn:
        conn.execute(
            text(
                """
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                    EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
                END LOOP;
            END $$;
        """
            )
        )
        conn.commit()

    return db_engine


@pytest.fixture(scope="module")
def migrated_database(clean_database: Engine) -> Engine:
    """
    Apply all Alembic migrations to a clean database.

    This fixture:
    1. Starts with a clean database (no tables)
    2. Runs 'alembic upgrade head'
    3. Returns the engine for inspection

    Scope: module (run once per test module for efficiency)
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = get_test_database_url()

    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(__file__)),  # ai-drug-discovery/
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        pytest.fail(
            f"alembic upgrade head failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    return clean_database


# =============================================================================
# Helper Functions
# =============================================================================


def get_table_names(engine: Engine) -> set[str]:
    """Get all table names in the database."""
    inspector = inspect(engine)
    return set(inspector.get_table_names())


def get_index_names(engine: Engine, table_name: str) -> set[str]:
    """Get all index names for a specific table."""
    inspector = inspect(engine)
    indexes = inspector.get_indexes(table_name)
    return {idx["name"] for idx in indexes if idx["name"]}


def get_unique_constraints(engine: Engine, table_name: str) -> set[str]:
    """Get all unique constraint names for a specific table."""
    inspector = inspect(engine)
    constraints = inspector.get_unique_constraints(table_name)
    return {c["name"] for c in constraints if c["name"]}


def get_pk_constraint(engine: Engine, table_name: str) -> dict | None:
    """Get primary key constraint for a table."""
    inspector = inspect(engine)
    return inspector.get_pk_constraint(table_name)


def get_foreign_keys(engine: Engine, table_name: str) -> list[dict]:
    """Get foreign key constraints for a table."""
    inspector = inspect(engine)
    return inspector.get_foreign_keys(table_name)


def get_columns(engine: Engine, table_name: str) -> dict[str, dict]:
    """Get column info for a table as dict keyed by column name."""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return {col["name"]: col for col in columns}


# =============================================================================
# Test Classes
# =============================================================================


class TestDiscoveryTablesExist:
    """Verify all Task 1.3 discovery tables are created."""

    EXPECTED_TABLES = {
        "molecules",
        "targets",
        "assays",
        "projects",
        "predictions",
    }

    EXPECTED_ASSOCIATION_TABLES = {
        "molecule_targets",
        "project_molecules",
        "project_targets",
    }

    def test_core_discovery_tables_exist(self, migrated_database: Engine) -> None:
        """All core discovery tables (molecules, targets, etc.) exist."""
        tables = get_table_names(migrated_database)

        missing = self.EXPECTED_TABLES - tables
        assert not missing, f"Missing discovery tables: {missing}"

    def test_association_tables_exist(self, migrated_database: Engine) -> None:
        """All association tables (molecule_targets, etc.) exist."""
        tables = get_table_names(migrated_database)

        missing = self.EXPECTED_ASSOCIATION_TABLES - tables
        assert not missing, f"Missing association tables: {missing}"

    def test_all_expected_tables_exist(self, migrated_database: Engine) -> None:
        """All Task 1.3 tables exist (comprehensive check)."""
        tables = get_table_names(migrated_database)

        all_expected = self.EXPECTED_TABLES | self.EXPECTED_ASSOCIATION_TABLES
        missing = all_expected - tables
        assert not missing, f"Missing tables: {missing}"

        # Report what was created
        print(f"\nDiscovery tables found: {sorted(all_expected & tables)}")


class TestMoleculeTableSchema:
    """Verify molecules table schema and constraints."""

    def test_molecules_has_required_columns(self, migrated_database: Engine) -> None:
        """molecules table has all required columns."""
        columns = get_columns(migrated_database, "molecules")

        required_columns = {
            "id",
            "organization_id",
            "canonical_smiles",
            "inchi_key",
            "smiles_hash",
            "created_at",
            "updated_at",
            "created_by",
            "deleted_at",
        }

        missing = required_columns - set(columns.keys())
        assert not missing, f"Missing columns in molecules: {missing}"

    def test_molecules_has_primary_key(self, migrated_database: Engine) -> None:
        """molecules table has id as primary key."""
        pk = get_pk_constraint(migrated_database, "molecules")

        assert pk is not None
        assert "id" in pk["constrained_columns"]

    def test_molecules_has_organization_fk(self, migrated_database: Engine) -> None:
        """molecules table has foreign key to organizations."""
        fks = get_foreign_keys(migrated_database, "molecules")

        org_fks = [
            fk for fk in fks if fk["referred_table"] == "organizations"
        ]
        assert len(org_fks) >= 1, "Missing foreign key to organizations"

    def test_molecules_inchikey_unique_constraint(
        self, migrated_database: Engine
    ) -> None:
        """molecules table has unique constraint on (organization_id, inchi_key)."""
        constraints = get_unique_constraints(migrated_database, "molecules")

        # Check for unique constraint name
        assert "uq_molecule_org_inchikey" in constraints, (
            f"Missing unique constraint uq_molecule_org_inchikey. "
            f"Found: {constraints}"
        )


class TestTargetTableSchema:
    """Verify targets table schema and constraints."""

    def test_targets_has_required_columns(self, migrated_database: Engine) -> None:
        """targets table has all required columns."""
        columns = get_columns(migrated_database, "targets")

        required_columns = {
            "id",
            "organization_id",
            "uniprot_id",
            "gene_symbol",
            "name",
            "organism",
            "created_at",
            "updated_at",
            "deleted_at",
        }

        missing = required_columns - set(columns.keys())
        assert not missing, f"Missing columns in targets: {missing}"

    def test_targets_has_uniprot_unique_index(self, migrated_database: Engine) -> None:
        """targets table has unique index on (organization_id, uniprot_id)."""
        indexes = get_index_names(migrated_database, "targets")

        # The index is named ix_targets_org_uniprot and is unique
        assert "ix_targets_org_uniprot" in indexes, (
            f"Missing unique index ix_targets_org_uniprot. Found: {indexes}"
        )

        # Verify it's actually unique by inspecting the index details
        inspector = inspect(migrated_database)
        for idx in inspector.get_indexes("targets"):
            if idx["name"] == "ix_targets_org_uniprot":
                assert idx["unique"] is True, (
                    "ix_targets_org_uniprot should be unique"
                )
                break


class TestChemicalSearchIndexes:
    """Verify indexes exist for chemical searches."""

    def test_molecules_canonical_smiles_index(self, migrated_database: Engine) -> None:
        """molecules table has index on canonical_smiles."""
        indexes = get_index_names(migrated_database, "molecules")

        assert "ix_molecules_canonical_smiles" in indexes, (
            f"Missing index ix_molecules_canonical_smiles. Found: {indexes}"
        )

    def test_molecules_inchikey_index(self, migrated_database: Engine) -> None:
        """molecules table has index on (organization_id, inchi_key)."""
        indexes = get_index_names(migrated_database, "molecules")

        assert "ix_molecules_org_inchikey" in indexes, (
            f"Missing index ix_molecules_org_inchikey. Found: {indexes}"
        )

    def test_molecules_smiles_hash_index(self, migrated_database: Engine) -> None:
        """molecules table has index on smiles_hash for fast lookup."""
        indexes = get_index_names(migrated_database, "molecules")

        assert "ix_molecules_org_smiles_hash" in indexes, (
            f"Missing index ix_molecules_org_smiles_hash. Found: {indexes}"
        )

    def test_all_chemical_indexes_exist(self, migrated_database: Engine) -> None:
        """All chemical search indexes exist (comprehensive)."""
        indexes = get_index_names(migrated_database, "molecules")

        expected_indexes = {
            "ix_molecules_canonical_smiles",
            "ix_molecules_org_inchikey",
            "ix_molecules_org_smiles_hash",
        }

        missing = expected_indexes - indexes
        assert not missing, f"Missing chemical indexes: {missing}"

        print(f"\nChemical indexes found: {sorted(expected_indexes & indexes)}")


class TestAssociationTableConstraints:
    """Verify association table constraints."""

    def test_molecule_targets_unique_constraint(
        self, migrated_database: Engine
    ) -> None:
        """molecule_targets has unique constraint on (molecule_id, target_id)."""
        constraints = get_unique_constraints(migrated_database, "molecule_targets")

        assert "uq_molecule_target" in constraints, (
            f"Missing unique constraint uq_molecule_target. Found: {constraints}"
        )

    def test_project_molecules_unique_constraint(
        self, migrated_database: Engine
    ) -> None:
        """project_molecules has unique constraint on (project_id, molecule_id)."""
        constraints = get_unique_constraints(migrated_database, "project_molecules")

        assert "uq_project_molecule" in constraints, (
            f"Missing unique constraint uq_project_molecule. Found: {constraints}"
        )

    def test_project_targets_unique_constraint(
        self, migrated_database: Engine
    ) -> None:
        """project_targets has unique constraint on (project_id, target_id)."""
        constraints = get_unique_constraints(migrated_database, "project_targets")

        assert "uq_project_target" in constraints, (
            f"Missing unique constraint uq_project_target. Found: {constraints}"
        )

    def test_molecule_targets_has_foreign_keys(
        self, migrated_database: Engine
    ) -> None:
        """molecule_targets has FKs to molecules and targets."""
        fks = get_foreign_keys(migrated_database, "molecule_targets")
        referred_tables = {fk["referred_table"] for fk in fks}

        assert "molecules" in referred_tables, "Missing FK to molecules"
        assert "targets" in referred_tables, "Missing FK to targets"


class TestProjectTableSchema:
    """Verify projects table schema and constraints."""

    def test_projects_has_unique_name_per_org(self, migrated_database: Engine) -> None:
        """projects table has unique constraint on (organization_id, name)."""
        constraints = get_unique_constraints(migrated_database, "projects")

        assert "uq_project_org_name" in constraints, (
            f"Missing unique constraint uq_project_org_name. Found: {constraints}"
        )


class TestAuditColumns:
    """Verify audit columns exist on audited tables."""

    AUDITED_TABLES = ["molecules", "targets", "projects", "assays"]

    @pytest.mark.parametrize("table_name", AUDITED_TABLES)
    def test_table_has_audit_columns(
        self, migrated_database: Engine, table_name: str
    ) -> None:
        """Audited tables have created_at, updated_at, created_by, updated_by."""
        columns = get_columns(migrated_database, table_name)

        audit_columns = {"created_at", "updated_at", "created_by"}
        missing = audit_columns - set(columns.keys())

        assert not missing, f"{table_name} missing audit columns: {missing}"

    @pytest.mark.parametrize("table_name", AUDITED_TABLES)
    def test_table_has_soft_delete_column(
        self, migrated_database: Engine, table_name: str
    ) -> None:
        """Audited tables have deleted_at for soft delete."""
        columns = get_columns(migrated_database, table_name)

        assert "deleted_at" in columns, f"{table_name} missing deleted_at column"


class TestPredictionsTable:
    """Verify predictions table schema."""

    def test_predictions_has_required_columns(self, migrated_database: Engine) -> None:
        """predictions table has all required columns."""
        columns = get_columns(migrated_database, "predictions")

        required_columns = {
            "id",
            "organization_id",
            "molecule_id",
            "model_name",
            "model_version",
            "prediction_type",
            "predicted_value",
            "confidence_score",
            "created_at",
            "created_by",
        }

        missing = required_columns - set(columns.keys())
        assert not missing, f"Missing columns in predictions: {missing}"

    def test_predictions_has_model_index(self, migrated_database: Engine) -> None:
        """predictions table has index for model lookups."""
        indexes = get_index_names(migrated_database, "predictions")

        assert "ix_predictions_org_model" in indexes, (
            f"Missing index ix_predictions_org_model. Found: {indexes}"
        )


class TestSchemaIntegrity:
    """Integration tests for overall schema integrity."""

    def test_can_query_all_discovery_tables(self, migrated_database: Engine) -> None:
        """All discovery tables can be queried without error."""
        tables = [
            "molecules",
            "targets",
            "projects",
            "assays",
            "predictions",
            "molecule_targets",
            "project_molecules",
            "project_targets",
        ]

        with migrated_database.connect() as conn:
            for table in tables:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                assert count == 0, f"{table} should be empty in fresh migration"

    def test_foreign_key_integrity_enabled(self, migrated_database: Engine) -> None:
        """Foreign key constraints are enforced."""
        with migrated_database.connect() as conn:
            # Try to insert a molecule with non-existent organization_id
            # This should fail due to FK constraint
            try:
                conn.execute(
                    text(
                        """
                    INSERT INTO molecules (
                        id, organization_id, canonical_smiles, inchi_key,
                        smiles_hash, created_by, metadata
                    ) VALUES (
                        gen_random_uuid(),
                        gen_random_uuid(),  -- Non-existent org
                        'CCO',
                        'LFQSCWFLJHTTHZ-UHFFFAOYSA-N',
                        'abc123',
                        gen_random_uuid(),
                        '{}'
                    )
                """
                    )
                )
                conn.commit()
                pytest.fail("FK constraint should have prevented insert")
            except Exception as e:
                # Expected: FK violation
                assert "foreign key" in str(e).lower() or "violates" in str(e).lower()
                conn.rollback()
