import pytest

from pitchvalue.config import ConfigurationError, load_settings


def test_configuration_loads_database_url_without_exposing_it() -> None:
    secret_url = "postgresql+psycopg://user:secret@localhost/pitchvalue"

    settings = load_settings({"DATABASE_URL": secret_url})

    assert settings.database_url == secret_url
    assert "secret" not in repr(settings)
    assert "<redacted>" in repr(settings)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_database_url_is_required(value: str | None) -> None:
    environment = {} if value is None else {"DATABASE_URL": value}

    with pytest.raises(ConfigurationError, match="DATABASE_URL is required"):
        load_settings(environment)


def test_database_url_must_use_postgresql() -> None:
    with pytest.raises(ConfigurationError, match="must use PostgreSQL"):
        load_settings({"DATABASE_URL": "sqlite:///local.db"})
