from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, text

from pitchvalue.api.app import create_app
from pitchvalue.api.database import DatabaseResource
from pitchvalue.api.fixture_models import DataAvailabilityState, PublicMarketState
from pitchvalue.api.fixtures import market_availability, today_fixtures
from pitchvalue.config import load_settings
from pitchvalue.prediction.repository import persist_match_prediction
from test_prediction_api import _clean_fixture_data
from test_prediction_repository import GENERATED, _request


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
    connection.execute(
        text(
            """DELETE FROM shadow_analysis_snapshots WHERE match_id IN (
            SELECT match_id FROM matches WHERE competition_id IN (
                SELECT competition_id FROM competitions
                WHERE canonical_name='TASK 21 Competition'))"""
        )
    )
    connection.execute(
        text(
            """DELETE FROM match_statistics WHERE match_id IN (
            SELECT match_id FROM matches WHERE competition_id IN (
                SELECT competition_id FROM competitions
                WHERE canonical_name='TASK 21 Competition'))"""
        )
    )
    _clean_fixture_data(connection)


def _fixture(
    engine: Engine,
    *,
    kickoff: datetime,
    finished: bool = False,
    public: bool = False,
    complete_score: bool = True,
) -> int:
    with engine.begin() as connection:
        request = _request(
            connection,
            exact=True,
            publication_eligible=public,
            bet_score=Decimal("80") if complete_score else None,
        )
        match_id = int(request.decision.match_id)
        connection.execute(
            text(
                """UPDATE matches SET kickoff_at_utc=:kickoff,status=:status,
                home_score=:home,away_score=:away,result=:result WHERE match_id=:match_id"""
            ),
            {
                "kickoff": kickoff,
                "status": "FINISHED" if finished else "SCHEDULED",
                "home": 2 if finished else None,
                "away": 1 if finished else None,
                "result": "H" if finished else None,
                "match_id": match_id,
            },
        )
        if public:
            persist_match_prediction(
                connection,
                replace(request, generated_at=GENERATED),
            )
        return match_id


def _second_fixture(engine: Engine, kickoff: datetime) -> int:
    with engine.begin() as connection:
        first = _request(connection)
        match_id = connection.execute(
            text(
                """INSERT INTO matches (
                competition_id,season_id,home_team_id,away_team_id,kickoff_at_utc,status
                ) SELECT competition_id,season_id,away_team_id,home_team_id,:kickoff,'SCHEDULED'
                FROM matches WHERE match_id=:first RETURNING match_id"""
            ),
            {"kickoff": kickoff, "first": int(first.decision.match_id)},
        ).scalar_one()
        return int(match_id)


def test_today_lists_fixtures_chronologically_without_requiring_public_pick(
    fixture_client: TestClient, fixture_api_engine: Engine
) -> None:
    later = _fixture(fixture_api_engine, kickoff=datetime(2100, 1, 2, 15, tzinfo=UTC))
    earlier = _second_fixture(fixture_api_engine, datetime(2100, 1, 2, 10, tzinfo=UTC))
    response = fixture_client.get("/api/v1/fixtures/today?date=2100-01-02&timezone=UTC")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "FIXTURES_AVAILABLE"
    assert [item["match_id"] for item in body["fixtures"]] == [earlier, later]
    assert all(item["public_analysis"] == "NO_PUBLIC_ANALYSIS" for item in body["fixtures"])
    assert all(item["final_check"] == "FINAL_CHECK_UNAVAILABLE" for item in body["fixtures"])


def test_today_empty_state_is_success(fixture_client: TestClient) -> None:
    response = fixture_client.get("/api/v1/fixtures/today?date=2098-01-01&timezone=UTC")
    assert response.status_code == 200
    assert response.json()["state"] == "NO_FIXTURES"
    assert response.json()["fixtures"] == []


def test_today_returns_final_score_if_finished(
    fixture_client: TestClient, fixture_api_engine: Engine
) -> None:
    match_id = _fixture(
        fixture_api_engine,
        kickoff=datetime(2100, 1, 3, 10, tzinfo=UTC),
        finished=True,
    )
    scheduled_id = _second_fixture(
        fixture_api_engine,
        kickoff=datetime(2100, 1, 3, 15, tzinfo=UTC),
    )
    response = fixture_client.get("/api/v1/fixtures/today?date=2100-01-03&timezone=UTC")
    assert response.status_code == 200
    body = response.json()
    fixtures = {item["match_id"]: item for item in body["fixtures"]}
    
    finished_fixture = fixtures[match_id]
    assert finished_fixture["fixture_status"] == "FINISHED"
    assert finished_fixture["home_score"] == 2
    assert finished_fixture["away_score"] == 1
    
    scheduled_fixture = fixtures[scheduled_id]
    assert scheduled_fixture["fixture_status"] == "SCHEDULED"
    assert scheduled_fixture["home_score"] is None
    assert scheduled_fixture["away_score"] is None


