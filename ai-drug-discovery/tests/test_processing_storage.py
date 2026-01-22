"""
Integration tests for storing computed properties.

Tests the full pipeline:
1. Process molecule input -> upsert by InChIKey -> record exists in DB
2. Descriptor fields persisted (MW/LogP/TPSA/HBD/HBA not null)
3. Fingerprints stored and retrievable

Uses test database fixtures with async SQLAlchemy.

NOTE: These tests require a running PostgreSQL database.
Run with: docker-compose up -d postgres
Skip with: pytest tests/test_processing_storage.py -m "not integration"
"""

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


# Check if database is available
def _check_db_available() -> bool:
    """Check if test database is accessible."""
    try:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine

        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5433/drugdiscovery_test",
        )
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        async def check():
            engine = create_async_engine(database_url)
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                return True
            except Exception:
                return False
            finally:
                await engine.dispose()

        return asyncio.get_event_loop().run_until_complete(check())
    except Exception:
        return False


# Skip all tests if database not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _check_db_available(),
        reason="Test database not available. Start with: docker-compose up -d postgres"
    ),
]

from packages.chemistry.features import (
    calculate_descriptors,
    calculate_maccs_fingerprint,
    calculate_morgan_fingerprint,
    calculate_rdkit_fingerprint,
)
from packages.chemistry.molecule_repository import (
    MoleculeData,
    MoleculeRepository,
    UpsertResult,
    process_and_store_molecule,
)
from packages.chemistry.smiles import canonicalize_smiles


# =============================================================================
# Test Molecules
# =============================================================================

ETHANOL_SMILES = "CCO"
ASPIRIN_SMILES = "CC(=O)Oc1ccccc1C(=O)O"
CAFFEINE_SMILES = "Cn1cnc2n(C)c(=O)n(C)c(=O)c12"


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def async_engine():
    """Create async database engine for tests."""
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5433/drugdiscovery_test",
    )
    # Convert to async URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url, echo=False)
    return engine


@pytest.fixture(scope="module")
def async_session_factory(async_engine):
    """Create async session factory."""
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def db_session(async_session_factory) -> AsyncSession:
    """Provide an async database session with cleanup."""
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def test_org_id() -> uuid.UUID:
    """Provide a test organization ID."""
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def test_user_id() -> uuid.UUID:
    """Provide a test user ID."""
    return uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
async def clean_molecules(async_session_factory, test_org_id):
    """Clean up molecules table before and after test."""
    async def cleanup():
        async with async_session_factory() as session:
            # Delete molecules for test org
            await session.execute(
                text("DELETE FROM molecule_fingerprints WHERE molecule_id IN "
                     "(SELECT id FROM molecules WHERE organization_id = :org_id)"),
                {"org_id": str(test_org_id)},
            )
            await session.execute(
                text("DELETE FROM molecules WHERE organization_id = :org_id"),
                {"org_id": str(test_org_id)},
            )
            await session.commit()

    await cleanup()
    yield
    await cleanup()


@pytest.fixture
async def setup_test_org(async_session_factory, test_org_id, test_user_id):
    """Ensure test organization and user exist."""
    async with async_session_factory() as session:
        # Check if org exists
        result = await session.execute(
            text("SELECT id FROM organizations WHERE id = :org_id"),
            {"org_id": str(test_org_id)},
        )
        if result.scalar_one_or_none() is None:
            # Create test org
            await session.execute(
                text("""
                    INSERT INTO organizations (id, name, slug, created_at, updated_at)
                    VALUES (:org_id, 'Test Org', 'test-org', NOW(), NOW())
                    ON CONFLICT (id) DO NOTHING
                """),
                {"org_id": str(test_org_id)},
            )

        # Check if user exists
        result = await session.execute(
            text("SELECT id FROM users WHERE id = :user_id"),
            {"user_id": str(test_user_id)},
        )
        if result.scalar_one_or_none() is None:
            # Create test user
            await session.execute(
                text("""
                    INSERT INTO users (id, email, password_hash, created_at, updated_at)
                    VALUES (:user_id, 'test@example.com', 'hash', NOW(), NOW())
                    ON CONFLICT (id) DO NOTHING
                """),
                {"user_id": str(test_user_id)},
            )

        await session.commit()
    yield


