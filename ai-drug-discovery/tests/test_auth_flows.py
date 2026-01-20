"""
Integration tests for authentication flows.

Tests cover:
1. Register -> 201, user created
2. Login -> returns access_token + refresh_token
3. Access protected endpoint /auth/me with access token -> 200
4. Refresh -> returns new tokens, old refresh becomes invalid (rotation)
5. Logout -> refresh token revoked, further refresh fails
6. Wrong password -> 401
7. Expired access token -> 401

Uses TestClient (sync) with test database isolation.
"""

from datetime import datetime, timedelta

import jwt
from fastapi.testclient import TestClient

# =============================================================================
# Test Data
# =============================================================================

TEST_USER = {
    "email": "testuser@example.com",
    "password": "SecurePass123",
    "full_name": "Test User",
}

TEST_USER_2 = {
    "email": "testuser2@example.com",
    "password": "AnotherPass456",
    "full_name": "Test User Two",
}


# =============================================================================
# Helper Functions
# =============================================================================


def register_user(client: TestClient, user_data: dict | None = None) -> dict:
    """Register a user and return the response JSON."""
    data = user_data or TEST_USER
    response = client.post("/auth/register", json=data)
    return response


def login_user(client: TestClient, email: str, password: str) -> dict:
    """Login and return the response."""
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    return response


def get_auth_header(access_token: str) -> dict:
    """Create Authorization header."""
    return {"Authorization": f"Bearer {access_token}"}


# =============================================================================
# Test: Registration
# =============================================================================


class TestRegistration:
    """Tests for user registration."""

    def test_register_success(self, client_clean_db: TestClient):
        """Register new user -> 201, returns user data."""
        response = register_user(client_clean_db)

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == TEST_USER["email"]
        assert data["full_name"] == TEST_USER["full_name"]
        assert "id" in data
        assert "password" not in data  # Password should not be returned
        assert "password_hash" not in data

    def test_register_duplicate_email(self, client_clean_db: TestClient):
        """Register with existing email -> 409 Conflict."""
        # First registration
        response1 = register_user(client_clean_db)
        assert response1.status_code == 201

        # Duplicate registration
        response2 = register_user(client_clean_db)
        assert response2.status_code == 409
        assert "already registered" in response2.json()["detail"].lower()

    def test_register_weak_password(self, client_clean_db: TestClient):
        """Register with weak password -> 422 Validation Error."""
        weak_passwords = [
            "short",  # Too short
            "alllowercase123",  # No uppercase
            "ALLUPPERCASE123",  # No lowercase
            "NoDigitsHere",  # No digits
        ]

        for password in weak_passwords:
            response = client_clean_db.post(
                "/auth/register",
                json={
                    "email": f"test_{password}@example.com",
                    "password": password,
                    "full_name": "Test",
                },
            )
            assert response.status_code == 422, f"Password '{password}' should fail"

    def test_register_invalid_email(self, client_clean_db: TestClient):
        """Register with invalid email -> 422 Validation Error."""
        response = client_clean_db.post(
            "/auth/register",
            json={
                "email": "not-an-email",
                "password": "SecurePass123",
                "full_name": "Test User",
            },
        )
        assert response.status_code == 422


# =============================================================================
# Test: Login
# =============================================================================


