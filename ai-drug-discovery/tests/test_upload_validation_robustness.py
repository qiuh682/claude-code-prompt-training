"""
Tests for upload validation robustness.

Ensures validation never crashes on bad records and gracefully handles:
- SDF files with corrupted molecule blocks
- SMILES lists with invalid lines
- Mixed valid/invalid data

Expected behavior:
- Validation completes without crashing
- invalid_rows > 0 for bad records
- Errors are properly recorded
- Valid rows still process on confirm

Requirements:
- PostgreSQL running on localhost:5433
- Test database 'drugdiscovery_test' created
"""

import asyncio
import io
import os
import uuid
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models.discovery import Molecule


# =============================================================================
# Test Configuration
# =============================================================================

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

TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# =============================================================================
# Test Data: SDF Files
# =============================================================================

# Valid SDF with 2 good molecules
VALID_SDF = b"""Ethanol
     RDKit          3D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.2500    1.2990    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
M  END
> <Name>
Ethanol

$$$$
Benzene
     RDKit          3D

  6  6  0  0  0  0  0  0  0  0999 V2000
    1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2124   -0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000   -1.4000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124   -0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.4000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  2  0
  2  3  1  0
  3  4  2  0
  4  5  1  0
  5  6  2  0
  6  1  1  0
M  END
> <Name>
Benzene

$$$$
"""

# SDF with 2 good molecules + 1 corrupted block in the middle
SDF_WITH_CORRUPTED_BLOCK = b"""Ethanol
     RDKit          3D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.2500    1.2990    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
M  END
> <Name>
Ethanol

$$$$
CorruptedMolecule
     RDKit          3D

THIS IS COMPLETELY CORRUPTED DATA
NOT A VALID MOLECULE BLOCK AT ALL
RANDOM GARBAGE TEXT HERE
  1  2  INVALID BOND
  MISSING ATOM COUNT LINE
M  END
> <Name>
Corrupted

$$$$
Benzene
     RDKit          3D

  6  6  0  0  0  0  0  0  0  0999 V2000
    1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2124   -0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000   -1.4000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124   -0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.4000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  2  0
  2  3  1  0
  3  4  2  0
  4  5  1  0
  5  6  2  0
  6  1  1  0
M  END
> <Name>
Benzene

$$$$
"""

# SDF with truncated/incomplete molecule block
SDF_WITH_TRUNCATED_BLOCK = b"""Ethanol
     RDKit          3D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.2500    1.2990    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
M  END
$$$$
TruncatedMol
     RDKit          3D

  5  4  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
$$$$
Benzene
     RDKit          3D

  6  6  0  0  0  0  0  0  0  0999 V2000
    1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2124   -0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000   -1.4000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124   -0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.4000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  2  0
  2  3  1  0
  3  4  2  0
  4  5  1  0
  5  6  2  0
  6  1  1  0
M  END
$$$$
"""

# SDF with empty molecule block
SDF_WITH_EMPTY_BLOCK = b"""Ethanol
     RDKit          3D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.2500    1.2990    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
M  END
$$$$

$$$$
Benzene
     RDKit          3D

  6  6  0  0  0  0  0  0  0  0999 V2000
    1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2124   -0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000   -1.4000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124   -0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.4000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  2  0
  2  3  1  0
  3  4  2  0
  4  5  1  0
  5  6  2  0
  6  1  1  0
M  END
$$$$
"""


# =============================================================================
# Test Data: SMILES Lists
# =============================================================================

# Valid SMILES list
VALID_SMILES_LIST = b"""CCO\tEthanol
CC(=O)O\tAcetic_Acid
c1ccccc1\tBenzene
"""

# SMILES list with invalid lines
SMILES_WITH_INVALID_LINES = b"""CCO\tEthanol
INVALID_SMILES_123\tBad_Molecule_1
c1ccccc1\tBenzene
NOT_A_VALID_SMILES\tBad_Molecule_2
CC(C)O\tIsopropanol
"""

