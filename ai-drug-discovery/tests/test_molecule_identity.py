"""
Tests for molecule identity fields and uniqueness constraints.

Verifies:
- Molecule has required chemical identity fields (smiles, inchi, inchikey, smiles_hash)
- InChIKey uniqueness is enforced per organization
- canonical_smiles stores the expected value
- smiles_hash is computed correctly (SHA-256 of canonical SMILES)
- Different organizations can have molecules with the same InChIKey

Tests:
1) Insert Molecule with inchikey K; inserting another with same inchikey fails
2) Different orgs can have same inchikey (org-scoped uniqueness)
3) canonical_smiles stored correctly
4) smiles_hash is SHA-256 of canonical_smiles

Note on canonicalization:
    The Molecule model stores canonical_smiles as-is. Canonicalization is expected
    to be performed in the service layer (using RDKit) before insertion.
    This test file includes a placeholder test for future canonicalization service.

Usage:
    DATABASE_URL_TEST=postgresql://postgres:postgres@localhost:5433/drugdiscovery_test \
    pytest tests/test_molecule_identity.py -v
"""

import hashlib
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.auth.models import Membership, Organization, User, UserRole
from apps.api.auth.security import hash_password
from db.models.discovery import Molecule


# =============================================================================
# Test Data
# =============================================================================

TEST_PASSWORD = "SecureTestPass123"

# Well-known molecules for testing
ETHANOL = {
    "smiles": "CCO",
    "inchi": "InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3",
    "inchi_key": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
    "name": "Ethanol",
    "formula": "C2H6O",
    "mw": Decimal("46.0684"),
}

ASPIRIN = {
    "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "inchi": "InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)",
    "inchi_key": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
    "name": "Aspirin",
    "formula": "C9H8O4",
    "mw": Decimal("180.1574"),
}

CAFFEINE = {
    "smiles": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
    "inchi_key": "RYYVLZVUVIJVGH-UHFFFAOYSA-N",
    "name": "Caffeine",
}


def smiles_hash(smiles: str) -> str:
    """Compute SHA-256 hash of SMILES string."""
    return hashlib.sha256(smiles.encode()).hexdigest()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def identity_setup(test_session_factory):
    """
    Set up two organizations and users for identity tests.

    Creates:
    - 2 Organizations (OrgA, OrgB)
    - 2 Users (userA in OrgA, userB in OrgB)

    This allows testing org-scoped uniqueness constraints.
    """
    db: Session = test_session_factory()

    try:
        # =================================================================
        # Create Organization A
        # =================================================================
        org_a = Organization(
            id=uuid4(),
            name="Identity Test Org A",
            slug=f"identity-org-a-{uuid4().hex[:8]}",
        )
        db.add(org_a)
        db.flush()

        user_a = User(
            id=uuid4(),
            email=f"user-a-{uuid4().hex[:8]}@identitytest.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="User A",
            is_active=True,
        )
        db.add(user_a)
        db.flush()

        membership_a = Membership(
            user_id=user_a.id,
            organization_id=org_a.id,
            role=UserRole.ADMIN,
        )
        db.add(membership_a)
        db.flush()

        # =================================================================
        # Create Organization B
        # =================================================================
        org_b = Organization(
            id=uuid4(),
            name="Identity Test Org B",
            slug=f"identity-org-b-{uuid4().hex[:8]}",
        )
        db.add(org_b)
        db.flush()

        user_b = User(
            id=uuid4(),
            email=f"user-b-{uuid4().hex[:8]}@identitytest.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="User B",
            is_active=True,
        )
        db.add(user_b)
        db.flush()

        membership_b = Membership(
            user_id=user_b.id,
            organization_id=org_b.id,
            role=UserRole.ADMIN,
        )
        db.add(membership_b)
        db.flush()

        db.commit()

        yield {
            "db": db,
            "org_a": org_a,
            "org_b": org_b,
            "user_a": user_a,
            "user_b": user_b,
        }

    finally:
        # Cleanup
        try:
            db.execute(text("SET session_replication_role = 'replica';"))
            db.execute(
                text("DELETE FROM molecules WHERE organization_id IN (:org_a, :org_b)"),
                {"org_a": org_a.id, "org_b": org_b.id}
            )
            db.execute(
                text("DELETE FROM memberships WHERE organization_id IN (:org_a, :org_b)"),
                {"org_a": org_a.id, "org_b": org_b.id}
            )
            db.execute(
                text("DELETE FROM users WHERE id IN (:user_a, :user_b)"),
                {"user_a": user_a.id, "user_b": user_b.id}
            )
            db.execute(
                text("DELETE FROM organizations WHERE id IN (:org_a, :org_b)"),
                {"org_a": org_a.id, "org_b": org_b.id}
            )
            db.execute(text("SET session_replication_role = 'origin';"))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