class TestLogin:
    """Tests for user login."""

    def test_login_success(self, client_clean_db: TestClient):
        """Login with valid credentials -> 200, returns tokens."""
        # Register first
        register_user(client_clean_db)

        # Login
        response = login_user(
            client_clean_db, TEST_USER["email"], TEST_USER["password"]
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
        assert data["expires_in"] > 0

        # User info should be included
        assert "user" in data
        assert data["user"]["email"] == TEST_USER["email"]

    def test_login_wrong_password(self, client_clean_db: TestClient):
        """Login with wrong password -> 401 Unauthorized."""
        # Register first
        register_user(client_clean_db)

        # Login with wrong password
        response = login_user(client_clean_db, TEST_USER["email"], "WrongPassword123")

        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()

    def test_login_nonexistent_user(self, client_clean_db: TestClient):
        """Login with non-existent user -> 401 Unauthorized."""
        response = login_user(
            client_clean_db, "nonexistent@example.com", "SomePassword123"
        )

        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()

    def test_login_returns_different_tokens_each_time(
        self, client_clean_db: TestClient
    ):
        """Each login should return different tokens."""
        register_user(client_clean_db)

        response1 = login_user(
            client_clean_db, TEST_USER["email"], TEST_USER["password"]
        )
        response2 = login_user(
            client_clean_db, TEST_USER["email"], TEST_USER["password"]
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Tokens should be different
        assert (
            response1.json()["access_token"] != response2.json()["access_token"]
        )
        assert (
            response1.json()["refresh_token"] != response2.json()["refresh_token"]
        )


# =============================================================================
# Test: Protected Endpoint Access
# =============================================================================


class TestProtectedEndpoint:
    """Tests for accessing protected endpoints with access token."""

    def test_access_me_with_valid_token(self, client_clean_db: TestClient):
        """Access /auth/me with valid token -> 200."""
        # Register and login
        register_user(client_clean_db)
        login_response = login_user(
            client_clean_db, TEST_USER["email"], TEST_USER["password"]
        )
        access_token = login_response.json()["access_token"]

        # Access protected endpoint
        response = client_clean_db.get(
            "/auth/me", headers=get_auth_header(access_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == TEST_USER["email"]
        assert data["full_name"] == TEST_USER["full_name"]

    def test_access_me_without_token(self, client_clean_db: TestClient):
        """Access /auth/me without token -> 401."""
        response = client_clean_db.get("/auth/me")

        assert response.status_code == 401

    def test_access_me_with_invalid_token(self, client_clean_db: TestClient):
        """Access /auth/me with invalid token -> 401."""
        response = client_clean_db.get(
            "/auth/me", headers=get_auth_header("invalid.token.here")
        )

        assert response.status_code == 401

    def test_access_me_with_malformed_header(self, client_clean_db: TestClient):
        """Access /auth/me with malformed Authorization header -> 401."""
        # Missing "Bearer" prefix
        response = client_clean_db.get(
            "/auth/me", headers={"Authorization": "some-token"}
        )

        assert response.status_code in (401, 403)


# =============================================================================
# Test: Token Refresh with Rotation
# =============================================================================


class TestTokenRefresh:
    """Tests for token refresh with rotation."""

    def test_refresh_success(self, client_clean_db: TestClient):
        """Refresh token -> 200, returns new access + refresh tokens."""
        # Register and login
        register_user(client_clean_db)
        login_response = login_user(
            client_clean_db, TEST_USER["email"], TEST_USER["password"]
        )
        original_refresh_token = login_response.json()["refresh_token"]
        original_access_token = login_response.json()["access_token"]

        # Refresh
        response = client_clean_db.post(
            "/auth/refresh",
            json={"refresh_token": original_refresh_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

        # New tokens should be different from original
        assert data["access_token"] != original_access_token
        assert data["refresh_token"] != original_refresh_token

    def test_refresh_token_rotation_invalidates_old(
        self, client_clean_db: TestClient
    ):
        """After refresh, old refresh token should be invalid (rotation)."""
        # Register and login
        register_user(client_clean_db)
        login_response = login_user(
            client_clean_db, TEST_USER["email"], TEST_USER["password"]
        )
        original_refresh_token = login_response.json()["refresh_token"]

        # First refresh - should succeed
        response1 = client_clean_db.post(
            "/auth/refresh",
            json={"refresh_token": original_refresh_token},
        )
        assert response1.status_code == 200

        # Second refresh with same token - should fail (token was rotated)
        response2 = client_clean_db.post(
            "/auth/refresh",
            json={"refresh_token": original_refresh_token},
        )
        assert response2.status_code == 401
        assert "invalid" in response2.json()["detail"].lower()

    def test_refresh_with_invalid_token(self, client_clean_db: TestClient):
        """Refresh with invalid token -> 401."""
        response = client_clean_db.post(
            "/auth/refresh",
            json={"refresh_token": "invalid-refresh-token"},
        )

        assert response.status_code == 401

    def test_new_access_token_works(self, client_clean_db: TestClient):
        """New access token from refresh should work for protected endpoints."""
        # Register and login
        register_user(client_clean_db)
        login_response = login_user(
            client_clean_db, TEST_USER["email"], TEST_USER["password"]
        )
        refresh_token = login_response.json()["refresh_token"]

        # Refresh to get new access token
        refresh_response = client_clean_db.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        new_access_token = refresh_response.json()["access_token"]

        # Use new access token
        response = client_clean_db.get(
            "/auth/me", headers=get_auth_header(new_access_token)
        )

        assert response.status_code == 200
        assert response.json()["email"] == TEST_USER["email"]


# =============================================================================
# Test: Logout
# =============================================================================


class TestLogout:
    """Tests for logout functionality."""

    def test_logout_revokes_refresh_token(self, client_clean_db: TestClient):
        """Logout revokes refresh token, further refresh fails."""
        # Register and login
        register_user(client_clean_db)
        login_response = login_user(
            client_clean_db, TEST_USER["email"], TEST_USER["password"]
        )
        access_token = login_response.json()["access_token"]
        refresh_token = login_response.json()["refresh_token"]

        # Logout
        logout_response = client_clean_db.post(
            "/auth/logout",
            json={"refresh_token": refresh_token},
            headers=get_auth_header(access_token),
        )

        assert logout_response.status_code == 200
        assert "logged out" in logout_response.json()["message"].lower()

        # Try to refresh with revoked token
        refresh_response = client_clean_db.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert refresh_response.status_code == 401

    def test_logout_all_sessions(self, client_clean_db: TestClient):
        """Logout all sessions revokes all refresh tokens."""
        # Register and login twice (simulating two sessions)
        register_user(client_clean_db)
        login_response1 = login_user(
            client_clean_db, TEST_USER["email"], TEST_USER["password"]
        )
        login_response2 = login_user(
            client_clean_db, TEST_USER["email"], TEST_USER["password"]
        )

        access_token = login_response1.json()["access_token"]
        refresh_token1 = login_response1.json()["refresh_token"]
        refresh_token2 = login_response2.json()["refresh_token"]

        # Logout all sessions
        logout_response = client_clean_db.post(
            "/auth/logout",
            json={"refresh_token": refresh_token1, "all_sessions": True},
            headers=get_auth_header(access_token),
        )

        assert logout_response.status_code == 200
        assert "2" in logout_response.json()["message"]  # Should mention 2 sessions

        # Both refresh tokens should be invalid
        for token in [refresh_token1, refresh_token2]:
            refresh_response = client_clean_db.post(
                "/auth/refresh",
                json={"refresh_token": token},
            )
            assert refresh_response.status_code == 401

    def test_logout_requires_authentication(self, client_clean_db: TestClient):
        """Logout requires valid access token."""
        response = client_clean_db.post(
            "/auth/logout",
            json={"refresh_token": "some-token"},
        )

        assert response.status_code == 401


# =============================================================================
# Test: Expired Access Token
# =============================================================================


class TestExpiredToken:
    """Tests for expired access token handling."""

    def test_expired_access_token_rejected(self, client_clean_db: TestClient):
        """Expired access token -> 401 Unauthorized."""
        # Register user first
        register_user(client_clean_db)

        # Create an expired token manually
        from apps.api.auth.security import ALGORITHM, SECRET_KEY

        expired_payload = {
            "sub": "some-user-id",
            "role": "user",
            "exp": datetime.utcnow() - timedelta(hours=1),  # Expired 1 hour ago
            "iat": datetime.utcnow() - timedelta(hours=2),
            "jti": "test-token-id",
        }
        expired_token = jwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)

        # Try to access protected endpoint
        response = client_clean_db.get(
            "/auth/me", headers=get_auth_header(expired_token)
        )

        assert response.status_code == 401

    def test_token_with_wrong_secret_rejected(self, client_clean_db: TestClient):
        """Token signed with wrong secret -> 401."""
        from apps.api.auth.security import ALGORITHM

        payload = {
            "sub": "some-user-id",
            "role": "user",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
            "jti": "test-token-id",
        }
        bad_token = jwt.encode(payload, "wrong-secret-key", algorithm=ALGORITHM)

        response = client_clean_db.get(
            "/auth/me", headers=get_auth_header(bad_token)
        )

        assert response.status_code == 401


# =============================================================================
# Test: Full Auth Flow (End-to-End)
# =============================================================================


class TestFullAuthFlow:
    """End-to-end test of complete authentication flow."""

    def test_complete_auth_lifecycle(self, client_clean_db: TestClient):
        """Test complete flow: register -> login -> access -> refresh -> logout."""
        # 1. Register
        register_response = register_user(client_clean_db)
        assert register_response.status_code == 201
        user_id = register_response.json()["id"]

        # 2. Login
        login_response = login_user(
            client_clean_db, TEST_USER["email"], TEST_USER["password"]
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]
        refresh_token = login_response.json()["refresh_token"]

        # 3. Access protected endpoint
        me_response = client_clean_db.get(
            "/auth/me", headers=get_auth_header(access_token)
        )
        assert me_response.status_code == 200
        assert me_response.json()["id"] == user_id

        # 4. Refresh token
        refresh_response = client_clean_db.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_response.status_code == 200
        new_access_token = refresh_response.json()["access_token"]
        new_refresh_token = refresh_response.json()["refresh_token"]

        # 5. Access with new token
        me_response2 = client_clean_db.get(
            "/auth/me", headers=get_auth_header(new_access_token)
        )
        assert me_response2.status_code == 200

        # 6. Logout
        logout_response = client_clean_db.post(
            "/auth/logout",
            json={"refresh_token": new_refresh_token},
            headers=get_auth_header(new_access_token),
        )
        assert logout_response.status_code == 200

        # 7. Verify refresh token is revoked
        final_refresh_response = client_clean_db.post(
            "/auth/refresh",
            json={"refresh_token": new_refresh_token},
        )
        assert final_refresh_response.status_code == 401
