"""Predictions API router - placeholder."""

from fastapi import APIRouter, Depends

from apps.api.ratelimit import rate_limit_default, rate_limit_expensive

router = APIRouter()


@router.get(
    "/",
    dependencies=[Depends(rate_limit_default)],
)
async def list_predictions() -> dict[str, str]:
    """List predictions - placeholder endpoint."""
    return {"message": "Predictions endpoint - not yet implemented"}


@router.post(
    "/",
    dependencies=[Depends(rate_limit_expensive)],
)
async def create_prediction() -> dict[str, str]:
    """Create a new prediction - placeholder endpoint.

    This endpoint uses rate_limit_expensive (10 req/min) because
    ML predictions are computationally expensive operations.
    """
    return {"message": "Create prediction - not yet implemented"}


@router.get("/{prediction_id}")
async def get_prediction(prediction_id: str) -> dict[str, str]:
    """Get prediction by ID - placeholder endpoint."""
    return {"message": f"Get prediction {prediction_id} - not yet implemented"}
