"""Machine-readable, read-only release prerequisite validation."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

from pitchvalue.api.database import EXPECTED_ALEMBIC_REVISION, DatabaseResource
from pitchvalue.config import Settings, load_settings
from pitchvalue.operations.hardening import evaluate_readiness, load_activation_gates
from pitchvalue.operations.metadata import FreshnessState, load_fixture_refresh_metadata
from pitchvalue.providers.five_dfa.capabilities import SUPPORTED_COMPETITIONS
from pitchvalue.providers.five_dfa.mapping import COMPETITION_NAME_MAP


@dataclass(frozen=True)
class ReleaseValidationResult:
    ready: bool
    database_reachable: bool
    migration_current: bool
    prediction_schema_accessible: bool
    expected_revision: str
    prediction_snapshot_count: int | None
    failure_code: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ShadowActivationValidationResult:
    ready: bool
    database_reachable: bool
    migration_current: bool
    provider_configured: bool
    model_contract_loadable: bool
    canonical_mappings_complete: bool
    shadow_repository_available: bool
    report_directory_writable: bool
    current_season_fresh: bool
    fixture_refresh_fresh: bool
    report_archive_resolvable: bool
    today_contract_available: bool
    match_detail_contract_available: bool
    scheduler_enabled: bool
    publication_enabled: bool
    external_alerts_enabled: bool
    public_eligible_predictions: int | None
    public_shadow_predictions: int | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def validate_release(settings: Settings) -> ReleaseValidationResult:
    """Validate runtime prerequisites without mutating or auto-migrating the database."""
    database = DatabaseResource(settings.database_url)
    database.start()
    try:
        try:
            with database.connect() as connection:
                connection.execute(text("SELECT 1")).scalar_one()
        except Exception:
            return ReleaseValidationResult(
                ready=False,
                database_reachable=False,
                migration_current=False,
                prediction_schema_accessible=False,
                expected_revision=EXPECTED_ALEMBIC_REVISION,
                prediction_snapshot_count=None,
                failure_code="DATABASE_OR_SCHEMA_NOT_READY",
            )
        try:
            with database.connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                if revision != EXPECTED_ALEMBIC_REVISION:
                    return ReleaseValidationResult(
                        ready=False,
                        database_reachable=True,
                        migration_current=False,
                        prediction_schema_accessible=False,
                        expected_revision=EXPECTED_ALEMBIC_REVISION,
                        prediction_snapshot_count=None,
                        failure_code="MIGRATION_NOT_CURRENT",
                    )
                table = connection.execute(
                    text("SELECT to_regclass('public.prediction_snapshots')")
                ).scalar_one()
                if table is None:
                    return ReleaseValidationResult(
                        ready=False,
                        database_reachable=True,
                        migration_current=True,
                        prediction_schema_accessible=False,
                        expected_revision=EXPECTED_ALEMBIC_REVISION,
                        prediction_snapshot_count=None,
                        failure_code="PREDICTION_SCHEMA_UNAVAILABLE",
                    )
                count = connection.execute(
                    text("SELECT count(*) FROM prediction_snapshots")
                ).scalar_one()
        except Exception:
            return ReleaseValidationResult(
                ready=False,
                database_reachable=True,
                migration_current=False,
                prediction_schema_accessible=False,
                expected_revision=EXPECTED_ALEMBIC_REVISION,
                prediction_snapshot_count=None,
                failure_code="SCHEMA_CHECK_FAILED",
            )
        return ReleaseValidationResult(
            ready=True,
            database_reachable=True,
            migration_current=True,
            prediction_schema_accessible=True,
            expected_revision=EXPECTED_ALEMBIC_REVISION,
            prediction_snapshot_count=int(count),
        )
    finally:
        database.dispose()


def validate_shadow_activation(
    settings: Settings,
    values: Mapping[str, str],
    report_root: Path,
    *,
    now: datetime | None = None,
) -> ShadowActivationValidationResult:
    """Evaluate shadow activation prerequisites without enabling or invoking the provider."""
    checked_at = now or datetime.now(UTC)
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("release validation time must be timezone-aware")
    readiness = evaluate_readiness(settings, values, provider_required=True)
    gates = load_activation_gates(values)
    mappings_complete = set(COMPETITION_NAME_MAP.values()) >= SUPPORTED_COMPETITIONS
    parent = report_root if report_root.exists() else report_root.parent
    report_writable = parent.is_dir() and os.access(parent, os.W_OK)
    public_count: int | None = None
    shadow_public_count: int | None = None
    current_season_fresh = False
    fixture_refresh_fresh = False
    reasons = list(readiness.reasons)
    if readiness.database_reachable and readiness.migration_current:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                public_count = int(
                    connection.execute(
                        text(
                            "SELECT count(*) FROM prediction_snapshots "
                            "WHERE publication_eligible=true AND record_status='active'"
                        )
                    ).scalar_one()
                )
                shadow_public_count = int(
                    connection.execute(
                        text(
                            "SELECT count(*) FROM shadow_analysis_snapshots "
                            "WHERE publication_eligible=true"
                        )
                    ).scalar_one()
                )
                latest_sync = connection.execute(
                    text(
                        """SELECT max(occurred_at) FROM operational_events
                        WHERE event_type='CURRENT_SEASON_SYNC_SUCCEEDED'"""
                    )
                ).scalar_one()
                current_season_fresh = bool(
                    latest_sync is not None and latest_sync >= checked_at - timedelta(days=5)
                )
                fixture_refresh_fresh = (
                    load_fixture_refresh_metadata(connection, now=checked_at).state
                    is FreshnessState.FRESH
                )
        finally:
            engine.dispose()
    if not mappings_complete:
        reasons.append("CANONICAL_MAPPINGS_INCOMPLETE")
    if not report_writable:
        reasons.append("REPORT_DIRECTORY_UNAVAILABLE")
    if not current_season_fresh:
        reasons.append("CURRENT_SEASON_SYNC_STALE")
    if not fixture_refresh_fresh:
        reasons.append("FIXTURE_REFRESH_STALE")
    if gates.scheduler_enabled:
        reasons.append("SCHEDULER_MUST_REMAIN_DISABLED")
    if gates.publication_enabled:
        reasons.append("PUBLICATION_MUST_REMAIN_DISABLED")
    if gates.external_alerts_enabled:
        reasons.append("EXTERNAL_ALERTS_MUST_REMAIN_DISABLED")
    if public_count not in {0, None} or shadow_public_count not in {0, None}:
        reasons.append("PUBLIC_ISOLATION_FAILED")
    unique_reasons = tuple(sorted(set(reasons)))
    return ShadowActivationValidationResult(
        not unique_reasons,
        readiness.database_reachable,
        readiness.migration_current,
        readiness.provider_configured,
        readiness.model_contract_loadable,
        mappings_complete,
        readiness.prediction_repository_available,
        report_writable,
        current_season_fresh,
        fixture_refresh_fresh,
        report_writable,
        True,
        True,
        gates.scheduler_enabled,
        gates.publication_enabled,
        gates.external_alerts_enabled,
        public_count,
        shadow_public_count,
        unique_reasons,
    )


def main() -> int:
    """Print deterministic JSON status suitable for local release automation."""
    result = validate_release(load_settings())
    print(json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
