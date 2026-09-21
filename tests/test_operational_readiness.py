from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

from pitchvalue.api.app import create_app
from pitchvalue.api.database import EXPECTED_ALEMBIC_REVISION, DatabaseResource
from pitchvalue.config import Settings, load_settings
from pitchvalue.operations.release_validation import validate_release, validate_shadow_activation
from pitchvalue.prediction.persistence import (
    PredictionPersistenceError,
    PredictionPersistenceRequest,
)
from pitchvalue.prediction.repository import (
    invalidate_prediction,
    persist_match_prediction,
    predictions_for_match,
)
from test_prediction_api import _clean_fixture_data
from test_prediction_repository import GENERATED, _request

D = Decimal


@pytest.fixture(scope="session")
def operational_engine() -> Engine:
    return create_engine(load_settings(os.environ).database_url)


@pytest.fixture(autouse=True)
def clean_operational_data(operational_engine: Engine) -> Iterator[None]:
    with operational_engine.begin() as connection:
        _clean_fixture_data(connection)
    yield
    with operational_engine.begin() as connection:
        _clean_fixture_data(connection)


def _app_client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings, lambda _: DatabaseResource(settings.database_url)))


def _persist(
    engine: Engine,
    *,
    generated_at: datetime = GENERATED,
    **kwargs: object,
) -> PredictionPersistenceRequest:
    with engine.begin() as connection:
        request = replace(_request(connection, **kwargs), generated_at=generated_at)
        persist_match_prediction(connection, request)
        return request


class BrokenDatabase:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def start(self) -> None:
        pass

    def check(self) -> None:
        raise RuntimeError(self.secret)

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        raise RuntimeError(self.secret)
        yield  # pragma: no cover

    def dispose(self) -> None:
        pass


@pytest.mark.integration
def test_empty_table_is_ready_and_returns_empty_without_engine_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(os.environ)

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("prediction execution is forbidden during API reads")

    monkeypatch.setattr("pitchvalue.prediction.orchestration.orchestrate_match", forbidden)
    with _app_client(settings) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ready").json() == {"status": "ready"}
        assert client.get("/api/v1/predictions").json() == {"predictions": [], "count": 0}


def test_database_failure_is_not_converted_to_empty_success_or_fake_readiness(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "postgresql+psycopg://operator:never-log@example.invalid/private"
    settings = Settings(database_url=secret)
    database = BrokenDatabase(secret)
    app = create_app(settings, lambda _: database)
    with caplog.at_level(logging.WARNING), TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        ready = client.get("/ready")
        predictions = client.get("/api/v1/predictions")
    assert ready.status_code == 503
    assert ready.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert predictions.status_code == 500
    assert predictions.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "never-log" not in ready.text + predictions.text + caplog.text
    assert "example.invalid" not in ready.text + predictions.text + caplog.text


@pytest.mark.integration
def test_release_validation_reports_current_migration_and_prediction_schema() -> None:
    result = validate_release(load_settings(os.environ))
    assert result.ready
    assert result.database_reachable
    assert result.migration_current
    assert result.prediction_schema_accessible
    assert result.expected_revision == EXPECTED_ALEMBIC_REVISION
    assert result.prediction_snapshot_count == 0
    assert result.failure_code is None


@pytest.mark.integration
def test_shadow_activation_validation_is_complete_read_only_and_fail_closed(
    tmp_path: Path,
) -> None:
    settings = load_settings(os.environ)
    values = dict(os.environ)
    values.update(
        {
            "FIVEDFA_API_KEY": "fake-release-validation-key",
            "SCHEDULER_ENABLED": "false",
            "PUBLICATION_ENABLED": "false",
            "EXTERNAL_ALERTS_ENABLED": "false",
        }
    )
    with create_engine(settings.database_url).begin() as conn:
        _eid = "0000000000000000000000000000000000000000000000000000000000000000"
        _etype = "CURRENT_SEASON_SYNC_SUCCEEDED"
        conn.execute(
            text(
                "INSERT INTO operational_events("
                "event_id, event_type, event_version,"
                " occurred_at, severity, correlation_id,"
                " source_component, metadata,"
                " delivery_visibility, persisted_at) "
                "SELECT :eid, :etype, 1, :now,"
                " 'INFO', 'dummy-correlation', 'TEST',"
                " '{}'::jsonb, 'INTERNAL', :now "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM operational_events"
                " WHERE event_type = :etype)"
            ),
            {
                "now": datetime(2026, 9, 13, tzinfo=UTC),
                "eid": _eid,
                "etype": _etype,
            },
        )
    result = validate_shadow_activation(
        settings,
        values,
        tmp_path,
        now=datetime(2026, 9, 14, tzinfo=UTC),
    )
    assert result.ready
    assert result.current_season_fresh
    assert result.public_eligible_predictions == 0
    assert result.public_shadow_predictions == 0
    blocked = validate_shadow_activation(
        settings,
        {**values, "PUBLICATION_ENABLED": "true"},
        tmp_path,
        now=datetime(2026, 9, 14, tzinfo=UTC),
    )
    assert not blocked.ready
    assert "PUBLICATION_MUST_REMAIN_DISABLED" in blocked.reasons


@pytest.mark.integration
def test_migration_mismatch_fails_readiness_and_release_validation(
    operational_engine: Engine,
) -> None:
    settings = load_settings(os.environ)
    with operational_engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = '20260910_0007'"))
    try:
        with _app_client(settings) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 503
        result = validate_release(settings)
        assert not result.ready
        assert result.database_reachable
        assert not result.migration_current
        assert result.failure_code == "MIGRATION_NOT_CURRENT"
    finally:
        with operational_engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": EXPECTED_ALEMBIC_REVISION},
            )


