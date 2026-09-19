import os

import pytest
from sqlalchemy import Engine, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.product_services.auth import AuthError, register_email


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


def test_country_code_validation_accepts_valid(db_connection):
    register_email(db_connection, "tr@example.com", "Password123!", "TR")
    register_email(db_connection, "us@example.com", "Password123!", "US")
    register_email(db_connection, "gb@example.com", "Password123!", "GB")


def test_country_code_validation_normalizes_case(db_connection):
    # 'tr' normalizes to 'TR', 'us' normalizes to 'US'
    register_email(db_connection, "tr_lower@example.com", "Password123!", "tr")
    register_email(db_connection, "us_lower@example.com", "Password123!", "us")

    # Verify in DB
    row1 = db_connection.execute(
        text(
            "SELECT country_code FROM app_users JOIN auth_identities USING(user_id) "
            "WHERE normalized_email='tr_lower@example.com'"
        )
    ).scalar_one()
    assert row1 == "TR"

    row2 = db_connection.execute(
        text(
            "SELECT country_code FROM app_users JOIN auth_identities USING(user_id) "
            "WHERE normalized_email='us_lower@example.com'"
        )
    ).scalar_one()
    assert row2 == "US"


def test_country_code_validation_rejects_invalid(db_connection):
    with pytest.raises(AuthError, match="invalid country code"):
        register_email(db_connection, "zz@example.com", "Password123!", "ZZ")

    with pytest.raises(AuthError, match="invalid country code"):
        register_email(db_connection, "xx@example.com", "Password123!", "XX")

    with pytest.raises(AuthError, match="invalid country code"):
        register_email(db_connection, "aa@example.com", "Password123!", "AA")
