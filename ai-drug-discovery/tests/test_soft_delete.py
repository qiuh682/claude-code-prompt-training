"""
Tests for soft delete behavior on Task 1.3 models.

Verifies:
- soft_delete() sets deleted_at timestamp
- is_deleted property returns True after soft delete
- restore() clears deleted_at and restores the record
- active_query() excludes soft-deleted records (default pattern)
- deleted_query() returns only soft-deleted records (admin/audit)
- select() without filter includes all records (admin override)
- Soft delete does not break FK relationships (associations remain intact)

Query Patterns Tested:
- Default (active only): Model.active_query() or where(deleted_at.is_(None))
- Include deleted (admin): select(Model) without filter
- Only deleted (recovery): Model.deleted_query()

Usage:
    DATABASE_URL_TEST=postgresql://postgres:postgres@localhost:5433/drugdiscovery_test \
    pytest tests/test_soft_delete.py -v
"""

import hashlib
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from apps.api.auth.models import Membership, Organization, User, UserRole
from apps.api.auth.security import hash_password
from db.models.discovery import (
    Molecule,
    MoleculeTarget,
    Project,
    ProjectMolecule,
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
def soft_delete_setup(test_session_factory):
    """
    Set up organization, user, and entities for soft delete tests.

    Creates:
    - 1 Organization
    - 1 User
    - 1 Project
    - 3 Molecules (to test filtering)
    - 1 Target
    - Association links between them

    Returns dict with all entities and the session.
    """
    db: Session = test_session_factory()

    try:
        # =================================================================
        # Create Organization
        # =================================================================
        org = Organization(
            id=uuid4(),
            name="Soft Delete Test Org",
            slug=f"soft-delete-org-{uuid4().hex[:8]}",
        )
        db.add(org)
        db.flush()

        # =================================================================
        # Create User
        # =================================================================
        user = User(
            id=uuid4(),
            email=f"softdelete-{uuid4().hex[:8]}@test.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="Soft Delete Tester",
            is_active=True,
        )
        db.add(user)
        db.flush()

        membership = Membership(
            user_id=user.id,
            organization_id=org.id,
            role=UserRole.ADMIN,
        )
        db.add(membership)
        db.flush()

        # =================================================================
        # Create Project
        # =================================================================
        project = Project(
            id=uuid4(),
            organization_id=org.id,
            name="Soft Delete Test Project",
            status="active",
            created_by=user.id,
        )
        db.add(project)
        db.flush()

        # =================================================================
        # Create Molecules
        # =================================================================
        molecule1_smiles = "CCO"  # Ethanol
        molecule1 = Molecule(
            id=uuid4(),
            organization_id=org.id,
            canonical_smiles=molecule1_smiles,
            inchi_key="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            smiles_hash=smiles_hash(molecule1_smiles),
            name="Ethanol",
            created_by=user.id,
        )
        db.add(molecule1)
        db.flush()

        molecule2_smiles = "C"  # Methane
        molecule2 = Molecule(
            id=uuid4(),
            organization_id=org.id,
            canonical_smiles=molecule2_smiles,
            inchi_key="VNWKTOKETHGBQD-UHFFFAOYSA-N",
            smiles_hash=smiles_hash(molecule2_smiles),
            name="Methane",
            created_by=user.id,
        )
        db.add(molecule2)
        db.flush()

        molecule3_smiles = "CC"  # Ethane
        molecule3 = Molecule(
            id=uuid4(),
            organization_id=org.id,
            canonical_smiles=molecule3_smiles,
            inchi_key="OTMSDBZUPAUEDD-UHFFFAOYSA-N",
            smiles_hash=smiles_hash(molecule3_smiles),
            name="Ethane",
            created_by=user.id,
        )
        db.add(molecule3)
        db.flush()

        # =================================================================
        # Create Target
        # =================================================================
        target = Target(
            id=uuid4(),
            organization_id=org.id,
            uniprot_id="P12345",
            gene_symbol="TEST1",
            name="Test Target 1",
            organism="Homo sapiens",
            created_by=user.id,
        )
        db.add(target)
        db.flush()

        # =================================================================
        # Create Associations
        # =================================================================

        # Link molecule1 to project
        pm1 = ProjectMolecule(
            id=uuid4(),
            project_id=project.id,
            molecule_id=molecule1.id,
            added_by=user.id,
        )
        db.add(pm1)
        db.flush()

        # Link molecule1 to target
        mt1 = MoleculeTarget(
            id=uuid4(),
            molecule_id=molecule1.id,
            target_id=target.id,
            relationship_type="tested",
        )
        db.add(mt1)
        db.flush()

        db.commit()

        yield {
            "db": db,
            "org": org,
            "user": user,
            "project": project,
            "molecule1": molecule1,
            "molecule2": molecule2,
            "molecule3": molecule3,
            "target": target,
            "project_molecule": pm1,
            "molecule_target": mt1,
        }

    finally:
        # Cleanup
        try:
            db.execute(text("SET session_replication_role = 'replica';"))
            db.execute(
                text("DELETE FROM molecule_targets WHERE molecule_id IN "
                     "(SELECT id FROM molecules WHERE organization_id = :org_id)"),
                {"org_id": org.id}
            )
            db.execute(
                text("DELETE FROM project_molecules WHERE project_id IN "
                     "(SELECT id FROM projects WHERE organization_id = :org_id)"),
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
                text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user.id}
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
# Test: soft_delete() Method
# =============================================================================


class TestSoftDeleteMethod:
    """Tests for the soft_delete() method."""

    def test_soft_delete_sets_deleted_at(self, soft_delete_setup):
        """Calling soft_delete() sets deleted_at timestamp."""
        db = soft_delete_setup["db"]
        molecule = soft_delete_setup["molecule1"]

        # Before soft delete
        assert molecule.deleted_at is None

        # Perform soft delete
        molecule.soft_delete(db)

        # After soft delete
        assert molecule.deleted_at is not None

    def test_soft_delete_sets_current_timestamp(self, soft_delete_setup):
        """deleted_at is set to approximately current time."""
        from datetime import UTC, datetime, timedelta

        db = soft_delete_setup["db"]
        molecule = soft_delete_setup["molecule1"]

        before_delete = datetime.now(UTC)
        molecule.soft_delete(db)
        after_delete = datetime.now(UTC)

        # deleted_at should be between before and after
        assert molecule.deleted_at >= before_delete - timedelta(seconds=1)
        assert molecule.deleted_at <= after_delete + timedelta(seconds=1)

    def test_is_deleted_returns_true_after_soft_delete(self, soft_delete_setup):
        """is_deleted property returns True after soft_delete()."""
        db = soft_delete_setup["db"]
        molecule = soft_delete_setup["molecule1"]

        assert molecule.is_deleted is False

        molecule.soft_delete(db)

        assert molecule.is_deleted is True

    def test_soft_delete_persists_to_database(self, soft_delete_setup):
        """Soft delete is persisted when committed."""
        db = soft_delete_setup["db"]
        molecule = soft_delete_setup["molecule1"]
        molecule_id = molecule.id

        molecule.soft_delete(db)
        db.commit()

        # Clear session cache and re-fetch
        db.expire_all()
        refetched = db.get(Molecule, molecule_id)

        assert refetched.deleted_at is not None
        assert refetched.is_deleted is True


# =============================================================================
# Test: restore() Method
# =============================================================================


class TestRestoreMethod:
    """Tests for the restore() method."""

    def test_restore_clears_deleted_at(self, soft_delete_setup):
        """Calling restore() clears deleted_at."""
        db = soft_delete_setup["db"]
        molecule = soft_delete_setup["molecule1"]

        # Soft delete first
        molecule.soft_delete(db)
        assert molecule.deleted_at is not None

        # Restore
        molecule.restore(db)

        assert molecule.deleted_at is None
        assert molecule.is_deleted is False

    def test_restore_persists_to_database(self, soft_delete_setup):
        """Restore is persisted when committed."""
        db = soft_delete_setup["db"]
        molecule = soft_delete_setup["molecule1"]
        molecule_id = molecule.id

        molecule.soft_delete(db)
        db.commit()

        molecule.restore(db)
        db.commit()

        # Re-fetch
        db.expire_all()
        refetched = db.get(Molecule, molecule_id)

        assert refetched.deleted_at is None
        assert refetched.is_deleted is False


# =============================================================================
# Test: active_query() - Default Query Pattern
# =============================================================================


class TestActiveQuery:
    """Tests for active_query() which excludes soft-deleted records."""

    def test_active_query_returns_non_deleted_records(self, soft_delete_setup):
        """active_query() returns only non-deleted records."""
        db = soft_delete_setup["db"]
        org = soft_delete_setup["org"]

        # All 3 molecules should appear
        stmt = Molecule.active_query().where(Molecule.organization_id == org.id)
        results = db.execute(stmt).scalars().all()

        assert len(results) == 3

    def test_active_query_excludes_soft_deleted(self, soft_delete_setup):
        """Soft-deleted molecule does not appear in active_query()."""
        db = soft_delete_setup["db"]
        org = soft_delete_setup["org"]
        molecule1 = soft_delete_setup["molecule1"]

        # Soft delete molecule1
        molecule1.soft_delete(db)
        db.commit()

        # Query active molecules
        stmt = Molecule.active_query().where(Molecule.organization_id == org.id)
        results = db.execute(stmt).scalars().all()

        # Only 2 molecules should appear
        assert len(results) == 2
        result_ids = {m.id for m in results}
        assert molecule1.id not in result_ids

    def test_active_query_with_additional_filters(self, soft_delete_setup):
        """active_query() can be chained with additional filters."""
        db = soft_delete_setup["db"]
        org = soft_delete_setup["org"]

        stmt = (
            Molecule.active_query()
            .where(Molecule.organization_id == org.id)
            .where(Molecule.name == "Ethanol")
        )
        results = db.execute(stmt).scalars().all()

        assert len(results) == 1
        assert results[0].name == "Ethanol"

    def test_soft_deleted_molecule_not_in_active_query(self, soft_delete_setup):
        """Verify a specific molecule disappears from active_query after delete."""
        db = soft_delete_setup["db"]
        org = soft_delete_setup["org"]
        molecule1 = soft_delete_setup["molecule1"]

        # Verify it exists before
        stmt = (
            Molecule.active_query()
            .where(Molecule.organization_id == org.id)
            .where(Molecule.id == molecule1.id)
        )
        before = db.execute(stmt).scalars().first()
        assert before is not None

        # Soft delete
        molecule1.soft_delete(db)
        db.commit()
        db.expire_all()

        # Verify it's gone from active query
        after = db.execute(stmt).scalars().first()
        assert after is None


# =============================================================================
# Test: Include Deleted (Admin/Audit Pattern)
# =============================================================================


class TestIncludeDeleted:
    """Tests for querying all records including deleted (admin pattern)."""

    def test_select_without_filter_includes_deleted(self, soft_delete_setup):
        """select(Model) without deleted_at filter includes all records."""
        db = soft_delete_setup["db"]
        org = soft_delete_setup["org"]
        molecule1 = soft_delete_setup["molecule1"]

        # Soft delete molecule1
        molecule1.soft_delete(db)
        db.commit()

        # Query all molecules (no deleted_at filter)
        stmt = select(Molecule).where(Molecule.organization_id == org.id)
        results = db.execute(stmt).scalars().all()

        # All 3 molecules should appear
        assert len(results) == 3
        result_ids = {m.id for m in results}
        assert molecule1.id in result_ids

    def test_admin_can_see_deleted_records(self, soft_delete_setup):
        """Admin audit query pattern includes soft-deleted records."""
        db = soft_delete_setup["db"]
        org = soft_delete_setup["org"]
        molecule1 = soft_delete_setup["molecule1"]
        molecule2 = soft_delete_setup["molecule2"]

        # Soft delete two molecules
        molecule1.soft_delete(db)
        molecule2.soft_delete(db)
        db.commit()

        # Admin query: all records
        stmt = select(Molecule).where(Molecule.organization_id == org.id)
        all_results = db.execute(stmt).scalars().all()
        assert len(all_results) == 3

        # Active query: only non-deleted
        active_stmt = Molecule.active_query().where(Molecule.organization_id == org.id)
        active_results = db.execute(active_stmt).scalars().all()
        assert len(active_results) == 1

    def test_can_identify_deleted_records_in_full_query(self, soft_delete_setup):
        """In full query, can identify which records are deleted."""
        db = soft_delete_setup["db"]
        org = soft_delete_setup["org"]
        molecule1 = soft_delete_setup["molecule1"]

        molecule1.soft_delete(db)
        db.commit()

        stmt = select(Molecule).where(Molecule.organization_id == org.id)
        results = db.execute(stmt).scalars().all()

        deleted_count = sum(1 for m in results if m.is_deleted)
        active_count = sum(1 for m in results if not m.is_deleted)

        assert deleted_count == 1
        assert active_count == 2


# =============================================================================
# Test: deleted_query() - Only Deleted Records
# =============================================================================


class TestDeletedQuery:
    """Tests for deleted_query() which returns only soft-deleted records."""

    def test_deleted_query_returns_only_deleted(self, soft_delete_setup):
        """deleted_query() returns only soft-deleted records."""
        db = soft_delete_setup["db"]
        org = soft_delete_setup["org"]
        molecule1 = soft_delete_setup["molecule1"]

        # Initially no deleted records
        stmt = Molecule.deleted_query().where(Molecule.organization_id == org.id)
        before = db.execute(stmt).scalars().all()
        assert len(before) == 0

        # Soft delete molecule1
        molecule1.soft_delete(db)
        db.commit()

        # Now 1 deleted record
        after = db.execute(stmt).scalars().all()
        assert len(after) == 1
        assert after[0].id == molecule1.id

    def test_deleted_query_for_recovery_ui(self, soft_delete_setup):
        """deleted_query() can be used for admin recovery interface."""
        db = soft_delete_setup["db"]
        org = soft_delete_setup["org"]
        molecule1 = soft_delete_setup["molecule1"]
        molecule2 = soft_delete_setup["molecule2"]

        # Delete two molecules
        molecule1.soft_delete(db)
        molecule2.soft_delete(db)
        db.commit()

        # Recovery UI: show deleted items
        stmt = Molecule.deleted_query().where(Molecule.organization_id == org.id)
        deleted_molecules = db.execute(stmt).scalars().all()

        assert len(deleted_molecules) == 2
        deleted_names = {m.name for m in deleted_molecules}
        assert "Ethanol" in deleted_names
        assert "Methane" in deleted_names


# =============================================================================
# Test: FK Relationships with Soft Delete
# =============================================================================


class TestSoftDeleteForeignKeys:
    """Tests that soft delete does not break foreign key relationships."""

    def test_project_association_intact_after_molecule_soft_delete(
        self, soft_delete_setup
    ):
        """ProjectMolecule association remains after molecule soft delete."""
        db = soft_delete_setup["db"]
        molecule1 = soft_delete_setup["molecule1"]
        project_molecule = soft_delete_setup["project_molecule"]

        # Soft delete the molecule
        molecule1.soft_delete(db)
        db.commit()

        # Association record still exists
        db.expire_all()
        assoc = db.get(ProjectMolecule, project_molecule.id)

        assert assoc is not None
        assert assoc.molecule_id == molecule1.id

    def test_can_access_deleted_molecule_via_association(self, soft_delete_setup):
        """Can still access soft-deleted molecule through FK relationship."""
        db = soft_delete_setup["db"]
        molecule1 = soft_delete_setup["molecule1"]
        project = soft_delete_setup["project"]

        # Soft delete the molecule
        molecule1.soft_delete(db)
        db.commit()

        # Refresh project associations
        db.expire_all()
        db.refresh(project)

        # Can still access molecule through association
        assoc = project.molecule_associations[0]
        linked_molecule = assoc.molecule

        assert linked_molecule is not None
        assert linked_molecule.id == molecule1.id
        assert linked_molecule.is_deleted is True

    def test_target_association_intact_after_molecule_soft_delete(
        self, soft_delete_setup
    ):
        """MoleculeTarget association remains after molecule soft delete."""
        db = soft_delete_setup["db"]
        molecule1 = soft_delete_setup["molecule1"]
        molecule_target = soft_delete_setup["molecule_target"]

        molecule1.soft_delete(db)
        db.commit()

        db.expire_all()
        assoc = db.get(MoleculeTarget, molecule_target.id)

        assert assoc is not None
        assert assoc.molecule_id == molecule1.id

    def test_target_still_has_molecule_association_after_soft_delete(
        self, soft_delete_setup
    ):
        """Target.molecule_associations still includes soft-deleted molecule."""
        db = soft_delete_setup["db"]
        molecule1 = soft_delete_setup["molecule1"]
        target = soft_delete_setup["target"]

        molecule1.soft_delete(db)
        db.commit()

        db.expire_all()
        db.refresh(target)

        # Association still exists
        assert len(target.molecule_associations) == 1
        linked_mol = target.molecule_associations[0].molecule
        assert linked_mol.is_deleted is True

    def test_project_soft_delete_keeps_associations(self, soft_delete_setup):
        """Soft deleting a project keeps its molecule associations."""
        db = soft_delete_setup["db"]
        project = soft_delete_setup["project"]
        project_molecule = soft_delete_setup["project_molecule"]

        project.soft_delete(db)
        db.commit()

        db.expire_all()
        assoc = db.get(ProjectMolecule, project_molecule.id)

        assert assoc is not None
        assert assoc.project_id == project.id

    def test_can_query_active_molecules_in_project(self, soft_delete_setup):
        """Can filter to only active molecules within a project."""
        db = soft_delete_setup["db"]
        molecule1 = soft_delete_setup["molecule1"]
        project = soft_delete_setup["project"]

        # Add molecule2 to project as well
        molecule2 = soft_delete_setup["molecule2"]
        pm2 = ProjectMolecule(
            id=uuid4(),
            project_id=project.id,
            molecule_id=molecule2.id,
            added_by=soft_delete_setup["user"].id,
        )
        db.add(pm2)
        db.commit()

        # Soft delete molecule1
        molecule1.soft_delete(db)
        db.commit()

        # Query active molecules in project
        stmt = (
            select(Molecule)
            .join(ProjectMolecule)
            .where(ProjectMolecule.project_id == project.id)
            .where(Molecule.deleted_at.is_(None))
        )
        active_molecules = db.execute(stmt).scalars().all()

        assert len(active_molecules) == 1
        assert active_molecules[0].id == molecule2.id


# =============================================================================
# Test: Soft Delete on Target Model
# =============================================================================


class TestTargetSoftDelete:
    """Tests for soft delete on Target model."""

    def test_target_soft_delete_sets_deleted_at(self, soft_delete_setup):
        """Target.soft_delete() sets deleted_at."""
        db = soft_delete_setup["db"]
        target = soft_delete_setup["target"]

        assert target.deleted_at is None

        target.soft_delete(db)

        assert target.deleted_at is not None
        assert target.is_deleted is True

    def test_target_active_query_excludes_deleted(self, soft_delete_setup):
        """Target.active_query() excludes soft-deleted targets."""
        db = soft_delete_setup["db"]
        org = soft_delete_setup["org"]
        target = soft_delete_setup["target"]

        # Before delete
        stmt = Target.active_query().where(Target.organization_id == org.id)
        before = db.execute(stmt).scalars().all()
        assert len(before) == 1

        # Soft delete
        target.soft_delete(db)
        db.commit()

        # After delete
        after = db.execute(stmt).scalars().all()
        assert len(after) == 0


# =============================================================================
# Test: Soft Delete on Project Model
# =============================================================================


class TestProjectSoftDelete:
    """Tests for soft delete on Project model."""

    def test_project_soft_delete_sets_deleted_at(self, soft_delete_setup):
        """Project.soft_delete() sets deleted_at."""
        db = soft_delete_setup["db"]
        project = soft_delete_setup["project"]

        project.soft_delete(db)

        assert project.deleted_at is not None
        assert project.is_deleted is True

    def test_project_active_query_excludes_deleted(self, soft_delete_setup):
        """Project.active_query() excludes soft-deleted projects."""
        db = soft_delete_setup["db"]
        org = soft_delete_setup["org"]
        project = soft_delete_setup["project"]

        # Before delete
        stmt = Project.active_query().where(Project.organization_id == org.id)
        before = db.execute(stmt).scalars().all()
        assert len(before) == 1

        # Soft delete
        project.soft_delete(db)
        db.commit()

        # After delete
        after = db.execute(stmt).scalars().all()
        assert len(after) == 0


# =============================================================================
# Test: Multiple Soft Deletes and Restores
# =============================================================================


class TestMultipleSoftDeleteOperations:
    """Tests for multiple soft delete and restore operations."""

    def test_multiple_molecules_soft_deleted(self, soft_delete_setup):
        """Can soft delete multiple molecules."""
        db = soft_delete_setup["db"]
        org = soft_delete_setup["org"]
        molecule1 = soft_delete_setup["molecule1"]
        molecule2 = soft_delete_setup["molecule2"]
        molecule3 = soft_delete_setup["molecule3"]

        molecule1.soft_delete(db)
        molecule2.soft_delete(db)
        db.commit()

        stmt = Molecule.active_query().where(Molecule.organization_id == org.id)
        active = db.execute(stmt).scalars().all()

        assert len(active) == 1
        assert active[0].id == molecule3.id

    def test_restore_after_soft_delete_cycle(self, soft_delete_setup):
        """Can restore, soft delete again, and restore again."""
        db = soft_delete_setup["db"]
        molecule1 = soft_delete_setup["molecule1"]

        # Delete
        molecule1.soft_delete(db)
        assert molecule1.is_deleted is True

        # Restore
        molecule1.restore(db)
        assert molecule1.is_deleted is False

        # Delete again
        molecule1.soft_delete(db)
        assert molecule1.is_deleted is True

        # Restore again
        molecule1.restore(db)
        assert molecule1.is_deleted is False

    def test_deleted_at_timestamp_updated_on_re_delete(self, soft_delete_setup):
        """deleted_at gets new timestamp when re-deleted."""
        from datetime import timedelta
        import time

        db = soft_delete_setup["db"]
        molecule1 = soft_delete_setup["molecule1"]

        # First delete
        molecule1.soft_delete(db)
        first_deleted_at = molecule1.deleted_at

        # Restore
        molecule1.restore(db)

        # Small delay
        time.sleep(0.01)

        # Second delete
        molecule1.soft_delete(db)
        second_deleted_at = molecule1.deleted_at

        # Timestamps should be different
        assert second_deleted_at > first_deleted_at
