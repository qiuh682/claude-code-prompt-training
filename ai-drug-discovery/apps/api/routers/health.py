"""
Health check endpoint.
GET /health - Returns 200 if all checks pass, 503 otherwise.
"""

import time
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db, get_redis

router = APIRouter()


@router.get("/health")
def health_check(
    response: Response,
    db: Session = Depends(get_db),
    redis_client: Any = Depends(get_redis),
) -> dict[str, Any]:
    """
    Health check endpoint.

    Returns:
        200 + {"status": "ok", ...} if all checks pass
        503 + {"status": "degraded", ...} if any check fails
    """
    result: dict[str, Any] = {
        "status": "ok",
        "api": "ok",
        "db": "ok",
        "redis": "ok",
    }
    all_healthy = True

    # --- Check PostgreSQL (SELECT 1, 1s timeout) ---
    try:
        start = time.perf_counter()
        db.execute(text("SELECT 1"))
        result["db_latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
    except Exception:
        result["db"] = "fail"
        all_healthy = False

    # --- Check Redis (PING, 1s timeout) ---
    try:
        start = time.perf_counter()
        redis_client.ping()
        result["redis_latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
    except Exception:
        result["redis"] = "fail"
        all_healthy = False

    # --- Set response ---
    if not all_healthy:
        result["status"] = "degraded"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return result