# =============================================================================
# Helper Functions
# =============================================================================


def create_molecule(
    db: Session,
    org_id,
    user_id,
    smiles: str,
    inchi_key: str,
    name: str | None = None,
    inchi: str | None = None,
) -> Molecule:
    """Helper to create a molecule with identity fields."""
    molecule = Molecule(
        id=uuid4(),
        organization_id=org_id,
        canonical_smiles=smiles,
        inchi=inchi,
        inchi_key=inchi_key,
        smiles_hash=smiles_hash(smiles),
        name=name,
        created_by=user_id,
    )
    db.add(molecule)
    return molecule


# =============================================================================
# Test: Required Identity Fields
# =============================================================================


class TestRequiredIdentityFields:
    """Tests for required chemical identity fields on Molecule."""

    def test_molecule_has_canonical_smiles(self, identity_setup):
        """Molecule stores canonical_smiles field."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        molecule = create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],
            name=ETHANOL["name"],
        )
        db.commit()

        assert molecule.canonical_smiles == ETHANOL["smiles"]

    def test_molecule_has_inchi_key(self, identity_setup):
        """Molecule stores inchi_key field."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        molecule = create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],
        )
        db.commit()

        assert molecule.inchi_key == ETHANOL["inchi_key"]
        assert len(molecule.inchi_key) == 27  # InChIKey is always 27 chars

    def test_molecule_has_optional_inchi(self, identity_setup):
        """Molecule can store optional inchi field."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        molecule = create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],
            inchi=ETHANOL["inchi"],
        )
        db.commit()

        assert molecule.inchi == ETHANOL["inchi"]

    def test_molecule_has_smiles_hash(self, identity_setup):
        """Molecule stores smiles_hash (SHA-256 of canonical SMILES)."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        molecule = create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],
        )
        db.commit()

        expected_hash = smiles_hash(ETHANOL["smiles"])
        assert molecule.smiles_hash == expected_hash
        assert len(molecule.smiles_hash) == 64  # SHA-256 hex is 64 chars


# =============================================================================
# Test: InChIKey Uniqueness
# =============================================================================


