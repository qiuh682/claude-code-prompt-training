"""Molecules API router - placeholder."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_molecules() -> dict[str, str]:
    """List molecules - placeholder endpoint."""
    return {"message": "Molecules endpoint - not yet implemented"}


@router.get("/{molecule_id}")
async def get_molecule(molecule_id: str) -> dict[str, str]:
    """Get molecule by ID - placeholder endpoint."""
    return {"message": f"Get molecule {molecule_id} - not yet implemented"}
