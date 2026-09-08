from __future__ import annotations

import logging
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from fastapi import Query
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from pitchvalue.api.app import create_app
from pitchvalue.api.database import DatabaseResource
from pitchvalue.api.errors import ApiError, ErrorCode
from pitchvalue.config import ConfigurationError, Settings, load_settings


class FakeDatabase:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.started = False
        self.disposed = False
        self.checks = 0

    def start(self) -> None:
        self.started = True

    def check(self) -> None:
        self.checks += 1
        if self.failure is not None:
            raise self.failure

    def dispose(self) -> None:
        self.disposed = True


def api_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql+psycopg://user:secret@localhost/pitchvalue",
        "environment_name": "test",
        "api_host": "127.0.0.1",
        "api_port": 8000,
        "cors_allowed_origins": ("http://localhost:8081",),
        "log_level": "INFO",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def client_for(
    database: FakeDatabase | None = None,
    *,
    settings: Settings | None = None,
    raise_server_exceptions: bool = True,
) -> Iterator[tuple[TestClient, FakeDatabase]]:
    resource = database or FakeDatabase()
    application = create_app(settings or api_settings(), lambda _: resource)
    with TestClient(application, raise_server_exceptions=raise_server_exceptions) as client:
        yield client, resource


def test_application_factory_creates_configured_app() -> None:
    application = create_app(api_settings(), lambda _: FakeDatabase())

    assert application.title == "PitchValue API"
    assert application.version == "1.0.0"
    assert application.debug is False


def test_application_construction_does_not_create_database_engine() -> None:
    engine = Mock(spec=Engine)
    engine_factory = Mock(return_value=engine)
    settings = api_settings()
    database = DatabaseResource(settings.database_url, engine_factory)

    application = create_app(settings, lambda _: database)

    engine_factory.assert_not_called()
    with TestClient(application):
        engine_factory.assert_called_once()
    engine.dispose.assert_called_once()


def test_health_returns_small_success_response() -> None:
    for client, _ in client_for():
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_does_not_check_unavailable_database() -> None:
    database = FakeDatabase(failure=RuntimeError("database unavailable"))
    for client, _ in client_for(database):
        response = client.get("/health")

    assert response.status_code == 200
    assert database.checks == 0


def test_ready_returns_success_when_database_is_available() -> None:
    database = FakeDatabase()
    for client, _database in client_for(database):
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert database.checks == 1


def test_ready_returns_service_unavailable_when_database_fails() -> None:
    database = FakeDatabase(failure=RuntimeError("connection failed"))
    for client, _ in client_for(database):
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_readiness_does_not_leak_database_error_details() -> None:
    secret = "postgresql+psycopg://admin:do-not-leak@example.invalid/private"
    database = FakeDatabase(failure=RuntimeError(secret))
    for client, _ in client_for(database):
        response = client.get("/ready")

    body = response.text
    assert "do-not-leak" not in body
    assert "example.invalid" not in body
    assert "Service is not ready" in body


def test_readiness_failure_log_does_not_expose_database_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "postgresql+psycopg://admin:do-not-log@example.invalid/private"
    database = FakeDatabase(failure=RuntimeError(secret))
    with caplog.at_level(logging.WARNING):
        for client, _ in client_for(database):
            client.get("/ready")

    assert "database readiness check failed" in caplog.text
    assert "do-not-log" not in caplog.text
    assert "example.invalid" not in caplog.text


def test_response_contains_generated_request_id() -> None:
    for client, _ in client_for():
        response = client.get("/health")

    assert len(response.headers["X-Request-ID"]) == 32
    assert response.json() == {"status": "ok"}


def test_valid_supplied_request_id_is_preserved() -> None:
    for client, _ in client_for():
        response = client.get("/health", headers={"X-Request-ID": "mobile.dev-42"})

    assert response.headers["X-Request-ID"] == "mobile.dev-42"


@pytest.mark.parametrize("request_id", ["x" * 129, "contains spaces", "line\nbreak"])
def test_invalid_request_id_is_replaced(request_id: str) -> None:
    for client, _ in client_for():
        response = client.get("/health", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] != request_id
    assert len(response.headers["X-Request-ID"]) == 32


