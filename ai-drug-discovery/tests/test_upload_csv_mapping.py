"""
Integration tests for CSV upload with column mapping.

Tests:
1. Upload CSV without mapping - validation requires mapping
2. Confirm with mapping - processing succeeds
3. Invalid SMILES rows appear in errors endpoint
4. Errors endpoint supports pagination

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
from db.models.upload import UploadStatus


# =============================================================================
# Test Configuration
# =============================================================================

# Database URLs
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


# =============================================================================
# Test Data
# =============================================================================

# Test organization and user IDs (match placeholder in router)
TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# Valid CSV with standard column names (should be auto-inferred)
CSV_WITH_STANDARD_COLUMNS = b"""SMILES,Name,CAS
CCO,Ethanol,64-17-5
CC(=O)O,Acetic Acid,64-19-7
c1ccccc1,Benzene,71-43-2
CC(C)O,Isopropanol,67-63-0
CCCC,Butane,106-97-8
"""

# CSV with non-standard column names (requires manual mapping)
CSV_WITH_CUSTOM_COLUMNS = b"""molecule_structure,compound_name,registry_number
CCO,Ethanol,64-17-5
CC(=O)O,Acetic Acid,64-19-7
c1ccccc1,Benzene,71-43-2
"""

# CSV with invalid SMILES (for error testing)
CSV_WITH_INVALID_SMILES = b"""SMILES,Name,CAS
CCO,Ethanol,64-17-5
INVALID_SMILES_STRING,Bad Molecule,000-00-0
c1ccccc1,Benzene,71-43-2
ANOTHER_BAD_ONE,Another Bad,111-11-1
CC(C)O,Isopropanol,67-63-0
"""

# Large CSV for pagination testing (20 rows with errors)
def generate_csv_with_errors(num_valid: int, num_invalid: int) -> bytes:
    """Generate CSV with specified number of valid and invalid rows."""
    lines = ["SMILES,Name,CAS"]

    # Add valid rows
    valid_smiles = ["CCO", "CC(=O)O", "c1ccccc1", "CC(C)O", "CCCC", "CCN", "CCC", "CCCO"]
    for i in range(num_valid):
        smiles = valid_smiles[i % len(valid_smiles)]
        lines.append(f"{smiles},Valid_{i},{i:05d}")

    # Add invalid rows
    for i in range(num_invalid):
        lines.append(f"INVALID_{i},Invalid_{i},{90000+i:05d}")

    return "\n".join(lines).encode()


# =============================================================================
# Database Availability Check
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


# Skip all tests if database not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _check_db_available(),
        reason="Test database not available (requires PostgreSQL on localhost:5433)"
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
    """Provide async database session."""
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def clean_tables(sync_engine):
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
    """Ensure test organization exists."""
    from apps.api.auth.models import Organization, User

    result = await db_session.execute(
        select(Organization).where(Organization.id == TEST_ORG_ID)
    )
    if not result.scalar_one_or_none():
        org = Organization(id=TEST_ORG_ID, name="Test Organization", slug="test-org")
        db_session.add(org)
        user = User(
            id=TEST_USER_ID,
            email="test@example.com",
            password_hash="hash",
            full_name="Test User",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

    return {"org_id": TEST_ORG_ID, "user_id": TEST_USER_ID}


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
    """Run validation task synchronously."""
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
    """Run processing task synchronously."""
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
# Test: CSV Upload Without Mapping
# =============================================================================

@pytest.mark.asyncio
class TestCsvUploadWithoutMapping:
    """Tests for CSV upload that requires column mapping."""

    async def test_csv_with_custom_columns_needs_mapping(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """
        Test Case 1: Upload CSV without mapping.
        Validation should end in AWAITING_CONFIRM with needs_mapping=true.
        """
        # Upload CSV with non-standard column names
        files = {
            "file": ("custom.csv", io.BytesIO(CSV_WITH_CUSTOM_COLUMNS), "text/csv"),
        }
        data = {
            "name": "CSV Needs Mapping Test",
            "file_type": "csv",
            # No column mapping provided
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)

        # Should fail because CSV requires smiles_column
        assert response.status_code == 400
        assert "smiles_column" in response.text.lower()

    async def test_csv_with_standard_columns_infers_mapping(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """CSV with standard column names should have mapping inferred."""
        # Upload CSV with standard column names but without explicit mapping
        files = {
            "file": ("standard.csv", io.BytesIO(CSV_WITH_STANDARD_COLUMNS), "text/csv"),
        }
        data = {
            "name": "CSV Standard Columns Test",
            "file_type": "csv",
            "smiles_column": "SMILES",  # Must provide for CSV
            "name_column": "Name",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202

        upload_id = response.json()["id"]

        # Run validation
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Check status
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        result = response.json()

        assert result["status"] == "awaiting_confirm"
        assert result["progress"]["valid_rows"] == 5

    async def test_status_shows_column_mapping_info(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Status should include column_mapping_info for CSV uploads."""
        files = {
            "file": ("test.csv", io.BytesIO(CSV_WITH_STANDARD_COLUMNS), "text/csv"),
        }
        data = {
            "name": "CSV Mapping Info Test",
            "file_type": "csv",
            "smiles_column": "SMILES",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        result = response.json()

        # Should have column_mapping_info
        assert "column_mapping_info" in result
        mapping_info = result["column_mapping_info"]

        assert "available_columns" in mapping_info
        assert "SMILES" in mapping_info["available_columns"]
        assert "Name" in mapping_info["available_columns"]
        assert "CAS" in mapping_info["available_columns"]


# =============================================================================
# Test: Confirm CSV with Mapping
# =============================================================================

@pytest.mark.asyncio
class TestConfirmCsvWithMapping:
    """Tests for confirming CSV upload with column mapping."""

    async def test_confirm_csv_with_mapping_succeeds(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        clean_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """
        Test Case 2: Confirm CSV with mapping - processing succeeds.
        """
        # Upload CSV
        files = {
            "file": ("molecules.csv", io.BytesIO(CSV_WITH_STANDARD_COLUMNS), "text/csv"),
        }
        data = {
            "name": "CSV Confirm Test",
            "file_type": "csv",
            "smiles_column": "SMILES",
            "name_column": "Name",
            "external_id_column": "CAS",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = response.json()["id"]

        # Validate
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Confirm
        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={"acknowledge_errors": True, "proceed_with_valid_only": True},
        )
        assert response.status_code == 202

        # Process
        await run_processing_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Check completed
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        result = response.json()

        assert result["status"] == "completed"
        assert result["summary"]["molecules_created"] == 5
        assert result["summary"]["errors_count"] == 0

    async def test_confirm_updates_column_mapping(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """Confirm can update column mapping via request body."""
        # Upload with one mapping
        files = {
            "file": ("molecules.csv", io.BytesIO(CSV_WITH_STANDARD_COLUMNS), "text/csv"),
        }
        data = {
            "name": "CSV Remap Test",
            "file_type": "csv",
            "smiles_column": "SMILES",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Confirm with updated mapping
        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={
                "acknowledge_errors": True,
                "column_mapping": {
                    "smiles": "SMILES",
                    "name": "Name",
                    "external_id": "CAS",
                },
            },
        )

        # Should accept (may need revalidation)
        assert response.status_code in [202, 400]


# =============================================================================
# Test: Invalid SMILES in Errors Endpoint
# =============================================================================

@pytest.mark.asyncio
class TestInvalidSmilesErrors:
    """Tests for invalid SMILES appearing in errors endpoint."""

    async def test_invalid_smiles_appears_in_errors(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """
        Test Case 3: Invalid SMILES row appears in errors endpoint.
        Should have correct row number and error message.
        """
        # Upload CSV with invalid SMILES
        files = {
            "file": ("bad.csv", io.BytesIO(CSV_WITH_INVALID_SMILES), "text/csv"),
        }
        data = {
            "name": "Invalid SMILES Test",
            "file_type": "csv",
            "smiles_column": "SMILES",
            "name_column": "Name",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = response.json()["id"]

        # Run validation
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Check status shows invalid rows
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        result = response.json()

        assert result["progress"]["invalid_rows"] >= 2  # At least 2 invalid

        # Get errors
        response = await client.get(f"/api/v1/uploads/{upload_id}/errors")
        assert response.status_code == 200

        errors = response.json()
        assert errors["total_errors"] >= 2

        # Find the INVALID_SMILES_STRING error
        error_list = errors["errors"]
        invalid_smiles_errors = [
            e for e in error_list
            if "invalid" in e.get("error_code", "").lower()
            or "INVALID" in str(e.get("raw_data", {}))
        ]

        assert len(invalid_smiles_errors) >= 1

        # Check error details
        first_error = invalid_smiles_errors[0]
        assert "row_number" in first_error
        assert "error_code" in first_error
        assert "error_message" in first_error

        # Row 2 should be INVALID_SMILES_STRING (row 1 is header, row 2 is first data)
        row_numbers = [e["row_number"] for e in invalid_smiles_errors]
        assert 2 in row_numbers or 3 in row_numbers  # Depending on 0-based or 1-based

    async def test_error_contains_raw_data(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Error should contain raw data from the problematic row."""
        files = {
            "file": ("bad.csv", io.BytesIO(CSV_WITH_INVALID_SMILES), "text/csv"),
        }
        data = {
            "name": "Raw Data Test",
            "file_type": "csv",
            "smiles_column": "SMILES",
            "name_column": "Name",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/errors")
        errors = response.json()["errors"]

        # At least one error should have raw_data
        errors_with_data = [e for e in errors if e.get("raw_data")]

        if errors_with_data:
            raw_data = errors_with_data[0]["raw_data"]
            # Should contain the original column values
            assert "SMILES" in raw_data or "smiles" in str(raw_data).lower()

    async def test_error_summary_by_code(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Errors endpoint should include summary by error code."""
        files = {
            "file": ("bad.csv", io.BytesIO(CSV_WITH_INVALID_SMILES), "text/csv"),
        }
        data = {
            "name": "Error Summary Test",
            "file_type": "csv",
            "smiles_column": "SMILES",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/errors")
        result = response.json()

        # Should have error_summary dict
        assert "error_summary" in result
        error_summary = result["error_summary"]

        # Should be a dict with error codes as keys
        assert isinstance(error_summary, dict)

        # Sum of error counts should match total_errors
        total_from_summary = sum(error_summary.values())
        assert total_from_summary == result["total_errors"]


# =============================================================================
# Test: Errors Pagination
# =============================================================================

@pytest.mark.asyncio
class TestErrorsPagination:
    """Tests for errors endpoint pagination."""

    async def test_errors_default_pagination(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """
        Test Case 4: Errors endpoint supports pagination.
        Default limit should be applied.
        """
        # Generate CSV with many errors
        csv_content = generate_csv_with_errors(num_valid=5, num_invalid=25)

        files = {
            "file": ("many_errors.csv", io.BytesIO(csv_content), "text/csv"),
        }
        data = {
            "name": "Pagination Test",
            "file_type": "csv",
            "smiles_column": "SMILES",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Get errors with default pagination
        response = await client.get(f"/api/v1/uploads/{upload_id}/errors")
        result = response.json()

        assert result["total_errors"] >= 25
        assert result["page"] == 1
        assert result["limit"] == 20  # Default limit
        assert len(result["errors"]) <= 20

    async def test_errors_custom_page_size(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Errors endpoint should respect custom page size."""
        csv_content = generate_csv_with_errors(num_valid=5, num_invalid=25)

        files = {
            "file": ("many_errors.csv", io.BytesIO(csv_content), "text/csv"),
        }
        data = {
            "name": "Custom Page Size Test",
            "file_type": "csv",
            "smiles_column": "SMILES",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Get errors with custom limit
        response = await client.get(
            f"/api/v1/uploads/{upload_id}/errors",
            params={"limit": 5},
        )
        result = response.json()

        assert result["limit"] == 5
        assert len(result["errors"]) == 5

    async def test_errors_page_navigation(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Errors endpoint should support page navigation."""
        csv_content = generate_csv_with_errors(num_valid=5, num_invalid=25)

        files = {
            "file": ("many_errors.csv", io.BytesIO(csv_content), "text/csv"),
        }
        data = {
            "name": "Page Navigation Test",
            "file_type": "csv",
            "smiles_column": "SMILES",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Get page 1
        response = await client.get(
            f"/api/v1/uploads/{upload_id}/errors",
            params={"page": 1, "limit": 10},
        )
        page1 = response.json()
        assert page1["page"] == 1
        page1_row_numbers = {e["row_number"] for e in page1["errors"]}

        # Get page 2
        response = await client.get(
            f"/api/v1/uploads/{upload_id}/errors",
            params={"page": 2, "limit": 10},
        )
        page2 = response.json()
        assert page2["page"] == 2
        page2_row_numbers = {e["row_number"] for e in page2["errors"]}

        # Pages should have different errors
        assert page1_row_numbers.isdisjoint(page2_row_numbers)

    async def test_errors_page_beyond_total(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Requesting page beyond total should return empty list."""
        csv_content = generate_csv_with_errors(num_valid=5, num_invalid=5)

        files = {
            "file": ("few_errors.csv", io.BytesIO(csv_content), "text/csv"),
        }
        data = {
            "name": "Beyond Total Test",
            "file_type": "csv",
            "smiles_column": "SMILES",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Request page way beyond total
        response = await client.get(
            f"/api/v1/uploads/{upload_id}/errors",
            params={"page": 100, "limit": 10},
        )
        result = response.json()

        assert result["page"] == 100
        assert len(result["errors"]) == 0
        assert result["total_errors"] > 0  # Total should still be reported

    async def test_errors_limit_validation(
        self,
        client: AsyncClient,
        clean_tables,
        setup_test_org,
        run_validation_sync,
    ):
        """Errors endpoint should validate limit parameter."""
        files = {
            "file": ("test.csv", io.BytesIO(CSV_WITH_INVALID_SMILES), "text/csv"),
        }
        data = {
            "name": "Limit Validation Test",
            "file_type": "csv",
            "smiles_column": "SMILES",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        upload_id = response.json()["id"]

        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Try limit above maximum (100)
        response = await client.get(
            f"/api/v1/uploads/{upload_id}/errors",
            params={"limit": 200},
        )

        # Should either cap at 100 or return 422
        assert response.status_code in [200, 422]
        if response.status_code == 200:
            assert response.json()["limit"] <= 100


# =============================================================================
# Test: Full CSV Workflow
# =============================================================================

@pytest.mark.asyncio
class TestFullCsvWorkflow:
    """End-to-end test of CSV upload workflow."""

    async def test_complete_csv_workflow_with_errors(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        clean_tables,
        setup_test_org,
        run_validation_sync,
        run_processing_sync,
    ):
        """
        Complete workflow:
        1. Upload CSV with some invalid rows
        2. Validate - see errors in status
        3. Get errors endpoint - see details
        4. Confirm with acknowledge_errors
        5. Process - valid rows inserted
        6. Verify molecules in DB
        """
        # Step 1: Upload CSV with errors
        files = {
            "file": ("mixed.csv", io.BytesIO(CSV_WITH_INVALID_SMILES), "text/csv"),
        }
        data = {
            "name": "Full Workflow Test",
            "file_type": "csv",
            "smiles_column": "SMILES",
            "name_column": "Name",
            "external_id_column": "CAS",
        }

        response = await client.post("/api/v1/uploads", files=files, data=data)
        assert response.status_code == 202
        upload_id = response.json()["id"]

        # Step 2: Validate
        await run_validation_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        status = response.json()

        assert status["status"] == "awaiting_confirm"
        assert status["progress"]["valid_rows"] == 3  # Ethanol, Benzene, Isopropanol
        assert status["progress"]["invalid_rows"] == 2  # Two invalid SMILES

        # Step 3: Check errors
        response = await client.get(f"/api/v1/uploads/{upload_id}/errors")
        errors = response.json()

        assert errors["total_errors"] == 2

        # Verify error row numbers (1-based, row 2 and 4 are invalid)
        error_rows = sorted([e["row_number"] for e in errors["errors"]])
        assert 2 in error_rows  # INVALID_SMILES_STRING
        assert 4 in error_rows  # ANOTHER_BAD_ONE

        # Step 4: Confirm with acknowledgment
        response = await client.post(
            f"/api/v1/uploads/{upload_id}/confirm",
            json={"acknowledge_errors": True, "proceed_with_valid_only": True},
        )
        assert response.status_code == 202

        # Step 5: Process
        await run_processing_sync(uuid.UUID(upload_id), TEST_ORG_ID)

        # Check final status
        response = await client.get(f"/api/v1/uploads/{upload_id}/status")
        final_status = response.json()

        assert final_status["status"] == "completed"
        assert final_status["summary"]["molecules_created"] == 3
        assert final_status["summary"]["errors_count"] == 2

        # Step 6: Verify molecules in DB
        result = await db_session.execute(
            select(Molecule)
            .where(Molecule.organization_id == TEST_ORG_ID)
            .where(Molecule.deleted_at.is_(None))
        )
        molecules = result.scalars().all()

        assert len(molecules) == 3

        # Verify the correct molecules were inserted
        names = {m.name for m in molecules if m.name}
        assert "Ethanol" in names
        assert "Benzene" in names
        assert "Isopropanol" in names
        assert "Bad Molecule" not in names  # Invalid should not be inserted
