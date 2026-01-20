"""
Integration tests for API key authentication.

Tests cover:
1. Create API key (admin only) -> returns plaintext key once
2. Use X-API-Key to call a protected endpoint -> 200
3. Revoke key -> subsequent use returns 401
4. API key from OrgA cannot access OrgB resources -> 403/404 per policy
"""

from typing import Annotated
from uuid import UUID, uuid4

import pytest
from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import AuthContext, get_auth_context
from apps.api.auth.models import Membership, Organization, User, UserRole
from apps.api.auth.security import hash_password
from apps.api.auth.service import create_tokens

# =============================================================================
# Test Router for API Key Authentication
# =============================================================================

api_key_test_router = APIRouter(prefix="/api-key-test", tags=["API Key Test"])


@api_key_test_router.get("/protected")
def protected_endpoint(auth: AuthContext = Depends(get_auth_context)):
    """Test endpoint that accepts both JWT and API key auth."""
    return {
        "authenticated": True,
        "is_api_key": auth.is_api_key,
        "is_user": auth.is_user,
        "org_id": str(auth.org_id) if auth.org_id else None,
        "role": auth.role.value if auth.role else None,
    }


@api_key_test_router.get("/orgs/{org_id}/data")
def get_org_data(
    org_id: Annotated[UUID, Path(description="Organization ID")],
    auth: AuthContext = Depends(get_auth_context),
):
    """Test endpoint that requires org access via API key."""
    # For API key auth, verify the key belongs to this org
    if auth.is_api_key:
        if auth.org_id != org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key does not have access to this organization",
            )
        return {
            "org_id": str(org_id),
            "data": "org-specific-data",
            "role": auth.role.value if auth.role else None,
        }

    # For JWT auth, would need to check membership (simplified for test)
    return {
        "org_id": str(org_id),
        "data": "org-specific-data",
        "user_id": str(auth.user.id) if auth.user else None,
    }


# =============================================================================
# Test Data
# =============================================================================

TEST_PASSWORD = "SecureTestPass123"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def api_key_setup(test_session_factory, app):
    """
    Set up two organizations with admin users for API key testing.

    Structure:
        OrgA:
            - admin_a (admin)
            - researcher_a (researcher)
        OrgB:
            - admin_b (admin)

    Returns dict with all entities and tokens.
    """
    # Add test router to app
    if api_key_test_router not in app.routes:
        app.include_router(api_key_test_router)

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

        # Create admin_a
        admin_a = User(
            id=uuid4(),
            email=f"admin-a-{uuid4().hex[:8]}@orga.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="Admin A",
            is_active=True,
        )
        db.add(admin_a)
        db.flush()

        membership_admin_a = Membership(
            user_id=admin_a.id,
            organization_id=org_a.id,
            role=UserRole.ADMIN,
        )
        db.add(membership_admin_a)
        db.flush()

        # Create researcher_a (non-admin)
        researcher_a = User(
            id=uuid4(),
            email=f"researcher-a-{uuid4().hex[:8]}@orga.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="Researcher A",
            is_active=True,
        )
        db.add(researcher_a)
        db.flush()

        membership_researcher_a = Membership(
            user_id=researcher_a.id,
            organization_id=org_a.id,
            role=UserRole.RESEARCHER,
        )
        db.add(membership_researcher_a)
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

        # Create admin_b
        admin_b = User(
            id=uuid4(),
            email=f"admin-b-{uuid4().hex[:8]}@orgb.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="Admin B",
            is_active=True,
        )
        db.add(admin_b)
        db.flush()

        membership_admin_b = Membership(
            user_id=admin_b.id,
            organization_id=org_b.id,
            role=UserRole.ADMIN,
        )
        db.add(membership_admin_b)
        db.flush()

        db.commit()

        # =================================================================
        # Create tokens for each user
        # =================================================================
        token_admin_a, _ = create_tokens(db, admin_a)
        token_researcher_a, _ = create_tokens(db, researcher_a)
        token_admin_b, _ = create_tokens(db, admin_b)

        yield {
            "org_a": org_a,
            "org_a_id": org_a.id,
            "admin_a": admin_a,
            "researcher_a": researcher_a,
            "token_admin_a": token_admin_a,
            "token_researcher_a": token_researcher_a,
            "org_b": org_b,
            "org_b_id": org_b.id,
            "admin_b": admin_b,
            "token_admin_b": token_admin_b,
            "db": db,
        }

    finally:
        db.rollback()
        db.close()