@pytest.mark.integration
def test_exact_time_golden_path_survives_application_restart(
    operational_engine: Engine,
) -> None:
    settings = load_settings(os.environ)
    request = _persist(
        operational_engine,
        exact=True,
        publication_eligible=True,
        bet_score=D("80.125"),
    )
    url = f"/api/v1/matches/{request.decision.match_id}/predictions"
    with _app_client(settings) as first_client:
        first = first_client.get(url)
    with _app_client(settings) as restarted_client:
        second = restarted_client.get(url)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert second.json()["count"] == 3
    assert {row["comparison_status"] for row in second.json()["predictions"]} == {
        "EXACT_TIME_COMPARISON"
    }
    assert {row["bet_score"] for row in second.json()["predictions"]} == {"80.125"}


@pytest.mark.integration
def test_role_only_and_null_score_evidence_remains_non_public(
    operational_engine: Engine,
) -> None:
    settings = load_settings(os.environ)
    request = _persist(
        operational_engine,
        exact=False,
        publication_eligible=False,
        bet_score=None,
    )
    with operational_engine.connect() as connection:
        history = predictions_for_match(connection, int(request.decision.match_id))
    assert len(history) == 3
    assert all(row.bet_score is None for row in history)
    assert all(row.comparison_status == "ROLE_ONLY_COMPARISON" for row in history)
    with _app_client(settings) as client:
        assert client.get("/api/v1/predictions").json()["count"] == 0


@pytest.mark.integration
def test_invalidation_hides_public_rows_but_retains_history(
    operational_engine: Engine,
) -> None:
    settings = load_settings(os.environ)
    request = _persist(
        operational_engine,
        exact=True,
        publication_eligible=True,
        bet_score=D("80"),
    )
    url = f"/api/v1/matches/{request.decision.match_id}/predictions"
    with _app_client(settings) as client:
        assert client.get(url).json()["count"] == 3
        with operational_engine.begin() as connection:
            ids = connection.execute(
                text(
                    "SELECT prediction_snapshot_id FROM prediction_snapshots "
                    "WHERE match_id = :match_id"
                ),
                {"match_id": int(request.decision.match_id)},
            ).scalars()
            for prediction_id in ids:
                assert invalidate_prediction(
                    connection,
                    int(prediction_id),
                    invalidated_at=datetime(2026, 1, 3, tzinfo=UTC),
                    reason="OPERATIONAL_TEST_INVALIDATION",
                )
        assert client.get(url).json()["count"] == 0
    with operational_engine.connect() as connection:
        history = predictions_for_match(connection, int(request.decision.match_id))
    assert len(history) == 3
    assert all(row.record_status.value == "invalidated" for row in history)


