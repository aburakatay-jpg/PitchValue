import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text

from pitchvalue.api.dependencies import get_connection, get_transaction
from pitchvalue.api.main import create_app
from pitchvalue.config import load_settings
from pitchvalue.product_services.auth import (
    register_email,
)
from pitchvalue.product_services.email_delivery import ResendEmailVerificationDelivery


@pytest.fixture(scope="session")
def product_engine() -> Engine:
    return create_engine(load_settings(os.environ).database_url)


@pytest.fixture
def db_connection(product_engine: Engine):
    with product_engine.connect() as conn, conn.begin() as trans:
        conn.execute(text("DELETE FROM auth_sessions"))
        conn.execute(text("DELETE FROM auth_email_verifications"))
        conn.execute(text("DELETE FROM push_tokens"))
        conn.execute(text("DELETE FROM followed_matches"))
        conn.execute(text("DELETE FROM auth_identities"))
        conn.execute(text("DELETE FROM app_users"))
        yield conn
        trans.rollback()


@pytest.fixture
def client(db_connection) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_connection] = lambda: db_connection
    app.dependency_overrides[get_transaction] = lambda: db_connection
    with TestClient(app) as test_client:
        yield test_client


def test_registration_creates_unverified_account_and_token(db_connection):
    register_email(db_connection, "test@example.com", "Password123!", "US")
    row = db_connection.execute(
        text("SELECT last_verified_at FROM auth_identities WHERE provider='EMAIL'")
    ).scalar_one_or_none()
    assert row is None

    token_row = db_connection.execute(
        text("SELECT token_hash, expires_at, used_at FROM auth_email_verifications")
    ).fetchone()
    assert token_row is not None
    assert token_row[2] is None
    # 24h expiry
    assert token_row[1] > datetime.now(UTC) + timedelta(hours=23, minutes=50)


def test_verification_success(client, db_connection):
    register_email(db_connection, "verify@example.com", "Password123!", "US")

    login_response = client.post(
        "/api/v1/auth/email/login", json={"email": "verify@example.com", "password": "Password123!"}
    )
    token = login_response.json()["access_token"]

    # Bypass cooldown
    db_connection.execute(
        text("UPDATE auth_email_verifications SET expires_at = :past"),
        {"past": datetime.now(UTC) + timedelta(hours=23)},
    )

    # We must mock secrets.token_urlsafe to know the raw token
    with patch("secrets.token_urlsafe", return_value="raw_token_123"):
        # Resend creates a known token
        client.post(
            "/api/v1/auth/email/verification/resend", headers={"Authorization": f"Bearer {token}"}
        )

    # valid confirmation
    conf_resp = client.post(
        "/api/v1/auth/email/verification/confirm", json={"token": "raw_token_123"}
    )
    assert conf_resp.status_code == 204

    # last_verified_at transition
    row = db_connection.execute(
        text("SELECT last_verified_at FROM auth_identities WHERE provider='EMAIL'")
    ).scalar_one()
    assert row is not None


def test_invalid_and_reused_confirmation(client, db_connection):
    register_email(db_connection, "invalid@example.com", "Password123!", "US")
    login_response = client.post(
        "/api/v1/auth/email/login",
        json={"email": "invalid@example.com", "password": "Password123!"},
    )
    token = login_response.json()["access_token"]

    # Bypass cooldown
    db_connection.execute(
        text("UPDATE auth_email_verifications SET expires_at = :past"),
        {"past": datetime.now(UTC) + timedelta(hours=23)},
    )

    with patch("secrets.token_urlsafe", return_value="raw_token_456"):
        client.post(
            "/api/v1/auth/email/verification/resend", headers={"Authorization": f"Bearer {token}"}
        )

    # invalid confirmation
    conf_resp = client.post(
        "/api/v1/auth/email/verification/confirm", json={"token": "wrong_token"}
    )
    assert conf_resp.status_code == 400

    # valid confirmation
    conf_resp = client.post(
        "/api/v1/auth/email/verification/confirm", json={"token": "raw_token_456"}
    )
    assert conf_resp.status_code == 204

    # reused confirmation
    conf_resp = client.post(
        "/api/v1/auth/email/verification/confirm", json={"token": "raw_token_456"}
    )
    assert conf_resp.status_code == 400


def test_expired_confirmation(client, db_connection):
    register_email(db_connection, "expired@example.com", "Password123!", "US")
    login_response = client.post(
        "/api/v1/auth/email/login",
        json={"email": "expired@example.com", "password": "Password123!"},
    )
    token = login_response.json()["access_token"]

    # Bypass cooldown
    db_connection.execute(
        text("UPDATE auth_email_verifications SET expires_at = :past"),
        {"past": datetime.now(UTC) + timedelta(hours=23)},
    )

    with patch("secrets.token_urlsafe", return_value="raw_token_789"):
        client.post(
            "/api/v1/auth/email/verification/resend", headers={"Authorization": f"Bearer {token}"}
        )

    db_connection.execute(
        text("UPDATE auth_email_verifications SET expires_at = :past"),
        {"past": datetime.now(UTC) - timedelta(hours=1)},
    )

    conf_resp = client.post(
        "/api/v1/auth/email/verification/confirm", json={"token": "raw_token_789"}
    )
    assert conf_resp.status_code == 400