def test_unknown_route_uses_controlled_error() -> None:
    for client, _ in client_for():
        response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_validation_error_uses_controlled_envelope() -> None:
    application = create_app(api_settings(), lambda _: FakeDatabase())

    @application.get("/_test/validated")
    def validated(limit: int = Query(ge=1, le=10)) -> dict[str, int]:
        return {"limit": limit}

    with TestClient(application) as client:
        response = client.get("/_test/validated?limit=not-an-int")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "input" not in response.text


def test_application_error_uses_controlled_envelope() -> None:
    application = create_app(api_settings(), lambda _: FakeDatabase())

    @application.get("/_test/application-error")
    def application_error() -> None:
        raise ApiError(503, ErrorCode.SERVICE_UNAVAILABLE, "Temporarily unavailable")

    with TestClient(application) as client:
        response = client.get("/_test/application-error")

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Temporarily unavailable"


def test_unexpected_error_uses_safe_internal_envelope(
    caplog: pytest.LogCaptureFixture,
) -> None:
    application = create_app(api_settings(), lambda _: FakeDatabase())

    @application.get("/_test/unexpected")
    def unexpected() -> None:
        raise RuntimeError("private internal detail")

    with (
        caplog.at_level(logging.ERROR),
        TestClient(application, raise_server_exceptions=False) as client,
    ):
        response = client.get("/_test/unexpected")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "private internal detail" not in response.text
    assert "unhandled server exception" in caplog.text
    assert "private internal detail" not in caplog.text


def test_production_errors_do_not_include_tracebacks() -> None:
    application = create_app(api_settings(environment_name="production"), lambda _: FakeDatabase())

    @application.get("/_test/production-error")
    def production_error() -> None:
        raise RuntimeError("production secret")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/_test/production-error")

    assert "Traceback" not in response.text
    assert "production secret" not in response.text


def test_allowed_cors_origin_receives_permission() -> None:
    for client, _ in client_for():
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:8081",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8081"
    assert response.headers.get("Access-Control-Allow-Credentials") is None


def test_unapproved_cors_origin_receives_no_permission() -> None:
    for client, _ in client_for():
        response = client.get("/health", headers={"Origin": "https://unapproved.invalid"})

    assert "Access-Control-Allow-Origin" not in response.headers


def test_database_resource_is_started_during_lifespan() -> None:
    database = FakeDatabase()
    application = create_app(api_settings(), lambda _: database)
    assert database.started is False

    with TestClient(application):
        assert database.started is True


def test_database_resource_is_disposed_after_lifespan() -> None:
    database = FakeDatabase()
    application = create_app(api_settings(), lambda _: database)

    with TestClient(application):
        assert database.disposed is False

    assert database.disposed is True


def test_backend_settings_load_safe_defaults() -> None:
    settings = load_settings(
        {"DATABASE_URL": "postgresql+psycopg://user:secret@localhost/pitchvalue"}
    )

    assert settings.environment_name == "development"
    assert settings.api_port == 8000
    assert settings.log_level == "INFO"


def test_settings_repr_never_exposes_database_password() -> None:
    settings = api_settings()

    assert "secret" not in repr(settings)
    assert "<redacted>" in repr(settings)


def test_wildcard_cors_origin_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="CORS_ALLOWED_ORIGINS"):
        load_settings(
            {
                "DATABASE_URL": "postgresql+psycopg://localhost/pitchvalue",
                "CORS_ALLOWED_ORIGINS": "*",
            }
        )


def test_openapi_generation_succeeds() -> None:
    application = create_app(api_settings(), lambda _: FakeDatabase())

    schema = application.openapi()

    assert schema["info"]["title"] == "PitchValue API"
    assert schema["info"]["version"] == "1.0.0"
    assert "/health" in schema["paths"]
    assert "/ready" in schema["paths"]


def test_v1_router_exposes_only_version_metadata() -> None:
    for client, _ in client_for():
        response = client.get("/api/v1")

    assert response.status_code == 200
    assert response.json() == {"version": "v1"}


def test_no_football_business_routes_exist() -> None:
    application = create_app(api_settings(), lambda _: FakeDatabase())
    paths = {path for route in application.routes if (path := getattr(route, "path", None))}

    assert not paths.intersection(
        {"/api/v1/matches", "/api/v1/predictions", "/api/v1/odds", "/api/v1/subscriptions"}
    )
