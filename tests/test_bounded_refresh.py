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
    from sqlalchemy import text

    connection.execute(text("DELETE FROM competition_provider_refs"))
    connection.execute(text("DELETE FROM shadow_analysis_snapshots"))
    connection.execute(text("DELETE FROM match_statistics"))
    connection.execute(text("DELETE FROM engine_runs WHERE run_id != 'test-dummy-run-id'"))
    connection.execute(
        text("DELETE FROM source_entity_references WHERE provider_entity_id NOT LIKE 'dummy-%'")
    )
    connection.execute(text("DELETE FROM match_provider_refs"))
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


def _mark_fresh(engine: Engine, match_id: int, fresh_at: datetime) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO source_entity_references ("
                "provider_id, entity_type, provider_entity_id,"
                " provider_display_name, "
                "mapping_status, mapping_version, provenance,"
                " canonical_match_id, first_seen_at, last_seen_at"
                ") VALUES ("
                "(SELECT max(provider_id) FROM providers), 'FIXTURE', 'mock', 'mock', 'RESOLVED',"
                " 'v1', 'mock', :match_id, :fresh_at, :fresh_at"
                ")"
            ),
            {"match_id": match_id, "fresh_at": fresh_at},
        )


def test_today_executes_exactly_one_provider_fetch_if_stale(
    fixture_client: TestClient, fixture_api_engine: Engine
) -> None:
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
    kickoff = datetime.now(UTC) - timedelta(minutes=20)
    fixture_date = kickoff.date()
    date_str = fixture_date.isoformat()
    match_id = _fixture(fixture_api_engine, kickoff=kickoff, finished=False)

    _mark_fresh(fixture_api_engine, match_id, datetime.now(UTC))

    with patch(
        "pitchvalue.providers.five_dfa.adapter.FiveDfaFreeAdapter.fixture_payloads"
    ) as mock_payloads:
        response = fixture_client.get(f"/api/v1/fixtures/today?date={date_str}&timezone=UTC")

    assert response.status_code == 200
    mock_payloads.assert_not_called()


def test_today_does_not_fetch_if_not_stale(
    fixture_client: TestClient, fixture_api_engine: Engine
) -> None:
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


def test_today_live_transition_and_score_persistence(
    fixture_client: TestClient, fixture_api_engine: Engine
) -> None:
    kickoff = (datetime.now(UTC) - timedelta(minutes=5)).replace(microsecond=0)
    fixture_date = kickoff.date()
    match_id = _fixture(fixture_api_engine, kickoff=kickoff, finished=False)

    with fixture_api_engine.connect() as connection:
        row = (
            connection.execute(
                text("""
                SELECT c.canonical_name as comp_name,
                    ht.canonical_name as home_name,
                    at.canonical_name as away_name
                FROM matches m
                JOIN competitions c ON c.competition_id = m.competition_id
                JOIN teams ht ON ht.team_id = m.home_team_id
                JOIN teams at ON at.team_id = m.away_team_id
                WHERE m.match_id = :match_id
            """),
                {"match_id": match_id},
            )
            .mappings()
            .first()
        )
        assert row is not None
        comp_name = str(row["comp_name"])
        home_name = str(row["home_name"])
        away_name = str(row["away_name"])

        from pitchvalue.providers.five_dfa.capabilities import PROVIDER_NAME
        from pitchvalue.providers.source_persistence import ensure_provider

        provider_id = ensure_provider(connection, PROVIDER_NAME, plan="FREE")

        connection.execute(
            text(
                "INSERT INTO match_provider_refs"
                " (match_id, provider_id, provider_match_id)"
                " VALUES (:match_id, :provider_id, :prov_id)"
                " ON CONFLICT DO NOTHING"
            ),
            {
                "match_id": match_id,
                "provider_id": provider_id,
                "prov_id": str(match_id),
            },
        )
        connection.commit()

    # Provider mock returning LIVE with score
    mock_payload = {
        "id": match_id,
        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
        "status": "in_play",
        "goals": {"home": 2, "away": 1},
        "statistics": {},
        "league": {"id": 1, "name": comp_name, "country": "England"},
        "teams": {"home": {"id": 1, "name": home_name}, "away": {"id": 2, "name": away_name}},
    }

    with (
        patch(
            "pitchvalue.providers.five_dfa.adapter.FiveDfaFreeAdapter.fixture_payloads"
        ) as mock_fetch,
        patch("pitchvalue.providers.five_dfa.fixtures.map_competition") as mock_map_comp,
        patch("pitchvalue.operations.current_season.map_competition") as mock_map_comp2,
    ):
        # Fake rate limit state for adapter mock
        from pitchvalue.providers.five_dfa.client import RateLimitState
        from pitchvalue.providers.five_dfa.mapping import CompetitionReference, MappingStatus

        mock_fetch.return_value = ((mock_payload,), (RateLimitState(100, 100, 60, None),))
        comp_ref = CompetitionReference(
            provider="5DollarFootballAPI",
            provider_competition_id="1",
            provider_name=comp_name,
            canonical_name=comp_name,
            status=MappingStatus.RESOLVED,
        )
        mock_map_comp.return_value = comp_ref
        mock_map_comp2.return_value = comp_ref

        response = fixture_client.get(
            f"/api/v1/fixtures/today?date={fixture_date.isoformat()}&timezone=UTC"
        )
        assert response.status_code == 200
        data = response.json()

        # Verify provider called
        assert mock_fetch.call_count == 1

        # Verify Today API response is LIVE with score
        fixtures = data.get("fixtures", [])
        assert len(fixtures) == 1
        match = fixtures[0]
        assert match["fixture_status"] == "IN_PLAY"
        assert match["home_score"] == 2
        assert match["away_score"] == 1

        # Verify DB is LIVE with score
        with fixture_api_engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT status, home_score, away_score"
                        " FROM matches"
                        " WHERE match_id = :match_id"
                    ),
                    {"match_id": match_id},
                )
                .mappings()
                .first()
            )
            assert row is not None
            assert row["status"] == "IN_PLAY"
            assert row["home_score"] == 2
            assert row["away_score"] == 1
