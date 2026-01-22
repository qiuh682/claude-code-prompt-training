"""
Integration tests for Task 2.3: Upload API happy path.

Tests the complete upload workflow:
1. Upload a SMILES file via POST /uploads
2. Poll GET /uploads/{id}/status until validation completes
3. Confirm upload via POST /uploads/{id}/confirm
4. Verify molecules were inserted into DB

These tests use:
- Async test fixtures with real test database
- Synchronous task execution (no background workers)
- Proper cleanup between tests

Requirements:
- PostgreSQL running on localhost:5433
- Test database 'drugdiscovery_test' created
- Redis running on localhost:6380 (optional)

To run:
    pytest tests/test_upload_happy_path.py -v

To skip if database unavailable:
    pytest tests/test_upload_happy_path.py -v -m "not integration"
"""

import asyncio
import io
import os
import uuid
from datetime import datetime, UTC
from decimal import Decimal
from typing import AsyncGenerator, Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from db.base import Base
from db.models.discovery import Molecule
from db.models.upload import (
    DuplicateAction,
    FileType,
    Upload,
    UploadFile,
    UploadProgress,
    UploadResultSummary,
    UploadRowError,
    UploadStatus,
)


# Check if test database is available
def _check_db_available() -> bool:
    """Check if test database is available."""
    try:
        from sqlalchemy import create_engine, text
        sync_url = "postgresql://postgres:postgres@localhost:5433/drugdiscovery_test"
        engine = create_engine(sync_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# Skip all tests in this module if database is not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _check_db_available(),
        reason="Test database not available (requires PostgreSQL on localhost:5433 with 'drugdiscovery_test' database)"
    ),
]


# =============================================================================
# Test Configuration
# =============================================================================

# Test database URLs
# Sync URL for table cleanup (uses psycopg2)
TEST_SYNC_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/drugdiscovery_test",
).replace("+asyncpg", "")

# Async URL for async operations (uses asyncpg)
TEST_ASYNC_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/drugdiscovery_test",
)
if not TEST_ASYNC_DATABASE_URL.startswith("postgresql+asyncpg://"):
    TEST_ASYNC_DATABASE_URL = TEST_ASYNC_DATABASE_URL.replace(
        "postgresql://", "postgresql+asyncpg://"
    )


# =============================================================================
# Test Data
# =============================================================================

# Simple SMILES list with 5 valid molecules
SAMPLE_SMILES_FILE = b"""CCO\tEthanol
CC(=O)O\tAcetic_Acid
c1ccccc1\tBenzene
CC(C)O\tIsopropanol
CCCC\tButane
"""

# SMILES list with some invalid entries
SMILES_WITH_ERRORS = b"""CCO\tEthanol
INVALID_SMILES\tBad_Molecule
c1ccccc1\tBenzene
"""

# CSV format test data
SAMPLE_CSV_FILE = b"""SMILES,Name,CAS
CCO,Ethanol,64-17-5
CC(=O)O,Acetic Acid,64-19-7
c1ccccc1,Benzene,71-43-2
"""

# Test organization and user IDs (match placeholder in router)
TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# =============================================================================
# Fixtures: Database
# =============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def sync_engine():
    """Create sync engine for table setup (uses psycopg2)."""
    engine = create_engine(TEST_SYNC_DATABASE_URL, pool_pre_ping=True)
    return engine


@pytest.fixture(scope="session")
def async_engine():
    """Create async engine for tests."""
    engine = create_async_engine(TEST_ASYNC_DATABASE_URL, pool_pre_ping=True)
    return engine


@pytest.fixture(scope="session")
def async_session_factory(async_engine):
    """Create async session factory."""
    return async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
