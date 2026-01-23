"""
Tests for audit fields on Task 1.3 models.

Verifies:
- created_at is automatically set on insert
- updated_at is automatically set on insert and changes on update
- created_by is set to the user who created the record
- updated_by is set to the user who last modified the record
- Soft delete updates updated_by to the deleting user

Test Scenarios:
1) Create a Molecule as userA -> created_by=userA, created_at set
2) Update Molecule as userB -> updated_by=userB, updated_at increases
3) Soft delete as userB -> updated_by=userB

Usage:
    DATABASE_URL_TEST=postgresql://postgres:postgres@localhost:5433/drugdiscovery_test \
    pytest tests/test_audit_fields.py -v
"""

import hashlib
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.auth.models import Membership, Organization, User, UserRole
from apps.api.auth.security import hash_password
from db.models.discovery import (
    Assay,
    Molecule,
    Project,
    Target,
)


# =============================================================================
# Test Data
# =============================================================================

TEST_PASSWORD = "SecureTestPass123"


def smiles_hash(smiles: str) -> str:
    """Compute SHA-256 hash of SMILES string."""
    return hashlib.sha256(smiles.encode()).hexdigest()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def audit_setup(test_session_factory):
    """
    Set up organization and two users for audit field tests.

    Creates:
    - 1 Organization
    - 2 Users (userA = admin, userB = researcher)
    - Both users have membership in the org

    Returns dict with org, users, and session.
    """
    db: Session = test_session_factory()

    try:
        # =================================================================
        # Create Organization
        # =================================================================
        org = Organization(
            id=uuid4(),
            name="Audit Test Org",
            slug=f"audit-test-{uuid4().hex[:8]}",
        )
        db.add(org)
        db.flush()

        # =================================================================
        # Create User A (Admin - will create records)
        # =================================================================
        user_a = User(
            id=uuid4(),
            email=f"user-a-{uuid4().hex[:8]}@auditorg.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="User A (Creator)",
            is_active=True,
        )
        db.add(user_a)
        db.flush()

        membership_a = Membership(
            user_id=user_a.id,
            organization_id=org.id,
            role=UserRole.ADMIN,
        )
        db.add(membership_a)
        db.flush()

        # =================================================================
        # Create User B (Researcher - will update records)
        # =================================================================
        user_b = User(
            id=uuid4(),
            email=f"user-b-{uuid4().hex[:8]}@auditorg.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="User B (Updater)",
            is_active=True,
        )
        db.add(user_b)
        db.flush()

        membership_b = Membership(
            user_id=user_b.id,
            organization_id=org.id,
            role=UserRole.RESEARCHER,
        )
        db.add(membership_b)
        db.flush()

        db.commit()

        yield {
            "db": db,
            "org": org,
            "user_a": user_a,
            "user_b": user_b,
        }

    finally:
        # Cleanup
        try:
            db.execute(text("SET session_replication_role = 'replica';"))
            db.execute(
                text("DELETE FROM assays WHERE organization_id = :org_id"),
                {"org_id": org.id}
            )
            db.execute(
                text("DELETE FROM molecules WHERE organization_id = :org_id"),
                {"org_id": org.id}
            )
            db.execute(
                text("DELETE FROM targets WHERE organization_id = :org_id"),
                {"org_id": org.id}
            )
            db.execute(
                text("DELETE FROM projects WHERE organization_id = :org_id"),
                {"org_id": org.id}
            )
            db.execute(
                text("DELETE FROM memberships WHERE organization_id = :org_id"),
                {"org_id": org.id}
            )
            db.execute(
                text("DELETE FROM users WHERE id IN (:user_a_id, :user_b_id)"),
                {"user_a_id": user_a.id, "user_b_id": user_b.id}
            )
            db.execute(
                text("DELETE FROM organizations WHERE id = :org_id"),
                {"org_id": org.id}
            )
            db.execute(text("SET session_replication_role = 'origin';"))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


# =============================================================================
# Helper: Create Molecule
# =============================================================================


