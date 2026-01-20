"""Predictions API router - placeholder."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_predictions() -> dict[str, str]:
    """List predictions - placeholder endpoint."""
    return {"message": "Predictions endpoint - not yet implemented"}


@router.post("/")
async def create_prediction() -> dict[str, str]:
    """Create a new prediction - placeholder endpoint."""
    return {"message": "Create prediction - not yet implemented"}


@router.get("/{prediction_id}")
async def get_prediction(prediction_id: str) -> dict[str, str]:
    """Get prediction by ID - placeholder endpoint."""
    return {"message": f"Get prediction {prediction_id} - not yet implemented"}
