"""FastAPI dependencies for application-managed resources."""

from fastapi import Request

from pitchvalue.api.database import DatabaseResourceProtocol


def get_database(request: Request) -> DatabaseResourceProtocol:
    """Return the database resource created by the active lifespan."""
    database: DatabaseResourceProtocol = request.app.state.database
    return database
