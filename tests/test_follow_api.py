import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from pitchvalue.api.app import create_app
from pitchvalue.config import load_settings
from pitchvalue.product_services.auth import AccountKind, ProductUser, _issue_session, _now


@pytest.fixture
def db_connection() -> Iterator[Connection]:
    from sqlalchemy import create_engine

    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM auth_sessions WHERE user_id IN ('test_user_fa_1')"))
        conn.execute(text("DELETE FROM followed_matches"))
        conn.execute(text("DELETE FROM app_users WHERE user_id IN ('test_user_fa_1')"))

        conn.execute(
            text(
                "INSERT INTO app_users (user_id, account_kind, created_at, updated_at) "
                "VALUES ('test_user_fa_1', 'AUTHENTICATED', now(), now()) ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO competitions (competition_id, canonical_name, country_code, "
                "competition_type, gender) VALUES (99991, 'Test', 'GBR', 'domestic_league', 'men') "
                "ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO seasons (season_id, competition_id, season_name, "
                "start_year, end_year, "
                "status) VALUES (99991, 99991, '2020', 2020, 2021, 'active') ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO teams (team_id, canonical_name, normalized_name) VALUES "
                "(99991, 'T1', 't1'), (99992, 'T2', 't2') ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO matches (match_id, competition_id, season_id, "
                "home_team_id, away_team_id, "
                "kickoff_at_utc, status) VALUES (99991, 99991, 99991, 99991, 99992, "
                "'2026-09-13 12:00:00', 'SCHEDULED') ON CONFLICT DO NOTHING"
            )
        )

        yield conn


@pytest.fixture
def app_client(db_connection: Connection) -> Iterator[TestClient]:
    app = create_app(load_settings())
    from pitchvalue.api.dependencies import get_connection, get_transaction

    app.dependency_overrides[get_transaction] = lambda: db_connection
    app.dependency_overrides[get_connection] = lambda: db_connection
    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth_headers(db_connection: Connection) -> dict[str, str]:
    user = ProductUser(
        user_id="test_user_fa_1", email="test@test.com", account_kind=AccountKind.AUTHENTICATED
    )
    session = _issue_session(db_connection, user, _now(None))
    return {"Authorization": f"Bearer {session.access_token}"}


def test_follow_api_lifecycle(
    app_client: TestClient, auth_headers: dict[str, str], db_connection: Connection
) -> None:
    match_id = 99991

    # GET empty
    r = app_client.get("/api/v1/me/follows", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []

    # POST follow
    r = app_client.post(f"/api/v1/me/follows/{match_id}", headers=auth_headers)
    assert r.status_code == 204

    # GET single
    r = app_client.get("/api/v1/me/follows", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == [match_id]

    # POST idempotent
    r = app_client.post(f"/api/v1/me/follows/{match_id}", headers=auth_headers)
    assert r.status_code == 204

    # DELETE unfollow
    r = app_client.delete(f"/api/v1/me/follows/{match_id}", headers=auth_headers)
    assert r.status_code == 204

    # GET empty again
    r = app_client.get("/api/v1/me/follows", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_follow_api_unauthenticated(app_client: TestClient) -> None:
    match_id = 99991
    assert app_client.post(f"/api/v1/me/follows/{match_id}").status_code == 401
    assert app_client.delete(f"/api/v1/me/follows/{match_id}").status_code == 401
    assert app_client.get("/api/v1/me/follows").status_code == 401