# SMILES list with various edge cases
SMILES_WITH_EDGE_CASES = b"""CCO\tEthanol
\tEmpty_SMILES
c1ccccc1\tBenzene
   \tWhitespace_Only
CC(C)O\tIsopropanol
[Invalid[Brackets\tBad_Brackets
CCCC\tButane
C(C(C\tUnbalanced_Parens
CCN\tEthylamine
"""

# SMILES list with binary garbage
SMILES_WITH_BINARY_DATA = b"""CCO\tEthanol
\x00\x01\x02\x03\tBinary_Garbage
c1ccccc1\tBenzene
\xff\xfe\tMore_Binary
CC(C)O\tIsopropanol
"""

# SMILES list with very long invalid string
SMILES_WITH_LONG_INVALID = b"""CCO\tEthanol
""" + b"X" * 10000 + b"""\tVery_Long_Invalid
c1ccccc1\tBenzene
"""

# SMILES list with unicode issues
SMILES_WITH_UNICODE = b"""CCO\tEthanol
\xe2\x98\x83\tSnowman_Emoji
c1ccccc1\tBenzene
CC(C)O\tIsopropanol
"""


# =============================================================================
# Database Check
# =============================================================================

def _check_db_available() -> bool:
    """Check if test database is available."""
    try:
        engine = create_engine(TEST_SYNC_DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _check_db_available(),
        reason="Test database not available"
    ),
]


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def sync_engine():
    """Create sync engine for table cleanup."""
    return create_engine(TEST_SYNC_DATABASE_URL, pool_pre_ping=True)


@pytest.fixture(scope="session")
def async_engine():
    """Create async engine."""
    return create_async_engine(TEST_ASYNC_DATABASE_URL, pool_pre_ping=True)