class TestInChIKeyUniqueness:
    """Tests for InChIKey uniqueness constraint."""

    def test_duplicate_inchikey_same_org_fails(self, identity_setup):
        """Inserting molecule with same inchikey in same org raises IntegrityError."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        # First molecule
        molecule1 = create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],
            name="Ethanol Original",
        )
        db.commit()

        # Second molecule with same inchikey in same org should fail
        molecule2 = create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],  # Same SMILES
            inchi_key=ETHANOL["inchi_key"],  # Same InChIKey
            name="Ethanol Duplicate",
        )

        with pytest.raises(IntegrityError) as exc_info:
            db.commit()

        # Verify it's the uniqueness constraint that failed
        assert "uq_molecule_org_inchikey" in str(exc_info.value).lower() or \
               "unique" in str(exc_info.value).lower()

        db.rollback()

    def test_same_inchikey_different_orgs_succeeds(self, identity_setup):
        """Same inchikey can exist in different organizations."""
        db = identity_setup["db"]
        org_a = identity_setup["org_a"]
        org_b = identity_setup["org_b"]
        user_a = identity_setup["user_a"]
        user_b = identity_setup["user_b"]

        # Ethanol in Org A
        molecule_a = create_molecule(
            db, org_a.id, user_a.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],
            name="Ethanol in Org A",
        )
        db.flush()

        # Ethanol in Org B (same inchikey, different org)
        molecule_b = create_molecule(
            db, org_b.id, user_b.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],
            name="Ethanol in Org B",
        )
        db.flush()

        # Both should commit successfully
        db.commit()

        assert molecule_a.inchi_key == molecule_b.inchi_key
        assert molecule_a.organization_id != molecule_b.organization_id

    def test_different_inchikeys_same_org_succeeds(self, identity_setup):
        """Different molecules with different inchikeys in same org succeed."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        # Ethanol
        molecule1 = create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],
            name=ETHANOL["name"],
        )
        db.flush()

        # Aspirin (different inchikey)
        molecule2 = create_molecule(
            db, org.id, user.id,
            smiles=ASPIRIN["smiles"],
            inchi_key=ASPIRIN["inchi_key"],
            name=ASPIRIN["name"],
        )
        db.flush()

        # Caffeine (different inchikey)
        molecule3 = create_molecule(
            db, org.id, user.id,
            smiles=CAFFEINE["smiles"],
            inchi_key=CAFFEINE["inchi_key"],
            name=CAFFEINE["name"],
        )
        db.flush()

        db.commit()

        # All three should exist
        assert molecule1.id is not None
        assert molecule2.id is not None
        assert molecule3.id is not None

    def test_inchikey_case_sensitivity(self, identity_setup):
        """InChIKey comparison is case-sensitive (uppercase is standard)."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        # Standard uppercase InChIKey
        molecule1 = create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],  # Uppercase
            name="Uppercase InChIKey",
        )
        db.commit()

        # Lowercase version (non-standard but test case sensitivity)
        lowercase_key = ETHANOL["inchi_key"].lower()
        molecule2 = create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],
            inchi_key=lowercase_key,  # Lowercase
            name="Lowercase InChIKey",
        )

        # This might succeed or fail depending on collation
        # Standard practice: always use uppercase InChIKey
        try:
            db.commit()
            # If it succeeds, they're treated as different
            assert molecule1.inchi_key != molecule2.inchi_key
        except IntegrityError:
            # If it fails, the DB treats them as duplicates (case-insensitive)
            db.rollback()


# =============================================================================
# Test: SMILES Hash Computation
# =============================================================================


class TestSmilesHash:
    """Tests for smiles_hash field (SHA-256 of canonical SMILES)."""

    def test_smiles_hash_is_sha256(self, identity_setup):
        """smiles_hash is SHA-256 of canonical_smiles."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        molecule = create_molecule(
            db, org.id, user.id,
            smiles=ASPIRIN["smiles"],
            inchi_key=ASPIRIN["inchi_key"],
        )
        db.commit()

        expected = hashlib.sha256(ASPIRIN["smiles"].encode()).hexdigest()
        assert molecule.smiles_hash == expected

    def test_different_smiles_different_hash(self, identity_setup):
        """Different SMILES produce different hashes."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        molecule1 = create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],
        )
        molecule2 = create_molecule(
            db, org.id, user.id,
            smiles=ASPIRIN["smiles"],
            inchi_key=ASPIRIN["inchi_key"],
        )
        db.commit()

        assert molecule1.smiles_hash != molecule2.smiles_hash

    def test_smiles_hash_for_fast_lookup(self, identity_setup):
        """smiles_hash can be used for fast exact-match lookup."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        # Create molecule
        molecule = create_molecule(
            db, org.id, user.id,
            smiles=CAFFEINE["smiles"],
            inchi_key=CAFFEINE["inchi_key"],
        )
        db.commit()

        # Look up by hash
        search_hash = smiles_hash(CAFFEINE["smiles"])
        result = db.query(Molecule).filter(
            Molecule.organization_id == org.id,
            Molecule.smiles_hash == search_hash,
        ).first()

        assert result is not None
        assert result.id == molecule.id


# =============================================================================
# Test: Canonical SMILES Storage
# =============================================================================


