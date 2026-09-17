"""PitchValue HTTP API foundation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from pitchvalue.api.database import DatabaseFactory
    from pitchvalue.config import Settings


def create_app(
    settings: Settings | None = None,
    database_factory: DatabaseFactory | None = None,
) -> FastAPI:
    """Load the application factory lazily to keep operational imports acyclic."""
    from pitchvalue.api.app import create_app as app_factory

    if database_factory is None:
        return app_factory(settings=settings)
    return app_factory(settings=settings, database_factory=database_factory)


__all__ = ["create_app"]