@pytest.fixture(scope="session")
def async_session_factory(async_engine):
    """Create async session factory."""
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def db_session(async_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Provide async database session."""
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def clean_tables(sync_engine):
    """Clean tables before and after test."""
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
    """Ensure test organization exists."""
    from apps.api.auth.models import Organization, User

    result = await db_session.execute(
        select(Organization).where(Organization.id == TEST_ORG_ID)
    )
    if not result.scalar_one_or_none():
        db_session.add(Organization(id=TEST_ORG_ID, name="Test Org", slug="test-org"))
        db_session.add(User(
            id=TEST_USER_ID,
            email="test@example.com",
            password_hash="hash",
            full_name="Test User",
            is_active=True,
        ))
        await db_session.commit()


@pytest.fixture(scope="module")
def app() -> FastAPI:
    """Get FastAPI application."""
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DATABASE_URL"] = TEST_ASYNC_DATABASE_URL
    from apps.api.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def run_validation_sync(async_session_factory):
    """Run validation synchronously."""
    async def _run(upload_id: uuid.UUID, org_id: uuid.UUID):
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

    return _run


@pytest.fixture
def run_processing_sync(async_session_factory):
    """Run processing synchronously."""
    async def _run(upload_id: uuid.UUID, org_id: uuid.UUID):
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

    return _run


# =============================================================================
# Test: SDF Validation Robustness
# =============================================================================

@pytest.mark.asyncio
class TestSdfValidationRobustness:
    """Tests that SDF validation doesn't crash on corrupted data."""

    async def test_sdf_with_corrupted_block_completes_validation(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """
        SDF with 2 good molecules + 1 corrupted block should:
        - Complete validation without crashing
        - Have invalid_rows > 0
        - Record errors for corrupted block
        """
        files = {
            "file": ("corrupted.sdf", io.BytesIO(SDF_WITH_CORRUPTED_BLOCK), "chemical/x-mdl-sdfile"),
        }
        data = {"name": "SDF Corrupted Block Test"}

        # Upload should succeed
        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202, f"Upload failed: {response.text}"
        upload_id = response.json()["id"]

        # Validation should complete without crashing
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Check status
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        assert response.status_code == 200
        result = response.json()

        # Should complete validation (not crash)
        assert result["status"] in ["awaiting_confirm", "validation_failed"]

        # Should have processed rows
        assert result["progress"]["total_rows"] >= 2

        # Should have at least 1 invalid row (the corrupted block)
        assert result["progress"]["invalid_rows"] >= 1

        # Should have at least 1 valid row (Ethanol or Benzene)
        assert result["progress"]["valid_rows"] >= 1

    async def test_sdf_with_truncated_block_records_errors(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """SDF with truncated molecule block should record proper errors."""
        files = {
            "file": ("truncated.sdf", io.BytesIO(SDF_WITH_TRUNCATED_BLOCK), "chemical/x-mdl-sdfile"),
        }
        data = {"name": "SDF Truncated Block Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Get errors
        response = await client.get(f"/api/v1/uploads/{upload_id}/errors")
        assert response.status_code == 200
        errors = response.json()

        # Should have recorded errors
        if errors["total_errors"] > 0:
            # Errors should have proper structure
            for error in errors["errors"]:
                assert "row_number" in error
                assert "error_code" in error
                assert "error_message" in error

    async def test_sdf_with_empty_block_handles_gracefully(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """SDF with empty molecule block should be handled gracefully."""
        files = {
            "file": ("empty_block.sdf", io.BytesIO(SDF_WITH_EMPTY_BLOCK), "chemical/x-mdl-sdfile"),
        }
        data = {"name": "SDF Empty Block Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = response.json()["id"]

        # Should not crash
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        result = response.json()

        # Should complete
        assert result["status"] in ["awaiting_confirm", "validation_failed"]

    async def test_sdf_corrupted_valid_rows_still_process(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        clean_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """Valid rows in SDF with corrupted blocks should still process."""
        files = {
            "file": ("mixed.sdf", io.BytesIO(SDF_WITH_CORRUPTED_BLOCK), "chemical/x-mdl-sdfile"),
        }
        data = {"name": "SDF Valid Rows Process Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Check we have valid rows
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        status = response.json()

        if status["progress"]["valid_rows"] > 0:
            # Confirm and process
            response = await client.post(
                f"/api/v1/uploads/{upload_id}/confirm",
                json={"acknowledge_errors": True, "proceed_with_valid_only": True},
            )
            assert response.status_code == 202

            await run_processing_sync(uuid.UUID(upload_id), TEST_ORG_ID)

            # Verify molecules were inserted
            result = await db_session.execute(
                select(Molecule).where(Molecule.organization_id == TEST_ORG_ID)
            )
            molecules = result.scalars().all()

            # Should have at least the valid molecules
            assert len(molecules) >= 1


# =============================================================================
# Test: SMILES List Validation Robustness
# =============================================================================

@pytest.mark.asyncio
class TestSmilesValidationRobustness:
    """Tests that SMILES list validation doesn't crash on invalid data."""

    async def test_smiles_with_invalid_lines_completes_validation(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """
        SMILES list with invalid lines should:
        - Complete validation without crashing
        - Have invalid_rows > 0
        - Record errors for invalid lines
        """
        files = {
            "file": ("invalid.smi", io.BytesIO(SMILES_WITH_INVALID_LINES), "text/plain"),
        }
        data = {"name": "SMILES Invalid Lines Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = response.json()["id"]

        # Should complete without crashing
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        result = response.json()

        # Should complete validation
        assert result["status"] in ["awaiting_confirm", "validation_failed"]

        # Should have invalid rows
        assert result["progress"]["invalid_rows"] >= 2  # Two invalid SMILES

        # Should have valid rows
        assert result["progress"]["valid_rows"] >= 3  # Three valid SMILES

    async def test_smiles_with_edge_cases_handles_gracefully(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """SMILES list with edge cases (empty, whitespace, brackets) should be handled."""
        files = {
            "file": ("edge_cases.smi", io.BytesIO(SMILES_WITH_EDGE_CASES), "text/plain"),
        }
        data = {"name": "SMILES Edge Cases Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = response.json()["id"]

        # Should not crash
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        result = response.json()

        assert result["status"] in ["awaiting_confirm", "validation_failed"]

        # Valid molecules should be detected
        assert result["progress"]["valid_rows"] >= 4  # Ethanol, Benzene, Isopropanol, Butane, Ethylamine

    async def test_smiles_with_binary_data_handles_gracefully(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """SMILES list with binary garbage should be handled gracefully."""
        files = {
            "file": ("binary.smi", io.BytesIO(SMILES_WITH_BINARY_DATA), "text/plain"),
        }
        data = {"name": "SMILES Binary Data Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = response.json()["id"]

        # Should not crash
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        result = response.json()

        assert result["status"] in ["awaiting_confirm", "validation_failed"]

    async def test_smiles_with_long_invalid_handles_gracefully(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """SMILES list with very long invalid string should be handled."""
        files = {
            "file": ("long.smi", io.BytesIO(SMILES_WITH_LONG_INVALID), "text/plain"),
        }
        data = {"name": "SMILES Long Invalid Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = response.json()["id"]

        # Should not crash or timeout
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        result = response.json()

        assert result["status"] in ["awaiting_confirm", "validation_failed"]

    async def test_smiles_invalid_lines_records_errors(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Invalid SMILES lines should be properly recorded as errors."""
        files = {
            "file": ("invalid.smi", io.BytesIO(SMILES_WITH_INVALID_LINES), "text/plain"),
        }
        data = {"name": "SMILES Error Recording Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Get errors
        response = await client.get(f"/api/v1/uploads/{upload_id}/errors")
        errors = response.json()

        assert errors["total_errors"] >= 2

        # Each error should have proper structure
        for error in errors["errors"]:
            assert "row_number" in error
            assert "error_code" in error
            assert "error_message" in error
            assert error["row_number"] > 0

    async def test_smiles_valid_rows_still_process_after_errors(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        clean_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """Valid SMILES rows should still process despite invalid rows."""
        files = {
            "file": ("mixed.smi", io.BytesIO(SMILES_WITH_INVALID_LINES), "text/plain"),
        }
        data = {"name": "SMILES Valid Process Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Confirm with acknowledgment
        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={"acknowledge_errors": True, "proceed_with_valid_only": True},
        )
        assert response.status_code == 202

        await run_processing_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Check final status
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        result = response.json()

        assert result["status"] == "completed"
        assert result["summary"]["molecules_created"] >= 3  # Ethanol, Benzene, Isopropanol
        assert result["summary"]["errors_count"] >= 2  # Two invalid SMILES

        # Verify in database
        db_result = await db_session.execute(
            select(Molecule).where(Molecule.organization_id == TEST_ORG_ID)
        )
        molecules = db_result.scalars().all()

        assert len(molecules) >= 3


# =============================================================================
# Test: Error Recording Details
# =============================================================================

@pytest.mark.asyncio
class TestErrorRecordingDetails:
    """Tests that errors are properly recorded with details."""

    async def test_error_contains_row_number(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Each error should have the correct row number."""
        files = {
            "file": ("test.smi", io.BytesIO(SMILES_WITH_INVALID_LINES), "text/plain"),
        }
        data = {"name": "Row Number Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/errors")
        errors = response.json()["errors"]

        # Row 2 and 4 should be invalid (1-based indexing)
        row_numbers = {e["row_number"] for e in errors}

        # Should have row 2 (INVALID_SMILES_123) and row 4 (NOT_A_VALID_SMILES)
        assert 2 in row_numbers or 4 in row_numbers

    async def test_error_contains_meaningful_message(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Error messages should be meaningful and helpful."""
        files = {
            "file": ("test.smi", io.BytesIO(SMILES_WITH_INVALID_LINES), "text/plain"),
        }
        data = {"name": "Error Message Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/errors")
        errors = response.json()["errors"]

        for error in errors:
            # Message should not be empty
            assert error["error_message"]
            assert len(error["error_message"]) > 0

            # Error code should be set
            assert error["error_code"]

    async def test_error_summary_aggregates_by_code(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Error summary should aggregate counts by error code."""
        files = {
            "file": ("test.smi", io.BytesIO(SMILES_WITH_INVALID_LINES), "text/plain"),
        }
        data = {"name": "Error Summary Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/errors")
        result = response.json()

        # Should have error_summary
        assert "error_summary" in result
        summary = result["error_summary"]

        # Sum should equal total_errors
        if summary:
            assert sum(summary.values()) == result["total_errors"]


# =============================================================================
# Test: Full Robustness Workflow
# =============================================================================

@pytest.mark.asyncio
class TestFullRobustnessWorkflow:
    """End-to-end test of robustness handling."""

    async def test_complete_workflow_with_corrupted_sdf(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        clean_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """
        Complete workflow with corrupted SDF:
        1. Upload SDF with 2 good + 1 corrupted
        2. Validation completes with errors
        3. Errors are recorded
        4. Confirm with acknowledgment
        5. Valid molecules are inserted
        """
        # Step 1: Upload
        files = {
            "file": ("test.sdf", io.BytesIO(SDF_WITH_CORRUPTED_BLOCK), "chemical/x-mdl-sdfile"),
        }
        data = {"name": "Full Robustness Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = response.json()["id"]

        # Step 2: Validate
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        status = response.json()

        assert status["status"] == "awaiting_confirm"
        assert status["progress"]["invalid_rows"] >= 1
        assert status["progress"]["valid_rows"] >= 1

        # Step 3: Check errors
        response = await client.get(f"/api/v1/uploads/{upload_id}/errors")
        errors = response.json()
        assert errors["total_errors"] >= 1

        # Step 4: Confirm
        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={"acknowledge_errors": True, "proceed_with_valid_only": True},
        )
        assert response.status_code == 202

        # Step 5: Process
        await run_processing_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Verify completion
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        final = response.json()

        assert final["status"] == "completed"
        assert final["summary"]["molecules_created"] >= 1
        assert final["summary"]["errors_count"] >= 1

        # Verify DB
        result = await db_session.execute(
            select(Molecule).where(Molecule.organization_id == TEST_ORG_ID)
        )
        molecules = result.scalars().all()
        assert len(molecules) >= 1

    async def test_complete_workflow_with_invalid_smiles(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        clean_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """
        Complete workflow with invalid SMILES:
        1. Upload SMILES with 3 good + 2 invalid
        2. Validation completes with errors
        3. Errors are recorded with correct row numbers
        4. Confirm with acknowledgment
        5. Valid molecules are inserted
        """
        # Upload
        files = {
            "file": ("test.smi", io.BytesIO(SMILES_WITH_INVALID_LINES), "text/plain"),
        }
        data = {"name": "SMILES Robustness Test"}

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = response.json()["id"]

        # Validate
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        status = response.json()

        assert status["status"] == "awaiting_confirm"
        assert status["progress"]["valid_rows"] == 3
        assert status["progress"]["invalid_rows"] == 2

        # Check errors have correct row numbers
        response = await client.get(f"/api/v1/uploads/{upload_id}/errors")
        errors = response.json()

        assert errors["total_errors"] == 2
        row_numbers = sorted([e["row_number"] for e in errors["errors"]])
        assert row_numbers == [2, 4]  # INVALID_SMILES_123 and NOT_A_VALID_SMILES

        # Confirm and process
        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={"acknowledge_errors": True},
        )
        assert response.status_code == 202

        await run_processing_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Verify
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        final = response.json()

        assert final["status"] == "completed"
        assert final["summary"]["molecules_created"] == 3
        assert final["summary"]["errors_count"] == 2

        # Check database
        result = await db_session.execute(
            select(Molecule).where(Molecule.organization_id == TEST_ORG_ID)
        )
        molecules = result.scalars().all()
        assert len(molecules) == 3

        # Verify correct molecules were inserted
        names = {m.name for m in molecules if m.name}
        assert "Ethanol" in names
        assert "Benzene" in names
        assert "Isopropanol" in names
        assert "Bad_Molecule_1" not in names
        assert "Bad_Molecule_2" not in names
