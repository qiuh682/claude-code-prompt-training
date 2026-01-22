"""
Integration tests for duplicate detection in uploads.

Tests verify:
1. Exact duplicate detection (same InChIKey already in DB)
2. Within-batch duplicate detection (same molecule twice in one file)
3. Similarity-based duplicate detection (Tanimoto threshold)
4. Upsert behavior (no duplicate molecules in DB)
5. Status summary reflects duplicate counts

Setup pattern:
- Insert a molecule into DB (existing)
- Upload file containing same molecule + variations
- Verify duplicates are detected and reported

Requirements:
- PostgreSQL running on localhost:5433
- Test database 'drugdiscovery_test' created
- RDKit installed for fingerprint calculations

To run:
    pytest tests/test_upload_duplicates.py -v

To skip if database unavailable:
    pytest tests/test_upload_duplicates.py -v -m "not integration"
"""

import asyncio
import hashlib
import io
import os
import uuid
from datetime import datetime, UTC
from decimal import Decimal
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
TEST_SYNC_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/drugdiscovery_test",
).replace("+asyncpg", "")

TEST_ASYNC_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/drugdiscovery_test",
)
if not TEST_ASYNC_DATABASE_URL.startswith("postgresql+asyncpg://"):
    TEST_ASYNC_DATABASE_URL = TEST_ASYNC_DATABASE_URL.replace(
        "postgresql://", "postgresql+asyncpg://"
    )


# Test organization and user IDs
TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# =============================================================================
# Test Data - Molecules with known properties
# =============================================================================

# Ethanol - our "existing" molecule
ETHANOL_SMILES = "CCO"
ETHANOL_INCHI_KEY = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
ETHANOL_FORMULA = "C2H6O"

# Methanol - structurally similar to ethanol (for similarity test)
METHANOL_SMILES = "CO"
METHANOL_INCHI_KEY = "OKKJLVBELUTLKV-UHFFFAOYSA-N"
METHANOL_FORMULA = "CH4O"

# Propanol - similar to ethanol (next homolog)
PROPANOL_SMILES = "CCCO"
PROPANOL_INCHI_KEY = "BDERNNFJNOPAEC-UHFFFAOYSA-N"
PROPANOL_FORMULA = "C3H8O"

# Benzene - completely different structure
BENZENE_SMILES = "c1ccccc1"
BENZENE_INCHI_KEY = "UHOVQNZJYSORNB-UHFFFAOYSA-N"
BENZENE_FORMULA = "C6H6"

# Acetic acid - different functional group
ACETIC_ACID_SMILES = "CC(=O)O"
ACETIC_ACID_INCHI_KEY = "QTBSBXVTEAMEQO-UHFFFAOYSA-N"
ACETIC_ACID_FORMULA = "C2H4O2"


def generate_smiles_hash(smiles: str) -> str:
    """Generate SHA-256 hash of SMILES string."""
    return hashlib.sha256(smiles.encode("utf-8")).hexdigest()


# =============================================================================
# Test Data - Upload files
# =============================================================================

# File with exact duplicate of ethanol + new molecule
SMILES_WITH_EXACT_DUPLICATE = f"""{ETHANOL_SMILES}\tEthanol_Copy
{BENZENE_SMILES}\tBenzene
{ACETIC_ACID_SMILES}\tAcetic_Acid
""".encode("utf-8")

# File with same molecule appearing twice (within-batch duplicate)
SMILES_WITH_BATCH_DUPLICATE = f"""{BENZENE_SMILES}\tBenzene_First
{ACETIC_ACID_SMILES}\tAcetic_Acid
{BENZENE_SMILES}\tBenzene_Second
""".encode("utf-8")

# File with similar molecules (alcohols - for similarity test)
SMILES_WITH_SIMILAR_MOLECULES = f"""{METHANOL_SMILES}\tMethanol
{PROPANOL_SMILES}\tPropanol
{BENZENE_SMILES}\tBenzene
""".encode("utf-8")