# =============================================================================
# Test: Process and Store Molecule
# =============================================================================

class TestProcessAndStoreMolecule:
    """
    Test that processing a molecule creates a record in the database.
    """

    @pytest.mark.asyncio
    async def test_upsert_creates_record_by_inchikey(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """Process molecule input -> upsert by InChIKey -> record exists in DB."""
        # Arrange: Canonicalize and prepare data
        canon_result = canonicalize_smiles(ETHANOL_SMILES, standardize=True)
        descriptors = calculate_descriptors(ETHANOL_SMILES)

        mol_data = MoleculeData(
            canonical_smiles=canon_result.canonical_smiles,
            inchi_key=canon_result.inchikey,
            name="Ethanol",
            molecular_weight=descriptors.molecular_weight,
            logp=descriptors.logp,
            tpsa=descriptors.tpsa,
            hbd=descriptors.hbd,
            hba=descriptors.hba,
        )

        # Act: Upsert molecule
        repo = MoleculeRepository(db_session, test_org_id, test_user_id)
        result = await repo.upsert(mol_data)
        await db_session.commit()

        # Assert: Record was created
        assert result.created is True
        assert result.molecule_id is not None
        assert result.inchi_key == canon_result.inchikey

        # Verify record exists in DB
        found = await repo.find_by_inchikey(canon_result.inchikey)
        assert found is not None
        assert found.canonical_smiles == "CCO"
        assert found.inchi_key == canon_result.inchikey

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_by_inchikey(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """Second upsert with same InChIKey updates existing record."""
        # Arrange
        canon_result = canonicalize_smiles(ETHANOL_SMILES)
        descriptors = calculate_descriptors(ETHANOL_SMILES)

        mol_data = MoleculeData(
            canonical_smiles=canon_result.canonical_smiles,
            inchi_key=canon_result.inchikey,
            name="Ethanol",
            molecular_weight=descriptors.molecular_weight,
        )

        repo = MoleculeRepository(db_session, test_org_id, test_user_id)

        # First upsert (create)
        result1 = await repo.upsert(mol_data)
        await db_session.commit()
        assert result1.created is True

        # Second upsert (update)
        mol_data.name = "Ethyl Alcohol"  # Changed name
        result2 = await repo.upsert(mol_data)
        await db_session.commit()

        # Assert: Same molecule ID, updated
        assert result2.created is False
        assert result2.molecule_id == result1.molecule_id

        # Verify name was updated
        found = await repo.find_by_inchikey(canon_result.inchikey)
        assert found.name == "Ethyl Alcohol"


# =============================================================================
# Test: Descriptor Fields Persisted
# =============================================================================

class TestDescriptorFieldsPersisted:
    """
    Test that descriptor fields (MW/LogP/TPSA/HBD/HBA) are persisted and not null.
    """

    @pytest.mark.asyncio
    async def test_molecular_weight_persisted(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """Molecular weight is stored and not null."""
        # Arrange
        canon_result = canonicalize_smiles(ETHANOL_SMILES)
        descriptors = calculate_descriptors(ETHANOL_SMILES)

        mol_data = MoleculeData(
            canonical_smiles=canon_result.canonical_smiles,
            inchi_key=canon_result.inchikey,
            molecular_weight=descriptors.molecular_weight,
        )

        repo = MoleculeRepository(db_session, test_org_id, test_user_id)
        result = await repo.upsert(mol_data)
        await db_session.commit()

        # Assert
        found = await repo.find_by_inchikey(canon_result.inchikey)
        assert found.molecular_weight is not None
        assert float(found.molecular_weight) == pytest.approx(46.07, abs=0.1)

    @pytest.mark.asyncio
    async def test_logp_persisted(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """LogP is stored and not null."""
        canon_result = canonicalize_smiles(ETHANOL_SMILES)
        descriptors = calculate_descriptors(ETHANOL_SMILES)

        mol_data = MoleculeData(
            canonical_smiles=canon_result.canonical_smiles,
            inchi_key=canon_result.inchikey,
            logp=descriptors.logp,
        )

        repo = MoleculeRepository(db_session, test_org_id, test_user_id)
        await repo.upsert(mol_data)
        await db_session.commit()

        found = await repo.find_by_inchikey(canon_result.inchikey)
        assert found.logp is not None

    @pytest.mark.asyncio
    async def test_tpsa_persisted(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """TPSA is stored and not null."""
        canon_result = canonicalize_smiles(ETHANOL_SMILES)
        descriptors = calculate_descriptors(ETHANOL_SMILES)

        mol_data = MoleculeData(
            canonical_smiles=canon_result.canonical_smiles,
            inchi_key=canon_result.inchikey,
            tpsa=descriptors.tpsa,
        )

        repo = MoleculeRepository(db_session, test_org_id, test_user_id)
        await repo.upsert(mol_data)
        await db_session.commit()

        found = await repo.find_by_inchikey(canon_result.inchikey)
        assert found.tpsa is not None
        assert float(found.tpsa) == pytest.approx(20.23, abs=1.0)

    @pytest.mark.asyncio
    async def test_hbd_hba_persisted(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """HBD and HBA are stored and not null."""
        canon_result = canonicalize_smiles(ETHANOL_SMILES)
        descriptors = calculate_descriptors(ETHANOL_SMILES)

        mol_data = MoleculeData(
            canonical_smiles=canon_result.canonical_smiles,
            inchi_key=canon_result.inchikey,
            hbd=descriptors.hbd,
            hba=descriptors.hba,
        )

        repo = MoleculeRepository(db_session, test_org_id, test_user_id)
        await repo.upsert(mol_data)
        await db_session.commit()

        found = await repo.find_by_inchikey(canon_result.inchikey)
        assert found.hbd is not None
        assert found.hba is not None
        assert found.hbd == 1  # Ethanol has 1 OH
        assert found.hba == 1  # Ethanol has 1 O

    @pytest.mark.asyncio
    async def test_all_descriptors_persisted_for_aspirin(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """All descriptors are persisted for a complex molecule (aspirin)."""
        canon_result = canonicalize_smiles(ASPIRIN_SMILES)
        descriptors = calculate_descriptors(ASPIRIN_SMILES)

        mol_data = MoleculeData(
            canonical_smiles=canon_result.canonical_smiles,
            inchi_key=canon_result.inchikey,
            name="Aspirin",
            molecular_weight=descriptors.molecular_weight,
            logp=descriptors.logp,
            tpsa=descriptors.tpsa,
            hbd=descriptors.hbd,
            hba=descriptors.hba,
            rotatable_bonds=descriptors.num_rotatable_bonds,
            num_rings=descriptors.num_rings,
            num_aromatic_rings=descriptors.num_aromatic_rings,
            num_heavy_atoms=descriptors.num_heavy_atoms,
            fraction_sp3=descriptors.fraction_sp3,
            lipinski_violations=descriptors.lipinski_violations(),
        )

        repo = MoleculeRepository(db_session, test_org_id, test_user_id)
        await repo.upsert(mol_data)
        await db_session.commit()

        found = await repo.find_by_inchikey(canon_result.inchikey)

        # All descriptors should be not null
        assert found.molecular_weight is not None
        assert found.logp is not None
        assert found.tpsa is not None
        assert found.hbd is not None
        assert found.hba is not None
        assert found.rotatable_bonds is not None
        assert found.num_rings is not None
        assert found.num_aromatic_rings is not None
        assert found.num_heavy_atoms is not None
        assert found.fraction_sp3 is not None
        assert found.lipinski_violations is not None

        # Verify some specific values
        assert float(found.molecular_weight) == pytest.approx(180.16, abs=0.1)
        assert found.num_rings == 1
        assert found.num_aromatic_rings == 1


# =============================================================================
# Test: Fingerprints Stored and Retrievable
# =============================================================================

class TestFingerprintsStoredAndRetrievable:
    """
    Test that fingerprints are stored in the database and can be retrieved.
    """

    @pytest.mark.asyncio
    async def test_morgan_fingerprint_stored(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """Morgan fingerprint is stored in molecules table."""
        canon_result = canonicalize_smiles(ETHANOL_SMILES)
        fp_morgan = calculate_morgan_fingerprint(ETHANOL_SMILES)

        mol_data = MoleculeData(
            canonical_smiles=canon_result.canonical_smiles,
            inchi_key=canon_result.inchikey,
            fingerprint_morgan=fp_morgan.bytes_data,
        )

        repo = MoleculeRepository(db_session, test_org_id, test_user_id)
        await repo.upsert(mol_data)
        await db_session.commit()

        found = await repo.find_by_inchikey(canon_result.inchikey)

        assert found.fingerprint_morgan is not None
        assert len(found.fingerprint_morgan) == 256  # 2048 bits / 8
        assert found.fingerprint_morgan == fp_morgan.bytes_data

    @pytest.mark.asyncio
    async def test_maccs_fingerprint_stored(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """MACCS fingerprint is stored in molecules table."""
        canon_result = canonicalize_smiles(ETHANOL_SMILES)
        fp_maccs = calculate_maccs_fingerprint(ETHANOL_SMILES)

        mol_data = MoleculeData(
            canonical_smiles=canon_result.canonical_smiles,
            inchi_key=canon_result.inchikey,
            fingerprint_maccs=fp_maccs.bytes_data,
        )

        repo = MoleculeRepository(db_session, test_org_id, test_user_id)
        await repo.upsert(mol_data)
        await db_session.commit()

        found = await repo.find_by_inchikey(canon_result.inchikey)

        assert found.fingerprint_maccs is not None
        assert len(found.fingerprint_maccs) == 21  # 167 bits / 8 rounded up
        assert found.fingerprint_maccs == fp_maccs.bytes_data

    @pytest.mark.asyncio
    async def test_rdkit_fingerprint_stored(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """RDKit fingerprint is stored in molecules table."""
        canon_result = canonicalize_smiles(ETHANOL_SMILES)
        fp_rdkit = calculate_rdkit_fingerprint(ETHANOL_SMILES)

        mol_data = MoleculeData(
            canonical_smiles=canon_result.canonical_smiles,
            inchi_key=canon_result.inchikey,
            fingerprint_rdkit=fp_rdkit.bytes_data,
        )

        repo = MoleculeRepository(db_session, test_org_id, test_user_id)
        await repo.upsert(mol_data)
        await db_session.commit()

        found = await repo.find_by_inchikey(canon_result.inchikey)

        assert found.fingerprint_rdkit is not None
        assert len(found.fingerprint_rdkit) == 256  # 2048 bits / 8
        assert found.fingerprint_rdkit == fp_rdkit.bytes_data

    @pytest.mark.asyncio
    async def test_all_fingerprints_stored_together(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """All three fingerprints can be stored and retrieved together."""
        canon_result = canonicalize_smiles(CAFFEINE_SMILES)
        fp_morgan = calculate_morgan_fingerprint(CAFFEINE_SMILES)
        fp_maccs = calculate_maccs_fingerprint(CAFFEINE_SMILES)
        fp_rdkit = calculate_rdkit_fingerprint(CAFFEINE_SMILES)

        mol_data = MoleculeData(
            canonical_smiles=canon_result.canonical_smiles,
            inchi_key=canon_result.inchikey,
            name="Caffeine",
            fingerprint_morgan=fp_morgan.bytes_data,
            fingerprint_maccs=fp_maccs.bytes_data,
            fingerprint_rdkit=fp_rdkit.bytes_data,
        )

        repo = MoleculeRepository(db_session, test_org_id, test_user_id)
        await repo.upsert(mol_data)
        await db_session.commit()

        found = await repo.find_by_inchikey(canon_result.inchikey)

        # All fingerprints should be stored
        assert found.fingerprint_morgan is not None
        assert found.fingerprint_maccs is not None
        assert found.fingerprint_rdkit is not None

        # All should match original
        assert found.fingerprint_morgan == fp_morgan.bytes_data
        assert found.fingerprint_maccs == fp_maccs.bytes_data
        assert found.fingerprint_rdkit == fp_rdkit.bytes_data

    @pytest.mark.asyncio
    async def test_extended_fingerprints_stored_in_separate_table(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """Extended fingerprints are stored in molecule_fingerprints table."""
        canon_result = canonicalize_smiles(ETHANOL_SMILES)
        fp_morgan = calculate_morgan_fingerprint(ETHANOL_SMILES)
        fp_maccs = calculate_maccs_fingerprint(ETHANOL_SMILES)

        mol_data = MoleculeData(
            canonical_smiles=canon_result.canonical_smiles,
            inchi_key=canon_result.inchikey,
        )

        repo = MoleculeRepository(db_session, test_org_id, test_user_id)
        result = await repo.upsert(mol_data)

        # Store extended fingerprints
        count = await repo.store_fingerprints(
            result.molecule_id,
            {
                "morgan": (fp_morgan.bytes_data, {"radius": 2, "num_bits": 2048}),
                "maccs": (fp_maccs.bytes_data, {"num_bits": 167}),
            },
        )
        await db_session.commit()

        assert count == 2

        # Retrieve and verify
        molecule, fingerprints = await repo.get_molecule_with_fingerprints(result.molecule_id)

        assert molecule is not None
        assert len(fingerprints) == 2

        fp_types = {fp.fingerprint_type for fp in fingerprints}
        assert "morgan" in fp_types
        assert "maccs" in fp_types

        # Verify morgan fingerprint details
        morgan_fp = next(fp for fp in fingerprints if fp.fingerprint_type == "morgan")
        assert morgan_fp.fingerprint_bytes == fp_morgan.bytes_data
        assert morgan_fp.num_bits == 2048
        assert morgan_fp.radius == 2
        assert morgan_fp.num_on_bits > 0


# =============================================================================
# Test: Full Pipeline Integration
# =============================================================================

class TestFullPipelineIntegration:
    """
    Test the complete process_and_store_molecule function.
    """

    @pytest.mark.asyncio
    async def test_process_and_store_molecule_full_pipeline(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """Full pipeline: process molecule -> compute descriptors/fingerprints -> store."""
        # Act: Use the high-level function
        result = await process_and_store_molecule(
            session=db_session,
            organization_id=test_org_id,
            user_id=test_user_id,
            smiles=ASPIRIN_SMILES,
            name="Aspirin",
            compute_fingerprints=True,
            store_extended_fingerprints=False,
        )
        await db_session.commit()

        # Assert: Record created
        assert result.created is True
        assert result.molecule_id is not None

        # Verify in database
        repo = MoleculeRepository(db_session, test_org_id, test_user_id)
        found = await repo.find_by_inchikey(result.inchi_key)

        assert found is not None
        assert found.name == "Aspirin"

        # Descriptors populated
        assert found.molecular_weight is not None
        assert found.logp is not None
        assert found.tpsa is not None
        assert found.hbd is not None
        assert found.hba is not None

        # Fingerprints populated
        assert found.fingerprint_morgan is not None
        assert found.fingerprint_maccs is not None
        assert found.fingerprint_rdkit is not None

    @pytest.mark.asyncio
    async def test_process_and_store_with_extended_fingerprints(
        self,
        db_session: AsyncSession,
        test_org_id: uuid.UUID,
        test_user_id: uuid.UUID,
        setup_test_org,
        clean_molecules,
    ):
        """Full pipeline with extended fingerprints in separate table."""
        result = await process_and_store_molecule(
            session=db_session,
            organization_id=test_org_id,
            user_id=test_user_id,
            smiles=CAFFEINE_SMILES,
            name="Caffeine",
            compute_fingerprints=True,
            store_extended_fingerprints=True,
        )
        await db_session.commit()

        # Verify extended fingerprints
        repo = MoleculeRepository(db_session, test_org_id, test_user_id)
        molecule, fingerprints = await repo.get_molecule_with_fingerprints(result.molecule_id)

        assert molecule is not None
        assert len(fingerprints) == 3  # morgan, maccs, rdkit

        fp_types = {fp.fingerprint_type for fp in fingerprints}
        assert fp_types == {"morgan", "maccs", "rdkit"}
