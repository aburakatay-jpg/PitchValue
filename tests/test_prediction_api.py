from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, text

from pitchvalue.api.app import create_app
from pitchvalue.api.database import DatabaseResource
from pitchvalue.config import load_settings
from pitchvalue.prediction.persistence import PredictionPersistenceRequest
from pitchvalue.prediction.repository import invalidate_prediction, persist_match_prediction
from test_prediction_repository import GENERATED, _request

D = Decimal


@pytest.fixture(scope="session")
def api_engine() -> Engine:
    return create_engine(load_settings(os.environ).database_url)


@pytest.fixture(autouse=True)
def clean_prediction_snapshots(api_engine: Engine) -> Iterator[None]:
    with api_engine.begin() as connection:
        _clean_fixture_data(connection)
    yield
    with api_engine.begin() as connection:
        _clean_fixture_data(connection)


def _clean_fixture_data(connection: Connection) -> None:
    connection.execute(text("DELETE FROM prediction_snapshots"))
    connection.execute(
        text(
            """DELETE FROM match_provider_refs
            WHERE provider_id IN (
                SELECT provider_id FROM providers WHERE name = 'TASK 21 fixture provider'
            )"""
        )
    )
    connection.execute(
        text(
            """DELETE FROM football_data_staging_rows
            WHERE import_batch_id IN (
                SELECT import_batch_id FROM import_batches
                WHERE provider_id IN (
                    SELECT provider_id FROM providers WHERE name = 'TASK 21 fixture provider'
                )
            )"""
        )
    )
    connection.execute(
        text(
            """DELETE FROM import_batches
            WHERE provider_id IN (
                SELECT provider_id FROM providers WHERE name = 'TASK 21 fixture provider'
            )"""
        )
    )
    connection.execute(
        text(
            """DELETE FROM matches
            WHERE competition_id IN (
                SELECT competition_id FROM competitions
                WHERE canonical_name = 'TASK 21 Competition'
            )"""
        )
    )
    connection.execute(
        text(
            """DELETE FROM seasons
            WHERE competition_id IN (
                SELECT competition_id FROM competitions
                WHERE canonical_name = 'TASK 21 Competition'
            )"""
        )
    )
    connection.execute(
        text("DELETE FROM competitions WHERE canonical_name = 'TASK 21 Competition'")
    )
    connection.execute(
        text("DELETE FROM teams WHERE canonical_name IN ('TASK 21 Team 1', 'TASK 21 Team 2')")
    )
    connection.execute(text("DELETE FROM providers WHERE name = 'TASK 21 fixture provider'"))


@pytest.fixture
def client(api_engine: Engine) -> Iterator[TestClient]:
    settings = load_settings(os.environ)
    application = create_app(settings, lambda _: DatabaseResource(settings.database_url))
    with TestClient(application) as test_client:
        yield test_client


def _persist(
    engine: Engine,
    *,
    generated_at: datetime = GENERATED,
    **kwargs: object,
) -> PredictionPersistenceRequest:
    with engine.begin() as connection:
        request = _request(connection, **kwargs)
        request = replace(request, generated_at=generated_at)
        persist_match_prediction(connection, request)
        return request


def test_published_predictions_empty_state(client: TestClient) -> None:
    response = client.get("/api/v1/predictions")
    assert response.status_code == 200
    assert response.json() == {"predictions": [], "count": 0}


def test_match_predictions_returns_current_published_rows_in_stable_order(
    client: TestClient, api_engine: Engine
) -> None:
    request = _persist(
        api_engine,
        exact=True,
        publication_eligible=True,
        bet_score=D("80.125"),
    )
    response = client.get(f"/api/v1/matches/{request.decision.match_id}/predictions")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    assert [item["selection"] for item in body["predictions"]] == ["away", "draw", "home"]
    assert all(item["publication_eligible"] for item in body["predictions"])
    assert body["predictions"][0]["bet_score"] == "80.125"


def test_public_response_preserves_decimals_timestamps_and_stable_statuses(
    client: TestClient, api_engine: Engine
) -> None:
    request = _persist(
        api_engine,
        exact=True,
        publication_eligible=True,
        bet_score=D("80"),
    )
    response = client.get(f"/api/v1/matches/{request.decision.match_id}/predictions")
    item = response.json()["predictions"][0]
    assert item["model_probability"] in {"0.20", "0.30", "0.50"}
    assert item["decimal_odds"] in {"2.10", "3.40", "4.20"}
    assert item["edge"] in {"-0.05", "0.00", "0.05"}
    assert item["prediction_as_of"] == "2026-01-02T12:00:00Z"
    assert item["generated_at"] == "2026-01-02T12:01:00Z"
    assert item["market_observed_at"] == "2026-01-02T11:55:00Z"
    assert item["comparison_status"] == "EXACT_TIME_COMPARISON"
    assert item["bet_score_completeness"] == "COMPLETE"


