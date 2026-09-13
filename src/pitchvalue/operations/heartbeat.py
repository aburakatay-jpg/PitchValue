"""Provider-independent scheduler heartbeat and missed-run diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import Connection, text

from pitchvalue.operations.hardening import HealthState
from pitchvalue.operations.schedule import previous_configured_run

HEARTBEAT_VERSION = "provider_neutral_scheduler_heartbeat_v1"


class HeartbeatCode(StrEnum):
    SCHEDULER_DISABLED = "SCHEDULER_DISABLED"
    EXPECTED_RUN_NOT_STARTED = "EXPECTED_RUN_NOT_STARTED"
    RUN_STUCK = "RUN_STUCK"
    PREVIOUS_RUN_FAILED = "PREVIOUS_RUN_FAILED"
    RUN_PARTIAL = "RUN_PARTIAL"
    HEALTHY = "HEALTHY"


class FreshnessState(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class RunHeartbeatEvidence:
    run_id: str
    scheduled_for: datetime
    status: str
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True)
class HeartbeatResult:
    state: HealthState
    code: HeartbeatCode
    expected_run: datetime | None
    run_id: str | None
    current_season_sync: FreshnessState
    fixture_refresh: FreshnessState
    report_archive: FreshnessState
    reasons: tuple[str, ...]
    version: str = HEARTBEAT_VERSION

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_heartbeat(
    *,
    now: datetime,
    scheduler_enabled: bool,
    evidence: tuple[RunHeartbeatEvidence, ...],
    latest_sync: datetime | None,
    latest_fixture_refresh: datetime | None,
    latest_report_failure: datetime | None,
    grace: timedelta = timedelta(minutes=30),
    stuck_after: timedelta = timedelta(hours=2),
    freshness_after: timedelta = timedelta(days=5),
) -> HeartbeatResult:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("heartbeat time must be timezone-aware")
    if min(grace, stuck_after, freshness_after) <= timedelta(0):
        raise ValueError("heartbeat boundaries must be positive")
    sync = _freshness(latest_sync, now, freshness_after)
    refresh = _freshness(latest_fixture_refresh, now, freshness_after)
    report = (
        FreshnessState.STALE
        if latest_report_failure is not None and latest_report_failure >= now - freshness_after
        else FreshnessState.FRESH
    )
    if not scheduler_enabled:
        return HeartbeatResult(
            HealthState.HEALTHY,
            HeartbeatCode.SCHEDULER_DISABLED,
            None,
            None,
            sync,
            refresh,
            report,
            ("SCHEDULER_DISABLED_READY_FOR_ACTIVATION",),
        )
    expected = previous_configured_run(now - grace)
    matching = tuple(item for item in evidence if item.scheduled_for == expected)
    if not matching:
        return _result(
            HealthState.DEGRADED,
            HeartbeatCode.EXPECTED_RUN_NOT_STARTED,
            expected,
            None,
            sync,
            refresh,
            report,
        )
    if len(matching) != 1:
        return _result(
            HealthState.UNHEALTHY,
            HeartbeatCode.RUN_STUCK,
            expected,
            None,
            sync,
            refresh,
            report,
            "DUPLICATE_SCHEDULED_RUN_EVIDENCE",
        )
    run = matching[0]
    if (
        run.status == "RUNNING"
        and run.started_at is not None
        and run.started_at <= now - stuck_after
    ):
        return _result(
            HealthState.UNHEALTHY,
            HeartbeatCode.RUN_STUCK,
            expected,
            run.run_id,
            sync,
            refresh,
            report,
        )
    if run.status == "FAILED":
        return _result(
            HealthState.UNHEALTHY,
            HeartbeatCode.PREVIOUS_RUN_FAILED,
            expected,
            run.run_id,
            sync,
            refresh,
            report,
        )
    if run.status == "PARTIAL_WITH_QUARANTINES":
        return _result(
            HealthState.DEGRADED,
            HeartbeatCode.RUN_PARTIAL,
            expected,
            run.run_id,
            sync,
            refresh,
            report,
        )
    return _result(
        HealthState.HEALTHY,
        HeartbeatCode.HEALTHY,
        expected,
        run.run_id,
        sync,
        refresh,
        report,
    )


def load_heartbeat(
    connection: Connection, *, now: datetime, scheduler_enabled: bool
) -> HeartbeatResult:
    rows = connection.execute(
        text(
            """SELECT run_id,scheduled_for,status,started_at,finished_at
            FROM engine_runs ORDER BY scheduled_for,run_id"""
        )
    ).all()
    evidence = tuple(RunHeartbeatEvidence(*row) for row in rows)
    event_times: dict[str, datetime] = {}
    for event_type, occurred_at in connection.execute(
        text(
            """SELECT event_type,max(occurred_at) FROM operational_events
            WHERE event_type IN (
                'CURRENT_SEASON_SYNC_SUCCEEDED','FIXTURE_REFRESH_SUCCEEDED',
                'REPORT_ARCHIVE_FAILED')
            GROUP BY event_type"""
        )
    ):
        if occurred_at is not None:
            event_times[str(event_type)] = occurred_at
    return evaluate_heartbeat(
        now=now,
        scheduler_enabled=scheduler_enabled,
        evidence=evidence,
        latest_sync=event_times.get("CURRENT_SEASON_SYNC_SUCCEEDED"),
        latest_fixture_refresh=event_times.get("FIXTURE_REFRESH_SUCCEEDED"),
        latest_report_failure=event_times.get("REPORT_ARCHIVE_FAILED"),
    )


def _freshness(value: datetime | None, now: datetime, boundary: timedelta) -> FreshnessState:
    if value is None:
        return FreshnessState.UNAVAILABLE
    return FreshnessState.FRESH if value >= now - boundary else FreshnessState.STALE


def _result(
    state: HealthState,
    code: HeartbeatCode,
    expected: datetime,
    run_id: str | None,
    sync: FreshnessState,
    refresh: FreshnessState,
    report: FreshnessState,
    *extra: str,
) -> HeartbeatResult:
    reasons = list(extra)
    if sync is FreshnessState.STALE:
        reasons.append("CURRENT_SEASON_SYNC_STALE")
    if refresh is FreshnessState.STALE:
        reasons.append("FIXTURE_REFRESH_STALE")
    if report is FreshnessState.STALE:
        reasons.append("REPORT_GENERATION_FAILED")
    if reasons and state is HealthState.HEALTHY:
        state = HealthState.DEGRADED
    return HeartbeatResult(
        state, code, expected, run_id, sync, refresh, report, tuple(sorted(reasons))
    )
