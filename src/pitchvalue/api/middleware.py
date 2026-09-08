"""Request metadata and access logging middleware."""

from __future__ import annotations

import logging
import re
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def normalize_request_id(value: str | None) -> str:
    """Accept a bounded safe identifier or generate an opaque replacement."""
    if (
        value is not None
        and len(value) <= MAX_REQUEST_ID_LENGTH
        and _VALID_REQUEST_ID.fullmatch(value)
    ):
        return value
    return uuid.uuid4().hex


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request IDs, response headers, and safe access logs."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        started_at = time.perf_counter()
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            extra={"request_id": request_id},
        )
        return response