def test_nullable_bet_score_remains_null(client: TestClient, api_engine: Engine) -> None:
    request = _persist(api_engine, exact=True, publication_eligible=True, bet_score=None)
    response = client.get(f"/api/v1/matches/{request.decision.match_id}/predictions")
    assert response.status_code == 200
    assert all(item["bet_score"] is None for item in response.json()["predictions"])
    assert all(
        item["bet_score_completeness"] == "PARTIAL" for item in response.json()["predictions"]
    )


def test_role_only_records_never_appear_as_public_predictions(
    client: TestClient, api_engine: Engine
) -> None:
    request = _persist(api_engine, exact=False, publication_eligible=False)
    assert client.get("/api/v1/predictions").json()["count"] == 0
    assert (
        client.get(f"/api/v1/matches/{request.decision.match_id}/predictions").json()["count"] == 0
    )


@pytest.mark.parametrize("superseded", [False, True])
def test_invalidated_and_superseded_rows_are_excluded(
    client: TestClient,
    api_engine: Engine,
    superseded: bool,
) -> None:
    request = _persist(api_engine, exact=True, publication_eligible=True, bet_score=D("80"))
    with api_engine.begin() as connection:
        rows = connection.execute(
            text(
                "SELECT prediction_snapshot_id FROM prediction_snapshots WHERE match_id = :match_id"
            ),
            {"match_id": int(request.decision.match_id)},
        ).scalars()
        for prediction_id in rows:
            assert invalidate_prediction(
                connection,
                prediction_id,
                invalidated_at=datetime(2026, 1, 3, tzinfo=UTC),
                reason="API_TEST_SUPERSESSION" if superseded else "API_TEST_INVALIDATION",
                superseded=superseded,
            )
    assert client.get("/api/v1/predictions").json()["count"] == 0


def test_repository_drives_current_model_version(client: TestClient, api_engine: Engine) -> None:
    old = _persist(
        api_engine,
        generated_at=GENERATED,
        model_version="model-v1",
        exact=True,
        publication_eligible=True,
        bet_score=D("80"),
    )
    _persist(
        api_engine,
        generated_at=GENERATED + timedelta(minutes=1),
        model_version="model-v2",
        exact=True,
        publication_eligible=True,
        bet_score=D("80"),
    )
    response = client.get(f"/api/v1/matches/{old.decision.match_id}/predictions")
    assert response.json()["count"] == 3
    assert {item["model_version"] for item in response.json()["predictions"]} == {"model-v2"}


def test_newer_nonpublishable_version_does_not_fall_back_to_old_publication(
    client: TestClient, api_engine: Engine
) -> None:
    old = _persist(
        api_engine,
        generated_at=GENERATED,
        model_version="model-v1",
        exact=True,
        publication_eligible=True,
        bet_score=D("80"),
    )
    _persist(
        api_engine,
        generated_at=GENERATED + timedelta(minutes=1),
        model_version="model-v2",
        exact=False,
        publication_eligible=False,
    )
    assert client.get("/api/v1/predictions").json()["count"] == 0
    assert client.get(f"/api/v1/matches/{old.decision.match_id}/predictions").json()["count"] == 0


def test_published_endpoint_supports_fixture_set_filter(
    client: TestClient, api_engine: Engine
) -> None:
    request = _persist(api_engine, exact=True, publication_eligible=True, bet_score=D("80"))
    match_id = int(request.decision.match_id)
    assert client.get(f"/api/v1/predictions?match_id={match_id}").json()["count"] == 3
    assert client.get("/api/v1/predictions?match_id=999999999").json()["count"] == 0


def test_public_response_excludes_internal_storage_and_lineage_fields(
    client: TestClient, api_engine: Engine
) -> None:
    _persist(api_engine, exact=True, publication_eligible=True, bet_score=D("80"))
    item = client.get("/api/v1/predictions").json()["predictions"][0]
    assert not {
        "prediction_snapshot_id",
        "payload_hash",
        "source_staging_row_id",
        "source_match_provider_ref_id",
        "invalidation_reason",
    }.intersection(item)


def test_persisted_read_succeeds_when_orchestration_execution_is_disabled(
    client: TestClient,
    api_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _persist(api_engine, exact=True, publication_eligible=True, bet_score=D("80"))

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("orchestration must not run during API reads")

    monkeypatch.setattr("pitchvalue.prediction.orchestration.orchestrate_match", forbidden)
    response = client.get("/api/v1/predictions")
    assert response.status_code == 200
    assert response.json()["count"] == 3


def test_prediction_routes_are_read_only_and_documented_in_openapi(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/predictions" in paths
    assert "/api/v1/matches/{match_id}/predictions" in paths
    assert set(paths["/api/v1/predictions"]) == {"get"}
    assert set(paths["/api/v1/matches/{match_id}/predictions"]) == {"get"}


def test_prediction_query_validation_uses_existing_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/predictions?limit=101")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
