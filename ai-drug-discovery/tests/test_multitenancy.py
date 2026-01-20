"""
Integration tests for multi-tenancy isolation.

Policy choices (applied consistently):
- User not member of org: 403 Forbidden ("Not a member of this organization")
- Org does not exist: 404 Not Found ("Organization not found")
- Team does not exist: 404 Not Found ("Team not found")
- Team not in user's org: 404 Not Found ("Team not found in this organization")
- User not member of team (non-admin): 403 Forbidden ("Not a member of this team")

Setup:
- OrgA with userA (admin), OrgB with userB (admin)
- Team1 in OrgA with user_team1, Team2 in OrgA with user_team2
"""

from uuid import uuid4

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import (
    OrgContext,
    TeamContext,
    require_org_access,
    require_team_access,
)
from apps.api.auth.models import Membership, Organization, Team, User, UserRole
from apps.api.auth.security import hash_password
from apps.api.auth.service import create_tokens

# =============================================================================
# Test Router for Team-Scoped Endpoints
# =============================================================================

test_router = APIRouter(prefix="/test", tags=["Test"])


@test_router.get("/orgs/{org_id}/resources")
def get_org_resources(ctx: OrgContext = Depends(require_org_access)):
    """Test endpoint: org-scoped resource."""
    return {
        "org_id": str(ctx.org_id),
        "user_id": str(ctx.user.id),
        "role": ctx.role.value,
        "resources": ["resource-1", "resource-2"],
    }


@test_router.get("/orgs/{org_id}/teams/{team_id}/data")
def get_team_data(ctx: TeamContext = Depends(require_team_access)):
    """Test endpoint: team-scoped resource."""
    return {
        "org_id": str(ctx.org_id),
        "team_id": str(ctx.team_id),
        "user_id": str(ctx.user.id),
        "data": ["team-data-1", "team-data-2"],
    }


# =============================================================================
# Test Data
# =============================================================================

