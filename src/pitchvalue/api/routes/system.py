"""Liveness and dependency-readiness routes."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from pitchvalue.api.database import DatabaseResourceProtocol
from pitchvalue.api.dependencies import get_database
from pitchvalue.api.errors import ApiError, ErrorCode, ErrorResponse
from pitchvalue.api.models import HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report process liveness without touching the database."""
    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ErrorResponse, "description": "Core dependency unavailable"}},
)
def readiness(
    request: Request,
    database: Annotated[DatabaseResourceProtocol, Depends(get_database)],
) -> ReadinessResponse:
    """Report whether PostgreSQL can execute a lightweight query."""
    try:
        database.check()
    except Exception:
        logger.warning(
            "database readiness check failed",
            extra={"request_id": request.state.request_id},
        )
        raise ApiError(503, ErrorCode.SERVICE_UNAVAILABLE, "Service is not ready") from None
    return ReadinessResponse()