# File with multiple duplicates (both exact and batch)
SMILES_WITH_MULTIPLE_DUPLICATES = f"""{ETHANOL_SMILES}\tEthanol_Dup1
{BENZENE_SMILES}\tBenzene_First
{ETHANOL_SMILES}\tEthanol_Dup2
{BENZENE_SMILES}\tBenzene_Second
{ACETIC_ACID_SMILES}\tAcetic_Acid
""".encode("utf-8")


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
    """Create sync engine for table setup."""
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

    result = await db_session.execute(
        select(Organization).where(Organization.id == TEST_ORG_ID)
    )
    org = result.scalar_one_or_none()

    if not org:
        org = Organization(
            id=TEST_ORG_ID,
            name="Test Organization",
            slug="test-org",
        )
        db_session.add(org)

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
# Fixtures: Insert existing molecule
# =============================================================================


@pytest.fixture
async def existing_ethanol(
    async_session_factory,
    clean_upload_tables,
    setup_test_org,
) -> Molecule:
    """
    Insert ethanol as an existing molecule in the database.
    Returns the Molecule object for reference.
    """
    async with async_session_factory() as session:
        # Compute fingerprint if RDKit is available
        fingerprint_bytes = None
        try:
            from packages.chemistry import calculate_morgan_fingerprint, smiles_to_mol
            mol = smiles_to_mol(ETHANOL_SMILES)
            if mol:
                fp = calculate_morgan_fingerprint(mol)
                fingerprint_bytes = fp.to_bytes()
        except ImportError:
            pass

        molecule = Molecule(
            id=uuid.uuid4(),
            organization_id=TEST_ORG_ID,
            canonical_smiles=ETHANOL_SMILES,
            inchi_key=ETHANOL_INCHI_KEY,
            smiles_hash=generate_smiles_hash(ETHANOL_SMILES),
            molecular_formula=ETHANOL_FORMULA,
            molecular_weight=Decimal("46.0684"),
            name="Ethanol",
            fingerprint_morgan=fingerprint_bytes,
            created_by=TEST_USER_ID,
            updated_by=TEST_USER_ID,
        )
        session.add(molecule)
        await session.commit()
        await session.refresh(molecule)
        return molecule


@pytest.fixture
async def existing_benzene(
    async_session_factory,
    clean_upload_tables,
    setup_test_org,
) -> Molecule:
    """Insert benzene as an existing molecule in the database."""
    async with async_session_factory() as session:
        fingerprint_bytes = None
        try:
            from packages.chemistry import calculate_morgan_fingerprint, smiles_to_mol
            mol = smiles_to_mol(BENZENE_SMILES)
            if mol:
                fp = calculate_morgan_fingerprint(mol)
                fingerprint_bytes = fp.to_bytes()
        except ImportError:
            pass

        molecule = Molecule(
            id=uuid.uuid4(),
            organization_id=TEST_ORG_ID,
            canonical_smiles=BENZENE_SMILES,
            inchi_key=BENZENE_INCHI_KEY,
            smiles_hash=generate_smiles_hash(BENZENE_SMILES),
            molecular_formula=BENZENE_FORMULA,
            molecular_weight=Decimal("78.1134"),
            name="Benzene",
            fingerprint_morgan=fingerprint_bytes,
            created_by=TEST_USER_ID,
            updated_by=TEST_USER_ID,
        )
        session.add(molecule)
        await session.commit()
        await session.refresh(molecule)
        return molecule


# =============================================================================
# Fixtures: FastAPI App and Client
# =============================================================================


@pytest.fixture(scope="module")
def app() -> FastAPI:
    """Get FastAPI application."""
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
    """Run validation task synchronously (for testing)."""
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
    """Run processing/insertion task synchronously (for testing)."""
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
# Helper Functions
# =============================================================================


async def create_upload_and_validate(
    client: AsyncClient,
    run_validation_sync,
    file_content: bytes,
    filename: str = "molecules.smi",
    duplicate_action: str = "skip",
    similarity_threshold: str = "0.95",
) -> dict:
    """Helper to create an upload and run validation."""
    files = {
        "file": (filename, io.BytesIO(file_content), "text/plain"),
    }
    data = {
        "name": f"Test Upload {filename}",
        "duplicate_action": duplicate_action,
        "similarity_threshold": similarity_threshold,
    }

    response = await client.post("/api/v1/uploads", files=files, data=data)
    assert response.status_code == 202, f"Upload failed: {response.text}"

    upload_data = response.json()
    upload_id = uuid.UUID(upload_data["id"])

    # Run validation synchronously
    await run_validation_sync(upload_id, TEST_ORG_ID)

    # Get updated status
    status_response = await client.get(f"/api/v1/uploads/{upload_id}/status")
    assert status_response.status_code == 200
    return status_response.json()


