from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock

from pitchvalue.operations.staging_readiness import (
    ConnectionMode,
    StagingDatabaseProfile,
    check_staging_database,
    validate_staging_profile,
)


def _profile() -> StagingDatabaseProfile:
    return StagingDatabaseProfile(
        ConnectionMode.DIRECT,
        ssl_required=True,
        prepared_statements_disabled=False,
        application_pool_size=5,
        migration_connection_mode=ConnectionMode.DIRECT,
    )


def test_direct_persistent_backend_profile_is_compatible() -> None:
    assert validate_staging_profile(_profile()) == ()


def test_transaction_pool_requires_no_prepared_statements_and_single_app_connection() -> None:
    profile = replace(_profile(), connection_mode=ConnectionMode.TRANSACTION_POOL)
    assert validate_staging_profile(profile) == (
        "TRANSACTION_POOL_APPLICATION_POOL_MUST_BE_ONE",
        "TRANSACTION_POOL_PREPARED_STATEMENTS_UNSAFE",
    )
    safe = replace(profile, prepared_statements_disabled=True, application_pool_size=1)
    assert validate_staging_profile(safe) == ()


def test_migrations_require_direct_connection_and_ssl_is_explicit() -> None:
    profile = replace(
        _profile(),
        ssl_required=False,
        migration_connection_mode=ConnectionMode.SESSION_POOL,
    )
    assert validate_staging_profile(profile) == (
        "MIGRATIONS_REQUIRE_DIRECT_CONNECTION",
        "SSL_REQUIRED",
    )


def test_database_check_is_read_only_and_detects_revision_mismatch() -> None:
    connection = Mock()
    connection.execute.return_value.scalar_one_or_none.return_value = "old"
    connection.execute.return_value.scalar_one.return_value = 1
    result = check_staging_database(
        connection,
        expected_revision="head",
        profile=_profile(),
    )
    assert not result.ready
    assert result.diagnostics == ("MIGRATION_MISMATCH",)
    assert connection.execute.call_count == 2
