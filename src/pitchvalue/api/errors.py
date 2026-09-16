"""Stable, client-safe API error responses."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    EXTERNAL_ACTIVATION_REQUIRED = "EXTERNAL_ACTIVATION_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ApiError(Exception):
    """An expected application failure with safe client-facing details."""

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = dict(headers or {})


def _request_id(request: Request) -> str:
    value: str = getattr(request.state, "request_id", "unavailable")
    return value


def _response(
    request: Request,
    status_code: int,
    code: ErrorCode,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    content = ErrorResponse(
        error=ErrorDetail(code=code, message=message, request_id=request_id)
    ).model_dump(mode="json")
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers={**dict(headers or {}), "X-Request-ID": request_id},
    )


async def api_error_handler(request: Request, error: ApiError) -> JSONResponse:
    return _response(request, error.status_code, error.code, error.message, error.headers)


async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    del error
    return _response(request, 422, ErrorCode.VALIDATION_ERROR, "Request validation failed")


async def http_error_handler(request: Request, error: StarletteHTTPException) -> JSONResponse:
    if error.status_code == 404:
        return _response(request, 404, ErrorCode.NOT_FOUND, "Resource not found")
    return _response(request, error.status_code, ErrorCode.INTERNAL_ERROR, "Request failed")


async def internal_error_handler(request: Request, error: Exception) -> JSONResponse:
    del error
    logger.error(
        "unhandled server exception",
        extra={"request_id": _request_id(request)},
    )
    return _response(request, 500, ErrorCode.INTERNAL_ERROR, "Internal server error")


def install_error_handlers(app: FastAPI) -> None:
    """Install handlers without changing FastAPI's OpenAPI behavior."""
    app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, internal_error_handler)


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication required"},
    403: {"model": ErrorResponse, "description": "Forbidden"},
    409: {"model": ErrorResponse, "description": "Conflict"},
    429: {"model": ErrorResponse, "description": "Rate limited"},
    503: {"model": ErrorResponse, "description": "Service unavailable"},
    422: {"model": ErrorResponse, "description": "Validation error"},
    500: {"model": ErrorResponse, "description": "Internal error"},
}
