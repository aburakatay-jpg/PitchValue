"""Lifespan-managed SQLAlchemy Core database resource."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol

from sqlalchemy import Connection, Engine, create_engine, text

from pitchvalue.config import Settings

EngineFactory = Callable[..., Engine]
EXPECTED_ALEMBIC_REVISION = "9c7c56a20a35"


class DatabaseResourceProtocol(Protocol):
    """Interface used by routes and deterministic test replacements."""

    def start(self) -> None: ...

    def check(self) -> None: ...

    def connect(self) -> AbstractContextManager[Connection]: ...

    def transaction(self) -> AbstractContextManager[Connection]: ...

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
                pool_timeout=5,
            )

    def check(self) -> None:
        if self._engine is None:
            raise RuntimeError("database resource is not initialized")
        with self._engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            if revision != EXPECTED_ALEMBIC_REVISION:
                raise RuntimeError("database schema revision is not ready")
            table = connection.execute(
                text("SELECT to_regclass('public.prediction_snapshots')")
            ).scalar_one()
            if table is None:
                raise RuntimeError("prediction persistence schema is unavailable")
            connection.execute(text("SELECT 1 FROM prediction_snapshots LIMIT 1"))

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        """Provide one read transaction boundary for an API request."""
        if self._engine is None:
            raise RuntimeError("database resource is not initialized")
        with self._engine.connect() as connection:
            yield connection

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """Provide one committed write transaction for product-service commands."""
        if self._engine is None:
            raise RuntimeError("database resource is not initialized")
        with self._engine.begin() as connection:
            yield connection

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None


DatabaseFactory = Callable[[Settings], DatabaseResourceProtocol]


def create_database(settings: Settings) -> DatabaseResource:
    """Build an unstarted resource without opening a database connection."""
    return DatabaseResource(settings.database_url)
