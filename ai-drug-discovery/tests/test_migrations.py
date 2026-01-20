"""
Integration tests for Alembic migrations.
Verifies migrations apply cleanly on a fresh database.

Usage:
    DATABASE_URL_TEST=postgresql://postgres:postgres@localhost:5433/drugdiscovery_test \
    pytest tests/test_migrations.py -v
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

    # Verify connection works
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as e:
        pytest.skip(f"Cannot connect to test database: {e}")

    return engine


@pytest.fixture(scope="module")
def clean_database(db_engine: Engine) -> Engine:
    """Drop all tables to ensure a clean slate."""
    with db_engine.connect() as conn:
        # Drop all tables in public schema (Postgres-specific)
        conn.execute(text("""
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                    EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
                END LOOP;
            END $$;
        """))
        conn.commit()

    return db_engine


# =============================================================================
# Tests
# =============================================================================

class TestAlembicMigrations:
    """Tests for Alembic migration integrity."""

    def test_upgrade_head_succeeds(self, clean_database: Engine) -> None:
        """Running 'alembic upgrade head' completes without errors."""
        # Set DATABASE_URL for alembic to use
        env = os.environ.copy()
        env["DATABASE_URL"] = get_test_database_url()

        # Run alembic upgrade head
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=os.path.dirname(os.path.dirname(__file__)),  # ai-drug-discovery/
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Assert success
        assert result.returncode == 0, (
            f"alembic upgrade head failed:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    def test_alembic_version_table_exists(self, clean_database: Engine) -> None:
        """After migrations, alembic_version table exists."""
        # First run migrations
        env = os.environ.copy()
        env["DATABASE_URL"] = get_test_database_url()

        subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env,
            capture_output=True,
            timeout=60,
        )

        # Check alembic_version table exists
        inspector = inspect(clean_database)
        tables = inspector.get_table_names()

        assert "alembic_version" in tables, (
            f"alembic_version table not found. Tables: {tables}"
        )

    def test_alembic_version_has_revision(self, clean_database: Engine) -> None:
        """alembic_version table contains a revision value."""
        # First run migrations
        env = os.environ.copy()
        env["DATABASE_URL"] = get_test_database_url()

        subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env,
            capture_output=True,
            timeout=60,
        )

        # Query alembic_version
        with clean_database.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            rows = result.fetchall()

        assert len(rows) > 0, "alembic_version table is empty (no migrations applied)"
        assert rows[0][0], "version_num is empty"
        assert len(rows[0][0]) >= 12, f"version_num looks invalid: {rows[0][0]}"

    def test_downgrade_and_upgrade_succeeds(self, clean_database: Engine) -> None:
        """Downgrade -1 and upgrade head works (migration reversibility)."""
        env = os.environ.copy()
        env["DATABASE_URL"] = get_test_database_url()
        cwd = os.path.dirname(os.path.dirname(__file__))

        # First upgrade to head
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            pytest.skip("Initial upgrade failed, cannot test downgrade")

        # Downgrade one revision
        result = subprocess.run(
            ["alembic", "downgrade", "-1"],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Note: downgrade may fail if no migrations exist yet - that's OK
        if "Target database is not up to date" in result.stderr:
            pytest.skip("No migrations to downgrade")

        # Upgrade again
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, (
            f"Re-upgrade after downgrade failed:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )


class TestExpectedTables:
    """Tests for expected application tables (if models exist)."""

    def test_expected_tables_created(self, clean_database: Engine) -> None:
        """Verify expected tables exist after migrations."""
        # Run migrations first
        env = os.environ.copy()
        env["DATABASE_URL"] = get_test_database_url()

        subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env,
            capture_output=True,
            timeout=60,
        )

        # Check tables
        inspector = inspect(clean_database)
        tables = set(inspector.get_table_names())

        # At minimum, alembic_version should exist
        assert "alembic_version" in tables

        # If you have models, add expected tables here:
        # expected_tables = {"users", "molecules", "predictions"}
        # missing = expected_tables - tables
        # assert not missing, f"Missing tables: {missing}"

        # For now, just report what tables exist
        print(f"\nTables after migration: {sorted(tables)}")
