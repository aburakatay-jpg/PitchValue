"""Machine-readable, read-only release prerequisite validation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from sqlalchemy import text

from pitchvalue.api.database import EXPECTED_ALEMBIC_REVISION, DatabaseResource
from pitchvalue.config import Settings, load_settings


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


def main() -> int:
    """Print deterministic JSON status suitable for local release automation."""
    result = validate_release(load_settings())
    print(json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
