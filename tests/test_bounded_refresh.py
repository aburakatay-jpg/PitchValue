from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, text

from pitchvalue.api.app import create_app
from pitchvalue.api.database import DatabaseResource
from pitchvalue.config import load_settings
from test_prediction_api import _clean_fixture_data
from test_prediction_repository import _request


@pytest.fixture(scope="session")
def fixture_api_engine() -> Engine:
    return create_engine(load_settings(os.environ).database_url)


@pytest.fixture(autouse=True)
def clean_fixture_api_data(fixture_api_engine: Engine) -> Iterator[None]:
    with fixture_api_engine.begin() as connection:
        _clean_extended(connection)
    yield
    with fixture_api_engine.begin() as connection:
        _clean_extended(connection)


@pytest.fixture
def fixture_client(fixture_api_engine: Engine) -> Iterator[TestClient]:
    settings = load_settings(os.environ)
    app = create_app(settings, lambda _: DatabaseResource(settings.database_url))
    with TestClient(app) as client:
        yield client


def _clean_extended(connection: Connection) -> None:
    connection.execute(text("DELETE FROM shadow_analysis_snapshots"))
    connection.execute(text("DELETE FROM match_statistics"))
    connection.execute(text("DELETE FROM engine_runs"))
    _clean_fixture_data(connection)


def _fixture(engine: Engine, *, kickoff: datetime, finished: bool = False) -> int:
    with engine.begin() as connection:
        request = _request(connection, exact=True, publication_eligible=False, bet_score=None)
        match_id = int(request.decision.match_id)
        connection.execute(
            text(
                "UPDATE matches SET kickoff_at_utc=:kickoff,status=:status WHERE match_id=:match_id"
            ),
            {
                "kickoff": kickoff,
                "status": "FINISHED" if finished else "SCHEDULED",
                "match_id": match_id,
            },
        )
        return match_id


def test_today_executes_exactly_one_provider_fetch_if_stale(
    fixture_client: TestClient, fixture_api_engine: Engine
) -> None:
    from pitchvalue.api.fixtures import _refresh_attempts

    _refresh_attempts.clear()

    kickoff = datetime.now(UTC) - timedelta(minutes=20)
    fixture_date = kickoff.date()
    date_str = fixture_date.isoformat()

    _fixture(fixture_api_engine, kickoff=kickoff, finished=False)

    with fixture_api_engine.begin() as connection:
        count_before = connection.execute(text("SELECT count(*) FROM engine_runs")).scalar()

    with patch(
        "pitchvalue.providers.five_dfa.adapter.FiveDfaFreeAdapter.fixture_payloads"
    ) as mock_payloads:
        mock_payloads.return_value = ([], None)
        response = fixture_client.get(f"/api/v1/fixtures/today?date={date_str}&timezone=UTC")

    assert response.status_code == 200
    mock_payloads.assert_called_once()

    with fixture_api_engine.begin() as connection:
        count_after = connection.execute(text("SELECT count(*) FROM engine_runs")).scalar()
    assert count_before == count_after


def test_today_does_not_fetch_if_within_ttl(
    fixture_client: TestClient, fixture_api_engine: Engine
) -> None:
    from pitchvalue.api.fixtures import _refresh_attempts

    _refresh_attempts.clear()

    kickoff = datetime.now(UTC) - timedelta(minutes=20)
    fixture_date = kickoff.date()
    date_str = fixture_date.isoformat()
    _fixture(fixture_api_engine, kickoff=kickoff, finished=False)

    # Inject process-local TTL
    _refresh_attempts[fixture_date] = datetime.now(UTC)

    with patch(
        "pitchvalue.providers.five_dfa.adapter.FiveDfaFreeAdapter.fixture_payloads"
    ) as mock_payloads:
        response = fixture_client.get(f"/api/v1/fixtures/today?date={date_str}&timezone=UTC")

    assert response.status_code == 200
    mock_payloads.assert_not_called()


def test_today_does_not_fetch_if_not_stale(
    fixture_client: TestClient, fixture_api_engine: Engine
) -> None:
    from pitchvalue.api.fixtures import _refresh_attempts

    _refresh_attempts.clear()

    kickoff = datetime.now(UTC) + timedelta(minutes=20)
    fixture_date = kickoff.date()
    date_str = fixture_date.isoformat()
    _fixture(fixture_api_engine, kickoff=kickoff, finished=False)

    with patch(
        "pitchvalue.providers.five_dfa.adapter.FiveDfaFreeAdapter.fixture_payloads"
    ) as mock_payloads:
        response = fixture_client.get(f"/api/v1/fixtures/today?date={date_str}&timezone=UTC")

    assert response.status_code == 200
    mock_payloads.assert_not_called()
