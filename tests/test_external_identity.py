import os

import pytest
from sqlalchemy import Engine, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.product_services.auth import (
    AccountKind,
    AuthError,
    authenticate_external,
)


@pytest.fixture(scope="session")
def product_engine() -> Engine:
    return create_engine(load_settings(os.environ).database_url)


@pytest.fixture
def db_connection(product_engine: Engine):
    with product_engine.begin() as conn:
        conn.execute(text("DELETE FROM auth_sessions"))
        conn.execute(text("DELETE FROM auth_identities"))
        conn.execute(text("DELETE FROM app_users"))
        yield conn


def test_external_identity_new_user(db_connection):
    session = authenticate_external(db_connection, "APPLE", "apple_subject_123", "test@apple.com")
    assert session.user.account_kind == AccountKind.AUTHENTICATED
    assert session.user.email == "test@apple.com"

    # Verify DB state
    row = (
        db_connection.execute(
            text("SELECT provider, provider_subject FROM auth_identities WHERE user_id=:uid"),
            {"uid": session.user.user_id},
        )
        .mappings()
        .one()
    )
    assert row["provider"] == "APPLE"
    assert row["provider_subject"] == "apple_subject_123"


def test_external_identity_existing_user(db_connection):
    session1 = authenticate_external(
        db_connection, "GOOGLE", "google_subject_123", "test@google.com"
    )
    session2 = authenticate_external(
        db_connection, "GOOGLE", "google_subject_123", "test@google.com"
    )

    assert session1.user.user_id == session2.user.user_id


def test_external_identity_email_collision(db_connection):
    # Register email identity
    from pitchvalue.product_services.auth import register_email

    register_email(db_connection, "collide@test.com", "password12345!")

    # Attempt to authenticate with same email via external provider
    with pytest.raises(AuthError, match="EMAIL_IDENTITY_COLLISION"):
        authenticate_external(db_connection, "APPLE", "some_subject", "collide@test.com")
