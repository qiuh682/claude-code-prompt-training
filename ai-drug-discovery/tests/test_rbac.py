"""
Integration tests for Role-Based Access Control (RBAC).

Tests verify that:
- Viewer can GET resources but cannot POST/PUT/DELETE (403)
- Researcher can POST/PUT but cannot perform admin-only actions (403)
- Admin can perform all actions including admin-only (200/204)

Setup: Creates three users in the same org with roles: admin, researcher, viewer.
Uses the /orgs/{org_id}/projects endpoints which have proper RBAC decorators.
"""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.auth.models import Membership, Organization, User, UserRole
from apps.api.auth.security import hash_password
from apps.api.auth.service import create_tokens

# =============================================================================
# Test Data
# =============================================================================

TEST_PASSWORD = "SecureTestPass123"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def rbac_setup(test_session_factory) -> dict:
    """
    Set up organization with three users: admin, researcher, viewer.

    Returns dict with:
        - org_id: UUID of the test organization
        - admin: dict with user, token
        - researcher: dict with user, token
        - viewer: dict with user, token
        - db: database session (for cleanup)
    """
    db: Session = test_session_factory()

    try:
        # Create organization
        org = Organization(
            id=uuid4(),
            name="Test RBAC Organization",
            slug=f"test-rbac-{uuid4().hex[:8]}",
        )
        db.add(org)
        db.flush()

        # Create users with different roles
        users_data = {
            "admin": {"email": f"admin-{uuid4().hex[:8]}@test.com", "role": UserRole.ADMIN},
            "researcher": {"email": f"researcher-{uuid4().hex[:8]}@test.com", "role": UserRole.RESEARCHER},
            "viewer": {"email": f"viewer-{uuid4().hex[:8]}@test.com", "role": UserRole.VIEWER},
        }

        result = {"org_id": org.id, "db": db}

        for role_name, data in users_data.items():
            # Create user
            user = User(
                id=uuid4(),
                email=data["email"],
                password_hash=hash_password(TEST_PASSWORD),
                full_name=f"Test {role_name.title()}",
                is_active=True,
            )
            db.add(user)
            db.flush()

            # Create membership with role
            membership = Membership(
                user_id=user.id,
                organization_id=org.id,
                role=data["role"],
            )
            db.add(membership)
            db.flush()

            # Create access token for the user
            access_token, _ = create_tokens(db, user)

            result[role_name] = {
                "user": user,
                "user_id": user.id,
                "email": data["email"],
                "role": data["role"],
                "token": access_token,
                "headers": {"Authorization": f"Bearer {access_token}"},
            }

        db.commit()
        yield result

    finally:
        # Cleanup
        db.rollback()
        db.close()


@pytest.fixture
def rbac_client(app, rbac_setup) -> tuple[TestClient, dict]:
    """
    TestClient with RBAC setup data.

    Returns tuple of (client, rbac_setup_data).
    """
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        yield client, rbac_setup
    app.dependency_overrides.clear()


# =============================================================================
# Helper Functions
# =============================================================================


def get_projects_url(org_id: UUID) -> str:
    """Get projects list URL for an org."""
    return f"/orgs/{org_id}/projects"


def get_project_url(org_id: UUID, project_id: str = "proj-123") -> str:
    """Get single project URL."""
    return f"/orgs/{org_id}/projects/{project_id}"


# =============================================================================
# Test: Viewer Permissions
# =============================================================================


