import os

import pytest
from sqlalchemy import Engine, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.product_services.auth import (
    AuthError,
    _token_hash,
    confirm_password_reset,
    login_email,
    register_email,
    request_password_reset,
)


@pytest.fixture(scope="session")
def product_engine() -> Engine:
    return create_engine(load_settings(os.environ).database_url)


@pytest.fixture
def db_connection(product_engine: Engine):
    with product_engine.begin() as conn:
        conn.execute(text("DELETE FROM auth_password_resets"))
        conn.execute(text("DELETE FROM auth_sessions"))
        conn.execute(text("DELETE FROM auth_identities"))
        conn.execute(text("DELETE FROM app_users"))
        yield conn


def test_password_reset_lifecycle(db_connection):
    # Setup
    session, _ = register_email(db_connection, "reset@test.com", "OldPassword123!", "US")
    user_id = session.user.user_id

    # Request
    raw_token = request_password_reset(db_connection, "reset@test.com")
    assert raw_token is not None

    # Verify stored in DB
    row = (
        db_connection.execute(
            text("SELECT * FROM auth_password_resets WHERE token_hash=:hash"),
            {"hash": _token_hash(raw_token)},
        )
        .mappings()
        .one()
    )
    assert row["user_id"] == user_id
    assert row["used_at"] is None

    # Confirm
    confirm_password_reset(db_connection, raw_token, "NewPassword123!")

    # Verify used_at set
    row = (
        db_connection.execute(
            text("SELECT * FROM auth_password_resets WHERE token_hash=:hash"),
            {"hash": _token_hash(raw_token)},
        )
        .mappings()
        .one()
    )
    assert row["used_at"] is not None

    # Login with new password works
    new_session = login_email(db_connection, "reset@test.com", "NewPassword123!")
    assert new_session.user.user_id == user_id

    # Login with old password fails
    with pytest.raises(AuthError, match="credentials"):
        login_email(db_connection, "reset@test.com", "OldPassword123!")


def test_password_reset_invalid_token(db_connection):
    register_email(db_connection, "badtoken@test.com", "OldPassword123!", "US")

    with pytest.raises(AuthError, match="Invalid or expired reset token"):
        confirm_password_reset(db_connection, "bad_token_value", "NewPassword123!")


def test_password_reset_anti_enumeration(db_connection):
    # Request for non-existent email should return None (not reveal user existence)
    raw_token = request_password_reset(db_connection, "nobody@test.com")
    assert raw_token is None
