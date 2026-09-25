"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pitchvalue.api.database import DatabaseFactory, create_database
from pitchvalue.api.errors import ERROR_RESPONSES, install_error_handlers
from pitchvalue.api.logging import configure_logging
from pitchvalue.api.middleware import RequestContextMiddleware
from pitchvalue.api.routes.system import router as system_router
from pitchvalue.api.routes.v1 import router as v1_router
from pitchvalue.api.routes.web import router as web_router
from pitchvalue.config import Settings, load_settings
from pitchvalue.product_services.abuse import InMemoryAuthLimiter

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    database_factory: DatabaseFactory = create_database,
) -> FastAPI:
    """Create an isolated application without connecting during import or construction."""
    resolved_settings = settings or load_settings()
    database = database_factory(resolved_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(resolved_settings.log_level)
        application.state.database = database
        database.start()
        logger.info("application startup", extra={"request_id": "-"})
        try:
            yield
        finally:
            database.dispose()
            logger.info("application shutdown", extra={"request_id": "-"})

    application = FastAPI(
        title="PitchValue API",
        description="HTTP foundation for PitchValue services.",
        version="1.0.0",
        debug=False,
        lifespan=lifespan,
        responses=ERROR_RESPONSES,
    )
    application.state.settings = resolved_settings
    application.state.api_v1_prefix = v1_router.prefix
    application.state.auth_limiter = InMemoryAuthLimiter()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Accept", "Authorization", "Content-Type", "X-Request-ID"],
    )
    application.add_middleware(RequestContextMiddleware)
    install_error_handlers(application)
    application.include_router(system_router)
    application.include_router(web_router)
    application.include_router(v1_router)
    return application