@pytest.fixture
def api_client(app, api_key_setup) -> tuple[TestClient, dict]:
    """TestClient with API key setup."""
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        yield client, api_key_setup
    app.dependency_overrides.clear()


# =============================================================================
# Test: API Key Creation (Admin Only)
# =============================================================================


class TestApiKeyCreation:
    """Tests for API key creation."""

    def test_admin_can_create_api_key(self, api_client):
        """Admin can create an API key and receives plaintext key once."""
        client, setup = api_client

        response = client.post(
            f"/orgs/{setup['org_a_id']}/api-keys",
            json={"name": "Test API Key", "role": "viewer"},
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )

        assert response.status_code == 201
        data = response.json()

        # Verify response contains plaintext key
        assert "key" in data
        assert data["key"].startswith("sk_")  # API key prefix
        assert len(data["key"]) > 20  # Reasonable key length

        # Verify other fields
        assert data["name"] == "Test API Key"
        assert "key_prefix" in data
        assert data["role"] == "viewer"
        assert "warning" in data  # Warning about storing key securely

    def test_researcher_cannot_create_api_key(self, api_client):
        """Non-admin (researcher) cannot create API keys -> 403."""
        client, setup = api_client

        response = client.post(
            f"/orgs/{setup['org_a_id']}/api-keys",
            json={"name": "Unauthorized Key"},
            headers={"Authorization": f"Bearer {setup['token_researcher_a']}"},
        )

        assert response.status_code == 403
        assert "admin" in response.json()["detail"].lower()

    def test_create_api_key_with_scopes(self, api_client):
        """Admin can create API key with specific scopes."""
        client, setup = api_client

        response = client.post(
            f"/orgs/{setup['org_a_id']}/api-keys",
            json={
                "name": "Scoped API Key",
                "role": "researcher",
                "scopes": ["read:molecules", "write:predictions"],
            },
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["scopes"] == ["read:molecules", "write:predictions"]
        assert data["role"] == "researcher"

    def test_create_api_key_with_expiration(self, api_client):
        """Admin can create API key with expiration."""
        client, setup = api_client

        response = client.post(
            f"/orgs/{setup['org_a_id']}/api-keys",
            json={
                "name": "Expiring Key",
                "expires_in_days": 30,
            },
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["expires_at"] is not None


# =============================================================================
# Test: API Key Authentication
# =============================================================================


class TestApiKeyAuthentication:
    """Tests for using API keys to authenticate."""

    def test_api_key_authenticates_protected_endpoint(self, api_client):
        """Valid API key can access protected endpoint -> 200."""
        client, setup = api_client

        # First create an API key
        create_response = client.post(
            f"/orgs/{setup['org_a_id']}/api-keys",
            json={"name": "Auth Test Key", "role": "viewer"},
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )
        assert create_response.status_code == 201
        api_key = create_response.json()["key"]

        # Use API key to access protected endpoint
        response = client.get(
            "/api-key-test/protected",
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["is_api_key"] is True
        assert data["is_user"] is False
        assert data["org_id"] == str(setup["org_a_id"])
        assert data["role"] == "viewer"

    def test_api_key_accesses_org_specific_endpoint(self, api_client):
        """API key can access its own org's data."""
        client, setup = api_client

        # Create API key for OrgA
        create_response = client.post(
            f"/orgs/{setup['org_a_id']}/api-keys",
            json={"name": "Org Access Key", "role": "researcher"},
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )
        api_key = create_response.json()["key"]

        # Access OrgA data with API key
        response = client.get(
            f"/api-key-test/orgs/{setup['org_a_id']}/data",
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == str(setup["org_a_id"])
        assert data["role"] == "researcher"

    def test_invalid_api_key_returns_401(self, api_client):
        """Invalid API key returns 401."""
        client, setup = api_client

        response = client.get(
            "/api-key-test/protected",
            headers={"X-API-Key": "sk_invalid_key_12345"},
        )

        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()

    def test_api_key_with_different_roles(self, api_client):
        """API keys with different roles have correct role context."""
        client, setup = api_client

        # Create keys with different roles
        roles = ["viewer", "researcher", "admin"]

        for role in roles:
            create_response = client.post(
                f"/orgs/{setup['org_a_id']}/api-keys",
                json={"name": f"{role.title()} Key", "role": role},
                headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
            )
            api_key = create_response.json()["key"]

            # Verify role in auth context
            response = client.get(
                "/api-key-test/protected",
                headers={"X-API-Key": api_key},
            )
            assert response.status_code == 200
            assert response.json()["role"] == role


# =============================================================================
# Test: API Key Revocation
# =============================================================================


class TestApiKeyRevocation:
    """Tests for API key revocation."""

    def test_revoked_key_returns_401(self, api_client):
        """After revocation, API key returns 401."""
        client, setup = api_client

        # Create API key
        create_response = client.post(
            f"/orgs/{setup['org_a_id']}/api-keys",
            json={"name": "To Be Revoked"},
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )
        assert create_response.status_code == 201
        api_key = create_response.json()["key"]
        key_id = create_response.json()["id"]

        # Verify key works before revocation
        before_response = client.get(
            "/api-key-test/protected",
            headers={"X-API-Key": api_key},
        )
        assert before_response.status_code == 200

        # Revoke the key
        revoke_response = client.delete(
            f"/orgs/{setup['org_a_id']}/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )
        assert revoke_response.status_code == 204

        # Verify key no longer works
        after_response = client.get(
            "/api-key-test/protected",
            headers={"X-API-Key": api_key},
        )
        assert after_response.status_code == 401
        assert "invalid" in after_response.json()["detail"].lower()

    def test_admin_can_revoke_api_key(self, api_client):
        """Admin can revoke API keys."""
        client, setup = api_client

        # Create key
        create_response = client.post(
            f"/orgs/{setup['org_a_id']}/api-keys",
            json={"name": "Admin Revoke Test"},
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )
        key_id = create_response.json()["id"]

        # Revoke key
        response = client.delete(
            f"/orgs/{setup['org_a_id']}/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )

        assert response.status_code == 204

    def test_researcher_cannot_revoke_api_key(self, api_client):
        """Non-admin cannot revoke API keys -> 403."""
        client, setup = api_client

        # Create key as admin
        create_response = client.post(
            f"/orgs/{setup['org_a_id']}/api-keys",
            json={"name": "Researcher Revoke Test"},
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )
        key_id = create_response.json()["id"]

        # Try to revoke as researcher
        response = client.delete(
            f"/orgs/{setup['org_a_id']}/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {setup['token_researcher_a']}"},
        )

        assert response.status_code == 403

    def test_revoke_nonexistent_key_returns_404(self, api_client):
        """Revoking non-existent key returns 404."""
        client, setup = api_client

        fake_key_id = uuid4()
        response = client.delete(
            f"/orgs/{setup['org_a_id']}/api-keys/{fake_key_id}",
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )

        assert response.status_code == 404


# =============================================================================
# Test: Cross-Organization Isolation
# =============================================================================


class TestCrossOrgIsolation:
    """Tests for API key cross-organization isolation."""

    def test_api_key_cannot_access_other_org_resources(self, api_client):
        """API key from OrgA cannot access OrgB resources -> 403."""
        client, setup = api_client

        # Create API key for OrgA
        create_response = client.post(
            f"/orgs/{setup['org_a_id']}/api-keys",
            json={"name": "OrgA Key"},
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )
        api_key_a = create_response.json()["key"]

        # Try to access OrgB data with OrgA's key
        response = client.get(
            f"/api-key-test/orgs/{setup['org_b_id']}/data",
            headers={"X-API-Key": api_key_a},
        )

        assert response.status_code == 403
        assert "access" in response.json()["detail"].lower()

    def test_cannot_create_api_key_for_other_org(self, api_client):
        """Admin cannot create API key for another org -> 403."""
        client, setup = api_client

        # Admin A tries to create key for OrgB
        response = client.post(
            f"/orgs/{setup['org_b_id']}/api-keys",
            json={"name": "Cross Org Key"},
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )

        assert response.status_code == 403

    def test_cannot_revoke_other_org_api_key(self, api_client):
        """Admin cannot revoke API key from another org."""
        client, setup = api_client

        # Create key in OrgB
        create_response = client.post(
            f"/orgs/{setup['org_b_id']}/api-keys",
            json={"name": "OrgB Key"},
            headers={"Authorization": f"Bearer {setup['token_admin_b']}"},
        )
        key_id_b = create_response.json()["id"]

        # Admin A tries to revoke OrgB's key
        response = client.delete(
            f"/orgs/{setup['org_b_id']}/api-keys/{key_id_b}",
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )

        # Should fail - either 403 (not member) or 404 (not found in their org)
        assert response.status_code in [403, 404]

    def test_cannot_list_other_org_api_keys(self, api_client):
        """Admin cannot list API keys from another org -> 403."""
        client, setup = api_client

        # Admin A tries to list OrgB's keys
        response = client.get(
            f"/orgs/{setup['org_b_id']}/api-keys",
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )

        assert response.status_code == 403


# =============================================================================
# Test: API Key Listing
# =============================================================================


class TestApiKeyListing:
    """Tests for API key listing."""

    def test_admin_can_list_org_api_keys(self, api_client):
        """Admin can list all API keys for their org."""
        client, setup = api_client

        # Create some keys
        for i in range(3):
            client.post(
                f"/orgs/{setup['org_a_id']}/api-keys",
                json={"name": f"List Test Key {i}"},
                headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
            )

        # List keys
        response = client.get(
            f"/orgs/{setup['org_a_id']}/api-keys",
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )

        assert response.status_code == 200
        keys = response.json()
        assert isinstance(keys, list)
        assert len(keys) >= 3

        # Verify plaintext key is NOT included in list
        for key in keys:
            assert "key" not in key or key.get("key") is None
            assert "key_prefix" in key  # Only prefix is shown

    def test_researcher_cannot_list_api_keys(self, api_client):
        """Non-admin cannot list API keys -> 403."""
        client, setup = api_client

        response = client.get(
            f"/orgs/{setup['org_a_id']}/api-keys",
            headers={"Authorization": f"Bearer {setup['token_researcher_a']}"},
        )

        assert response.status_code == 403


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestApiKeyEdgeCases:
    """Edge case tests for API keys."""

    def test_api_key_priority_over_jwt(self, api_client):
        """When both X-API-Key and JWT provided, API key takes priority."""
        client, setup = api_client

        # Create API key
        create_response = client.post(
            f"/orgs/{setup['org_a_id']}/api-keys",
            json={"name": "Priority Test Key"},
            headers={"Authorization": f"Bearer {setup['token_admin_a']}"},
        )
        api_key = create_response.json()["key"]

        # Call with both headers
        response = client.get(
            "/api-key-test/protected",
            headers={
                "X-API-Key": api_key,
                "Authorization": f"Bearer {setup['token_admin_a']}",
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Should use API key auth, not JWT
        assert data["is_api_key"] is True
        assert data["is_user"] is False

    def test_no_auth_returns_401(self, api_client):
        """No authentication provided returns 401."""
        client, setup = api_client

        response = client.get("/api-key-test/protected")

        assert response.status_code == 401
        assert "not authenticated" in response.json()["detail"].lower()

    def test_empty_api_key_header_falls_back_to_jwt(self, api_client):
        """Empty X-API-Key header falls back to JWT auth."""
        client, setup = api_client

        response = client.get(
            "/api-key-test/protected",
            headers={
                "X-API-Key": "",
                "Authorization": f"Bearer {setup['token_admin_a']}",
            },
        )

        # Should use JWT since API key is empty
        assert response.status_code == 200
        data = response.json()
        assert data["is_api_key"] is False
        assert data["is_user"] is True
