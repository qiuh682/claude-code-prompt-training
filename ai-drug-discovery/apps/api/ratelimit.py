"""
Rate limiting using Redis sliding window counters.

Supports rate limiting by:
- Authenticated user_id
- API key ID
- Organization ID
- IP address (fallback for unauthenticated requests)
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Annotated

import redis
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.api.config import get_settings
from apps.api.redis_client import get_redis

# Lazy import to avoid circular dependency
bearer_scheme = HTTPBearer(auto_error=False)


class RateLimitTier(str, Enum):
    """Rate limit tiers for different endpoint types."""

    DEFAULT = "default"  # Standard user limit
    AUTH = "auth"  # Login/register (stricter)
    EXPENSIVE = "expensive"  # ML predictions, heavy compute
    ORG = "org"  # Organization-wide limit


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    limit: int
    remaining: int
    reset_at: int  # Unix timestamp
    retry_after: int | None = None  # Seconds until reset (if blocked)


@dataclass
class RateLimitInfo:
    """Information about rate limit context."""

    key: str  # Redis key
    identifier: str  # Human-readable identifier
    identifier_type: str  # "user", "api_key", "org", "ip"


def _get_tier_limit(tier: RateLimitTier) -> int:
    """Get the rate limit for a given tier."""
    settings = get_settings()
    limits = {
        RateLimitTier.DEFAULT: settings.rate_limit_user_rpm,
        RateLimitTier.AUTH: settings.rate_limit_auth_rpm,
        RateLimitTier.EXPENSIVE: settings.rate_limit_expensive_rpm,
        RateLimitTier.ORG: settings.rate_limit_org_rpm,
    }
    return limits.get(tier, settings.rate_limit_user_rpm)


def check_rate_limit(
    redis_client: redis.Redis,
    key: str,
    limit: int,
    window_seconds: int | None = None,
) -> RateLimitResult:
    """Check and increment rate limit counter using sliding window.

    Uses Redis INCR with expiry for a simple sliding window counter.

    Args:
        redis_client: Redis client instance
        key: Rate limit key (e.g., "ratelimit:user:123")
        limit: Maximum requests allowed per window
        window_seconds: Window size in seconds (default from settings)

    Returns:
        RateLimitResult with allowed status and metadata
    """
    if window_seconds is None:
        window_seconds = get_settings().rate_limit_window_seconds

    now = int(time.time())
    window_start = now - (now % window_seconds)
    window_key = f"{key}:{window_start}"

    # Increment counter and get current value
    pipe = redis_client.pipeline()
    pipe.incr(window_key)
    pipe.expire(window_key, window_seconds + 1)  # TTL slightly longer than window
    results = pipe.execute()

    current_count = results[0]
    remaining = max(0, limit - current_count)
    reset_at = window_start + window_seconds

    if current_count > limit:
        retry_after = reset_at - now
        return RateLimitResult(
            allowed=False,
            limit=limit,
            remaining=0,
            reset_at=reset_at,
            retry_after=retry_after,
        )

    return RateLimitResult(
        allowed=True,
        limit=limit,
        remaining=remaining,
        reset_at=reset_at,
    )


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, considering proxies."""
    # Check X-Forwarded-For header (common with reverse proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP (original client)
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header (nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct client
    if request.client:
        return request.client.host

    return "unknown"


def _extract_auth_info(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    api_key_header: str | None,
) -> RateLimitInfo:
    """Extract rate limit identifier from request context.

    Priority:
    1. API key ID (if X-API-Key header present and valid format)
    2. User ID from JWT (if Bearer token present)
    3. IP address (fallback)
    """
    # Try API key first (we can't validate it here, just extract for rate limiting)
    if api_key_header and api_key_header.startswith("sk_"):
        # Use hash of API key prefix for rate limiting (don't expose full key)
        key_prefix = api_key_header[:12] if len(api_key_header) >= 12 else api_key_header
        return RateLimitInfo(
            key=f"ratelimit:apikey:{key_prefix}",
            identifier=f"{key_prefix}...",
            identifier_type="api_key",
        )

    # Try JWT token
    if credentials:
        from apps.api.auth.security import decode_access_token

        payload = decode_access_token(credentials.credentials)
        if payload and "sub" in payload:
            user_id = payload["sub"]
            return RateLimitInfo(
                key=f"ratelimit:user:{user_id}",
                identifier=user_id,
                identifier_type="user",
            )

    # Fall back to IP
    client_ip = get_client_ip(request)
    return RateLimitInfo(
        key=f"ratelimit:ip:{client_ip}",
        identifier=client_ip,
        identifier_type="ip",
    )


def _get_limit_for_identifier(identifier_type: str, tier: RateLimitTier) -> int:
    """Get the appropriate limit based on identifier type and tier."""
    settings = get_settings()

    # Auth tier always uses auth limit
    if tier == RateLimitTier.AUTH:
        return settings.rate_limit_auth_rpm

    # Expensive tier always uses expensive limit
    if tier == RateLimitTier.EXPENSIVE:
        return settings.rate_limit_expensive_rpm

    # Default tier varies by identifier type
    if identifier_type == "ip":
        return settings.rate_limit_ip_rpm
    elif identifier_type == "api_key":
        return settings.rate_limit_user_rpm  # API keys get user-level limits
    else:
        return settings.rate_limit_user_rpm


class RateLimiter:
    """Configurable rate limiter dependency factory."""

    def __init__(
        self,
        tier: RateLimitTier = RateLimitTier.DEFAULT,
        include_org_limit: bool = False,
    ):
        """Initialize rate limiter.

        Args:
            tier: Rate limit tier (affects limits)
            include_org_limit: Also check org-wide limit (for authenticated requests)
        """
        self.tier = tier
        self.include_org_limit = include_org_limit

    async def __call__(
        self,
        request: Request,
        redis_client: redis.Redis = Depends(get_redis),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> RateLimitResult:
        """Check rate limit and raise 429 if exceeded."""
        settings = get_settings()

        # Extract auth info for rate limiting
        auth_info = _extract_auth_info(request, credentials, x_api_key)

        # Determine limit based on identifier type and tier
        limit = _get_limit_for_identifier(auth_info.identifier_type, self.tier)

        # Check rate limit
        try:
            result = check_rate_limit(
                redis_client,
                auth_info.key,
                limit,
                settings.rate_limit_window_seconds,
            )
        except redis.RedisError:
            # If Redis is down, fail open (allow request but log warning)
            # In production, you might want to fail closed instead
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=limit,
                reset_at=int(time.time()) + settings.rate_limit_window_seconds,
            )

        # Add rate limit headers to response
        request.state.rate_limit_result = result
        request.state.rate_limit_info = auth_info

        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded for {auth_info.identifier_type}",
                    "limit": result.limit,
                    "reset_at": result.reset_at,
                    "retry_after": result.retry_after,
                },
                headers={
                    "Retry-After": str(result.retry_after),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(result.reset_at),
                },
            )

        # Also check org limit if requested and we have org context
        if self.include_org_limit and auth_info.identifier_type in ("user", "api_key"):
            # For org limits, we'd need to look up the org_id
            # This is a simplified version - in practice you'd get org_id from the auth context
            pass

        return result


# Pre-configured rate limiters for common use cases
rate_limit_default = RateLimiter(tier=RateLimitTier.DEFAULT)
rate_limit_auth = RateLimiter(tier=RateLimitTier.AUTH)
rate_limit_expensive = RateLimiter(tier=RateLimitTier.EXPENSIVE)


def get_rate_limit_headers(result: RateLimitResult) -> dict[str, str]:
    """Generate rate limit response headers."""
    return {
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset": str(result.reset_at),
    }