async def db_session(async_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Provide async database session with cleanup."""
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def clean_upload_tables(sync_engine):
    """Clean upload-related tables before and after test."""
    def truncate():
        with sync_engine.connect() as conn:
            conn.execute(text("SET session_replication_role = 'replica';"))
            # Truncate in order (respecting FK constraints)
            conn.execute(text("TRUNCATE TABLE upload_row_errors CASCADE;"))
            conn.execute(text("TRUNCATE TABLE upload_result_summaries CASCADE;"))
            conn.execute(text("TRUNCATE TABLE upload_progress CASCADE;"))
            conn.execute(text("TRUNCATE TABLE upload_files CASCADE;"))
            conn.execute(text("TRUNCATE TABLE uploads CASCADE;"))
            conn.execute(text("TRUNCATE TABLE molecules CASCADE;"))
            conn.execute(text("SET session_replication_role = 'origin';"))
            conn.commit()

    truncate()
    yield
    truncate()


@pytest.fixture
async def setup_test_org(db_session: AsyncSession):
    """Ensure test organization and user exist."""
    from apps.api.auth.models import Organization, User

    # Check if org exists
    result = await db_session.execute(
        select(Organization).where(Organization.id == TEST_ORG_ID)
    )
    org = result.scalar_one_or_none()

    if not org:
        # Create test organization
        org = Organization(
            id=TEST_ORG_ID,
            name="Test Organization",
            slug="test-org",
        )
        db_session.add(org)

        # Create test user
        user = User(
            id=TEST_USER_ID,
            email="test@example.com",
            password_hash="not_a_real_hash",
            full_name="Test User",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

    return {"org_id": TEST_ORG_ID, "user_id": TEST_USER_ID}


# =============================================================================
# Fixtures: FastAPI App and Client
# =============================================================================


@pytest.fixture(scope="module")
def app() -> FastAPI:
    """Get FastAPI application."""
    # Set test environment
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DATABASE_URL"] = TEST_ASYNC_DATABASE_URL

    from apps.api.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# =============================================================================
# Fixtures: Synchronous Task Execution
# =============================================================================


@pytest.fixture
def run_validation_sync(async_session_factory):
    """
    Run validation task synchronously (for testing).

    Returns a callable that runs validation and waits for completion.
    """
    async def _run_validation(upload_id: uuid.UUID, org_id: uuid.UUID):
        from apps.api.uploads.service import UploadService
        from apps.api.uploads.tasks import UploadProcessor
        from packages.shared.storage import get_storage_backend

        async with async_session_factory() as session:
            storage = get_storage_backend()
            service = UploadService(session, storage)
            upload = await service.get_upload(upload_id, org_id)

            if upload:
                processor = UploadProcessor(session, service)
                await processor.process_validation(upload)

    return _run_validation


@pytest.fixture
def run_processing_sync(async_session_factory):
    """
    Run processing/insertion task synchronously (for testing).

    Returns a callable that runs insertion and waits for completion.
    """
    async def _run_processing(upload_id: uuid.UUID, org_id: uuid.UUID):
        from apps.api.uploads.service import UploadService
        from apps.api.uploads.tasks import UploadProcessor
        from packages.shared.storage import get_storage_backend

        async with async_session_factory() as session:
            storage = get_storage_backend()
            service = UploadService(session, storage)
            upload = await service.get_upload(upload_id, org_id)

            if upload:
                processor = UploadProcessor(session, service)
                await processor.process_insertion(upload)

    return _run_processing


# =============================================================================
# Test: POST /uploads - Create Upload
# =============================================================================


@pytest.mark.asyncio
class TestCreateUpload:
    """Tests for POST /uploads endpoint."""

    async def test_upload_smiles_file_returns_upload_id(
        self,
        client: AsyncClient,
        clean_upload_tables,
        setup_test_org,
    ):
        """
        Test Case 1: Upload a small SMILES text file.
        Should return upload_id and status INITIATED/VALIDATING.
        """
        # Prepare file upload
        files = {
            "file": ("molecules.smi", io.BytesIO(SAMPLE_SMILES_FILE), "text/plain"),
        }
        data = {
            "name": "Test SMILES Upload",
            "duplicate_action": "skip",
            "similarity_threshold": "0.85",
        }

        # Make request
        response = await client.post("/api/v1/uploads", files=files, data=data)

        # Assertions
        assert response.status_code == 202, f"Response: {response.text}"
        result = response.json()

        # Verify response structure
        assert "id" in result
        assert result["name"] == "Test SMILES Upload"
        assert result["status"] in ["initiated", "validating"]
        assert result["file_type"] == "smiles_list"
        assert "links" in result
        assert "status" in result["links"]

        # Verify upload_id is valid UUID
        upload_id = uuid.UUID(result["id"])
        assert upload_id is not None

    async def test_upload_csv_requires_smiles_column(
        self,
        client: AsyncClient,
        clean_upload_tables,
        setup_test_org,
    ):
        """CSV upload without smiles_column should return 400."""
        files = {
            "file": ("molecules.csv", io.BytesIO(SAMPLE_CSV_FILE), "text/csv"),
        }
        data = {
            "name": "Test CSV Upload",
            "file_type": "csv",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)

        assert response.status_code == 400
        assert "smiles_column" in response.text.lower()

    async def test_upload_csv_with_column_mapping(
        self,
        client: AsyncClient,
        clean_upload_tables,
        setup_test_org,
    ):
        """CSV upload with column mapping should succeed."""
        files = {
            "file": ("molecules.csv", io.BytesIO(SAMPLE_CSV_FILE), "text/csv"),
        }
        data = {
            "name": "Test CSV Upload",
            "file_type": "csv",
            "smiles_column": "SMILES",
            "name_column": "Name",
            "external_id_column": "CAS",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)

        assert response.status_code == 202, f"Response: {response.text}"
        result = response.json()
        assert result["file_type"] == "csv"
        assert result["column_mapping"]["smiles"] == "SMILES"


# =============================================================================
# Test: GET /uploads/{id}/status - Poll Status
# =============================================================================


@pytest.mark.asyncio
class TestPollStatus:
    """Tests for GET /uploads/{id}/status endpoint."""

    async def test_status_shows_progress_during_validation(
        self,
        client: AsyncClient,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """
        Test Case 2: Poll status until validation completes.
        Progress should increase and summary counts should match expected.
        """
        # Step 1: Create upload
        files = {
            "file": ("molecules.smi", io.BytesIO(SAMPLE_SMILES_FILE), "text/plain"),
        }
        data = {"name": "Test Progress Upload"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = response.json()["id"]

        # Step 2: Run validation synchronously (in tests, background tasks may not run)
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Step 3: Check status after validation
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        assert response.status_code == 200

        result = response.json()

        # Verify validation completed
        assert result["status"] in ["awaiting_confirm", "validation_failed"]

        # Check progress
        if result["progress"]:
            progress = result["progress"]
            assert progress["total_rows"] == 5  # 5 molecules in sample
            assert progress["processed_rows"] == 5
            assert progress["phase"] in ["validation_complete", "needs_column_mapping"]
            assert progress["percent_complete"] == 100.0

    async def test_status_shows_validation_summary(
        self,
        client: AsyncClient,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Validation summary should show counts for awaiting_confirm state."""
        # Create and validate upload
        files = {
            "file": ("molecules.smi", io.BytesIO(SAMPLE_SMILES_FILE), "text/plain"),
        }
        data = {"name": "Test Summary Upload"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Check status
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        result = response.json()

        if result["status"] == "awaiting_confirm":
            assert "validation_summary" in result
            summary = result["validation_summary"]
            assert summary["ready_to_insert"] > 0
            assert "errors_to_review" in summary
            assert "error_rate_percent" in summary

    async def test_status_shows_errors_for_invalid_smiles(
        self,
        client: AsyncClient,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Upload with invalid SMILES should show errors."""
        files = {
            "file": ("bad.smi", io.BytesIO(SMILES_WITH_ERRORS), "text/plain"),
        }
        data = {"name": "Test Errors Upload"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Check status
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        result = response.json()

        # Should have invalid rows
        if result["progress"]:
            assert result["progress"]["invalid_rows"] >= 1

        # Check errors endpoint
        response = await client.get(f"/api/v1/uploads/{upload_id}/errors")
        assert response.status_code == 200
        errors = response.json()

        assert errors["total_errors"] >= 1
        assert len(errors["errors"]) >= 1

        # Find the INVALID_SMILES error
        error_codes = [e["error_code"] for e in errors["errors"]]
        assert "invalid_smiles" in error_codes or "INVALID_SMILES" in error_codes


# =============================================================================
# Test: POST /uploads/{id}/confirm - Confirm Upload
# =============================================================================


@pytest.mark.asyncio
class TestConfirmUpload:
    """Tests for POST /uploads/{id}/confirm endpoint."""

    async def test_confirm_starts_processing(
        self,
        client: AsyncClient,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """
        Test Case 3: Confirm upload transitions to PROCESSING then COMPLETED.
        """
        # Create and validate upload
        files = {
            "file": ("molecules.smi", io.BytesIO(SAMPLE_SMILES_FILE), "text/plain"),
        }
        data = {"name": "Test Confirm Upload"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Verify in awaiting_confirm state
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        assert response.json()["status"] == "awaiting_confirm"

        # Confirm upload
        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={"acknowledge_errors": True, "proceed_with_valid_only": True},
        )

        assert response.status_code == 202, f"Response: {response.text}"
        result = response.json()

        # Should transition to processing
        assert result["status"] in ["processing", "completed"]
        assert "message" in result

        # Run processing synchronously
        await run_processing_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Check final status
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        result = response.json()

        assert result["status"] == "completed"
        assert result["summary"] is not None
        assert result["summary"]["molecules_created"] > 0

    async def test_confirm_is_idempotent(
        self,
        client: AsyncClient,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """Confirming an already completed upload should be idempotent."""
        # Create, validate, confirm, and process
        files = {
            "file": ("molecules.smi", io.BytesIO(SAMPLE_SMILES_FILE), "text/plain"),
        }
        data = {"name": "Test Idempotent Upload"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Confirm
        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={"acknowledge_errors": True},
        )
        assert response.status_code == 202

        await run_processing_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Confirm again - should be idempotent
        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={"acknowledge_errors": True},
        )

        assert response.status_code == 202
        result = response.json()
        assert result["status"] == "completed"
        assert "already" in result["message"].lower()

    async def test_confirm_requires_error_acknowledgment(
        self,
        client: AsyncClient,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Confirming upload with errors without acknowledgment should fail."""
        # Upload file with errors
        files = {
            "file": ("bad.smi", io.BytesIO(SMILES_WITH_ERRORS), "text/plain"),
        }
        data = {"name": "Test Error Ack Upload"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Confirm without acknowledgment
        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={"acknowledge_errors": False},
        )

        # Should fail since there are errors
        assert response.status_code == 400
        assert "error" in response.text.lower()


# =============================================================================
# Test: Verify Molecules in DB
# =============================================================================


@pytest.mark.asyncio
class TestMoleculeInsertion:
    """Tests for verifying molecules were inserted into DB."""

    async def test_molecules_inserted_after_processing(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """
        Test Case 4: Verify molecules were inserted/upserted into DB.
        """
        # Create, validate, confirm, and process upload
        files = {
            "file": ("molecules.smi", io.BytesIO(SAMPLE_SMILES_FILE), "text/plain"),
        }
        data = {"name": "Test DB Insert Upload"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={"acknowledge_errors": True},
        )
        assert response.status_code == 202

        await run_processing_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Verify molecules in database
        result = await db_session.execute(
            select(Molecule).where(Molecule.organization_id == TEST_ORG_ID)
        )
        molecules = result.scalars().all()

        # Should have 5 molecules from sample file
        assert len(molecules) == 5

        # Verify molecule properties
        smiles_list = {m.canonical_smiles for m in molecules}

        # Check that expected molecules exist (canonical forms may differ)
        # Ethanol: CCO
        assert any("CCO" in s or "OCC" in s for s in smiles_list)

        # All molecules should have InChIKey
        for mol in molecules:
            assert mol.inchi_key is not None
            assert len(mol.inchi_key) == 27  # Standard InChIKey length
            assert mol.smiles_hash is not None

    async def test_molecule_metadata_contains_upload_info(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """Molecule metadata should contain upload provenance."""
        # Create and process upload
        files = {
            "file": ("molecules.smi", io.BytesIO(SAMPLE_SMILES_FILE), "text/plain"),
        }
        data = {"name": "Provenance Test Upload"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={"acknowledge_errors": True},
        )

        await run_processing_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Get a molecule and check metadata
        result = await db_session.execute(
            select(Molecule)
            .where(Molecule.organization_id == TEST_ORG_ID)
            .limit(1)
        )
        molecule = result.scalar_one_or_none()

        assert molecule is not None

        # Check metadata has upload info
        if molecule.metadata_:
            assert "source_upload_id" in molecule.metadata_
            assert molecule.metadata_["source_upload_id"] == upload_id

    async def test_duplicate_molecules_are_skipped(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """Uploading same molecules twice should skip duplicates."""
        # First upload
        files = {
            "file": ("molecules.smi", io.BytesIO(SAMPLE_SMILES_FILE), "text/plain"),
        }
        data = {"name": "First Upload", "duplicate_action": "skip"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id_1 = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id_1), TEST_ORG_ID)
        response = await client.post(
            f"/api/v1/uploads/{upload_id_1}/confirm",
            json={"acknowledge_errors": True},
        )
        await run_processing_sync(uuid.UUID(upload_id_1), TEST_ORG_ID)

        # Count molecules after first upload
        result = await db_session.execute(
            select(Molecule).where(Molecule.organization_id == TEST_ORG_ID)
        )
        count_after_first = len(result.scalars().all())

        # Second upload with same molecules
        files = {
            "file": ("molecules.smi", io.BytesIO(SAMPLE_SMILES_FILE), "text/plain"),
        }
        data = {"name": "Second Upload", "duplicate_action": "skip"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id_2 = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id_2), TEST_ORG_ID)
        response = await client.post(
            f"/api/v1/uploads/{upload_id_2}/confirm",
            json={"acknowledge_errors": True},
        )
        await run_processing_sync(uuid.UUID(upload_id_2), TEST_ORG_ID)

        # Check final status - should have skipped duplicates
        response = await client.get(f"/api/v1/uploads/{upload_id_2}/status")
        result = response.json()

        assert result["summary"]["molecules_skipped"] > 0 or \
               result["summary"]["exact_duplicates_found"] > 0

        # Count should be same (duplicates skipped)
        result = await db_session.execute(
            select(Molecule).where(Molecule.organization_id == TEST_ORG_ID)
        )
        count_after_second = len(result.scalars().all())

        assert count_after_second == count_after_first


# =============================================================================
# Test: Full Happy Path (End-to-End)
# =============================================================================


@pytest.mark.asyncio
class TestFullHappyPath:
    """End-to-end test of the complete upload workflow."""

    async def test_complete_upload_workflow(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """
        Complete happy path test:
        1. Upload SMILES file -> returns upload_id, status INITIATED
        2. Run validation -> status becomes AWAITING_CONFIRM
        3. Poll status -> see progress and validation summary
        4. Confirm -> status becomes PROCESSING then COMPLETED
        5. Verify molecules in DB
        """
        # =====================================================================
        # Step 1: Upload file
        # =====================================================================
        files = {
            "file": ("test_molecules.smi", io.BytesIO(SAMPLE_SMILES_FILE), "text/plain"),
        }
        data = {
            "name": "Happy Path Test",
            "duplicate_action": "skip",
            "similarity_threshold": "0.95",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)

        assert response.status_code == 202
        upload_result = response.json()

        upload_id = upload_result["id"]
        assert upload_result["status"] in ["initiated", "validating"]
        assert upload_result["file"]["original_filename"] == "test_molecules.smi"

        # =====================================================================
        # Step 2: Run validation (synchronously for tests)
        # =====================================================================
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # =====================================================================
        # Step 3: Poll status - should be AWAITING_CONFIRM
        # =====================================================================
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        assert response.status_code == 200

        status_result = response.json()
        assert status_result["status"] == "awaiting_confirm"
        assert status_result["progress"]["total_rows"] == 5
        assert status_result["progress"]["percent_complete"] == 100.0
        assert status_result["validation_summary"]["ready_to_insert"] > 0

        # Actions should include confirm
        assert status_result["actions"]["confirm"] is not None

        # =====================================================================
        # Step 4: Confirm upload
        # =====================================================================
        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={"acknowledge_errors": True, "proceed_with_valid_only": True},
        )

        assert response.status_code == 202
        confirm_result = response.json()
        assert confirm_result["status"] == "processing"

        # Run processing (synchronously for tests)
        await run_processing_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # =====================================================================
        # Step 5: Check final status - COMPLETED
        # =====================================================================
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        assert response.status_code == 200

        final_result = response.json()
        assert final_result["status"] == "completed"
        assert final_result["completed_at"] is not None
        assert final_result["summary"]["molecules_created"] == 5
        assert final_result["summary"]["errors_count"] == 0

        # =====================================================================
        # Step 6: Verify molecules in database
        # =====================================================================
        result = await db_session.execute(
            select(Molecule)
            .where(Molecule.organization_id == TEST_ORG_ID)
            .where(Molecule.deleted_at.is_(None))
        )
        molecules = result.scalars().all()

        assert len(molecules) == 5

        # Verify each molecule has required fields
        for mol in molecules:
            assert mol.canonical_smiles is not None
            assert mol.inchi_key is not None
            assert len(mol.inchi_key) == 27
            assert mol.smiles_hash is not None
            assert mol.organization_id == TEST_ORG_ID


# =============================================================================
# Test: Edge Cases
# =============================================================================


@pytest.mark.asyncio
class TestEdgeCases:
    """Tests for edge cases and error handling."""

    async def test_upload_not_found(self, client: AsyncClient):
        """Non-existent upload should return 404."""
        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/uploads/{fake_id}/status")
        assert response.status_code == 404

    async def test_confirm_invalid_state(
        self,
        client: AsyncClient,
        clean_upload_tables,
        setup_test_org,
    ):
        """Confirming upload in INITIATED state should fail."""
        # Create upload but don't validate
        files = {
            "file": ("molecules.smi", io.BytesIO(SAMPLE_SMILES_FILE), "text/plain"),
        }
        data = {"name": "Invalid State Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        # Try to confirm without validation
        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={"acknowledge_errors": True},
        )

        # Should fail - not in AWAITING_CONFIRM state
        assert response.status_code == 409

    async def test_cancel_upload(
        self,
        client: AsyncClient,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Cancel upload should transition to CANCELLED state."""
        # Create and validate
        files = {
            "file": ("molecules.smi", io.BytesIO(SAMPLE_SMILES_FILE), "text/plain"),
        }
        data = {"name": "Cancel Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Cancel
        response = await client.delete(f"/api/v1/uploads/{upload_id}")
        assert response.status_code == 204

        # Check status
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        assert response.json()["status"] == "cancelled"

    async def test_empty_file_upload(
        self,
        client: AsyncClient,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Empty file should be handled gracefully."""
        files = {
            "file": ("empty.smi", io.BytesIO(b""), "text/plain"),
        }
        data = {"name": "Empty File Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)

        # Should accept the upload (validation will fail later)
        assert response.status_code in [202, 400]
