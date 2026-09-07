"""Safe, explicit environment configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


class ConfigurationError(ValueError):
    """Raised when required project configuration is absent or invalid."""


@dataclass(frozen=True, repr=False)
class Settings:
    """Runtime settings whose representation never reveals credentials."""

    database_url: str

    def __repr__(self) -> str:
        return "Settings(database_url='<redacted>')"


def load_settings(environment: Mapping[str, str] | None = None) -> Settings:
    """Load and validate settings from an environment-like mapping."""
    values = os.environ if environment is None else environment
    database_url = values.get("DATABASE_URL", "").strip()
    if not database_url:
        raise ConfigurationError("DATABASE_URL is required")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ConfigurationError("DATABASE_URL must use PostgreSQL")
    return Settings(database_url=database_url)


def get_database_url() -> str:
    """Return the validated database URL for migration and runtime clients."""
    return load_settings().database_url
