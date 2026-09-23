import pytest

from pitchvalue.config import ConfigurationError, get_database_direct_url, load_settings


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


def test_direct_url_is_separate_and_redacted() -> None:
    settings = load_settings(
        {
            "DATABASE_URL": "postgresql+psycopg://user:runtime-secret@localhost/pitchvalue?sslmode=verify-full",
            "DATABASE_DIRECT_URL": "postgresql+psycopg://user:direct-secret@localhost/pitchvalue?sslmode=verify-full",
            "PITCHVALUE_ENV": "staging",
        }
    )

    assert settings.database_direct_url is not None
    assert "runtime-secret" not in repr(settings)
    assert "direct-secret" not in repr(settings)


@pytest.mark.parametrize("environment_name", ["staging", "production"])
def test_deployed_environments_require_direct_url(environment_name: str) -> None:
    with pytest.raises(ConfigurationError, match="DATABASE_DIRECT_URL is required"):
        load_settings(
            {
                "DATABASE_URL": "postgresql+psycopg://user:secret@localhost/pitchvalue",
                "PITCHVALUE_ENV": environment_name,
            }
        )


def test_direct_url_must_use_postgresql() -> None:
    with pytest.raises(ConfigurationError, match="DATABASE_DIRECT_URL must use PostgreSQL"):
        load_settings(
            {
                "DATABASE_URL": "postgresql+psycopg://localhost/pitchvalue",
                "DATABASE_DIRECT_URL": "sqlite:///local.db",
            }
        )


def test_migration_url_prefers_explicit_direct_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = "postgresql+psycopg://localhost/runtime"
    direct = "postgresql+psycopg://localhost/direct"
    monkeypatch.setenv("DATABASE_URL", runtime)
    monkeypatch.setenv("DATABASE_DIRECT_URL", direct)
    monkeypatch.setenv("PITCHVALUE_ENV", "development")

    assert get_database_direct_url() == direct


@pytest.mark.parametrize("setting_name", ["DATABASE_URL", "DATABASE_DIRECT_URL"])
def test_deployed_urls_require_verified_tls(setting_name: str) -> None:
    values = {
        "DATABASE_URL": "postgresql+psycopg://localhost/pitchvalue?sslmode=verify-full",
        "DATABASE_DIRECT_URL": "postgresql+psycopg://localhost/pitchvalue?sslmode=verify-full",
        "PITCHVALUE_ENV": "production",
    }
    values[setting_name] = "postgresql+psycopg://localhost/pitchvalue?sslmode=require"

    with pytest.raises(ConfigurationError, match=f"{setting_name} must use sslmode=verify-full"):
        load_settings(values)
