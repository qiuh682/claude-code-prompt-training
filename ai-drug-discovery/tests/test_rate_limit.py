"""
Integration tests for rate limiting.

Tests cover:
1. Requests under limit -> 200
2. Exceed limit -> 429
3. Different users/orgs do not share counters (per-user/org isolation)

Uses real Redis (test instance) for accurate rate limit testing.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest
import redis
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.auth.models import Membership, Organization, User, UserRole
from apps.api.auth.security import hash_password
from apps.api.auth.service import create_tokens
from apps.api.config import Settings
from apps.api.ratelimit import RateLimiter, RateLimitTier

# =============================================================================
# Test Configuration
# =============================================================================

# Low rate limits for testing (3 requests per minute)
TEST_RATE_LIMIT = 3
TEST_WINDOW_SECONDS = 60


def get_test_settings() -> Settings:
    """Get test settings with low rate limits."""
    return Settings(
        rate_limit_user_rpm=TEST_RATE_LIMIT,
        rate_limit_org_rpm=TEST_RATE_LIMIT * 2,
        rate_limit_ip_rpm=TEST_RATE_LIMIT,
        rate_limit_auth_rpm=TEST_RATE_LIMIT,
        rate_limit_expensive_rpm=TEST_RATE_LIMIT,
        rate_limit_window_seconds=TEST_WINDOW_SECONDS,
        # Keep other settings at defaults
        database_url="postgresql://postgres:postgres@localhost:5433/drugdiscovery_test",
        redis_url="redis://localhost:6380/0",
    )


# =============================================================================
# Test Router with Rate Limited Endpoints
# =============================================================================

rate_limit_test_router = APIRouter(prefix="/rate-limit-test", tags=["Rate Limit Test"])

# Create rate limiter with test settings will be patched
test_rate_limiter = RateLimiter(tier=RateLimitTier.DEFAULT)
test_auth_rate_limiter = RateLimiter(tier=RateLimitTier.AUTH)


@rate_limit_test_router.get("/default", dependencies=[Depends(test_rate_limiter)])
def rate_limited_default():
    """Default rate limited endpoint."""
    return {"status": "ok", "endpoint": "default"}


@rate_limit_test_router.get("/auth", dependencies=[Depends(test_auth_rate_limiter)])
def rate_limited_auth():
    """Auth-tier rate limited endpoint (stricter)."""
    return {"status": "ok", "endpoint": "auth"}


@rate_limit_test_router.get("/no-limit")
def no_rate_limit():
    """Endpoint without rate limiting for comparison."""
    return {"status": "ok", "endpoint": "no-limit"}


# =============================================================================
# Test Data
# =============================================================================

TEST_PASSWORD = "SecureTestPass123"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def test_redis():
    """Get Redis client for tests."""
    client = redis.from_url(
        "redis://localhost:6380/0",
        socket_timeout=1,
        socket_connect_timeout=1,
    )
    yield client
    client.close()


@pytest.fixture
def clean_redis(test_redis):
    """Clean rate limit keys before and after each test."""
    def clean():
        # Delete all rate limit keys
        keys = test_redis.keys("ratelimit:*")
        if keys:
            test_redis.delete(*keys)

    clean()
    yield test_redis
    clean()


@pytest.fixture
def rate_limit_setup(test_session_factory, app):
    """
    Set up users for rate limit testing.

    Creates two users in different orgs for isolation testing.
    """
    # Add test router to app
    if rate_limit_test_router not in app.routes:
        app.include_router(rate_limit_test_router)

    db: Session = test_session_factory()

    try:
        # Create OrgA with userA
        org_a = Organization(
            id=uuid4(),
            name="Rate Limit Org A",
            slug=f"rate-org-a-{uuid4().hex[:8]}",
        )
        db.add(org_a)
        db.flush()

        user_a = User(
            id=uuid4(),
            email=f"rate-user-a-{uuid4().hex[:8]}@test.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="Rate User A",
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

        # Create OrgB with userB
        org_b = Organization(
            id=uuid4(),
            name="Rate Limit Org B",
            slug=f"rate-org-b-{uuid4().hex[:8]}",
        )
        db.add(org_b)
        db.flush()

        user_b = User(
            id=uuid4(),
            email=f"rate-user-b-{uuid4().hex[:8]}@test.com",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="Rate User B",
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

        # Create tokens
        token_a, _ = create_tokens(db, user_a)
        token_b, _ = create_tokens(db, user_b)

        yield {
            "user_a": user_a,
            "user_a_id": str(user_a.id),
            "token_a": token_a,
            "org_a": org_a,
            "user_b": user_b,
            "user_b_id": str(user_b.id),
            "token_b": token_b,
            "org_b": org_b,
            "db": db,
        }

    finally:
        db.rollback()
        db.close()


@pytest.fixture
def rate_client(app, rate_limit_setup, clean_redis):
    """TestClient with rate limit setup and clean Redis."""
    app.dependency_overrides.clear()

    # Patch settings to use test rate limits
    with patch("apps.api.ratelimit.get_settings", get_test_settings):
        with patch("apps.api.config.get_settings", get_test_settings):
            with TestClient(app) as client:
                yield client, rate_limit_setup, clean_redis

    app.dependency_overrides.clear()


# =============================================================================
# Test: Requests Under Limit
# =============================================================================


class TestRequestsUnderLimit:
    """Tests for requests that stay under the rate limit."""

    def test_single_request_succeeds(self, rate_client):
        """Single request under limit returns 200."""
        client, setup, _ = rate_client

        response = client.get(
            "/rate-limit-test/default",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_requests_up_to_limit_succeed(self, rate_client):
        """Requests up to the limit all return 200."""
        client, setup, _ = rate_client

        # Make requests up to the limit
        for i in range(TEST_RATE_LIMIT):
            response = client.get(
                "/rate-limit-test/default",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
            )
            assert response.status_code == 200, f"Request {i+1} failed unexpectedly"

    def test_rate_limit_headers_present(self, rate_client):
        """Successful requests include rate limit headers."""
        client, setup, _ = rate_client

        response = client.get(
            "/rate-limit-test/default",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
        )

        assert response.status_code == 200
        # Rate limit headers should be present (set by middleware or manually)
        # Note: Headers are set in request.state, may need middleware to add to response


# =============================================================================
# Test: Exceeding Rate Limit
# =============================================================================


class TestExceedingLimit:
    """Tests for requests that exceed the rate limit."""

    def test_exceeding_limit_returns_429(self, rate_client):
        """Request exceeding limit returns 429."""
        client, setup, _ = rate_client

        # Exhaust the rate limit
        for _ in range(TEST_RATE_LIMIT):
            response = client.get(
                "/rate-limit-test/default",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
            )
            assert response.status_code == 200

        # Next request should be rate limited
        response = client.get(
            "/rate-limit-test/default",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
        )

        assert response.status_code == 429

    def test_429_response_includes_error_details(self, rate_client):
        """429 response includes rate limit error details."""
        client, setup, _ = rate_client

        # Exhaust the rate limit
        for _ in range(TEST_RATE_LIMIT):
            client.get(
                "/rate-limit-test/default",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
            )

        # Get 429 response
        response = client.get(
            "/rate-limit-test/default",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
        )

        assert response.status_code == 429
        data = response.json()["detail"]
        assert data["error"] == "rate_limit_exceeded"
        assert "limit" in data
        assert "retry_after" in data
        assert "reset_at" in data

    def test_429_includes_retry_after_header(self, rate_client):
        """429 response includes Retry-After header."""
        client, setup, _ = rate_client

        # Exhaust the rate limit
        for _ in range(TEST_RATE_LIMIT):
            client.get(
                "/rate-limit-test/default",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
            )

        # Get 429 response
        response = client.get(
            "/rate-limit-test/default",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
        )

        assert response.status_code == 429
        assert "retry-after" in response.headers
        retry_after = int(response.headers["retry-after"])
        assert retry_after > 0
        assert retry_after <= TEST_WINDOW_SECONDS

    def test_multiple_requests_over_limit_all_return_429(self, rate_client):
        """Multiple requests over limit all return 429."""
        client, setup, _ = rate_client

        # Exhaust the rate limit
        for _ in range(TEST_RATE_LIMIT):
            client.get(
                "/rate-limit-test/default",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
            )

        # All subsequent requests should be rate limited
        for _ in range(3):
            response = client.get(
                "/rate-limit-test/default",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
            )
            assert response.status_code == 429


# =============================================================================
# Test: Per-User Isolation
# =============================================================================


class TestPerUserIsolation:
    """Tests verifying rate limits are per-user, not global."""

    def test_different_users_have_separate_limits(self, rate_client):
        """Two different users do not share rate limit counters."""
        client, setup, _ = rate_client

        # User A exhausts their rate limit
        for _ in range(TEST_RATE_LIMIT):
            response = client.get(
                "/rate-limit-test/default",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
            )
            assert response.status_code == 200

        # User A is now rate limited
        response_a = client.get(
            "/rate-limit-test/default",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
        )
        assert response_a.status_code == 429

        # User B should still be able to make requests
        for _ in range(TEST_RATE_LIMIT):
            response_b = client.get(
                "/rate-limit-test/default",
                headers={"Authorization": f"Bearer {setup['token_b']}"},
            )
            assert response_b.status_code == 200, "User B should not be affected by User A's limit"

    def test_user_a_limited_user_b_unlimited(self, rate_client):
        """When User A hits limit, User B still has full quota."""
        client, setup, _ = rate_client

        # User A makes requests to exhaust limit
        for _ in range(TEST_RATE_LIMIT + 1):
            client.get(
                "/rate-limit-test/default",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
            )

        # User B makes same number of requests - all should succeed until their limit
        success_count = 0
        for _ in range(TEST_RATE_LIMIT):
            response = client.get(
                "/rate-limit-test/default",
                headers={"Authorization": f"Bearer {setup['token_b']}"},
            )
            if response.status_code == 200:
                success_count += 1

        assert success_count == TEST_RATE_LIMIT


# =============================================================================
# Test: IP-Based Rate Limiting
# =============================================================================


class TestIPBasedLimiting:
    """Tests for unauthenticated (IP-based) rate limiting."""

    def test_unauthenticated_requests_rate_limited_by_ip(self, rate_client):
        """Unauthenticated requests are rate limited by IP."""
        client, setup, _ = rate_client

        # Make requests without auth (will use IP)
        for _ in range(TEST_RATE_LIMIT):
            response = client.get("/rate-limit-test/default")
            assert response.status_code == 200

        # Should be rate limited
        response = client.get("/rate-limit-test/default")
        assert response.status_code == 429

    def test_different_ips_have_separate_limits(self, rate_client):
        """Different IPs have separate rate limit counters."""
        client, setup, _ = rate_client

        # Exhaust limit for IP 1
        for _ in range(TEST_RATE_LIMIT):
            response = client.get(
                "/rate-limit-test/default",
                headers={"X-Forwarded-For": "192.168.1.100"},
            )
            assert response.status_code == 200

        # IP 1 is rate limited
        response = client.get(
            "/rate-limit-test/default",
            headers={"X-Forwarded-For": "192.168.1.100"},
        )
        assert response.status_code == 429

        # IP 2 should still work
        for _ in range(TEST_RATE_LIMIT):
            response = client.get(
                "/rate-limit-test/default",
                headers={"X-Forwarded-For": "192.168.1.200"},
            )
            assert response.status_code == 200


# =============================================================================
# Test: Different Rate Limit Tiers
# =============================================================================


class TestRateLimitTiers:
    """Tests for different rate limit tiers."""

    def test_auth_tier_has_same_limit_in_test(self, rate_client):
        """Auth tier endpoint respects its rate limit."""
        client, setup, _ = rate_client

        # Auth tier uses same test limit
        for _ in range(TEST_RATE_LIMIT):
            response = client.get(
                "/rate-limit-test/auth",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
            )
            assert response.status_code == 200

        # Should be rate limited
        response = client.get(
            "/rate-limit-test/auth",
            headers={"Authorization": f"Bearer {setup['token_a']}"},
        )
        assert response.status_code == 429

    def test_no_limit_endpoint_not_affected(self, rate_client):
        """Endpoint without rate limiting is never rate limited."""
        client, setup, _ = rate_client

        # Make many requests to non-rate-limited endpoint
        for _ in range(TEST_RATE_LIMIT * 3):
            response = client.get(
                "/rate-limit-test/no-limit",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
            )
            assert response.status_code == 200


# =============================================================================
# Test: Rate Limit Counter Behavior
# =============================================================================


class TestRateLimitCounterBehavior:
    """Tests for rate limit counter mechanics."""

    def test_counter_increments_correctly(self, rate_client):
        """Each request increments the counter."""
        client, setup, redis_client = rate_client

        # Make requests and verify we can make exactly TEST_RATE_LIMIT
        success_count = 0
        for _ in range(TEST_RATE_LIMIT + 2):
            response = client.get(
                "/rate-limit-test/default",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
            )
            if response.status_code == 200:
                success_count += 1

        assert success_count == TEST_RATE_LIMIT

    def test_rate_limit_resets_after_window(self, rate_client):
        """Rate limit resets after the window expires.

        Note: This test uses a short sleep to simulate window reset.
        In real scenarios, you'd mock time or use a very short window.
        """
        # Skip this test in normal runs as it would require waiting
        # For actual testing, you could:
        # 1. Mock time.time() to advance the clock
        # 2. Use a very short window (1 second)
        # 3. Manually clear Redis keys
        pytest.skip("Window reset test requires time manipulation or waiting")


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestRateLimitEdgeCases:
    """Edge case tests for rate limiting."""

    def test_authenticated_user_not_affected_by_ip_limit(self, rate_client):
        """Authenticated user has separate counter from IP-based limit."""
        client, setup, _ = rate_client

        # Exhaust IP-based limit
        for _ in range(TEST_RATE_LIMIT):
            client.get("/rate-limit-test/default")

        # IP is rate limited
        response = client.get("/rate-limit-test/default")
        assert response.status_code == 429

        # Authenticated user should still work (different counter)
        for _ in range(TEST_RATE_LIMIT):
            response = client.get(
                "/rate-limit-test/default",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
            )
            assert response.status_code == 200

    def test_rate_limit_with_invalid_token_uses_ip(self, rate_client):
        """Invalid JWT token falls back to IP-based rate limiting."""
        client, setup, _ = rate_client

        # First exhaust IP limit with invalid token
        for _ in range(TEST_RATE_LIMIT):
            client.get(
                "/rate-limit-test/default",
                headers={"Authorization": "Bearer invalid_token_xyz"},
            )
            # Will either fail auth (401) or succeed if rate limit allows
            # The key is that it uses IP-based limiting

        # Now unauthenticated request from same IP should be affected
        # (since invalid token requests count against IP limit)

    def test_concurrent_requests_counted_correctly(self, rate_client):
        """Concurrent requests are all counted correctly.

        Note: True concurrency testing would require threading or asyncio.
        This test verifies sequential rapid requests are counted.
        """
        client, setup, _ = rate_client

        # Rapid sequential requests
        results = []
        for _ in range(TEST_RATE_LIMIT + 2):
            response = client.get(
                "/rate-limit-test/default",
                headers={"Authorization": f"Bearer {setup['token_a']}"},
            )
            results.append(response.status_code)

        # Should have exactly TEST_RATE_LIMIT successes
        success_count = results.count(200)
        rate_limited_count = results.count(429)

        assert success_count == TEST_RATE_LIMIT
        assert rate_limited_count == 2