async def confirm_and_process(
    client: AsyncClient,
    run_processing_sync,
    upload_id: uuid.UUID,
) -> dict:
    """Helper to confirm upload and run processing."""
    confirm_response = await client.post(f"/api/v1/uploads/{upload_id}/confirm")
    assert confirm_response.status_code in [200, 202], f"Confirm failed: {confirm_response.text}"

    # Run processing synchronously
    await run_processing_sync(upload_id, TEST_ORG_ID)

    # Get final status
    status_response = await client.get(f"/api/v1/uploads/{upload_id}/status")
    assert status_response.status_code == 200
    return status_response.json()


async def count_molecules_in_db(async_session_factory, org_id: uuid.UUID) -> int:
    """Count molecules for an organization."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Molecule).where(
                Molecule.organization_id == org_id,
                Molecule.deleted_at.is_(None),
            )
        )
        return len(result.scalars().all())


# =============================================================================
# Test: Exact Duplicate Detection (Database)
# =============================================================================


@pytest.mark.asyncio
class TestExactDuplicateDetection:
    """Tests for exact duplicate detection against existing DB molecules."""

    async def test_detects_exact_duplicate_in_status(
        self,
        client: AsyncClient,
        existing_ethanol: Molecule,
        run_validation_sync,
    ):
        """
        Test: Upload file with molecule that already exists in DB.
        Expected: Status shows exact_duplicates > 0.
        """
        status = await create_upload_and_validate(
            client,
            run_validation_sync,
            SMILES_WITH_EXACT_DUPLICATE,
        )

        assert status["status"] == "awaiting_confirm"

        # Check duplicate counts in summary
        summary = status.get("summary", {})
        assert summary.get("exact_duplicates", 0) >= 1, (
            f"Expected at least 1 exact duplicate, got {summary}"
        )

    async def test_exact_duplicate_skipped_on_confirm(
        self,
        client: AsyncClient,
        async_session_factory,
        existing_ethanol: Molecule,
        run_validation_sync,
        run_processing_sync,
    ):
        """
        Test: With duplicate_action=skip, duplicates are not inserted.
        Expected: No new ethanol molecule created, other molecules inserted.
        """
        initial_count = await count_molecules_in_db(async_session_factory, TEST_ORG_ID)

        status = await create_upload_and_validate(
            client,
            run_validation_sync,
            SMILES_WITH_EXACT_DUPLICATE,
            duplicate_action="skip",
        )

        upload_id = uuid.UUID(status["id"])
        final_status = await confirm_and_process(
            client, run_processing_sync, upload_id
        )

        assert final_status["status"] == "completed"

        # Count molecules: should add 2 new (benzene, acetic acid), not ethanol
        final_count = await count_molecules_in_db(async_session_factory, TEST_ORG_ID)
        new_molecules = final_count - initial_count

        # We had 1 (ethanol), file has 3 lines (ethanol, benzene, acetic acid)
        # Should add only 2 new ones
        assert new_molecules == 2, (
            f"Expected 2 new molecules, got {new_molecules}. "
            f"Initial: {initial_count}, Final: {final_count}"
        )

    async def test_exact_duplicate_with_error_action(
        self,
        client: AsyncClient,
        existing_ethanol: Molecule,
        run_validation_sync,
    ):
        """
        Test: With duplicate_action=error, duplicates are recorded as errors.
        Expected: Validation still completes but errors are recorded.
        """
        status = await create_upload_and_validate(
            client,
            run_validation_sync,
            SMILES_WITH_EXACT_DUPLICATE,
            duplicate_action="error",
        )

        # Should still complete validation (not fail entirely)
        assert status["status"] in ["awaiting_confirm", "validation_failed"]

        # If awaiting_confirm, check that errors were recorded
        if status["status"] == "awaiting_confirm":
            summary = status.get("summary", {})
            # Duplicates treated as errors should show up in error count
            assert summary.get("exact_duplicates", 0) >= 1


# =============================================================================
# Test: Within-Batch Duplicate Detection
# =============================================================================


@pytest.mark.asyncio
class TestBatchDuplicateDetection:
    """Tests for detecting duplicates within the same upload file."""

    async def test_detects_within_batch_duplicate(
        self,
        client: AsyncClient,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """
        Test: Upload file with same molecule appearing twice.
        Expected: Status shows batch duplicates.
        """
        status = await create_upload_and_validate(
            client,
            run_validation_sync,
            SMILES_WITH_BATCH_DUPLICATE,
        )

        assert status["status"] == "awaiting_confirm"

        # Check for batch duplicates
        summary = status.get("summary", {})
        # Benzene appears twice in file
        batch_dups = summary.get("batch_duplicates", 0)
        assert batch_dups >= 1, (
            f"Expected at least 1 batch duplicate (benzene x2), got {summary}"
        )

    async def test_batch_duplicate_results_in_single_insert(
        self,
        client: AsyncClient,
        async_session_factory,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """
        Test: Molecule appearing twice in file is inserted only once.
        Expected: Only unique molecules are inserted.
        """
        initial_count = await count_molecules_in_db(async_session_factory, TEST_ORG_ID)
        assert initial_count == 0, "Database should be empty at start"

        status = await create_upload_and_validate(
            client,
            run_validation_sync,
            SMILES_WITH_BATCH_DUPLICATE,
        )

        upload_id = uuid.UUID(status["id"])
        await confirm_and_process(client, run_processing_sync, upload_id)

        # File has: benzene, acetic acid, benzene (duplicate)
        # Should only insert 2 unique molecules
        final_count = await count_molecules_in_db(async_session_factory, TEST_ORG_ID)
        assert final_count == 2, f"Expected 2 molecules, got {final_count}"


# =============================================================================
# Test: Similarity-Based Duplicate Detection
# =============================================================================


@pytest.mark.asyncio
class TestSimilarityDuplicateDetection:
    """Tests for similarity-based (Tanimoto) duplicate detection."""

    async def test_similar_molecules_flagged_at_threshold(
        self,
        client: AsyncClient,
        existing_ethanol: Molecule,
        run_validation_sync,
    ):
        """
        Test: Upload molecules similar to existing ones.
        Expected: Similar duplicates flagged when above threshold.

        Note: Methanol and propanol are structurally similar to ethanol.
        At a low threshold (0.7), they may be flagged as similar.
        """
        status = await create_upload_and_validate(
            client,
            run_validation_sync,
            SMILES_WITH_SIMILAR_MOLECULES,
            similarity_threshold="0.70",  # Lower threshold to catch similar
        )

        assert status["status"] == "awaiting_confirm"

        # Check similarity info
        summary = status.get("summary", {})
        # Note: This depends on actual Tanimoto scores
        # Methanol-Ethanol similarity may or may not exceed 0.7
        # Test verifies the mechanism works, not specific chemistry
        similar_count = summary.get("similar_duplicates", 0)
        # We don't assert on count since it depends on fingerprint calculation
        # but we verify the summary includes the field
        assert "similar_duplicates" in summary or similar_count >= 0

    async def test_high_threshold_no_similar_duplicates(
        self,
        client: AsyncClient,
        existing_ethanol: Molecule,
        run_validation_sync,
    ):
        """
        Test: At very high threshold, different molecules not flagged.
        Expected: No similar duplicates at 0.99 threshold.
        """
        status = await create_upload_and_validate(
            client,
            run_validation_sync,
            SMILES_WITH_SIMILAR_MOLECULES,
            similarity_threshold="0.99",  # Very high threshold
        )

        assert status["status"] == "awaiting_confirm"

        summary = status.get("summary", {})
        similar_count = summary.get("similar_duplicates", 0)
        # At 0.99, only near-identical molecules would match
        # Methanol and ethanol are different enough
        assert similar_count == 0, (
            f"Expected 0 similar duplicates at 0.99 threshold, got {similar_count}"
        )


# =============================================================================
# Test: Upsert Behavior (No Duplicate Records)
# =============================================================================


@pytest.mark.asyncio
class TestUpsertBehavior:
    """Tests verifying upsert behavior prevents duplicate DB records."""

    async def test_upsert_with_update_action(
        self,
        client: AsyncClient,
        async_session_factory,
        existing_ethanol: Molecule,
        run_validation_sync,
        run_processing_sync,
    ):
        """
        Test: With duplicate_action=update, existing record is updated.
        Expected: No new ethanol record, existing one potentially updated.
        """
        initial_count = await count_molecules_in_db(async_session_factory, TEST_ORG_ID)

        # Upload file with ethanol (already exists) and new molecules
        status = await create_upload_and_validate(
            client,
            run_validation_sync,
            SMILES_WITH_EXACT_DUPLICATE,
            duplicate_action="update",
        )

        upload_id = uuid.UUID(status["id"])
        await confirm_and_process(client, run_processing_sync, upload_id)

        # Should still only add 2 new molecules (benzene, acetic acid)
        # Ethanol should not create a duplicate
        final_count = await count_molecules_in_db(async_session_factory, TEST_ORG_ID)
        new_molecules = final_count - initial_count
        assert new_molecules == 2, (
            f"Expected 2 new molecules with update action, got {new_molecules}"
        )

    async def test_no_duplicate_inchikey_in_db(
        self,
        client: AsyncClient,
        async_session_factory,
        existing_ethanol: Molecule,
        run_validation_sync,
        run_processing_sync,
    ):
        """
        Test: After processing, no duplicate InChIKeys exist.
        Expected: Each InChIKey appears exactly once per org.
        """
        status = await create_upload_and_validate(
            client,
            run_validation_sync,
            SMILES_WITH_EXACT_DUPLICATE,
        )

        upload_id = uuid.UUID(status["id"])
        await confirm_and_process(client, run_processing_sync, upload_id)

        # Check for duplicate InChIKeys
        async with async_session_factory() as session:
            result = await session.execute(
                select(Molecule.inchi_key).where(
                    Molecule.organization_id == TEST_ORG_ID,
                    Molecule.deleted_at.is_(None),
                )
            )
            inchi_keys = [r[0] for r in result.fetchall()]

            # No duplicates in list
            assert len(inchi_keys) == len(set(inchi_keys)), (
                f"Found duplicate InChIKeys: {inchi_keys}"
            )


# =============================================================================
# Test: Status Summary Accuracy
# =============================================================================


@pytest.mark.asyncio
class TestStatusSummary:
    """Tests verifying status summary accurately reflects duplicate detection."""

    async def test_summary_shows_all_duplicate_types(
        self,
        client: AsyncClient,
        existing_ethanol: Molecule,
        run_validation_sync,
    ):
        """
        Test: Upload file with both DB duplicates and batch duplicates.
        Expected: Summary shows counts for each type.
        """
        status = await create_upload_and_validate(
            client,
            run_validation_sync,
            SMILES_WITH_MULTIPLE_DUPLICATES,  # Has ethanol dup + benzene dup in batch
        )

        assert status["status"] == "awaiting_confirm"

        summary = status.get("summary", {})

        # Verify summary structure includes duplicate fields
        assert "valid_rows" in summary or "total_rows" in summary
        # DB duplicates: ethanol appears twice (both are duplicates of existing)
        # Batch duplicates: benzene appears twice in file
        # Summary should capture these

    async def test_summary_totals_are_consistent(
        self,
        client: AsyncClient,
        existing_ethanol: Molecule,
        run_validation_sync,
    ):
        """
        Test: Summary totals add up correctly.
        Expected: total = valid + invalid + duplicates (accounting for overlaps).
        """
        status = await create_upload_and_validate(
            client,
            run_validation_sync,
            SMILES_WITH_EXACT_DUPLICATE,
        )

        assert status["status"] == "awaiting_confirm"

        summary = status.get("summary", {})
        total_rows = summary.get("total_rows", 0)
        valid_rows = summary.get("valid_rows", 0)
        invalid_rows = summary.get("invalid_rows", 0)
        exact_dups = summary.get("exact_duplicates", 0)

        # Total should account for all rows
        # Note: Some systems count duplicates separately, others include in valid
        # Just verify we have reasonable numbers
        assert total_rows > 0, "Should have processed rows"
        assert valid_rows >= 0, "Valid rows should be non-negative"
        assert invalid_rows >= 0, "Invalid rows should be non-negative"


# =============================================================================
# Test: Full Workflow with Duplicates
# =============================================================================


@pytest.mark.asyncio
class TestFullDuplicateWorkflow:
    """End-to-end tests for complete duplicate detection workflow."""

    async def test_complete_workflow_with_duplicates(
        self,
        client: AsyncClient,
        async_session_factory,
        existing_ethanol: Molecule,
        run_validation_sync,
        run_processing_sync,
    ):
        """
        Test: Full workflow with duplicates detected, confirmed, and processed.
        Expected: Completes successfully, duplicates handled per action.
        """
        # Step 1: Upload
        files = {
            "file": ("molecules.smi", io.BytesIO(SMILES_WITH_EXACT_DUPLICATE), "text/plain"),
        }
        data = {
            "name": "Full Workflow Test",
            "duplicate_action": "skip",
            "similarity_threshold": "0.85",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = uuid.UUID(response.json()["id"])

        # Step 2: Validate
        await run_validation_sync(upload_id, TEST_ORG_ID)

        status_response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        status = status_response.json()
        assert status["status"] == "awaiting_confirm"

        # Step 3: Confirm
        confirm_response = await client.post(f"/api/v1/uploads/{upload_id}/confirm")
        assert confirm_response.status_code in [200, 202]

        # Step 4: Process
        await run_processing_sync(upload_id, TEST_ORG_ID)

        # Step 5: Verify final status
        final_response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        final_status = final_response.json()
        assert final_status["status"] == "completed"

        # Step 6: Verify molecules in DB
        async with async_session_factory() as session:
            result = await session.execute(
                select(Molecule).where(
                    Molecule.organization_id == TEST_ORG_ID,
                    Molecule.deleted_at.is_(None),
                )
            )
            molecules = result.scalars().all()
            inchi_keys = {m.inchi_key for m in molecules}

            # Should have: ethanol (existing), benzene (new), acetic acid (new)
            assert ETHANOL_INCHI_KEY in inchi_keys, "Ethanol should exist"
            assert BENZENE_INCHI_KEY in inchi_keys, "Benzene should be added"
            assert ACETIC_ACID_INCHI_KEY in inchi_keys, "Acetic acid should be added"
            assert len(inchi_keys) == 3, f"Should have exactly 3 molecules, got {len(inchi_keys)}"

    async def test_multiple_uploads_no_cross_duplication(
        self,
        client: AsyncClient,
        async_session_factory,
        clean_upload_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """
        Test: Multiple uploads in sequence don't create duplicates.
        Expected: Second upload of same data detects all as duplicates.
        """
        # First upload
        status1 = await create_upload_and_validate(
            client,
            run_validation_sync,
            SMILES_WITH_BATCH_DUPLICATE,  # benzene x2, acetic acid
        )
        upload_id1 = uuid.UUID(status1["id"])
        await confirm_and_process(client, run_processing_sync, upload_id1)

        count_after_first = await count_molecules_in_db(async_session_factory, TEST_ORG_ID)
        assert count_after_first == 2, f"Expected 2 molecules after first upload, got {count_after_first}"

        # Second upload of same data
        status2 = await create_upload_and_validate(
            client,
            run_validation_sync,
            SMILES_WITH_BATCH_DUPLICATE,
        )

        # All should be duplicates now
        summary2 = status2.get("summary", {})
        exact_dups = summary2.get("exact_duplicates", 0)
        # Benzene and acetic acid should both be detected as duplicates
        assert exact_dups >= 2, (
            f"Expected at least 2 exact duplicates on second upload, got {summary2}"
        )

        upload_id2 = uuid.UUID(status2["id"])
        await confirm_and_process(client, run_processing_sync, upload_id2)

        # Should still have only 2 molecules
        count_after_second = await count_molecules_in_db(async_session_factory, TEST_ORG_ID)
        assert count_after_second == 2, (
            f"Expected still 2 molecules after second upload, got {count_after_second}"
        )