class TestViewerPermissions:
    """Tests for viewer role - read-only access."""

    def test_viewer_can_list_projects(self, rbac_client):
        """Viewer can GET /projects -> 200."""
        client, setup = rbac_client
        url = get_projects_url(setup["org_id"])

        response = client.get(url, headers=setup["viewer"]["headers"])

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_viewer_can_get_project(self, rbac_client):
        """Viewer can GET /projects/{id} -> 200."""
        client, setup = rbac_client
        url = get_project_url(setup["org_id"])

        response = client.get(url, headers=setup["viewer"]["headers"])

        assert response.status_code == 200
        assert "id" in response.json()

    def test_viewer_cannot_create_project(self, rbac_client):
        """Viewer cannot POST /projects -> 403."""
        client, setup = rbac_client
        url = get_projects_url(setup["org_id"])

        response = client.post(
            url,
            json={"name": "New Project", "description": "Test"},
            headers=setup["viewer"]["headers"],
        )

        assert response.status_code == 403
        assert "role" in response.json()["detail"].lower()

    def test_viewer_cannot_update_project(self, rbac_client):
        """Viewer cannot PATCH /projects/{id} -> 403."""
        client, setup = rbac_client
        url = get_project_url(setup["org_id"])

        response = client.patch(
            url,
            json={"name": "Updated Name"},
            headers=setup["viewer"]["headers"],
        )

        assert response.status_code == 403

    def test_viewer_cannot_delete_project(self, rbac_client):
        """Viewer cannot DELETE /projects/{id} -> 403."""
        client, setup = rbac_client
        url = get_project_url(setup["org_id"])

        response = client.delete(url, headers=setup["viewer"]["headers"])

        assert response.status_code == 403

    def test_viewer_cannot_archive_project(self, rbac_client):
        """Viewer cannot POST /projects/{id}/archive -> 403."""
        client, setup = rbac_client
        url = f"{get_project_url(setup['org_id'])}/archive"

        response = client.post(url, headers=setup["viewer"]["headers"])

        assert response.status_code == 403


# =============================================================================
# Test: Researcher Permissions
# =============================================================================


