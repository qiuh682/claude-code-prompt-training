"""
Tests for SQLAlchemy relationships among Task 1.3 core entities.

Verifies:
- Project.molecules and Project.targets return expected objects via association tables
- Target.assays returns expected assays
- Molecule.assays returns expected assays
- Prediction references correct inputs (project, molecule, target) and stores outputs

Setup:
- Create Organization + User (reuse Task 1.2 patterns)
- Create Project, Molecule, Target
- Link Molecule and Target to Project via ProjectMolecule, ProjectTarget
- Create Assay linked to Molecule and Target
- Create Prediction linked to Project + Molecule + Target

Usage:
    DATABASE_URL_TEST=postgresql://postgres:postgres@localhost:5433/drugdiscovery_test \
    pytest tests/test_relationships.py -v
"""

import hashlib
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
    MoleculeTarget,
    Prediction,
    Project,
    ProjectMolecule,
    ProjectTarget,
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
def relationship_setup(test_session_factory):
    """
    Set up organization, user, and discovery entities for relationship tests.

    Creates:
    - 1 Organization
    - 1 Admin User with membership
    - 1 Project
    - 2 Molecules
    - 2 Targets
    - Links between them via association tables
    - 2 Assays (one binding, one ADMET)
    - 2 Predictions

    Returns dict with all entity IDs and the session.
    """
    db: Session = test_session_factory()

    try:
        # =================================================================
        # Create Organization
        # =================================================================
        org = Organization(
            id=uuid4(),
            name="Test Pharma Inc",
            slug=f"test-pharma-{uuid4().hex[:8]}",
        )
        db.add(org)
        db.flush()

        # =================================================================
        # Create User + Membership
        # =================================================================
        user = User(
            id=uuid4(),
            email=f"researcher-{uuid4().hex[:8]}@testpharma.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="Test Researcher",
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
            name="Cancer Drug Discovery",
            description="Finding novel cancer therapeutics",
            status="active",
            therapeutic_area="Oncology",
            created_by=user.id,
        )
        db.add(project)
        db.flush()

        # =================================================================
        # Create Molecules
        # =================================================================
        molecule1_smiles = "CC(=O)OC1=CC=CC=C1C(=O)O"  # Aspirin
        molecule1 = Molecule(
            id=uuid4(),
            organization_id=org.id,
            canonical_smiles=molecule1_smiles,
            inchi_key="BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            smiles_hash=smiles_hash(molecule1_smiles),
            name="Aspirin",
            molecular_formula="C9H8O4",
            molecular_weight=Decimal("180.1574"),
            created_by=user.id,
        )
        db.add(molecule1)
        db.flush()

        molecule2_smiles = "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O"  # Ibuprofen
        molecule2 = Molecule(
            id=uuid4(),
            organization_id=org.id,
            canonical_smiles=molecule2_smiles,
            inchi_key="HEFNNWSXXWATRW-UHFFFAOYSA-N",
            smiles_hash=smiles_hash(molecule2_smiles),
            name="Ibuprofen",
            molecular_formula="C13H18O2",
            molecular_weight=Decimal("206.2808"),
            created_by=user.id,
        )
        db.add(molecule2)
        db.flush()

        # =================================================================
        # Create Targets
        # =================================================================
        target1 = Target(
            id=uuid4(),
            organization_id=org.id,
            uniprot_id="P00533",
            gene_symbol="EGFR",
            name="Epidermal Growth Factor Receptor",
            organism="Homo sapiens",
            family="Kinase",
            created_by=user.id,
        )
        db.add(target1)
        db.flush()

        target2 = Target(
            id=uuid4(),
            organization_id=org.id,
            uniprot_id="P04637",
            gene_symbol="TP53",
            name="Tumor Protein P53",
            organism="Homo sapiens",
            family="Tumor Suppressor",
            created_by=user.id,
        )
        db.add(target2)
        db.flush()

        # =================================================================
        # Create Association Links
        # =================================================================

        # Link molecules to project
        pm1 = ProjectMolecule(
            id=uuid4(),
            project_id=project.id,
            molecule_id=molecule1.id,
            added_by=user.id,
            notes="Lead compound",
        )
        db.add(pm1)

        pm2 = ProjectMolecule(
            id=uuid4(),
            project_id=project.id,
            molecule_id=molecule2.id,
            added_by=user.id,
            notes="Backup compound",
        )
        db.add(pm2)
        db.flush()

        # Link targets to project
        pt1 = ProjectTarget(
            id=uuid4(),
            project_id=project.id,
            target_id=target1.id,
            is_primary=True,
            added_by=user.id,
        )
        db.add(pt1)

        pt2 = ProjectTarget(
            id=uuid4(),
            project_id=project.id,
            target_id=target2.id,
            is_primary=False,
            added_by=user.id,
        )
        db.add(pt2)
        db.flush()

        # Link molecule1 to target1 (tested relationship)
        mt1 = MoleculeTarget(
            id=uuid4(),
            molecule_id=molecule1.id,
            target_id=target1.id,
            relationship_type="active",
        )
        db.add(mt1)
        db.flush()

        # =================================================================
        # Create Assays
        # =================================================================

        # Binding assay: molecule1 vs target1
        assay1 = Assay(
            id=uuid4(),
            organization_id=org.id,
            project_id=project.id,
            molecule_id=molecule1.id,
            target_id=target1.id,
            assay_type="binding",
            assay_name="EGFR Binding Assay",
            result_type="IC50",
            result_value=Decimal("0.150"),
            result_unit="nM",
            result_qualifier="=",
            confidence="high",
            source="internal",
            created_by=user.id,
        )
        db.add(assay1)
        db.flush()

        # ADMET assay: molecule2 (no target)
        assay2 = Assay(
            id=uuid4(),
            organization_id=org.id,
            project_id=project.id,
            molecule_id=molecule2.id,
            target_id=None,  # ADMET assays don't require target
            assay_type="admet",
            assay_name="Microsomal Stability",
            result_type="half_life",
            result_value=Decimal("45.5"),
            result_unit="min",
            result_qualifier="=",
            confidence="medium",
            source="internal",
            created_by=user.id,
        )
        db.add(assay2)
        db.flush()

        # =================================================================
        # Create Predictions
        # =================================================================

        # Activity prediction for molecule1 vs target1
        prediction1 = Prediction(
            id=uuid4(),
            organization_id=org.id,
            project_id=project.id,
            molecule_id=molecule1.id,
            target_id=target1.id,
            model_name="BindingPredictor",
            model_version="1.2.0",
            prediction_type="activity",
            predicted_value=Decimal("0.125"),
            confidence_score=Decimal("0.9234"),
            input_features={"morgan_fp": "binary_encoded", "mol_weight": 180.15},
            explanation={"top_fragments": ["acetyl", "carboxyl"]},
            created_by=user.id,
        )
        db.add(prediction1)
        db.flush()

        # Toxicity prediction for molecule2
        prediction2 = Prediction(
            id=uuid4(),
            organization_id=org.id,
            project_id=project.id,
            molecule_id=molecule2.id,
            target_id=None,
            model_name="ToxPredictor",
            model_version="2.0.0",
            prediction_type="toxicity",
            predicted_class="low_risk",
            confidence_score=Decimal("0.8567"),
            created_by=user.id,
        )
        db.add(prediction2)
        db.flush()

        db.commit()

        yield {
            "db": db,
            "org": org,
            "user": user,
            "project": project,
            "molecule1": molecule1,
            "molecule2": molecule2,
            "target1": target1,
            "target2": target2,
            "assay1": assay1,
            "assay2": assay2,
            "prediction1": prediction1,
            "prediction2": prediction2,
        }

    finally:
        # Cleanup: delete all created data
        try:
            db.execute(text("SET session_replication_role = 'replica';"))
            db.execute(text("DELETE FROM predictions WHERE organization_id = :org_id"), {"org_id": org.id})
            db.execute(text("DELETE FROM assays WHERE organization_id = :org_id"), {"org_id": org.id})
            db.execute(text("DELETE FROM molecule_targets WHERE molecule_id IN (SELECT id FROM molecules WHERE organization_id = :org_id)"), {"org_id": org.id})
            db.execute(text("DELETE FROM project_molecules WHERE project_id IN (SELECT id FROM projects WHERE organization_id = :org_id)"), {"org_id": org.id})
            db.execute(text("DELETE FROM project_targets WHERE project_id IN (SELECT id FROM projects WHERE organization_id = :org_id)"), {"org_id": org.id})
            db.execute(text("DELETE FROM molecules WHERE organization_id = :org_id"), {"org_id": org.id})
            db.execute(text("DELETE FROM targets WHERE organization_id = :org_id"), {"org_id": org.id})
            db.execute(text("DELETE FROM projects WHERE organization_id = :org_id"), {"org_id": org.id})
            db.execute(text("DELETE FROM memberships WHERE organization_id = :org_id"), {"org_id": org.id})
            db.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user.id})
            db.execute(text("DELETE FROM organizations WHERE id = :org_id"), {"org_id": org.id})
            db.execute(text("SET session_replication_role = 'origin';"))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


