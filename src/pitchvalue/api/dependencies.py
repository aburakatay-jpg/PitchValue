"""FastAPI dependencies for application-managed resources."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Connection

from pitchvalue.api.database import DatabaseResourceProtocol


def get_database(request: Request) -> DatabaseResourceProtocol:
    """Return the database resource created by the active lifespan."""
    database: DatabaseResourceProtocol = request.app.state.database
    return database


def get_connection(
    database: Annotated[DatabaseResourceProtocol, Depends(get_database)],
) -> Iterator[Connection]:
    """Yield the application-managed connection used by read-only API repositories."""
    with database.connect() as connection:
        yield connection
