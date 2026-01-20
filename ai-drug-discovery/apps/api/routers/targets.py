"""Targets API router - placeholder."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_targets() -> dict[str, str]:
    """List targets - placeholder endpoint."""
    return {"message": "Targets endpoint - not yet implemented"}


@router.get("/{target_id}")
async def get_target(target_id: str) -> dict[str, str]:
    """Get target by ID - placeholder endpoint."""
    return {"message": f"Get target {target_id} - not yet implemented"}