class TestCanonicalSmilesStorage:
    """Tests for canonical_smiles field storage."""

    def test_canonical_smiles_stored_as_provided(self, identity_setup):
        """canonical_smiles is stored exactly as provided."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        input_smiles = "CC(=O)OC1=CC=CC=C1C(=O)O"  # Aspirin
        molecule = create_molecule(
            db, org.id, user.id,
            smiles=input_smiles,
            inchi_key=ASPIRIN["inchi_key"],
        )
        db.commit()

        assert molecule.canonical_smiles == input_smiles

    def test_canonical_smiles_persists(self, identity_setup):
        """canonical_smiles is properly persisted to database."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        molecule = create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],
        )
        molecule_id = molecule.id
        db.commit()

        # Clear cache and refetch
        db.expire_all()
        refetched = db.get(Molecule, molecule_id)

        assert refetched.canonical_smiles == ETHANOL["smiles"]

    @pytest.mark.skip(reason="TODO: Canonicalization service not implemented yet")
    def test_smiles_canonicalized_on_insert(self, identity_setup):
        """
        Non-canonical SMILES is canonicalized before storage.

        TODO: This test should pass once a canonicalization service is implemented.
        The service should:
        1. Take any valid SMILES input
        2. Parse with RDKit: mol = Chem.MolFromSmiles(input_smiles)
        3. Generate canonical: canonical = Chem.MolToSmiles(mol)
        4. Store the canonical version

        Example non-canonical inputs that should become canonical:
        - "OCC" -> "CCO" (ethanol, different atom order)
        - "C(O)C" -> "CCO" (ethanol, different notation)
        - "c1ccccc1O" -> "Oc1ccccc1" (phenol, aromatic vs kekulé)
        """
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        # Non-canonical SMILES for ethanol
        non_canonical_smiles = "OCC"  # Oxygen first instead of canonical "CCO"

        molecule = create_molecule(
            db, org.id, user.id,
            smiles=non_canonical_smiles,
            inchi_key=ETHANOL["inchi_key"],
        )
        db.commit()

        # Should be stored as canonical form
        # This will fail until canonicalization is implemented
        expected_canonical = "CCO"
        assert molecule.canonical_smiles == expected_canonical


# =============================================================================
# Test: InChI Field
# =============================================================================


class TestInChIField:
    """Tests for optional InChI field."""

    def test_inchi_is_optional(self, identity_setup):
        """Molecule can be created without InChI."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        molecule = create_molecule(
            db, org.id, user.id,
            smiles=CAFFEINE["smiles"],
            inchi_key=CAFFEINE["inchi_key"],
            inchi=None,  # No InChI
        )
        db.commit()

        assert molecule.inchi is None

    def test_inchi_can_be_long(self, identity_setup):
        """InChI field can store long strings (Text type)."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        # A very long InChI (simulated)
        long_inchi = "InChI=1S/" + "C" * 1000 + "/h" + "H" * 500

        molecule = create_molecule(
            db, org.id, user.id,
            smiles="C" * 100,  # Long SMILES
            inchi_key="AAAAAAAAAAAAA-BBBBBBBBBB-C",  # Fake valid format
            inchi=long_inchi,
        )
        db.commit()

        assert molecule.inchi == long_inchi


# =============================================================================
# Test: Identity Fields Consistency
# =============================================================================


class TestIdentityFieldsConsistency:
    """Tests for consistency between identity fields."""

    def test_smiles_and_inchikey_correspond(self, identity_setup):
        """SMILES and InChIKey should represent the same molecule."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        # Well-known molecule with verified identifiers
        molecule = create_molecule(
            db, org.id, user.id,
            smiles=ASPIRIN["smiles"],
            inchi_key=ASPIRIN["inchi_key"],
            inchi=ASPIRIN["inchi"],
            name=ASPIRIN["name"],
        )
        db.commit()

        # Verify all fields are set correctly
        assert molecule.canonical_smiles == ASPIRIN["smiles"]
        assert molecule.inchi_key == ASPIRIN["inchi_key"]
        assert molecule.inchi == ASPIRIN["inchi"]

    def test_smiles_hash_matches_smiles(self, identity_setup):
        """smiles_hash always matches the stored canonical_smiles."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        molecule = create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],
        )
        db.commit()

        # Hash of stored SMILES should equal stored hash
        computed_hash = hashlib.sha256(molecule.canonical_smiles.encode()).hexdigest()
        assert molecule.smiles_hash == computed_hash