# =============================================================================
# Test: Project Relationships
# =============================================================================


class TestProjectRelationships:
    """Tests for Project relationships to Molecules and Targets."""

    def test_project_molecule_associations_exist(self, relationship_setup):
        """Project has molecule_associations populated."""
        db = relationship_setup["db"]
        project = relationship_setup["project"]

        # Refresh to ensure associations are loaded
        db.refresh(project)

        assert len(project.molecule_associations) == 2
        molecule_ids = {assoc.molecule_id for assoc in project.molecule_associations}
        assert relationship_setup["molecule1"].id in molecule_ids
        assert relationship_setup["molecule2"].id in molecule_ids

    def test_project_target_associations_exist(self, relationship_setup):
        """Project has target_associations populated."""
        db = relationship_setup["db"]
        project = relationship_setup["project"]

        db.refresh(project)

        assert len(project.target_associations) == 2
        target_ids = {assoc.target_id for assoc in project.target_associations}
        assert relationship_setup["target1"].id in target_ids
        assert relationship_setup["target2"].id in target_ids

    def test_project_molecules_via_association(self, relationship_setup):
        """Can access molecules via project.molecule_associations."""
        db = relationship_setup["db"]
        project = relationship_setup["project"]

        db.refresh(project)

        # Get molecules through associations
        molecules = [assoc.molecule for assoc in project.molecule_associations]
        molecule_names = {m.name for m in molecules}

        assert "Aspirin" in molecule_names
        assert "Ibuprofen" in molecule_names

    def test_project_targets_via_association(self, relationship_setup):
        """Can access targets via project.target_associations."""
        db = relationship_setup["db"]
        project = relationship_setup["project"]

        db.refresh(project)

        # Get targets through associations
        targets = [assoc.target for assoc in project.target_associations]
        target_genes = {t.gene_symbol for t in targets}

        assert "EGFR" in target_genes
        assert "TP53" in target_genes

    def test_project_primary_target_flag(self, relationship_setup):
        """ProjectTarget.is_primary flag is set correctly."""
        db = relationship_setup["db"]
        project = relationship_setup["project"]

        db.refresh(project)

        primary_targets = [
            assoc.target
            for assoc in project.target_associations
            if assoc.is_primary
        ]
        assert len(primary_targets) == 1
        assert primary_targets[0].gene_symbol == "EGFR"

    def test_project_assays_relationship(self, relationship_setup):
        """Project.assays returns assays linked to this project."""
        db = relationship_setup["db"]
        project = relationship_setup["project"]

        db.refresh(project)

        assert len(project.assays) == 2
        assay_types = {a.assay_type for a in project.assays}
        assert "binding" in assay_types
        assert "admet" in assay_types

    def test_project_predictions_relationship(self, relationship_setup):
        """Project.predictions returns predictions for this project."""
        db = relationship_setup["db"]
        project = relationship_setup["project"]

        db.refresh(project)

        assert len(project.predictions) == 2
        model_names = {p.model_name for p in project.predictions}
        assert "BindingPredictor" in model_names
        assert "ToxPredictor" in model_names


