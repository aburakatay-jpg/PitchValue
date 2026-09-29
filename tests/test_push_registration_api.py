"""Tests for push registration API endpoint."""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from pitchvalue.api.main import create_app
from pitchvalue.config import load_settings
from pitchvalue.product_services.auth import ProductUser, _issue_session, _now
from pitchvalue.product_services.push_tokens import get_user_expo_push_tokens


@pytest.fixture
def db_connection() -> Iterator[Connection]:
    from sqlalchemy import create_engine

    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM auth_sessions WHERE user_id IN ('test_user_pd_1', 'test_user_pd_2')")
        )
        conn.execute(text("DELETE FROM push_tokens"))
        conn.execute(
            text("DELETE FROM app_users WHERE user_id IN ('test_user_pd_1', 'test_user_pd_2')")
        )

        conn.execute(
            text(
                "INSERT INTO app_users (user_id, account_kind, created_at, updated_at) "
                "VALUES ('test_user_pd_1', 'AUTHENTICATED', now(), now()), "
                "('test_user_pd_2', 'AUTHENTICATED', now(), now()) ON CONFLICT DO NOTHING"
            )
        )
        yield conn


@pytest.fixture
def app_client(db_connection):
    app = create_app(load_settings())
    # Override get_transaction and get_connection to use db_connection
    from pitchvalue.api.dependencies import get_connection, get_transaction

    app.dependency_overrides[get_transaction] = lambda: db_connection
    app.dependency_overrides[get_connection] = lambda: db_connection

    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth_headers(db_connection):
    user = ProductUser(
        user_id="test_user_pd_1", email="test@test.com", account_kind="AUTHENTICATED"
    )
    session = _issue_session(db_connection, user, _now(None))
    return {"Authorization": f"Bearer {session.access_token}"}


@pytest.fixture
def auth_headers_user2(db_connection):
    user = ProductUser(
        user_id="test_user_pd_2", email="test2@test.com", account_kind="AUTHENTICATED"
    )
    session = _issue_session(db_connection, user, _now(None))
    return {"Authorization": f"Bearer {session.access_token}"}


def test_register_push_token_success(app_client, auth_headers, db_connection):
    response = app_client.post(
        "/api/v1/auth/push/register",
        headers=auth_headers,
        json={"provider": "EXPO", "token": "api_token_123"},
    )
    assert response.status_code == 204

    # Check db
    tokens = get_user_expo_push_tokens(db_connection, "test_user_pd_1")
    assert "api_token_123" in tokens


def test_register_push_token_unauthenticated(app_client):
    response = app_client.post(
        "/api/v1/auth/push/register",
        json={"provider": "EXPO", "token": "api_token_123"},
    )
    assert response.status_code == 401


def test_register_push_token_invalid_provider(app_client, auth_headers):
    response = app_client.post(
        "/api/v1/auth/push/register",
        headers=auth_headers,
        json={"provider": "APNS", "token": "api_token_123"},
    )
    assert response.status_code == 422
    assert "Unsupported provider" in response.json()["error"]["message"]


def test_register_push_token_transfer_ownership(
    app_client, auth_headers, auth_headers_user2, db_connection
):
    # Register to user1
    app_client.post(
        "/api/v1/auth/push/register",
        headers=auth_headers,
        json={"provider": "EXPO", "token": "shared_token"},
    )
    assert get_user_expo_push_tokens(db_connection, "test_user_pd_1") == ["shared_token"]

    # Register to user2
    app_client.post(
        "/api/v1/auth/push/register",
        headers=auth_headers_user2,
        json={"provider": "EXPO", "token": "shared_token"},
    )

    # user1 should not have it, user2 should
    assert get_user_expo_push_tokens(db_connection, "test_user_pd_1") == []
    assert get_user_expo_push_tokens(db_connection, "test_user_pd_2") == ["shared_token"]