def test_resend_cooldown_and_limit(client, db_connection):
    register_email(db_connection, "limit@example.com", "Password123!", "US")
    login_response = client.post(
        "/api/v1/auth/email/login", json={"email": "limit@example.com", "password": "Password123!"}
    )
    token = login_response.json()["access_token"]

    # 1. Resend immediate -> Blocked by cooldown
    resend_resp = client.post(
        "/api/v1/auth/email/verification/resend", headers={"Authorization": f"Bearer {token}"}
    )
    assert resend_resp.status_code == 400
    assert "wait" in resend_resp.json()["error"]["message"].lower()

    # 2. Advance time to bypass cooldown
    db_connection.execute(
        text("UPDATE auth_email_verifications SET expires_at = :past"),
        {
            "past": datetime.now(UTC) + timedelta(hours=23)
        },  # Cooldown is 1 min (expires_at is issued + 24h)
    )

    # 3. Resend -> Allowed
    resend_resp = client.post(
        "/api/v1/auth/email/verification/resend", headers={"Authorization": f"Bearer {token}"}
    )
    assert resend_resp.status_code == 200

    # 4. Old token invalidation
    rows = db_connection.execute(
        text(
            "SELECT expires_at FROM auth_email_verifications "
            "WHERE used_at IS NULL ORDER BY expires_at DESC"
        )
    ).fetchall()
    assert len(rows) == 2
    assert rows[1][0] < datetime.now(UTC) + timedelta(minutes=1)  # Old token invalidated

    # 5. Exhaust bounds
    client.app.state.auth_limiter._attempts.clear()
    for _ in range(1):
        db_connection.execute(
            text("UPDATE auth_email_verifications SET expires_at = :past WHERE expires_at > :now"),
            {
                "past": datetime.now(UTC) + timedelta(hours=23),
                "now": datetime.now(UTC) + timedelta(hours=23, minutes=30),
            },
        )
        resend_resp = client.post(
            "/api/v1/auth/email/verification/resend", headers={"Authorization": f"Bearer {token}"}
        )
        assert resend_resp.status_code == 200

    # 6. Bounded limit reached
    db_connection.execute(
        text("UPDATE auth_email_verifications SET expires_at = :past WHERE expires_at > :now"),
        {
            "past": datetime.now(UTC) + timedelta(hours=23),
            "now": datetime.now(UTC) + timedelta(hours=23, minutes=30),
        },
    )
    resend_resp = client.post(
        "/api/v1/auth/email/verification/resend", headers={"Authorization": f"Bearer {token}"}
    )
    assert resend_resp.status_code == 400
    assert "too many verification attempts" in resend_resp.json()["error"]["message"].lower()


def test_provider_unavailable(client, db_connection):
    register_email(db_connection, "unavail@example.com", "Password123!", "US")
    login_response = client.post(
        "/api/v1/auth/email/login",
        json={"email": "unavail@example.com", "password": "Password123!"},
    )
    token = login_response.json()["access_token"]

    db_connection.execute(
        text("UPDATE auth_email_verifications SET expires_at = :past"),
        {"past": datetime.now(UTC) + timedelta(hours=23)},
    )

    with patch.object(
        ResendEmailVerificationDelivery,
        "request_verification",
        side_effect=RuntimeError("Provider offline"),
    ):
        resend_resp = client.post(
            "/api/v1/auth/email/verification/resend", headers={"Authorization": f"Bearer {token}"}
        )
        assert resend_resp.status_code == 200
        assert resend_resp.json()["delivery_state"] == "VERIFICATION_DELIVERY_UNAVAILABLE"


def test_unverified_session_is_restricted(client, db_connection):
    register_email(db_connection, "restrict@example.com", "Password123!", "US")
    login_response = client.post(
        "/api/v1/auth/email/login",
        json={"email": "restrict@example.com", "password": "Password123!"},
    )
    token = login_response.json()["access_token"]
    me_resp = client.get("/api/v1/me/entitlement", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 403


def test_verified_session_is_allowed(client, db_connection):
    register_email(db_connection, "allow@example.com", "Password123!", "US")
    db_connection.execute(
        text("UPDATE auth_identities SET last_verified_at=CURRENT_TIMESTAMP WHERE provider='EMAIL'")
    )
    login_response = client.post(
        "/api/v1/auth/email/login", json={"email": "allow@example.com", "password": "Password123!"}
    )
    token = login_response.json()["access_token"]
    me_resp = client.get("/api/v1/me/entitlement", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
