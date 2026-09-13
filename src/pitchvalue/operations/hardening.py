"""Provider-neutral operational safety for manual and future scheduled runs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from sqlalchemy import Connection, create_engine, text

from pitchvalue.api.database import EXPECTED_ALEMBIC_REVISION
from pitchvalue.config import Settings
from pitchvalue.operations.events import (
    DeliveryVisibility,
    EventType,
    OperationalEvent,
    ReasonCode,
    severity_for,
)
from pitchvalue.operations.repository import persist_event
from pitchvalue.providers.five_dfa.client import FiveDfaError, ProviderErrorKind, RateLimitState
from pitchvalue.providers.five_dfa.config import load_five_dfa_config

RUN_LOCK_VERSION = "postgres_advisory_run_lock_v1"
READINESS_VERSION = "manual_engine_readiness_v1"
RECOVERY_VERSION = "stale_run_recovery_v1"
MAX_MANUAL_HORIZON = timedelta(days=7)
MAX_MANUAL_FIXTURES = 20
UNKNOWN_QUOTA_SAFE_CALLS = 8


class RunLockResult(StrEnum):
    RUN_LOCK_ACQUIRED = "RUN_LOCK_ACQUIRED"
    RUN_ALREADY_ACTIVE = "RUN_ALREADY_ACTIVE"
    RUN_LOCK_RELEASED = "RUN_LOCK_RELEASED"
    RUN_LOCK_STALE_RECOVERED = "RUN_LOCK_STALE_RECOVERED"


class HealthState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class FailureClass(StrEnum):
    SYSTEMIC = "SYSTEMIC"
    FIXTURE_LOCAL = "FIXTURE_LOCAL"
    MARKET_FAMILY_LOCAL = "MARKET_FAMILY_LOCAL"
    PROVIDER_TRANSIENT = "PROVIDER_TRANSIENT"
    PROVIDER_PERMANENT = "PROVIDER_PERMANENT"
    CONFIGURATION = "CONFIGURATION"
    PERSISTENCE = "PERSISTENCE"
    REPORTING = "REPORTING"


class RunLockError(RuntimeError):
    code = RunLockResult.RUN_ALREADY_ACTIVE


class ProviderQuotaError(RuntimeError):
    code = "PROVIDER_QUOTA_INSUFFICIENT"


@dataclass(frozen=True)
class ActivationGates:
    scheduler_enabled: bool
    publication_enabled: bool
    external_alerts_enabled: bool

    @property
    def safe_for_shadow(self) -> bool:
        return not (
            self.scheduler_enabled or self.publication_enabled or self.external_alerts_enabled
        )


@dataclass(frozen=True)
class ReadinessResult:
    state: HealthState
    database_reachable: bool
    migration_current: bool
    prediction_repository_available: bool
    model_contract_loadable: bool
    provider_configured: bool
    provider_required: bool
    scheduler_enabled: bool
    publication_enabled: bool
    external_alerts_enabled: bool
    reasons: tuple[str, ...]
    version: str = READINESS_VERSION

    @property
    def ready(self) -> bool:
        return self.state is not HealthState.UNHEALTHY

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class InfrastructureHealth:
    state: HealthState
    database_reachable: bool
    migration_current: bool | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class StaleRun:
    run_id: str
    started_at: datetime
    lock_active: bool


@dataclass(frozen=True)
class RecoveryResult:
    code: str
    run_id: str
    previous_status: str
    final_status: str


def _strict_flag(values: Mapping[str, str], name: str) -> bool:
    raw = values.get(name)
    if raw is None or not raw.strip():
        return False
    normalized = raw.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{name} must be explicitly true or false")
    return normalized == "true"


def load_activation_gates(values: Mapping[str, str]) -> ActivationGates:
    """Load fail-closed operational gates; missing never means enabled."""
    return ActivationGates(
        _strict_flag(values, "SCHEDULER_ENABLED"),
        _strict_flag(values, "PUBLICATION_ENABLED"),
        _strict_flag(values, "EXTERNAL_ALERTS_ENABLED"),
    )


def validate_manual_window(
    start_time: datetime, end_time: datetime, max_fixtures: int | None
) -> None:
    for name, value in (("start_time", start_time), ("end_time", end_time)):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
    if end_time <= start_time:
        raise ValueError("run window must be positive")
    if end_time - start_time > MAX_MANUAL_HORIZON:
        raise ValueError("run window exceeds the bounded manual horizon")
    if max_fixtures is not None and not 1 <= max_fixtures <= MAX_MANUAL_FIXTURES:
        raise ValueError("max_fixtures must be between 1 and 20")


def advisory_lock_key(semantic_identity: str) -> int:
    if not semantic_identity.strip():
        raise ValueError("semantic lock identity must be nonblank")
    unsigned = int.from_bytes(hashlib.sha256(semantic_identity.encode()).digest()[:8], "big")
    return unsigned - (1 << 64) if unsigned >= 1 << 63 else unsigned


@contextmanager
def run_lock(connection: Connection, semantic_identity: str) -> Iterator[RunLockResult]:
    """Hold a PostgreSQL session advisory lock for one semantic execution."""
    key = advisory_lock_key(f"{RUN_LOCK_VERSION}:{semantic_identity}")
    acquired = bool(
        connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar_one()
    )
    if not acquired:
        raise RunLockError(RunLockResult.RUN_ALREADY_ACTIVE.value)
    try:
        yield RunLockResult.RUN_LOCK_ACQUIRED
    finally:
        connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})


def ensure_provider_quota(
    states: tuple[RateLimitState, ...], *, expected_additional_calls: int
) -> None:
    if expected_additional_calls < 0:
        raise ValueError("expected calls must not be negative")
    if expected_additional_calls == 0:
        return
    known = next((item for item in reversed(states) if item.remaining is not None), None)
    if known is not None:
        if known.remaining is not None and known.remaining < expected_additional_calls:
            raise ProviderQuotaError("PROVIDER_QUOTA_INSUFFICIENT")
        return
    if expected_additional_calls > UNKNOWN_QUOTA_SAFE_CALLS:
        raise ProviderQuotaError("PROVIDER_QUOTA_UNKNOWN_BUDGET_EXCEEDED")


def classify_failure(error: BaseException, *, stage: str | None = None) -> FailureClass:
    if isinstance(error, FiveDfaError):
        if error.kind in {
            ProviderErrorKind.TIMEOUT,
            ProviderErrorKind.UNAVAILABLE,
            ProviderErrorKind.RATE_LIMIT,
        }:
            return FailureClass.PROVIDER_TRANSIENT
        return FailureClass.PROVIDER_PERMANENT
    if isinstance(error, ProviderQuotaError):
        return FailureClass.PROVIDER_TRANSIENT
    if stage == "fixture":
        return FailureClass.FIXTURE_LOCAL
    if stage == "market_family":
        return FailureClass.MARKET_FAMILY_LOCAL
    if stage == "configuration":
        return FailureClass.CONFIGURATION
    if stage == "persistence":
        return FailureClass.PERSISTENCE
    if stage == "reporting":
        return FailureClass.REPORTING
    return FailureClass.SYSTEMIC


def failure_event_contract(failure: FailureClass) -> tuple[EventType, ReasonCode]:
    """Map operational failure classes onto the existing durable event taxonomy."""
    return {
        FailureClass.SYSTEMIC: (EventType.RUN_FAILED, ReasonCode.DB_UNAVAILABLE),
        FailureClass.FIXTURE_LOCAL: (EventType.MATCH_ANALYSIS_FAILED, ReasonCode.FIXTURE_INVALID),
        FailureClass.MARKET_FAMILY_LOCAL: (
            EventType.DATA_GATE_FAILED,
            ReasonCode.MARKET_FAMILY_INCOMPLETE,
        ),
        FailureClass.PROVIDER_TRANSIENT: (
            EventType.PROVIDER_FAILED,
            ReasonCode.PROVIDER_UNAVAILABLE,
        ),
        FailureClass.PROVIDER_PERMANENT: (
            EventType.PROVIDER_FAILED,
            ReasonCode.PROVIDER_SCHEMA_INVALID,
        ),
        FailureClass.CONFIGURATION: (
            EventType.READINESS_FAILED,
            ReasonCode.CONFIG_VERSION_MISMATCH,
        ),
        FailureClass.PERSISTENCE: (EventType.PERSISTENCE_FAILED, ReasonCode.PERSISTENCE_FAILED),
        FailureClass.REPORTING: (
            EventType.REPORT_ARCHIVE_FAILED,
            ReasonCode.REPORT_ARCHIVE_FAILED,
        ),
    }[failure]


def evaluate_health(settings: Settings) -> InfrastructureHealth:
    """Evaluate infrastructure health without imposing run-specific readiness."""
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        if revision != EXPECTED_ALEMBIC_REVISION:
            return InfrastructureHealth(
                HealthState.DEGRADED, True, False, ("MIGRATION_NOT_CURRENT",)
            )
        return InfrastructureHealth(HealthState.HEALTHY, True, True, ())
    except Exception:
        return InfrastructureHealth(HealthState.UNHEALTHY, False, None, ("DATABASE_UNAVAILABLE",))
    finally:
        engine.dispose()


def evaluate_readiness(
    settings: Settings,
    values: Mapping[str, str],
    *,
    provider_required: bool,
) -> ReadinessResult:
    reasons: list[str] = []
    gates = load_activation_gates(values)
    database_reachable = migration_current = repository_available = False
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
            database_reachable = True
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            migration_current = revision == EXPECTED_ALEMBIC_REVISION
            repository_available = (
                connection.execute(
                    text("SELECT to_regclass('public.shadow_analysis_snapshots')")
                ).scalar_one()
                is not None
            )
    except Exception:
        reasons.append("DATABASE_UNAVAILABLE")
    finally:
        engine.dispose()
    if database_reachable and not migration_current:
        reasons.append("MIGRATION_NOT_CURRENT")
    if database_reachable and not repository_available:
        reasons.append("PERSISTENCE_REPOSITORY_UNAVAILABLE")
    try:
        from pitchvalue.ml.config import MLTrainingConfig

        model_loadable = bool(MLTrainingConfig().model_version)
    except Exception:
        model_loadable = False
        reasons.append("MODEL_CONTRACT_UNAVAILABLE")
    provider_configured = bool(values.get("FIVEDFA_API_KEY", "").strip())
    if provider_required:
        try:
            load_five_dfa_config(values)
            provider_configured = True
        except Exception:
            provider_configured = False
            reasons.append("PROVIDER_CONFIGURATION_INVALID")
    state = (
        HealthState.HEALTHY
        if not reasons
        else HealthState.UNHEALTHY
        if (
            not database_reachable
            or not migration_current
            or not model_loadable
            or (provider_required and not provider_configured)
        )
        else HealthState.DEGRADED
    )
    return ReadinessResult(
        state,
        database_reachable,
        migration_current,
        repository_available,
        model_loadable,
        provider_configured,
        provider_required,
        gates.scheduler_enabled,
        gates.publication_enabled,
        gates.external_alerts_enabled,
        tuple(sorted(reasons)),
    )


def validate_report_root(path: Path) -> None:
    parent = path if path.exists() else path.parent
    if not parent.exists() or not parent.is_dir():
        raise ValueError("report path parent is unavailable")


def stale_runs(
    connection: Connection, *, now: datetime, older_than: timedelta
) -> tuple[StaleRun, ...]:
    if now.tzinfo is None or older_than <= timedelta(0):
        raise ValueError("stale-run boundary is invalid")
    rows = connection.execute(
        text(
            """SELECT run_id,started_at FROM engine_runs
            WHERE status='RUNNING' AND started_at IS NOT NULL AND started_at <= :cutoff
            ORDER BY started_at,run_id"""
        ),
        {"cutoff": now - older_than},
    ).all()
    results: list[StaleRun] = []
    for run_id, started_at in rows:
        key = advisory_lock_key(f"{RUN_LOCK_VERSION}:{run_id}")
        acquired = bool(
            connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar_one()
        )
        if acquired:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
        results.append(StaleRun(str(run_id), started_at, not acquired))
    return tuple(results)


def recover_stale_run(
    connection: Connection,
    run_id: str,
    *,
    now: datetime,
    older_than: timedelta,
) -> RecoveryResult:
    candidates = {
        item.run_id: item for item in stale_runs(connection, now=now, older_than=older_than)
    }
    candidate = candidates.get(run_id)
    if candidate is None:
        status = connection.execute(
            text("SELECT status FROM engine_runs WHERE run_id=:run_id"), {"run_id": run_id}
        ).scalar_one_or_none()
        final_status = str(status or "NOT_FOUND")
        return RecoveryResult("RUN_NOT_STALE", run_id, final_status, final_status)
    if candidate.lock_active:
        return RecoveryResult("RUN_ALREADY_ACTIVE", run_id, "RUNNING", "RUNNING")
    with run_lock(connection, run_id):
        changed = connection.execute(
            text(
                """UPDATE engine_runs SET status='FAILED',finished_at=:now
                WHERE run_id=:run_id AND status='RUNNING' AND started_at <= :cutoff"""
            ),
            {"run_id": run_id, "now": now, "cutoff": now - older_than},
        ).rowcount
        if changed != 1:
            return RecoveryResult("RUN_STATE_CHANGED", run_id, "RUNNING", "UNKNOWN")
        event = OperationalEvent(
            OperationalEvent.deterministic_id(
                EventType.RUN_FAILED, run_id, "stale_run_recovery", RECOVERY_VERSION
            ),
            EventType.RUN_FAILED,
            RECOVERY_VERSION,
            now.astimezone(UTC),
            severity_for(EventType.RUN_FAILED),
            run_id,
            "stale_run_recovery",
            {"recovery": RunLockResult.RUN_LOCK_STALE_RECOVERED.value},
            DeliveryVisibility.OPERATIONS,
            run_id=run_id,
            reason_code=ReasonCode.PERSISTENCE_FAILED,
        )
        persist_event(connection, event)
    return RecoveryResult(RunLockResult.RUN_LOCK_STALE_RECOVERED.value, run_id, "RUNNING", "FAILED")


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