# =============================================================================
# Test: Target Relationships
# =============================================================================


class TestTargetRelationships:
    """Tests for Target relationships."""

    def test_target_assays_returns_expected_assays(self, relationship_setup):
        """Target.assays returns assays linked to this target."""
        db = relationship_setup["db"]
        target1 = relationship_setup["target1"]

        db.refresh(target1)

        # Target1 (EGFR) should have 1 binding assay
        assert len(target1.assays) == 1
        assert target1.assays[0].assay_type == "binding"
        assert target1.assays[0].result_type == "IC50"

    def test_target_without_assays(self, relationship_setup):
        """Target2 (TP53) has no assays linked."""
        db = relationship_setup["db"]
        target2 = relationship_setup["target2"]

        db.refresh(target2)

        assert len(target2.assays) == 0

    def test_target_predictions_relationship(self, relationship_setup):
        """Target.predictions returns predictions for this target."""
        db = relationship_setup["db"]
        target1 = relationship_setup["target1"]

        db.refresh(target1)

        # Target1 has 1 activity prediction
        assert len(target1.predictions) == 1
        assert target1.predictions[0].prediction_type == "activity"

    def test_target_molecule_associations(self, relationship_setup):
        """Target has molecule_associations for tested molecules."""
        db = relationship_setup["db"]
        target1 = relationship_setup["target1"]

        db.refresh(target1)

        assert len(target1.molecule_associations) == 1
        assoc = target1.molecule_associations[0]
        assert assoc.relationship_type == "active"
        assert assoc.molecule.name == "Aspirin"

    def test_target_project_associations(self, relationship_setup):
        """Target has project_associations linking to projects."""
        db = relationship_setup["db"]
        target1 = relationship_setup["target1"]

        db.refresh(target1)

        assert len(target1.project_associations) == 1
        assert target1.project_associations[0].project.name == "Cancer Drug Discovery"


