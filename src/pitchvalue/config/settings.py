"""Safe, explicit environment configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    """Raised when required project configuration is absent or invalid."""


@dataclass(frozen=True, repr=False)
class Settings:
    """Runtime settings whose representation never reveals credentials."""

    database_url: str
    environment_name: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_allowed_origins: tuple[str, ...] = (
        "http://localhost:8081",
        "http://localhost:19006",
    )
    log_level: str = "INFO"

    def __repr__(self) -> str:
        return (
            "Settings("
            f"environment_name={self.environment_name!r}, "
            f"api_host={self.api_host!r}, "
            f"api_port={self.api_port!r}, "
            "database_url='<redacted>', "
            f"cors_allowed_origins={self.cors_allowed_origins!r}, "
            f"log_level={self.log_level!r})"
        )


_ENVIRONMENTS = frozenset({"development", "test", "production"})
_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def _load_port(raw_value: str) -> int:
    try:
        port = int(raw_value)
    except ValueError as error:
        raise ConfigurationError("API_PORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise ConfigurationError("API_PORT must be between 1 and 65535")
    return port


def _load_origins(raw_value: str) -> tuple[str, ...]:
    origins = tuple(
        dict.fromkeys(part.strip().rstrip("/") for part in raw_value.split(",") if part.strip())
    )
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            origin == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ConfigurationError("CORS_ALLOWED_ORIGINS contains an invalid origin")
    return origins


def load_settings(environment: Mapping[str, str] | None = None) -> Settings:
    """Load and validate settings from an environment-like mapping."""
    try:
        from pathlib import Path

        env_path = Path(".env")
        if env_path.is_file():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    key, _, value = line.partition("=")
                    if key.strip() and key.strip() not in os.environ:
                        os.environ[key.strip()] = value.strip()
    except Exception:
        pass
    values = os.environ if environment is None else environment
    database_url = values.get("DATABASE_URL", "").strip()
    if not database_url:
        raise ConfigurationError("DATABASE_URL is required")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ConfigurationError("DATABASE_URL must use PostgreSQL")
    environment_name = values.get("PITCHVALUE_ENV", "development").strip().lower()
    if environment_name not in _ENVIRONMENTS:
        raise ConfigurationError("PITCHVALUE_ENV must be development, test, or production")
    api_host = values.get("API_HOST", "127.0.0.1").strip()
    if not api_host:
        raise ConfigurationError("API_HOST must not be empty")
    api_port = _load_port(values.get("API_PORT", "8000").strip())
    default_origins = (
        "" if environment_name == "production" else "http://localhost:8081,http://localhost:19006"
    )
    cors_allowed_origins = _load_origins(
        values.get("CORS_ALLOWED_ORIGINS", default_origins).strip()
    )
    log_level = values.get("LOG_LEVEL", "INFO").strip().upper()
    if log_level not in _LOG_LEVELS:
        raise ConfigurationError("LOG_LEVEL must be a standard Python logging level")
    return Settings(
        database_url=database_url,
        environment_name=environment_name,
        api_host=api_host,
        api_port=api_port,
        cors_allowed_origins=cors_allowed_origins,
        log_level=log_level,
    )


def get_database_url() -> str:
    """Return the validated database URL for migration and runtime clients."""
    return load_settings().database_url