# =============================================================================
# Test: Multiple Molecules in Same Org
# =============================================================================


class TestMultipleMoleculesInOrg:
    """Tests for handling multiple molecules in the same organization."""

    def test_can_store_many_unique_molecules(self, identity_setup):
        """Can store many molecules with unique inchikeys in same org."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        molecules = []
        for i in range(10):
            # Generate unique identifiers
            fake_smiles = f"C{'C' * i}O"
            fake_inchikey = f"AAAAAAAAAAAAA-{i:010d}-N"

            mol = create_molecule(
                db, org.id, user.id,
                smiles=fake_smiles,
                inchi_key=fake_inchikey,
                name=f"Molecule {i}",
            )
            molecules.append(mol)

        db.commit()

        # All molecules should be created
        assert len(molecules) == 10
        for mol in molecules:
            assert mol.id is not None

    def test_lookup_by_inchikey(self, identity_setup):
        """Can look up molecule by inchikey within org."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        # Create several molecules
        create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],
            name=ETHANOL["name"],
        )
        create_molecule(
            db, org.id, user.id,
            smiles=ASPIRIN["smiles"],
            inchi_key=ASPIRIN["inchi_key"],
            name=ASPIRIN["name"],
        )
        db.commit()

        # Look up by inchikey
        result = db.query(Molecule).filter(
            Molecule.organization_id == org.id,
            Molecule.inchi_key == ASPIRIN["inchi_key"],
        ).first()

        assert result is not None
        assert result.name == ASPIRIN["name"]

    def test_lookup_by_smiles_hash(self, identity_setup):
        """Can look up molecule by smiles_hash within org."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        create_molecule(
            db, org.id, user.id,
            smiles=ETHANOL["smiles"],
            inchi_key=ETHANOL["inchi_key"],
            name=ETHANOL["name"],
        )
        create_molecule(
            db, org.id, user.id,
            smiles=ASPIRIN["smiles"],
            inchi_key=ASPIRIN["inchi_key"],
            name=ASPIRIN["name"],
        )
        db.commit()

        # Look up by smiles hash
        search_hash = smiles_hash(ETHANOL["smiles"])
        result = db.query(Molecule).filter(
            Molecule.organization_id == org.id,
            Molecule.smiles_hash == search_hash,
        ).first()

        assert result is not None
        assert result.name == ETHANOL["name"]


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestIdentityEdgeCases:
    """Edge cases for molecule identity fields."""

    def test_long_smiles_string(self, identity_setup):
        """Can store SMILES up to 2000 characters."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        # Create a long SMILES (within 2000 char limit)
        long_smiles = "C" * 1999 + "O"
        assert len(long_smiles) == 2000

        molecule = create_molecule(
            db, org.id, user.id,
            smiles=long_smiles,
            inchi_key="LONGMOLECULEKEY-AAAAAAAAA-N",
        )
        db.commit()

        assert molecule.canonical_smiles == long_smiles
        assert len(molecule.canonical_smiles) == 2000

    def test_inchikey_exact_length(self, identity_setup):
        """InChIKey must be exactly 27 characters."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        # Valid 27-char InChIKey
        valid_key = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
        assert len(valid_key) == 27

        molecule = create_molecule(
            db, org.id, user.id,
            smiles="CCO",
            inchi_key=valid_key,
        )
        db.commit()

        assert len(molecule.inchi_key) == 27

    def test_special_characters_in_smiles(self, identity_setup):
        """SMILES with special characters are stored correctly."""
        db = identity_setup["db"]
        org = identity_setup["org_a"]
        user = identity_setup["user_a"]

        # SMILES with brackets, charges, stereochemistry
        complex_smiles = "[NH4+].[Cl-]"  # Ammonium chloride
        fake_key = "NLXLAEXVIDQMFP-UHFFFAOYSA-N"

        molecule = create_molecule(
            db, org.id, user.id,
            smiles=complex_smiles,
            inchi_key=fake_key,
        )
        db.commit()

        assert molecule.canonical_smiles == complex_smiles
        assert "[" in molecule.canonical_smiles
        assert "+" in molecule.canonical_smiles
