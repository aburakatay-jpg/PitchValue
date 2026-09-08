"""Lifespan-managed SQLAlchemy Core database resource."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from sqlalchemy import Engine, create_engine, text

from pitchvalue.config import Settings

EngineFactory = Callable[..., Engine]


class DatabaseResourceProtocol(Protocol):
    """Interface used by routes and deterministic test replacements."""

    def start(self) -> None: ...

    def check(self) -> None: ...

    def dispose(self) -> None: ...


class DatabaseResource:
    """Own one pooled engine for the application lifespan."""

    def __init__(self, database_url: str, engine_factory: EngineFactory = create_engine) -> None:
        self._database_url = database_url
        self._engine_factory = engine_factory
        self._engine: Engine | None = None

    @property
    def initialized(self) -> bool:
        return self._engine is not None

    def start(self) -> None:
        if self._engine is None:
            self._engine = self._engine_factory(
                self._database_url,
                pool_pre_ping=True,
                pool_recycle=1800,
            )

    def check(self) -> None:
        if self._engine is None:
            raise RuntimeError("database resource is not initialized")
        with self._engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None


DatabaseFactory = Callable[[Settings], DatabaseResourceProtocol]


def create_database(settings: Settings) -> DatabaseResource:
    """Build an unstarted resource without opening a database connection."""
    return DatabaseResource(settings.database_url)