# =============================================================================
# Test: Molecule Relationships
# =============================================================================


class TestMoleculeRelationships:
    """Tests for Molecule relationships."""

    def test_molecule_assays_returns_expected_assays(self, relationship_setup):
        """Molecule.assays returns assays for this molecule."""
        db = relationship_setup["db"]
        molecule1 = relationship_setup["molecule1"]

        db.refresh(molecule1)

        # Molecule1 (Aspirin) has 1 binding assay
        assert len(molecule1.assays) == 1
        assert molecule1.assays[0].assay_name == "EGFR Binding Assay"

    def test_molecule_predictions_relationship(self, relationship_setup):
        """Molecule.predictions returns predictions for this molecule."""
        db = relationship_setup["db"]
        molecule1 = relationship_setup["molecule1"]

        db.refresh(molecule1)

        assert len(molecule1.predictions) == 1
        assert molecule1.predictions[0].model_name == "BindingPredictor"

    def test_molecule_target_associations(self, relationship_setup):
        """Molecule has target_associations for linked targets."""
        db = relationship_setup["db"]
        molecule1 = relationship_setup["molecule1"]

        db.refresh(molecule1)

        assert len(molecule1.target_associations) == 1
        assoc = molecule1.target_associations[0]
        assert assoc.target.gene_symbol == "EGFR"

    def test_molecule_project_associations(self, relationship_setup):
        """Molecule has project_associations linking to projects."""
        db = relationship_setup["db"]
        molecule1 = relationship_setup["molecule1"]

        db.refresh(molecule1)

        assert len(molecule1.project_associations) == 1
        assoc = molecule1.project_associations[0]
        assert assoc.project.name == "Cancer Drug Discovery"
        assert assoc.notes == "Lead compound"

    def test_molecule2_admet_assay(self, relationship_setup):
        """Molecule2 has ADMET assay without target."""
        db = relationship_setup["db"]
        molecule2 = relationship_setup["molecule2"]

        db.refresh(molecule2)

        assert len(molecule2.assays) == 1
        assay = molecule2.assays[0]
        assert assay.assay_type == "admet"
        assert assay.target_id is None
        assert assay.target is None


# =============================================================================
# Test: Assay Relationships
# =============================================================================


class TestAssayRelationships:
    """Tests for Assay relationships."""

    def test_assay_molecule_relationship(self, relationship_setup):
        """Assay.molecule returns the linked molecule."""
        db = relationship_setup["db"]
        assay1 = relationship_setup["assay1"]

        db.refresh(assay1)

        assert assay1.molecule is not None
        assert assay1.molecule.name == "Aspirin"

    def test_assay_target_relationship(self, relationship_setup):
        """Assay.target returns the linked target."""
        db = relationship_setup["db"]
        assay1 = relationship_setup["assay1"]

        db.refresh(assay1)

        assert assay1.target is not None
        assert assay1.target.gene_symbol == "EGFR"

    def test_assay_project_relationship(self, relationship_setup):
        """Assay.project returns the linked project."""
        db = relationship_setup["db"]
        assay1 = relationship_setup["assay1"]

        db.refresh(assay1)

        assert assay1.project is not None
        assert assay1.project.name == "Cancer Drug Discovery"

    def test_assay_organization_relationship(self, relationship_setup):
        """Assay.organization returns the parent org."""
        db = relationship_setup["db"]
        assay1 = relationship_setup["assay1"]

        db.refresh(assay1)

        assert assay1.organization is not None
        assert assay1.organization.name == "Test Pharma Inc"

    def test_admet_assay_without_target(self, relationship_setup):
        """ADMET assay has target=None but molecule is present."""
        db = relationship_setup["db"]
        assay2 = relationship_setup["assay2"]

        db.refresh(assay2)

        assert assay2.target is None
        assert assay2.molecule is not None
        assert assay2.molecule.name == "Ibuprofen"


