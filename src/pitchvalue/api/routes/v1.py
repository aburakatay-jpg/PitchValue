"""Version-one API root; business routes are intentionally deferred."""

from fastapi import APIRouter

from pitchvalue.api.models import ApiVersionResponse

router = APIRouter(prefix="/api/v1", tags=["api-v1"])


@router.get("", response_model=ApiVersionResponse)
def api_version() -> ApiVersionResponse:
    """Identify the stable API namespace without exposing product data."""
    return ApiVersionResponse()