def test_match_detail_returns_legitimate_final_score_and_statistics(
    fixture_client: TestClient, fixture_api_engine: Engine
) -> None:
    match_id = _fixture(
        fixture_api_engine,
        kickoff=datetime(2100, 1, 2, 10, tzinfo=UTC),
        finished=True,
    )
    with fixture_api_engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO match_statistics (
                match_id,home_shots,away_shots,home_shots_on_target,away_shots_on_target,
                home_possession,away_possession,home_corners,away_corners
                ) VALUES (:match_id,12,8,5,3,55.5,44.5,7,2)"""
            ),
            {"match_id": match_id},
        )
    body = fixture_client.get(f"/api/v1/matches/{match_id}").json()
    assert body["score"] == {"home": 2, "away": 1, "result": "H"}
    assert body["statistics_state"] == "AVAILABLE"
    assert body["statistics"]["home_possession"] == "55.50"
    assert body["public_analysis"] == "NO_PUBLIC_ANALYSIS"
    assert body["public_predictions"] == []


def test_match_detail_missing_statistics_is_normal_data_insufficient_state(
    fixture_client: TestClient, fixture_api_engine: Engine
) -> None:
    match_id = _fixture(fixture_api_engine, kickoff=datetime(2100, 1, 2, tzinfo=UTC))
    body = fixture_client.get(f"/api/v1/matches/{match_id}").json()
    assert body["statistics"] is None
    assert body["statistics_state"] == "DATA_INSUFFICIENT"
    assert body["public_analysis"] == "NO_PUBLIC_ANALYSIS"


def test_public_prediction_and_final_check_are_separate_sections(
    fixture_client: TestClient, fixture_api_engine: Engine
) -> None:
    match_id = _fixture(
        fixture_api_engine,
        kickoff=datetime(2100, 1, 2, tzinfo=UTC),
        public=True,
    )
    body = fixture_client.get(f"/api/v1/matches/{match_id}").json()
    assert body["public_analysis"] == "AVAILABLE_PUBLIC"
    assert body["publication_state"] == "PICK"
    assert body["final_check"] == "FINAL_CHECK_UNAVAILABLE"
    assert len(body["public_predictions"]) == 3
    assert body["markets"][0]["state"] == "AVAILABLE_PUBLIC"


def test_score_incomplete_is_null_and_explicit(
    fixture_client: TestClient, fixture_api_engine: Engine
) -> None:
    match_id = _fixture(
        fixture_api_engine,
        kickoff=datetime(2100, 1, 2, tzinfo=UTC),
        public=True,
        complete_score=False,
    )
    market = fixture_client.get(f"/api/v1/matches/{match_id}").json()["markets"][0]
    assert market["state"] == "SCORE_INCOMPLETE"
    assert market["score"] is None
    assert market["score_completeness"] == "PARTIAL"


def test_market_contract_can_express_data_insufficient_without_fake_numbers() -> None:
    markets = market_availability((), fallback_state=PublicMarketState.DATA_INSUFFICIENT)
    assert len(markets) == 9
    assert all(item.state is PublicMarketState.DATA_INSUFFICIENT for item in markets)
    assert all(item.score is None for item in markets)


def test_stale_metadata_uses_persisted_evidence_not_response_time(
    fixture_api_engine: Engine,
) -> None:
    _fixture(fixture_api_engine, kickoff=datetime(2100, 1, 2, tzinfo=UTC))
    with fixture_api_engine.connect() as connection:
        result = today_fixtures(
            connection,
            fixture_date=date(2100, 1, 2),
            timezone_name="UTC",
            now=datetime(2100, 1, 2, tzinfo=UTC),
        )
    assert result.fixtures[0].data_availability is DataAvailabilityState.STALE
    assert result.fixtures[0].freshness.fixture_refresh_at is not None


def test_match_detail_not_found_uses_safe_error(fixture_client: TestClient) -> None:
    response = fixture_client.get("/api/v1/matches/999999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_fixture_routes_are_get_only_and_documented(fixture_client: TestClient) -> None:
    paths = fixture_client.get("/openapi.json").json()["paths"]
    assert set(paths["/api/v1/fixtures/today"]) == {"get"}
    assert set(paths["/api/v1/matches/{match_id}"]) == {"get"}


def test_shadow_repository_is_not_queried_by_public_fixture_service() -> None:
    source = __import__("inspect").getsource(today_fixtures)
    assert "shadow_analysis_snapshots" not in source