@pytest.mark.integration
def test_new_noneligible_version_suppresses_stale_eligible_version(
    operational_engine: Engine,
) -> None:
    settings = load_settings(os.environ)
    old = _persist(
        operational_engine,
        model_version="operational-v1",
        exact=True,
        publication_eligible=True,
        bet_score=D("80"),
    )
    _persist(
        operational_engine,
        generated_at=GENERATED + timedelta(minutes=1),
        model_version="operational-v2",
        exact=False,
        publication_eligible=False,
    )
    with _app_client(settings) as client:
        response = client.get(f"/api/v1/matches/{old.decision.match_id}/predictions")
    assert response.status_code == 200
    assert response.json()["count"] == 0


@pytest.mark.integration
def test_failed_new_version_is_atomic_and_prior_version_remains_public(
    operational_engine: Engine,
) -> None:
    settings = load_settings(os.environ)
    old = _persist(
        operational_engine,
        model_version="prior-valid-v1",
        exact=True,
        publication_eligible=True,
        bet_score=D("80"),
    )
    with pytest.raises(IntegrityError), operational_engine.begin() as connection:
        request = _request(
            connection,
            model_version="failed-v2",
            exact=True,
            publication_eligible=True,
            bet_score=D("80"),
        )
        decisions = list(request.decision.selection_decisions)
        decisions[-1] = replace(decisions[-1], decimal_odds=D("1"))
        broken = replace(request.decision, selection_decisions=tuple(decisions))
        persist_match_prediction(connection, PredictionPersistenceRequest(broken, GENERATED))
    with _app_client(settings) as client:
        response = client.get(f"/api/v1/matches/{old.decision.match_id}/predictions")
    assert response.json()["count"] == 3
    assert {row["model_version"] for row in response.json()["predictions"]} == {"prior-valid-v1"}
    with operational_engine.connect() as connection:
        assert not [
            row
            for row in predictions_for_match(connection, int(old.decision.match_id))
            if row.model_version == "failed-v2"
        ]


@pytest.mark.integration
def test_concurrent_identical_writes_create_one_semantic_prediction_set(
    operational_engine: Engine,
) -> None:
    with operational_engine.begin() as connection:
        request = _request(
            connection,
            model_version="concurrent-v1",
            exact=True,
            publication_eligible=True,
            bet_score=D("80"),
        )

    def persist_once() -> tuple[int, int]:
        with operational_engine.begin() as connection:
            result = persist_match_prediction(connection, request)
            return result.created, result.unchanged

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: persist_once(), range(2)))
    assert sorted(results) == [(0, 3), (3, 0)]
    with operational_engine.connect() as connection:
        rows = predictions_for_match(connection, int(request.decision.match_id))
    assert len(rows) == 3


@pytest.mark.integration
def test_conflicting_write_is_rejected_without_corrupting_existing_payload(
    operational_engine: Engine,
) -> None:
    with operational_engine.begin() as connection:
        request = _request(connection, model_version="conflict-v1")
        persist_match_prediction(connection, request)
    changed = replace(
        request.decision.selection_decisions[0],
        model_probability=D("0.49"),
    )
    conflict = replace(
        request.decision,
        selection_decisions=(changed, *request.decision.selection_decisions[1:]),
    )
    with pytest.raises(PredictionPersistenceError), operational_engine.begin() as connection:
        persist_match_prediction(connection, PredictionPersistenceRequest(conflict, GENERATED))
    with operational_engine.connect() as connection:
        rows = predictions_for_match(connection, int(request.decision.match_id))
    assert len(rows) == 3
    assert {row.model_probability for row in rows} == {D("0.20"), D("0.30"), D("0.50")}


@pytest.mark.integration
def test_concurrent_reads_are_deterministic_and_do_not_mutate_state(
    operational_engine: Engine,
) -> None:
    request = _persist(
        operational_engine,
        exact=True,
        publication_eligible=True,
        bet_score=D("80"),
    )
    settings = load_settings(os.environ)
    url = f"/api/v1/matches/{request.decision.match_id}/predictions"

    def read_once() -> dict[str, object]:
        with _app_client(settings) as client:
            return client.get(url).json()

    with ThreadPoolExecutor(max_workers=4) as executor:
        payloads = list(executor.map(lambda _: read_once(), range(8)))
    assert all(payload == payloads[0] for payload in payloads)
    with operational_engine.connect() as connection:
        count = connection.execute(text("SELECT count(*) FROM prediction_snapshots")).scalar_one()
    assert count == 3


def test_database_readiness_constant_is_the_committed_schema_head() -> None:
    assert EXPECTED_ALEMBIC_REVISION == "3af5899142ab"