class TestResearcherPermissions:
    """Tests for researcher role - read + create/update access."""

    def test_researcher_can_list_projects(self, rbac_client):
        """Researcher can GET /projects -> 200."""
        client, setup = rbac_client
        url = get_projects_url(setup["org_id"])

        response = client.get(url, headers=setup["researcher"]["headers"])

        assert response.status_code == 200

    def test_researcher_can_get_project(self, rbac_client):
        """Researcher can GET /projects/{id} -> 200."""
        client, setup = rbac_client
        url = get_project_url(setup["org_id"])

        response = client.get(url, headers=setup["researcher"]["headers"])

        assert response.status_code == 200

    def test_researcher_can_create_project(self, rbac_client):
        """Researcher can POST /projects -> 201."""
        client, setup = rbac_client
        url = get_projects_url(setup["org_id"])

        response = client.post(
            url,
            json={"name": "Research Project", "description": "ML analysis"},
            headers=setup["researcher"]["headers"],
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Research Project"

    def test_researcher_can_update_project(self, rbac_client):
        """Researcher can PATCH /projects/{id} -> 200."""
        client, setup = rbac_client
        url = get_project_url(setup["org_id"])

        response = client.patch(
            url,
            json={"name": "Updated by Researcher"},
            headers=setup["researcher"]["headers"],
        )

        assert response.status_code == 200

    def test_researcher_can_archive_project(self, rbac_client):
        """Researcher can POST /projects/{id}/archive -> 200."""
        client, setup = rbac_client
        url = f"{get_project_url(setup['org_id'])}/archive"

        response = client.post(url, headers=setup["researcher"]["headers"])

        assert response.status_code == 200
        assert response.json()["status"] == "archived"

    def test_researcher_cannot_delete_project(self, rbac_client):
        """Researcher cannot DELETE /projects/{id} -> 403 (admin only)."""
        client, setup = rbac_client
        url = get_project_url(setup["org_id"])

        response = client.delete(url, headers=setup["researcher"]["headers"])

        assert response.status_code == 403
        assert "role" in response.json()["detail"].lower()


# =============================================================================
# Test: Admin Permissions
# =============================================================================


class TestAdminPermissions:
    """Tests for admin role - full access."""

    def test_admin_can_list_projects(self, rbac_client):
        """Admin can GET /projects -> 200."""
        client, setup = rbac_client
        url = get_projects_url(setup["org_id"])

        response = client.get(url, headers=setup["admin"]["headers"])

        assert response.status_code == 200

    def test_admin_can_get_project(self, rbac_client):
        """Admin can GET /projects/{id} -> 200."""
        client, setup = rbac_client
        url = get_project_url(setup["org_id"])

        response = client.get(url, headers=setup["admin"]["headers"])

        assert response.status_code == 200

    def test_admin_can_create_project(self, rbac_client):
        """Admin can POST /projects -> 201."""
        client, setup = rbac_client
        url = get_projects_url(setup["org_id"])

        response = client.post(
            url,
            json={"name": "Admin Project", "description": "Created by admin"},
            headers=setup["admin"]["headers"],
        )

        assert response.status_code == 201

    def test_admin_can_update_project(self, rbac_client):
        """Admin can PATCH /projects/{id} -> 200."""
        client, setup = rbac_client
        url = get_project_url(setup["org_id"])

        response = client.patch(
            url,
            json={"name": "Updated by Admin"},
            headers=setup["admin"]["headers"],
        )

        assert response.status_code == 200

    def test_admin_can_delete_project(self, rbac_client):
        """Admin can DELETE /projects/{id} -> 204."""
        client, setup = rbac_client
        url = get_project_url(setup["org_id"])

        response = client.delete(url, headers=setup["admin"]["headers"])

        assert response.status_code == 204

    def test_admin_can_archive_project(self, rbac_client):
        """Admin can POST /projects/{id}/archive -> 200."""
        client, setup = rbac_client
        url = f"{get_project_url(setup['org_id'])}/archive"

        response = client.post(url, headers=setup["admin"]["headers"])

        assert response.status_code == 200

    def test_admin_sees_sensitive_audit_log(self, rbac_client):
        """Admin sees sensitive_events in audit log."""
        client, setup = rbac_client
        url = f"{get_project_url(setup['org_id'])}/audit-log"

        response = client.get(url, headers=setup["admin"]["headers"])

        assert response.status_code == 200
        data = response.json()
        assert "sensitive_events" in data  # Admin sees sensitive data


# =============================================================================
# Test: Cross-Role Comparison
# =============================================================================


class TestCrossRoleComparison:
    """Tests comparing behavior across roles."""

    def test_audit_log_visibility_differs_by_role(self, rbac_client):
        """Viewer/researcher don't see sensitive_events, admin does."""
        client, setup = rbac_client
        url = f"{get_project_url(setup['org_id'])}/audit-log"

        # Viewer response
        viewer_response = client.get(url, headers=setup["viewer"]["headers"])
        assert viewer_response.status_code == 200
        assert "sensitive_events" not in viewer_response.json()

        # Researcher response
        researcher_response = client.get(url, headers=setup["researcher"]["headers"])
        assert researcher_response.status_code == 200
        assert "sensitive_events" not in researcher_response.json()

        # Admin response
        admin_response = client.get(url, headers=setup["admin"]["headers"])
        assert admin_response.status_code == 200
        assert "sensitive_events" in admin_response.json()

    def test_all_roles_can_read(self, rbac_client):
        """All roles (admin, researcher, viewer) can read projects."""
        client, setup = rbac_client
        url = get_projects_url(setup["org_id"])

        for role in ["admin", "researcher", "viewer"]:
            response = client.get(url, headers=setup[role]["headers"])
            assert response.status_code == 200, f"{role} should be able to read"

    def test_only_admin_researcher_can_write(self, rbac_client):
        """Only admin and researcher can create projects."""
        client, setup = rbac_client
        url = get_projects_url(setup["org_id"])
        payload = {"name": "Test Project", "description": "Test"}

        # Admin can create
        admin_response = client.post(url, json=payload, headers=setup["admin"]["headers"])
        assert admin_response.status_code == 201

        # Researcher can create
        researcher_response = client.post(url, json=payload, headers=setup["researcher"]["headers"])
        assert researcher_response.status_code == 201

        # Viewer cannot create
        viewer_response = client.post(url, json=payload, headers=setup["viewer"]["headers"])
        assert viewer_response.status_code == 403

    def test_only_admin_can_delete(self, rbac_client):
        """Only admin can delete projects."""
        client, setup = rbac_client
        url = get_project_url(setup["org_id"])

        # Viewer cannot delete
        viewer_response = client.delete(url, headers=setup["viewer"]["headers"])
        assert viewer_response.status_code == 403

        # Researcher cannot delete
        researcher_response = client.delete(url, headers=setup["researcher"]["headers"])
        assert researcher_response.status_code == 403

        # Admin can delete
        admin_response = client.delete(url, headers=setup["admin"]["headers"])
        assert admin_response.status_code == 204


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestRBACEdgeCases:
    """Edge cases and error conditions."""

    def test_unauthenticated_request_rejected(self, rbac_client):
        """Request without token -> 401."""
        client, setup = rbac_client
        url = get_projects_url(setup["org_id"])

        response = client.get(url)  # No headers

        assert response.status_code == 401

    def test_wrong_org_access_denied(self, rbac_client):
        """User cannot access different org's resources -> 403/404."""
        client, setup = rbac_client
        wrong_org_id = uuid4()  # Random org ID
        url = get_projects_url(wrong_org_id)

        response = client.get(url, headers=setup["admin"]["headers"])

        # Should be 403 (not a member) or 404 (org not found)
        assert response.status_code in (403, 404)

    def test_invalid_token_rejected(self, rbac_client):
        """Invalid token -> 401."""
        client, setup = rbac_client
        url = get_projects_url(setup["org_id"])

        response = client.get(
            url,
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401


# =============================================================================
# Test: Permission Matrix Summary
# =============================================================================


class TestPermissionMatrix:
    """
    Comprehensive permission matrix test.

    Verifies the complete access control matrix in one place.
    """

    @pytest.mark.parametrize(
        "role,method,endpoint_suffix,expected_status",
        [
            # Viewer: read-only
            ("viewer", "GET", "", 200),
            ("viewer", "GET", "/proj-123", 200),
            ("viewer", "POST", "", 403),
            ("viewer", "PATCH", "/proj-123", 403),
            ("viewer", "DELETE", "/proj-123", 403),
            # Researcher: read + write (no delete)
            ("researcher", "GET", "", 200),
            ("researcher", "GET", "/proj-123", 200),
            ("researcher", "POST", "", 201),
            ("researcher", "PATCH", "/proj-123", 200),
            ("researcher", "DELETE", "/proj-123", 403),
            # Admin: full access
            ("admin", "GET", "", 200),
            ("admin", "GET", "/proj-123", 200),
            ("admin", "POST", "", 201),
            ("admin", "PATCH", "/proj-123", 200),
            ("admin", "DELETE", "/proj-123", 204),
        ],
    )
    def test_permission_matrix(
        self, rbac_client, role, method, endpoint_suffix, expected_status
    ):
        """Parametrized test for complete permission matrix."""
        client, setup = rbac_client
        url = f"/orgs/{setup['org_id']}/projects{endpoint_suffix}"
        headers = setup[role]["headers"]

        # Build request based on method
        if method == "GET":
            response = client.get(url, headers=headers)
        elif method == "POST":
            response = client.post(
                url,
                json={"name": "Matrix Test", "description": "Test"},
                headers=headers,
            )
        elif method == "PATCH":
            response = client.patch(
                url,
                json={"name": "Updated"},
                headers=headers,
            )
        elif method == "DELETE":
            response = client.delete(url, headers=headers)
        else:
            pytest.fail(f"Unknown method: {method}")

        assert response.status_code == expected_status, (
            f"{role} {method} {endpoint_suffix} expected {expected_status}, "
            f"got {response.status_code}: {response.text}"
        )