# =============================================================================
# Test: Prediction Relationships
# =============================================================================


class TestPredictionRelationships:
    """Tests for Prediction relationships and stored values."""

    def test_prediction_references_correct_molecule(self, relationship_setup):
        """Prediction.molecule returns correct molecule."""
        db = relationship_setup["db"]
        prediction1 = relationship_setup["prediction1"]

        db.refresh(prediction1)

        assert prediction1.molecule is not None
        assert prediction1.molecule.name == "Aspirin"

    def test_prediction_references_correct_target(self, relationship_setup):
        """Prediction.target returns correct target."""
        db = relationship_setup["db"]
        prediction1 = relationship_setup["prediction1"]

        db.refresh(prediction1)

        assert prediction1.target is not None
        assert prediction1.target.gene_symbol == "EGFR"

    def test_prediction_references_correct_project(self, relationship_setup):
        """Prediction.project returns correct project."""
        db = relationship_setup["db"]
        prediction1 = relationship_setup["prediction1"]

        db.refresh(prediction1)

        assert prediction1.project is not None
        assert prediction1.project.name == "Cancer Drug Discovery"

    def test_prediction_stores_model_metadata(self, relationship_setup):
        """Prediction stores model name and version."""
        prediction1 = relationship_setup["prediction1"]

        assert prediction1.model_name == "BindingPredictor"
        assert prediction1.model_version == "1.2.0"
        assert prediction1.prediction_type == "activity"

    def test_prediction_stores_output_value(self, relationship_setup):
        """Prediction stores predicted_value correctly."""
        prediction1 = relationship_setup["prediction1"]

        assert prediction1.predicted_value == Decimal("0.125")

    def test_prediction_stores_confidence_score(self, relationship_setup):
        """Prediction stores confidence_score in valid range."""
        prediction1 = relationship_setup["prediction1"]

        assert prediction1.confidence_score == Decimal("0.9234")
        assert 0 <= float(prediction1.confidence_score) <= 1

    def test_prediction_stores_input_features(self, relationship_setup):
        """Prediction stores input_features as JSONB."""
        prediction1 = relationship_setup["prediction1"]

        assert prediction1.input_features is not None
        assert "morgan_fp" in prediction1.input_features
        assert prediction1.input_features["mol_weight"] == 180.15

    def test_prediction_stores_explanation(self, relationship_setup):
        """Prediction stores explanation as JSONB."""
        prediction1 = relationship_setup["prediction1"]

        assert prediction1.explanation is not None
        assert "top_fragments" in prediction1.explanation
        assert "acetyl" in prediction1.explanation["top_fragments"]

    def test_classification_prediction(self, relationship_setup):
        """Classification prediction stores predicted_class."""
        prediction2 = relationship_setup["prediction2"]

        assert prediction2.predicted_class == "low_risk"
        assert prediction2.prediction_type == "toxicity"
        assert prediction2.predicted_value is None  # Classification, not regression

    def test_prediction_without_target(self, relationship_setup):
        """Toxicity prediction can have target=None."""
        db = relationship_setup["db"]
        prediction2 = relationship_setup["prediction2"]

        db.refresh(prediction2)

        assert prediction2.target is None
        assert prediction2.molecule is not None


# =============================================================================
# Test: Association Table Attributes
# =============================================================================