TEST_PASSWORD = "SecureTestPass123"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def multitenancy_setup(test_session_factory, app):
    """
    Set up two organizations with separate users.

    Structure:
        OrgA:
            - userA (admin)
            - Team1: user_team1 (researcher)
            - Team2: user_team2 (researcher)
        OrgB:
            - userB (admin)

    Returns dict with all entities and tokens.
    """
    # Add test router to app
    app.include_router(test_router)

    db: Session = test_session_factory()

    try:
        # =================================================================
        # Create OrgA
        # =================================================================
        org_a = Organization(
            id=uuid4(),
            name="Organization A",
            slug=f"org-a-{uuid4().hex[:8]}",
        )
        db.add(org_a)
        db.flush()

        # Create Team1 in OrgA
        team1 = Team(
            id=uuid4(),
            organization_id=org_a.id,
            name="Team One",
        )
        db.add(team1)
        db.flush()

        # Create Team2 in OrgA
        team2 = Team(
            id=uuid4(),
            organization_id=org_a.id,
            name="Team Two",
        )
        db.add(team2)
        db.flush()

        # Create userA (admin of OrgA, no specific team)
        user_a = User(
            id=uuid4(),
            email=f"user-a-{uuid4().hex[:8]}@orga.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="User A (Admin)",
            is_active=True,
        )
        db.add(user_a)
        db.flush()

        membership_a = Membership(
            user_id=user_a.id,
            organization_id=org_a.id,
            role=UserRole.ADMIN,
            team_id=None,  # Admin not assigned to specific team
        )
        db.add(membership_a)
        db.flush()

        # Create user_team1 (researcher in Team1)
        user_team1 = User(
            id=uuid4(),
            email=f"user-team1-{uuid4().hex[:8]}@orga.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="User Team1 (Researcher)",
            is_active=True,
        )
        db.add(user_team1)
        db.flush()

        membership_team1 = Membership(
            user_id=user_team1.id,
            organization_id=org_a.id,
            role=UserRole.RESEARCHER,
            team_id=team1.id,
        )
        db.add(membership_team1)
        db.flush()

        # Create user_team2 (researcher in Team2)
        user_team2 = User(
            id=uuid4(),
            email=f"user-team2-{uuid4().hex[:8]}@orga.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="User Team2 (Researcher)",
            is_active=True,
        )
        db.add(user_team2)
        db.flush()

        membership_team2 = Membership(
            user_id=user_team2.id,
            organization_id=org_a.id,
            role=UserRole.RESEARCHER,
            team_id=team2.id,
        )
        db.add(membership_team2)
        db.flush()

        # =================================================================
        # Create OrgB
        # =================================================================
        org_b = Organization(
            id=uuid4(),
            name="Organization B",
            slug=f"org-b-{uuid4().hex[:8]}",
        )
        db.add(org_b)
        db.flush()

        # Create userB (admin of OrgB)
        user_b = User(
            id=uuid4(),
            email=f"user-b-{uuid4().hex[:8]}@orgb.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="User B (Admin)",
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

        # Create tokens for all users
        token_a, _ = create_tokens(db, user_a)
        token_team1, _ = create_tokens(db, user_team1)
        token_team2, _ = create_tokens(db, user_team2)
        token_b, _ = create_tokens(db, user_b)

        yield {
            # OrgA
            "org_a": {
                "id": org_a.id,
                "name": org_a.name,
                "slug": org_a.slug,
            },
            "user_a": {
                "id": user_a.id,
                "email": user_a.email,
                "token": token_a,
                "headers": {"Authorization": f"Bearer {token_a}"},
            },
            "team1": {
                "id": team1.id,
                "name": team1.name,
            },
            "user_team1": {
                "id": user_team1.id,
                "email": user_team1.email,
                "token": token_team1,
                "headers": {"Authorization": f"Bearer {token_team1}"},
            },
            "team2": {
                "id": team2.id,
                "name": team2.name,
            },
            "user_team2": {
                "id": user_team2.id,
                "email": user_team2.email,
                "token": token_team2,
                "headers": {"Authorization": f"Bearer {token_team2}"},
            },
            # OrgB
            "org_b": {
                "id": org_b.id,
                "name": org_b.name,
                "slug": org_b.slug,
            },
            "user_b": {
                "id": user_b.id,
                "email": user_b.email,
                "token": token_b,
                "headers": {"Authorization": f"Bearer {token_b}"},
            },
        }

    finally:
        db.rollback()
        db.close()


@pytest.fixture
def mt_client(app, multitenancy_setup) -> tuple[TestClient, dict]:
    """
    TestClient with multi-tenancy setup.

    Returns tuple of (client, setup_data).
    """
    with TestClient(app) as client:
        yield client, multitenancy_setup


# =============================================================================
# Test: Organization Isolation
# =============================================================================


class TestOrganizationIsolation:
    """Tests for cross-organization isolation."""

    def test_user_can_access_own_org(self, mt_client):
        """UserA can access OrgA resources -> 200."""
        client, setup = mt_client
        url = f"/test/orgs/{setup['org_a']['id']}/resources"

        response = client.get(url, headers=setup["user_a"]["headers"])

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == str(setup["org_a"]["id"])
        assert data["user_id"] == str(setup["user_a"]["id"])

    def test_user_cannot_access_other_org(self, mt_client):
        """UserB cannot access OrgA resources -> 403."""
        client, setup = mt_client
        url = f"/test/orgs/{setup['org_a']['id']}/resources"

        response = client.get(url, headers=setup["user_b"]["headers"])

        assert response.status_code == 403
        assert "not a member" in response.json()["detail"].lower()

    def test_user_b_can_access_own_org(self, mt_client):
        """UserB can access OrgB resources -> 200."""
        client, setup = mt_client
        url = f"/test/orgs/{setup['org_b']['id']}/resources"

        response = client.get(url, headers=setup["user_b"]["headers"])

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == str(setup["org_b"]["id"])

    def test_user_a_cannot_access_org_b(self, mt_client):
        """UserA cannot access OrgB resources -> 403."""
        client, setup = mt_client
        url = f"/test/orgs/{setup['org_b']['id']}/resources"

        response = client.get(url, headers=setup["user_a"]["headers"])

        assert response.status_code == 403
        assert "not a member" in response.json()["detail"].lower()

    def test_nonexistent_org_returns_404(self, mt_client):
        """Accessing non-existent org -> 404."""
        client, setup = mt_client
        fake_org_id = uuid4()
        url = f"/test/orgs/{fake_org_id}/resources"

        response = client.get(url, headers=setup["user_a"]["headers"])

        assert response.status_code == 404
        assert "organization not found" in response.json()["detail"].lower()

    def test_projects_endpoint_org_isolation(self, mt_client):
        """Test actual projects endpoint respects org isolation."""
        client, setup = mt_client

        # UserA can access OrgA projects
        url_a = f"/orgs/{setup['org_a']['id']}/projects"
        response_a = client.get(url_a, headers=setup["user_a"]["headers"])
        assert response_a.status_code == 200

        # UserB cannot access OrgA projects
        response_b = client.get(url_a, headers=setup["user_b"]["headers"])
        assert response_b.status_code == 403


# =============================================================================
# Test: Team Isolation
# =============================================================================


class TestTeamIsolation:
    """Tests for cross-team isolation within an organization."""

    def test_user_can_access_own_team(self, mt_client):
        """User in Team1 can access Team1 data -> 200."""
        client, setup = mt_client
        url = f"/test/orgs/{setup['org_a']['id']}/teams/{setup['team1']['id']}/data"

        response = client.get(url, headers=setup["user_team1"]["headers"])

        assert response.status_code == 200
        data = response.json()
        assert data["team_id"] == str(setup["team1"]["id"])
        assert data["user_id"] == str(setup["user_team1"]["id"])

    def test_user_cannot_access_other_team(self, mt_client):
        """User in Team1 cannot access Team2 data -> 403."""
        client, setup = mt_client
        url = f"/test/orgs/{setup['org_a']['id']}/teams/{setup['team2']['id']}/data"

        response = client.get(url, headers=setup["user_team1"]["headers"])

        assert response.status_code == 403
        assert "not a member of this team" in response.json()["detail"].lower()

    def test_user_team2_cannot_access_team1(self, mt_client):
        """User in Team2 cannot access Team1 data -> 403."""
        client, setup = mt_client
        url = f"/test/orgs/{setup['org_a']['id']}/teams/{setup['team1']['id']}/data"

        response = client.get(url, headers=setup["user_team2"]["headers"])

        assert response.status_code == 403
        assert "not a member of this team" in response.json()["detail"].lower()

    def test_admin_can_access_any_team(self, mt_client):
        """Org admin can access any team in their org -> 200."""
        client, setup = mt_client

        # Admin can access Team1
        url1 = f"/test/orgs/{setup['org_a']['id']}/teams/{setup['team1']['id']}/data"
        response1 = client.get(url1, headers=setup["user_a"]["headers"])
        assert response1.status_code == 200

        # Admin can access Team2
        url2 = f"/test/orgs/{setup['org_a']['id']}/teams/{setup['team2']['id']}/data"
        response2 = client.get(url2, headers=setup["user_a"]["headers"])
        assert response2.status_code == 200

    def test_nonexistent_team_returns_404(self, mt_client):
        """Accessing non-existent team -> 404."""
        client, setup = mt_client
        fake_team_id = uuid4()
        url = f"/test/orgs/{setup['org_a']['id']}/teams/{fake_team_id}/data"

        response = client.get(url, headers=setup["user_a"]["headers"])

        assert response.status_code == 404
        assert "team not found" in response.json()["detail"].lower()

    def test_team_from_other_org_returns_404(self, mt_client):
        """Accessing team from different org -> 404 (not 403, to avoid info leak)."""
        client, setup = mt_client
        # Try to access OrgA's Team1 through OrgB's URL path
        # This should fail at org membership check first (403)
        # But if somehow bypassed, team check would give 404
        url = f"/test/orgs/{setup['org_b']['id']}/teams/{setup['team1']['id']}/data"

        response = client.get(url, headers=setup["user_b"]["headers"])

        # Team1 doesn't belong to OrgB, so it should be 404
        assert response.status_code == 404
        assert "team not found" in response.json()["detail"].lower()


# =============================================================================
# Test: Cross-Org Team Access
# =============================================================================


class TestCrossOrgTeamAccess:
    """Tests for attempting to access teams across organizations."""

    def test_user_b_cannot_access_org_a_team(self, mt_client):
        """UserB (OrgB) cannot access OrgA's teams -> 403 (org check fails first)."""
        client, setup = mt_client
        url = f"/test/orgs/{setup['org_a']['id']}/teams/{setup['team1']['id']}/data"

        response = client.get(url, headers=setup["user_b"]["headers"])

        # Fails at org membership check
        assert response.status_code == 403
        assert "not a member" in response.json()["detail"].lower()

    def test_user_a_cannot_access_org_b_with_fake_team(self, mt_client):
        """UserA cannot access OrgB even with fake team ID -> 403."""
        client, setup = mt_client
        fake_team_id = uuid4()
        url = f"/test/orgs/{setup['org_b']['id']}/teams/{fake_team_id}/data"

        response = client.get(url, headers=setup["user_a"]["headers"])

        # Fails at org membership check
        assert response.status_code == 403


# =============================================================================
# Test: Policy Consistency
# =============================================================================


class TestPolicyConsistency:
    """Verify consistent application of access control policies."""

    def test_403_for_not_member_of_org(self, mt_client):
        """Consistent 403 for 'not a member of organization'."""
        client, setup = mt_client

        # UserA trying to access OrgB
        url = f"/test/orgs/{setup['org_b']['id']}/resources"
        response = client.get(url, headers=setup["user_a"]["headers"])

        assert response.status_code == 403
        assert "not a member of this organization" in response.json()["detail"].lower()

    def test_404_for_org_not_found(self, mt_client):
        """Consistent 404 for 'organization not found'."""
        client, setup = mt_client
        fake_org_id = uuid4()

        url = f"/test/orgs/{fake_org_id}/resources"
        response = client.get(url, headers=setup["user_a"]["headers"])

        assert response.status_code == 404
        assert "organization not found" in response.json()["detail"].lower()

    def test_404_for_team_not_found(self, mt_client):
        """Consistent 404 for 'team not found'."""
        client, setup = mt_client
        fake_team_id = uuid4()

        url = f"/test/orgs/{setup['org_a']['id']}/teams/{fake_team_id}/data"
        response = client.get(url, headers=setup["user_a"]["headers"])

        assert response.status_code == 404
        assert "team not found" in response.json()["detail"].lower()

    def test_403_for_not_member_of_team(self, mt_client):
        """Consistent 403 for 'not a member of this team'."""
        client, setup = mt_client

        # user_team1 trying to access team2
        url = f"/test/orgs/{setup['org_a']['id']}/teams/{setup['team2']['id']}/data"
        response = client.get(url, headers=setup["user_team1"]["headers"])

        assert response.status_code == 403
        assert "not a member of this team" in response.json()["detail"].lower()


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestMultitenancyEdgeCases:
    """Edge cases and boundary conditions."""

    def test_unauthenticated_access_rejected(self, mt_client):
        """Unauthenticated request -> 401."""
        client, setup = mt_client
        url = f"/test/orgs/{setup['org_a']['id']}/resources"

        response = client.get(url)  # No auth headers

        assert response.status_code == 401

    def test_invalid_token_rejected(self, mt_client):
        """Invalid token -> 401."""
        client, setup = mt_client
        url = f"/test/orgs/{setup['org_a']['id']}/resources"

        response = client.get(
            url, headers={"Authorization": "Bearer invalid-token"}
        )

        assert response.status_code == 401

    def test_user_cannot_escalate_via_url_manipulation(self, mt_client):
        """User cannot access other org by changing URL org_id."""
        client, setup = mt_client

        # user_team1 is in OrgA, try to access OrgB
        url = f"/test/orgs/{setup['org_b']['id']}/resources"
        response = client.get(url, headers=setup["user_team1"]["headers"])

        assert response.status_code == 403

    def test_multiple_users_same_org_isolated(self, mt_client):
        """Multiple users in same org see correct user context."""
        client, setup = mt_client
        url = f"/test/orgs/{setup['org_a']['id']}/resources"

        # user_team1 sees their own context
        response1 = client.get(url, headers=setup["user_team1"]["headers"])
        assert response1.status_code == 200
        assert response1.json()["user_id"] == str(setup["user_team1"]["id"])

        # user_team2 sees their own context
        response2 = client.get(url, headers=setup["user_team2"]["headers"])
        assert response2.status_code == 200
        assert response2.json()["user_id"] == str(setup["user_team2"]["id"])

        # user_a sees their own context
        response_a = client.get(url, headers=setup["user_a"]["headers"])
        assert response_a.status_code == 200
        assert response_a.json()["user_id"] == str(setup["user_a"]["id"])


# =============================================================================
# Test: Isolation Summary Matrix
# =============================================================================


class TestIsolationMatrix:
    """Parametrized tests for complete isolation matrix."""

    @pytest.mark.parametrize(
        "user_key,org_key,expected_status",
        [
            # Same org access
            ("user_a", "org_a", 200),
            ("user_team1", "org_a", 200),
            ("user_team2", "org_a", 200),
            ("user_b", "org_b", 200),
            # Cross-org access (should fail)
            ("user_a", "org_b", 403),
            ("user_team1", "org_b", 403),
            ("user_team2", "org_b", 403),
            ("user_b", "org_a", 403),
        ],
    )
    def test_org_access_matrix(self, mt_client, user_key, org_key, expected_status):
        """Parametrized test for org access matrix."""
        client, setup = mt_client
        url = f"/test/orgs/{setup[org_key]['id']}/resources"

        response = client.get(url, headers=setup[user_key]["headers"])

        assert response.status_code == expected_status, (
            f"{user_key} accessing {org_key} expected {expected_status}, "
            f"got {response.status_code}"
        )

    @pytest.mark.parametrize(
        "user_key,team_key,expected_status",
        [
            # Admin can access all teams
            ("user_a", "team1", 200),
            ("user_a", "team2", 200),
            # Team members can only access their team
            ("user_team1", "team1", 200),
            ("user_team1", "team2", 403),
            ("user_team2", "team1", 403),
            ("user_team2", "team2", 200),
        ],
    )
    def test_team_access_matrix(self, mt_client, user_key, team_key, expected_status):
        """Parametrized test for team access matrix within OrgA."""
        client, setup = mt_client
        url = f"/test/orgs/{setup['org_a']['id']}/teams/{setup[team_key]['id']}/data"

        response = client.get(url, headers=setup[user_key]["headers"])

        assert response.status_code == expected_status, (
            f"{user_key} accessing {team_key} expected {expected_status}, "
            f"got {response.status_code}"
        )