def create_molecule(
    db: Session,
    org_id,
    user_id,
    name: str = "Test Molecule",
    smiles: str = "CCO",
) -> Molecule:
    """Helper to create a molecule with audit fields set."""
    molecule = Molecule(
        id=uuid4(),
        organization_id=org_id,
        canonical_smiles=smiles,
        inchi_key=f"TEST{uuid4().hex[:23].upper()}",
        smiles_hash=smiles_hash(smiles),
        name=name,
        created_by=user_id,
    )
    db.add(molecule)
    db.flush()
    return molecule


# =============================================================================
# Test: created_at Field
# =============================================================================


class TestCreatedAtField:
    """Tests for created_at timestamp field."""

    def test_created_at_is_set_on_insert(self, audit_setup):
        """created_at is automatically set when record is inserted."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        before_create = datetime.now(UTC)

        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        after_create = datetime.now(UTC)

        assert molecule.created_at is not None
        # Allow small time window
        assert molecule.created_at >= before_create - timedelta(seconds=2)
        assert molecule.created_at <= after_create + timedelta(seconds=2)

    def test_created_at_does_not_change_on_update(self, audit_setup):
        """created_at remains unchanged when record is updated."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        original_created_at = molecule.created_at

        # Small delay to ensure timestamps differ
        time.sleep(0.05)

        # Update the molecule
        molecule.name = "Updated Name"
        molecule.updated_by = user_a.id
        db.add(molecule)
        db.commit()

        assert molecule.created_at == original_created_at

    def test_created_at_persists_after_refetch(self, audit_setup):
        """created_at is properly persisted to database."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        molecule = create_molecule(db, org.id, user_a.id)
        molecule_id = molecule.id
        db.commit()

        original_created_at = molecule.created_at

        # Clear cache and refetch
        db.expire_all()
        refetched = db.get(Molecule, molecule_id)

        assert refetched.created_at == original_created_at


# =============================================================================
# Test: updated_at Field
# =============================================================================


class TestUpdatedAtField:
    """Tests for updated_at timestamp field."""

    def test_updated_at_is_set_on_insert(self, audit_setup):
        """updated_at is set when record is first inserted."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        assert molecule.updated_at is not None

    def test_updated_at_equals_created_at_initially(self, audit_setup):
        """On insert, updated_at equals created_at (or is very close)."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        # They should be equal or within milliseconds
        diff = abs((molecule.updated_at - molecule.created_at).total_seconds())
        assert diff < 1.0, "updated_at and created_at should be nearly equal on insert"

    def test_updated_at_changes_on_update(self, audit_setup):
        """updated_at changes when record is modified."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        original_updated_at = molecule.updated_at

        # Small delay
        time.sleep(0.05)

        # Update the molecule
        molecule.name = "New Name"
        molecule.updated_by = user_a.id
        db.add(molecule)
        db.commit()
        db.refresh(molecule)

        assert molecule.updated_at > original_updated_at

    def test_updated_at_increases_on_each_update(self, audit_setup):
        """updated_at increases with each subsequent update."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        timestamps = [molecule.updated_at]

        for i in range(3):
            time.sleep(0.02)
            molecule.name = f"Name v{i+1}"
            molecule.updated_by = user_a.id
            db.add(molecule)
            db.commit()
            db.refresh(molecule)
            timestamps.append(molecule.updated_at)

        # Each timestamp should be greater than the previous
        for i in range(1, len(timestamps)):
            assert timestamps[i] > timestamps[i-1], (
                f"Timestamp {i} ({timestamps[i]}) should be > "
                f"timestamp {i-1} ({timestamps[i-1]})"
            )


# =============================================================================
# Test: created_by Field
# =============================================================================


class TestCreatedByField:
    """Tests for created_by user reference field."""

    def test_created_by_is_set_to_creating_user(self, audit_setup):
        """created_by is set to the user who created the record."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        molecule = create_molecule(db, org.id, user_a.id, name="UserA's Molecule")
        db.commit()

        assert molecule.created_by == user_a.id

    def test_created_by_different_for_different_users(self, audit_setup):
        """Different users create records with their own IDs."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]
        user_b = audit_setup["user_b"]

        molecule_a = create_molecule(
            db, org.id, user_a.id, name="Molecule A", smiles="C"
        )
        molecule_b = create_molecule(
            db, org.id, user_b.id, name="Molecule B", smiles="CC"
        )
        db.commit()

        assert molecule_a.created_by == user_a.id
        assert molecule_b.created_by == user_b.id
        assert molecule_a.created_by != molecule_b.created_by

    def test_created_by_does_not_change_on_update(self, audit_setup):
        """created_by remains the original creator even when another user updates."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]
        user_b = audit_setup["user_b"]

        # User A creates
        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        assert molecule.created_by == user_a.id

        # User B updates
        molecule.name = "Updated by B"
        molecule.updated_by = user_b.id
        db.add(molecule)
        db.commit()

        # created_by should still be user A
        assert molecule.created_by == user_a.id

    def test_created_by_persists_after_refetch(self, audit_setup):
        """created_by is properly persisted."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        molecule = create_molecule(db, org.id, user_a.id)
        molecule_id = molecule.id
        db.commit()

        db.expire_all()
        refetched = db.get(Molecule, molecule_id)

        assert refetched.created_by == user_a.id


# =============================================================================
# Test: updated_by Field
# =============================================================================


class TestUpdatedByField:
    """Tests for updated_by user reference field."""

    def test_updated_by_is_null_on_insert(self, audit_setup):
        """updated_by is None when record is first created."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        assert molecule.updated_by is None

    def test_updated_by_set_to_updating_user(self, audit_setup):
        """updated_by is set to the user who updated the record."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]
        user_b = audit_setup["user_b"]

        # User A creates
        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        # User B updates
        molecule.name = "Updated by User B"
        molecule.updated_by = user_b.id
        db.add(molecule)
        db.commit()

        assert molecule.updated_by == user_b.id

    def test_updated_by_changes_with_each_updater(self, audit_setup):
        """updated_by changes to reflect the most recent updater."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]
        user_b = audit_setup["user_b"]

        # User A creates
        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        # User B updates
        molecule.name = "Update 1"
        molecule.updated_by = user_b.id
        db.add(molecule)
        db.commit()

        assert molecule.updated_by == user_b.id

        # User A updates
        molecule.name = "Update 2"
        molecule.updated_by = user_a.id
        db.add(molecule)
        db.commit()

        assert molecule.updated_by == user_a.id

        # User B updates again
        molecule.name = "Update 3"
        molecule.updated_by = user_b.id
        db.add(molecule)
        db.commit()

        assert molecule.updated_by == user_b.id

    def test_same_user_create_and_update(self, audit_setup):
        """When same user creates and updates, both fields reflect correctly."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        assert molecule.created_by == user_a.id
        assert molecule.updated_by is None

        # Same user updates
        molecule.name = "Self-updated"
        molecule.updated_by = user_a.id
        db.add(molecule)
        db.commit()

        assert molecule.created_by == user_a.id
        assert molecule.updated_by == user_a.id


# =============================================================================
# Test: Soft Delete Audit
# =============================================================================


class TestSoftDeleteAudit:
    """Tests for audit fields during soft delete."""

    def test_soft_delete_sets_updated_by(self, audit_setup):
        """Soft delete sets updated_by to the deleting user."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]
        user_b = audit_setup["user_b"]

        # User A creates
        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        # User B soft deletes
        molecule.updated_by = user_b.id
        molecule.soft_delete(db)
        db.commit()

        assert molecule.updated_by == user_b.id
        assert molecule.is_deleted is True

    def test_soft_delete_updates_updated_at(self, audit_setup):
        """Soft delete updates updated_at timestamp."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]
        user_b = audit_setup["user_b"]

        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        original_updated_at = molecule.updated_at

        time.sleep(0.05)

        # Soft delete
        molecule.updated_by = user_b.id
        molecule.soft_delete(db)
        db.commit()
        db.refresh(molecule)

        assert molecule.updated_at > original_updated_at

    def test_soft_delete_preserves_created_by(self, audit_setup):
        """Soft delete does not change created_by."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]
        user_b = audit_setup["user_b"]

        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        # User B soft deletes
        molecule.updated_by = user_b.id
        molecule.soft_delete(db)
        db.commit()

        assert molecule.created_by == user_a.id
        assert molecule.updated_by == user_b.id

    def test_restore_sets_updated_by(self, audit_setup):
        """Restore sets updated_by to the restoring user."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]
        user_b = audit_setup["user_b"]

        # User A creates
        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        # User A soft deletes
        molecule.updated_by = user_a.id
        molecule.soft_delete(db)
        db.commit()

        assert molecule.updated_by == user_a.id

        # User B restores
        molecule.updated_by = user_b.id
        molecule.restore(db)
        db.commit()

        assert molecule.updated_by == user_b.id
        assert molecule.is_deleted is False


# =============================================================================
# Test: Audit Fields on Other Models
# =============================================================================


class TestAuditFieldsOnTarget:
    """Tests for audit fields on Target model."""

    def test_target_created_by_set(self, audit_setup):
        """Target.created_by is set correctly."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        target = Target(
            id=uuid4(),
            organization_id=org.id,
            uniprot_id="P12345",
            gene_symbol="TEST",
            name="Test Target",
            organism="Homo sapiens",
            created_by=user_a.id,
        )
        db.add(target)
        db.commit()

        assert target.created_by == user_a.id
        assert target.created_at is not None
        assert target.updated_by is None

    def test_target_updated_by_set_on_update(self, audit_setup):
        """Target.updated_by is set on update."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]
        user_b = audit_setup["user_b"]

        target = Target(
            id=uuid4(),
            organization_id=org.id,
            name="Test Target",
            organism="Homo sapiens",
            created_by=user_a.id,
        )
        db.add(target)
        db.commit()

        # User B updates
        target.name = "Updated Target"
        target.updated_by = user_b.id
        db.add(target)
        db.commit()

        assert target.created_by == user_a.id
        assert target.updated_by == user_b.id


class TestAuditFieldsOnProject:
    """Tests for audit fields on Project model."""

    def test_project_created_by_set(self, audit_setup):
        """Project.created_by is set correctly."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        project = Project(
            id=uuid4(),
            organization_id=org.id,
            name="Test Project",
            status="active",
            created_by=user_a.id,
        )
        db.add(project)
        db.commit()

        assert project.created_by == user_a.id
        assert project.created_at is not None

    def test_project_updated_by_on_status_change(self, audit_setup):
        """Project.updated_by is set when status changes."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]
        user_b = audit_setup["user_b"]

        project = Project(
            id=uuid4(),
            organization_id=org.id,
            name="Test Project",
            status="active",
            created_by=user_a.id,
        )
        db.add(project)
        db.commit()

        # User B archives the project
        project.status = "archived"
        project.updated_by = user_b.id
        db.add(project)
        db.commit()

        assert project.created_by == user_a.id
        assert project.updated_by == user_b.id


class TestAuditFieldsOnAssay:
    """Tests for audit fields on Assay model."""

    def test_assay_created_by_set(self, audit_setup):
        """Assay.created_by is set correctly."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]

        # First create a molecule for the assay
        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        assay = Assay(
            id=uuid4(),
            organization_id=org.id,
            molecule_id=molecule.id,
            assay_type="admet",
            result_type="solubility",
            result_value=Decimal("50.0"),
            result_unit="mg/mL",
            created_by=user_a.id,
        )
        db.add(assay)
        db.commit()

        assert assay.created_by == user_a.id
        assert assay.created_at is not None

    def test_assay_updated_by_on_result_correction(self, audit_setup):
        """Assay.updated_by is set when results are corrected."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]
        user_b = audit_setup["user_b"]

        molecule = create_molecule(db, org.id, user_a.id)
        db.commit()

        assay = Assay(
            id=uuid4(),
            organization_id=org.id,
            molecule_id=molecule.id,
            assay_type="binding",
            result_type="IC50",
            result_value=Decimal("100.0"),
            result_unit="nM",
            created_by=user_a.id,
        )
        db.add(assay)
        db.commit()

        # User B corrects the result
        assay.result_value = Decimal("95.5")
        assay.updated_by = user_b.id
        db.add(assay)
        db.commit()

        assert assay.created_by == user_a.id
        assert assay.updated_by == user_b.id


# =============================================================================
# Test: Full Audit Trail Scenario
# =============================================================================


class TestFullAuditTrailScenario:
    """End-to-end test of audit trail across a molecule's lifecycle."""

    def test_molecule_full_lifecycle_audit(self, audit_setup):
        """
        Full lifecycle: create -> update -> update -> soft delete -> restore.
        Verify audit fields at each step.
        """
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]
        user_b = audit_setup["user_b"]

        # Step 1: User A creates molecule
        molecule = create_molecule(db, org.id, user_a.id, name="Original Name")
        db.commit()

        assert molecule.created_by == user_a.id
        assert molecule.updated_by is None
        step1_created_at = molecule.created_at
        step1_updated_at = molecule.updated_at

        time.sleep(0.02)

        # Step 2: User B updates name
        molecule.name = "First Update"
        molecule.updated_by = user_b.id
        db.add(molecule)
        db.commit()
        db.refresh(molecule)

        assert molecule.created_by == user_a.id  # Unchanged
        assert molecule.created_at == step1_created_at  # Unchanged
        assert molecule.updated_by == user_b.id
        assert molecule.updated_at > step1_updated_at
        step2_updated_at = molecule.updated_at

        time.sleep(0.02)

        # Step 3: User A updates weight
        molecule.molecular_weight = Decimal("150.0")
        molecule.updated_by = user_a.id
        db.add(molecule)
        db.commit()
        db.refresh(molecule)

        assert molecule.created_by == user_a.id  # Still unchanged
        assert molecule.updated_by == user_a.id  # Now user A
        assert molecule.updated_at > step2_updated_at
        step3_updated_at = molecule.updated_at

        time.sleep(0.02)

        # Step 4: User B soft deletes
        molecule.updated_by = user_b.id
        molecule.soft_delete(db)
        db.commit()
        db.refresh(molecule)

        assert molecule.created_by == user_a.id  # Still unchanged
        assert molecule.updated_by == user_b.id
        assert molecule.is_deleted is True
        assert molecule.deleted_at is not None
        assert molecule.updated_at > step3_updated_at
        step4_updated_at = molecule.updated_at

        time.sleep(0.02)

        # Step 5: User A restores
        molecule.updated_by = user_a.id
        molecule.restore(db)
        db.commit()
        db.refresh(molecule)

        assert molecule.created_by == user_a.id  # Still unchanged
        assert molecule.updated_by == user_a.id
        assert molecule.is_deleted is False
        assert molecule.deleted_at is None
        assert molecule.updated_at > step4_updated_at

    def test_audit_trail_integrity(self, audit_setup):
        """Verify audit trail maintains data integrity across operations."""
        db = audit_setup["db"]
        org = audit_setup["org"]
        user_a = audit_setup["user_a"]
        user_b = audit_setup["user_b"]

        # Create molecule and track state
        molecule = create_molecule(db, org.id, user_a.id)
        molecule_id = molecule.id
        db.commit()

        # Multiple updates
        for i in range(5):
            time.sleep(0.01)
            updater = user_a if i % 2 == 0 else user_b
            molecule.name = f"Version {i+1}"
            molecule.updated_by = updater.id
            db.add(molecule)
            db.commit()

        # Refetch and verify
        db.expire_all()
        refetched = db.get(Molecule, molecule_id)

        # created_by should always be user_a
        assert refetched.created_by == user_a.id
        # updated_by should be last updater (user_a for i=4)
        assert refetched.updated_by == user_a.id
        # updated_at should be greater than created_at
        assert refetched.updated_at > refetched.created_at
