"""Provider-independent PostgreSQL/Supabase staging compatibility checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import Connection, text


class ConnectionMode(StrEnum):
    DIRECT = "DIRECT"
    SESSION_POOL = "SESSION_POOL"
    TRANSACTION_POOL = "TRANSACTION_POOL"


@dataclass(frozen=True)
class StagingDatabaseProfile:
    connection_mode: ConnectionMode
    ssl_required: bool
    prepared_statements_disabled: bool
    application_pool_size: int
    migration_connection_mode: ConnectionMode

    def __post_init__(self) -> None:
        if self.application_pool_size < 1:
            raise ValueError("application_pool_size must be positive")


@dataclass(frozen=True)
class StagingReadinessResult:
    ready: bool
    diagnostics: tuple[str, ...]
    expected_revision: str
    actual_revision: str | None


def validate_staging_profile(profile: StagingDatabaseProfile) -> tuple[str, ...]:
    """Return deployment risks without changing the selected connection mode."""
    diagnostics: list[str] = []
    if not profile.ssl_required:
        diagnostics.append("SSL_REQUIRED")
    if profile.migration_connection_mode is not ConnectionMode.DIRECT:
        diagnostics.append("MIGRATIONS_REQUIRE_DIRECT_CONNECTION")
    if profile.connection_mode is ConnectionMode.TRANSACTION_POOL:
        if not profile.prepared_statements_disabled:
            diagnostics.append("TRANSACTION_POOL_PREPARED_STATEMENTS_UNSAFE")
        if profile.application_pool_size != 1:
            diagnostics.append("TRANSACTION_POOL_APPLICATION_POOL_MUST_BE_ONE")
    return tuple(sorted(diagnostics))


def check_staging_database(
    connection: Connection,
    *,
    expected_revision: str,
    profile: StagingDatabaseProfile,
) -> StagingReadinessResult:
    diagnostics = list(validate_staging_profile(profile))
    actual = connection.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one_or_none()
    if actual != expected_revision:
        diagnostics.append("MIGRATION_MISMATCH")
    connection.execute(text("SELECT 1")).scalar_one()
    ordered = tuple(sorted(set(diagnostics)))
    return StagingReadinessResult(not ordered, ordered, expected_revision, actual)
