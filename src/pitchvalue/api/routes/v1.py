"""Version-one API root; business routes are intentionally deferred."""

from fastapi import APIRouter

from pitchvalue.api.models import ApiVersionResponse
from pitchvalue.api.routes.fixtures import router as fixtures_router
from pitchvalue.api.routes.predictions import router as predictions_router

router = APIRouter(prefix="/api/v1", tags=["api-v1"])
router.include_router(fixtures_router)
router.include_router(predictions_router)


@router.get("", response_model=ApiVersionResponse)
def api_version() -> ApiVersionResponse:
    """Identify the stable API namespace without exposing product data."""
    return ApiVersionResponse()
