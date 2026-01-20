"""
Database connectivity check endpoint.
GET /db-check - Returns 200 if DB is reachable, 503 otherwise.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.db import get_db

router = APIRouter()


@router.get("/db-check")
def db_check(
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """
    Check database connectivity.

    Returns:
        200: {"db": "ok"} - Database is reachable
        503: {"db": "fail", "error": "..."} - Database unreachable
    """
    try:
        db.execute(text("SELECT 1"))
        return {"db": "ok"}
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        # Short error message (first 100 chars)
        error_msg = str(e)[:100] if str(e) else "Connection failed"
        return {"db": "fail", "error": error_msg}
