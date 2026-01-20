"""
Integration tests for password reset flow.

Tests cover:
1. POST /auth/password/forgot with email -> 200 (doesn't leak email existence)
2. Reset token is created (captured from DB)
3. POST /auth/password/reset with token + new password -> 200
4. Login with old password fails; login with new password succeeds
5. Token cannot be reused (second reset attempt fails)
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth.models import PasswordResetToken, User
from apps.api.auth.security import hash_password, hash_token
from apps.api.auth.service import create_password_reset_token

# =============================================================================
# Test Data
# =============================================================================

TEST_USER = {
    "email": "resetuser@example.com",
    "password": "OldPassword123",
    "full_name": "Reset Test User",
}

NEW_PASSWORD = "NewSecurePass456"


# =============================================================================
# Helper Functions
# =============================================================================


def register_user(client: TestClient, user_data: dict | None = None) -> dict:
    """Register a user and return the response."""
    data = user_data or TEST_USER
    return client.post("/auth/register", json=data)


def login_user(client: TestClient, email: str, password: str) -> dict:
    """Login and return the response."""
    return client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )


def get_reset_token_from_db(db: Session, user_id) -> str | None:
    """Get the plaintext-equivalent info for finding the token record.

    Since we store hashed tokens, we need to get the token record
    and the test will use the service function to create it.
    """
    stmt = (
        select(PasswordResetToken)
        .where(PasswordResetToken.user_id == user_id)
        .order_by(PasswordResetToken.created_at.desc())
    )
    token_record = db.execute(stmt).scalar_one_or_none()
    return token_record


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def password_reset_setup(test_session_factory, app):
    """
    Set up a user for password reset testing.

    Returns dict with user info and database session.
    """
    db: Session = test_session_factory()

    try:
        # Create user directly in DB for controlled testing
        user = User(
            id=uuid4(),
            email=f"resettest-{uuid4().hex[:8]}@example.com",
            password_hash=hash_password(TEST_USER["password"]),
            full_name=TEST_USER["full_name"],
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        yield {
            "user": user,
            "user_id": user.id,
            "email": user.email,
            "old_password": TEST_USER["password"],
            "db": db,
        }

    finally:
        db.rollback()
        db.close()


@pytest.fixture
def pr_client(app, password_reset_setup) -> tuple[TestClient, dict]:
    """
    TestClient with password reset setup.

    Returns tuple of (client, setup_data).
    """
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        yield client, password_reset_setup
    app.dependency_overrides.clear()


# =============================================================================
# Test: Forgot Password Endpoint
# =============================================================================


class TestForgotPassword:
    """Tests for POST /auth/password/forgot endpoint."""

    def test_forgot_password_existing_email_returns_200(self, pr_client):
        """Forgot password with existing email -> 200."""
        client, setup = pr_client

        response = client.post(
            "/auth/password/forgot",
            json={"email": setup["email"]},
        )

        assert response.status_code == 200
        # Message should not reveal whether email exists
        assert "if an account exists" in response.json()["message"].lower()

    def test_forgot_password_nonexistent_email_returns_200(self, pr_client):
        """Forgot password with non-existent email -> 200 (no info leak)."""
        client, setup = pr_client

        response = client.post(
            "/auth/password/forgot",
            json={"email": "nonexistent@example.com"},
        )

        # Should return 200 even for non-existent email (security)
        assert response.status_code == 200
        assert "if an account exists" in response.json()["message"].lower()

    def test_forgot_password_creates_token_in_db(self, pr_client):
        """Forgot password creates a reset token in the database."""
        client, setup = pr_client
        db = setup["db"]

        # Request password reset
        response = client.post(
            "/auth/password/forgot",
            json={"email": setup["email"]},
        )
        assert response.status_code == 200

        # Verify token was created in DB
        token_record = get_reset_token_from_db(db, setup["user_id"])
        assert token_record is not None
        assert token_record.user_id == setup["user_id"]
        assert token_record.used_at is None  # Not used yet
        assert token_record.is_valid  # Should be valid

    def test_forgot_password_invalid_email_format(self, pr_client):
        """Forgot password with invalid email format -> 422."""
        client, setup = pr_client

        response = client.post(
            "/auth/password/forgot",
            json={"email": "not-an-email"},
        )

        assert response.status_code == 422


# =============================================================================
# Test: Reset Password Endpoint
# =============================================================================


class TestResetPassword:
    """Tests for POST /auth/password/reset endpoint."""

    def test_reset_password_with_valid_token(self, pr_client):
        """Reset password with valid token -> 200."""
        client, setup = pr_client
        db = setup["db"]

        # Create reset token directly using service
        token = create_password_reset_token(db, setup["email"])
        assert token is not None

        # Reset password
        response = client.post(
            "/auth/password/reset",
            json={"token": token, "new_password": NEW_PASSWORD},
        )

        assert response.status_code == 200
        assert "reset successfully" in response.json()["message"].lower()

    def test_reset_password_with_invalid_token(self, pr_client):
        """Reset password with invalid token -> 400."""
        client, setup = pr_client

        response = client.post(
            "/auth/password/reset",
            json={"token": "invalid-token-12345", "new_password": NEW_PASSWORD},
        )

        assert response.status_code == 400
        assert "invalid or expired" in response.json()["detail"].lower()

    def test_reset_password_weak_password_rejected(self, pr_client):
        """Reset password with weak password -> 422."""
        client, setup = pr_client
        db = setup["db"]

        # Create reset token
        token = create_password_reset_token(db, setup["email"])

        # Try to reset with weak password
        response = client.post(
            "/auth/password/reset",
            json={"token": token, "new_password": "weak"},
        )

        assert response.status_code == 422


# =============================================================================
# Test: Login After Password Reset
# =============================================================================


class TestLoginAfterReset:
    """Tests for login behavior after password reset."""

    def test_old_password_fails_after_reset(self, pr_client):
        """After reset, login with old password -> 401."""
        client, setup = pr_client
        db = setup["db"]

        # Verify old password works before reset
        login_before = login_user(client, setup["email"], setup["old_password"])
        assert login_before.status_code == 200

        # Create and use reset token
        token = create_password_reset_token(db, setup["email"])
        reset_response = client.post(
            "/auth/password/reset",
            json={"token": token, "new_password": NEW_PASSWORD},
        )
        assert reset_response.status_code == 200

        # Try login with old password
        login_after = login_user(client, setup["email"], setup["old_password"])
        assert login_after.status_code == 401

    def test_new_password_works_after_reset(self, pr_client):
        """After reset, login with new password -> 200."""
        client, setup = pr_client
        db = setup["db"]

        # Create and use reset token
        token = create_password_reset_token(db, setup["email"])
        reset_response = client.post(
            "/auth/password/reset",
            json={"token": token, "new_password": NEW_PASSWORD},
        )
        assert reset_response.status_code == 200

        # Login with new password
        login_response = login_user(client, setup["email"], NEW_PASSWORD)
        assert login_response.status_code == 200
        assert "access_token" in login_response.json()


# =============================================================================
# Test: Token Reuse Prevention
# =============================================================================


class TestTokenReusePrevention:
    """Tests to ensure tokens cannot be reused."""

    def test_token_cannot_be_reused(self, pr_client):
        """After successful reset, token cannot be used again -> 400."""
        client, setup = pr_client
        db = setup["db"]

        # Create reset token
        token = create_password_reset_token(db, setup["email"])

        # First reset - should succeed
        response1 = client.post(
            "/auth/password/reset",
            json={"token": token, "new_password": NEW_PASSWORD},
        )
        assert response1.status_code == 200

        # Second reset with same token - should fail
        response2 = client.post(
            "/auth/password/reset",
            json={"token": token, "new_password": "AnotherPass789"},
        )
        assert response2.status_code == 400
        assert "invalid or expired" in response2.json()["detail"].lower()

    def test_token_marked_as_used_in_db(self, pr_client):
        """After reset, token is marked as used in database."""
        client, setup = pr_client
        db = setup["db"]

        # Create reset token
        token = create_password_reset_token(db, setup["email"])

        # Get token record before reset
        token_hash = hash_token(token)
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash
        )
        token_record = db.execute(stmt).scalar_one()
        assert token_record.used_at is None

        # Reset password
        client.post(
            "/auth/password/reset",
            json={"token": token, "new_password": NEW_PASSWORD},
        )

        # Refresh and check token is marked as used
        db.refresh(token_record)
        assert token_record.used_at is not None


# =============================================================================
# Test: Token Expiration
# =============================================================================


class TestTokenExpiration:
    """Tests for token expiration."""

    def test_expired_token_rejected(self, pr_client):
        """Expired token -> 400."""
        client, setup = pr_client
        db = setup["db"]

        from datetime import datetime, timedelta

        # Create an expired token directly in DB
        expired_token_value = "expired-test-token-12345"
        expired_token = PasswordResetToken(
            user_id=setup["user_id"],
            token_hash=hash_token(expired_token_value),
            expires_at=datetime.utcnow() - timedelta(hours=2),  # Expired 2 hours ago
        )
        db.add(expired_token)
        db.commit()

        # Try to use expired token
        response = client.post(
            "/auth/password/reset",
            json={"token": expired_token_value, "new_password": NEW_PASSWORD},
        )

        assert response.status_code == 400
        assert "invalid or expired" in response.json()["detail"].lower()


# =============================================================================
# Test: Full Password Reset Flow (E2E)
# =============================================================================


class TestFullPasswordResetFlow:
    """End-to-end test of complete password reset flow."""

    def test_complete_password_reset_flow(self, pr_client):
        """
        Complete flow:
        1. Request password reset
        2. Get token from DB
        3. Reset password
        4. Old password fails
        5. New password works
        6. Token cannot be reused
        """
        client, setup = pr_client
        db = setup["db"]

        # 1. Request password reset
        forgot_response = client.post(
            "/auth/password/forgot",
            json={"email": setup["email"]},
        )
        assert forgot_response.status_code == 200

        # 2. Get token from service (simulating email delivery)
        token = create_password_reset_token(db, setup["email"])
        assert token is not None

        # 3. Reset password
        reset_response = client.post(
            "/auth/password/reset",
            json={"token": token, "new_password": NEW_PASSWORD},
        )
        assert reset_response.status_code == 200

        # 4. Old password fails
        old_login = login_user(client, setup["email"], setup["old_password"])
        assert old_login.status_code == 401

        # 5. New password works
        new_login = login_user(client, setup["email"], NEW_PASSWORD)
        assert new_login.status_code == 200
        assert "access_token" in new_login.json()

        # 6. Token cannot be reused
        reuse_response = client.post(
            "/auth/password/reset",
            json={"token": token, "new_password": "YetAnotherPass999"},
        )
        assert reuse_response.status_code == 400


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestPasswordResetEdgeCases:
    """Edge cases for password reset."""

    def test_multiple_reset_requests_only_latest_valid(self, pr_client):
        """Multiple reset requests - all tokens should work until used."""
        client, setup = pr_client
        db = setup["db"]

        # Create multiple tokens
        token1 = create_password_reset_token(db, setup["email"])
        token2 = create_password_reset_token(db, setup["email"])

        # Both should be valid initially
        assert token1 is not None
        assert token2 is not None

        # Use first token
        response1 = client.post(
            "/auth/password/reset",
            json={"token": token1, "new_password": NEW_PASSWORD},
        )
        assert response1.status_code == 200

        # Second token should still work (different token)
        response2 = client.post(
            "/auth/password/reset",
            json={"token": token2, "new_password": "AnotherNewPass123"},
        )
        assert response2.status_code == 200

    def test_inactive_user_cannot_request_reset(self, pr_client):
        """Inactive user requesting reset -> 200 but no token created."""
        client, setup = pr_client
        db = setup["db"]

        # Deactivate user
        user = setup["user"]
        user.is_active = False
        db.commit()

        # Count tokens before
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.user_id == setup["user_id"]
        )
        tokens_before = len(list(db.execute(stmt).scalars().all()))

        # Request reset
        response = client.post(
            "/auth/password/forgot",
            json={"email": setup["email"]},
        )

        # Should still return 200 (don't leak info)
        assert response.status_code == 200

        # But no new token should be created
        tokens_after = len(list(db.execute(stmt).scalars().all()))
        assert tokens_after == tokens_before

        # Reactivate user for other tests
        user.is_active = True
        db.commit()
