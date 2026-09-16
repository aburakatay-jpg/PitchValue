"""FastAPI dependencies for application-managed resources."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Connection

from pitchvalue.api.database import DatabaseResourceProtocol
from pitchvalue.api.errors import ApiError, ErrorCode
from pitchvalue.product_services.auth import ProductUser, authenticate_access_token

bearer = HTTPBearer(auto_error=False)


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


def get_transaction(
    database: Annotated[DatabaseResourceProtocol, Depends(get_database)],
) -> Iterator[Connection]:
    """Yield a committed transaction for authenticated product-service writes."""
    with database.transaction() as connection:
        yield connection


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> ProductUser:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "Authentication required")
    user = authenticate_access_token(connection, credentials.credentials)
    if user is None:
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "Session is invalid or expired")
    return user


def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "Authentication required")
    return credentials.credentials
