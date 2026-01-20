"""
Redis connectivity check endpoint.
GET /redis-check - Returns 200 if Redis is reachable, 503 otherwise.
"""

from typing import Any

from fastapi import APIRouter, Depends, Response, status

from apps.api.redis_client import get_redis

router = APIRouter()


@router.get("/redis-check")
def redis_check(
    response: Response,
    redis_client: Any = Depends(get_redis),
) -> dict[str, str]:
    """
    Check Redis connectivity.

    Returns:
        200: {"redis": "ok"} - Redis is reachable
        503: {"redis": "fail", "error": "..."} - Redis unreachable
    """
    try:
        redis_client.ping()
        return {"redis": "ok"}
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        # Short error message (first 100 chars)
        error_msg = str(e)[:100] if str(e) else "Connection failed"
        return {"redis": "fail", "error": error_msg}