class TestAssociationTableAttributes:
    """Tests for attributes on association tables."""

    def test_project_molecule_has_notes(self, relationship_setup):
        """ProjectMolecule stores notes field."""
        db = relationship_setup["db"]
        project = relationship_setup["project"]

        db.refresh(project)

        lead_assoc = next(
            (a for a in project.molecule_associations if a.notes == "Lead compound"),
            None,
        )
        assert lead_assoc is not None
        assert lead_assoc.molecule.name == "Aspirin"

    def test_project_molecule_has_added_by(self, relationship_setup):
        """ProjectMolecule tracks who added the molecule."""
        db = relationship_setup["db"]
        project = relationship_setup["project"]
        user = relationship_setup["user"]

        db.refresh(project)

        for assoc in project.molecule_associations:
            assert assoc.added_by == user.id

    def test_project_target_has_is_primary(self, relationship_setup):
        """ProjectTarget has is_primary flag."""
        db = relationship_setup["db"]
        project = relationship_setup["project"]

        db.refresh(project)

        primary_count = sum(1 for a in project.target_associations if a.is_primary)
        assert primary_count == 1

    def test_molecule_target_relationship_type(self, relationship_setup):
        """MoleculeTarget stores relationship_type."""
        db = relationship_setup["db"]
        molecule1 = relationship_setup["molecule1"]

        db.refresh(molecule1)

        assert len(molecule1.target_associations) == 1
        assert molecule1.target_associations[0].relationship_type == "active"


# =============================================================================
# Test: Bidirectional Navigation
# =============================================================================


class TestBidirectionalNavigation:
    """Tests for navigating relationships in both directions."""

    def test_molecule_to_project_and_back(self, relationship_setup):
        """Can navigate Molecule -> Project -> Molecule."""
        db = relationship_setup["db"]
        molecule1 = relationship_setup["molecule1"]

        db.refresh(molecule1)

        # Molecule -> ProjectMolecule -> Project
        project = molecule1.project_associations[0].project

        # Project -> ProjectMolecule -> Molecules
        project_molecules = [a.molecule for a in project.molecule_associations]
        molecule_names = {m.name for m in project_molecules}

        assert molecule1.name in molecule_names

    def test_target_to_assay_to_molecule(self, relationship_setup):
        """Can navigate Target -> Assay -> Molecule."""
        db = relationship_setup["db"]
        target1 = relationship_setup["target1"]

        db.refresh(target1)

        # Target -> Assays -> Molecules
        assay = target1.assays[0]
        molecule = assay.molecule

        assert molecule.name == "Aspirin"

    def test_prediction_full_chain(self, relationship_setup):
        """Can navigate Prediction -> Project/Molecule/Target."""
        db = relationship_setup["db"]
        prediction1 = relationship_setup["prediction1"]

        db.refresh(prediction1)

        # Full navigation chain
        assert prediction1.project.name == "Cancer Drug Discovery"
        assert prediction1.molecule.name == "Aspirin"
        assert prediction1.target.gene_symbol == "EGFR"

        # And back from molecule to prediction
        db.refresh(prediction1.molecule)
        assert prediction1 in prediction1.molecule.predictions


# =============================================================================
# Test: Organization Isolation in Relationships
# =============================================================================


class TestOrganizationIsolation:
    """Tests that relationships respect organization boundaries."""

    def test_all_entities_belong_to_same_org(self, relationship_setup):
        """All created entities belong to the same organization."""
        org = relationship_setup["org"]
        project = relationship_setup["project"]
        molecule1 = relationship_setup["molecule1"]
        target1 = relationship_setup["target1"]
        assay1 = relationship_setup["assay1"]
        prediction1 = relationship_setup["prediction1"]

        assert project.organization_id == org.id
        assert molecule1.organization_id == org.id
        assert target1.organization_id == org.id
        assert assay1.organization_id == org.id
        assert prediction1.organization_id == org.id

    def test_organization_molecules_relationship(self, relationship_setup):
        """Organization.molecules returns all org molecules."""
        db = relationship_setup["db"]
        org = relationship_setup["org"]

        db.refresh(org)

        assert len(org.molecules) == 2
        molecule_names = {m.name for m in org.molecules}
        assert "Aspirin" in molecule_names
        assert "Ibuprofen" in molecule_names

    def test_organization_targets_relationship(self, relationship_setup):
        """Organization.targets returns all org targets."""
        db = relationship_setup["db"]
        org = relationship_setup["org"]

        db.refresh(org)

        assert len(org.targets) == 2

    def test_organization_projects_relationship(self, relationship_setup):
        """Organization.projects returns all org projects."""
        db = relationship_setup["db"]
        org = relationship_setup["org"]

        db.refresh(org)

        assert len(org.projects) == 1
        assert org.projects[0].name == "Cancer Drug Discovery"
