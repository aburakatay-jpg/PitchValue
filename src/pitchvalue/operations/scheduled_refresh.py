"""Bounded Tue/Fri fixture refresh without Engine, odds, or stale-date scans."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.operations.contracts import FixtureHorizon
from pitchvalue.operations.current_season import (
    CurrentSeasonPersistenceResult,
    persist_current_season_payloads,
)
from pitchvalue.operations.events import (
    DeliveryVisibility,
    EventType,
    OperationalEvent,
    severity_for,
)
from pitchvalue.operations.repository import persist_event
from pitchvalue.operations.schedule import SCHEDULE_VERSION, fixture_horizon, schedule_run_identity
from pitchvalue.providers.five_dfa.adapter import FiveDfaFreeAdapter
from pitchvalue.providers.five_dfa.client import FiveDfaClient, RateLimitState
from pitchvalue.providers.five_dfa.config import load_five_dfa_project_config

FIXTURE_TIMEZONE = "Europe/Istanbul"
EVENT_VERSION = "scheduled_fixture_refresh_v1"
SOURCE_COMPONENT = "scheduled_fixture_refresh"


class FixturePayloadAdapter(Protocol):
    def fixture_payloads(
        self, *, start_time: datetime, end_time: datetime, league_id: str | None = None
    ) -> tuple[tuple[Mapping[str, object], ...], tuple[RateLimitState, ...]]: ...


@dataclass(frozen=True)
class ScheduledPayloadBatch:
    scheduled_for: datetime
    horizon: FixtureHorizon
    logical_run_id: str
    payloads: tuple[Mapping[str, object], ...]
    rate_limit_states: tuple[RateLimitState, ...]


@dataclass(frozen=True)
class ScheduledRefreshResult:
    scheduled_for: str
    logical_run_id: str
    run_id: str
    attempt: int
    local_dates: tuple[str, ...]
    date_slice_count: int
    provider_payload_count: int
    canonical_fixture_count: int
    result: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _local_date_window(local_date: date, timezone_name: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    start = datetime.combine(local_date, time.min, zone).astimezone(UTC)
    end = datetime.combine(local_date + timedelta(days=1), time.min, zone).astimezone(UTC)
    if end - start > timedelta(days=1):
        raise ValueError("scheduled fixture window exceeds the provider 24-hour bound")
    return start, end


def collect_scheduled_payloads(
    adapter: FixturePayloadAdapter,
    scheduled_for: datetime,
    *,
    fixture_timezone: str = FIXTURE_TIMEZONE,
) -> ScheduledPayloadBatch:
    """Fetch exactly one paginated fixture sequence for each configured horizon date."""
    horizon = fixture_horizon(scheduled_for, fixture_timezone)
    logical_run_id = schedule_run_identity(scheduled_for, fixture_timezone)
    payloads: list[Mapping[str, object]] = []
    rate_states: list[RateLimitState] = []
    for local_date in horizon.local_dates:
        start_time, end_time = _local_date_window(local_date, horizon.timezone_name)
        rows, states = adapter.fixture_payloads(start_time=start_time, end_time=end_time)
        payloads.extend(rows)
        rate_states.extend(states)
    return ScheduledPayloadBatch(
        scheduled_for.astimezone(UTC),
        horizon,
        logical_run_id,
        tuple(payloads),
        tuple(rate_states),
    )


def _event_metadata(
    batch: ScheduledPayloadBatch,
    sync: CurrentSeasonPersistenceResult,
    attempt: int,
) -> dict[str, str]:
    return {
        "source": "scheduled",
        "scheduled_for": batch.scheduled_for.isoformat(),
        "logical_run_id": batch.logical_run_id,
        "run_id": sync.run_id,
        "attempt": str(attempt),
        "date_slice_count": str(len(batch.horizon.local_dates)),
        "provider_fixture_count": str(len(batch.payloads)),
        "canonical_fixture_count": str(len(sync.match_ids)),
        "result": sync.terminal_status.value,
    }


def persist_scheduled_payloads(
    connection: Connection,
    batch: ScheduledPayloadBatch,
    *,
    started_at: datetime,
    finished_at: datetime | None = None,
    clock: Callable[[], datetime] = _utc_now,
) -> ScheduledRefreshResult:
    """Persist a collected scheduled batch and complete its existing-schema audit evidence."""
    started_at = _as_utc(started_at, "started_at")
    if started_at < batch.scheduled_for:
        raise ValueError("scheduled_for cannot be in the future")

    window_start, _ = _local_date_window(batch.horizon.local_dates[0], batch.horizon.timezone_name)
    _, window_end = _local_date_window(batch.horizon.local_dates[-1], batch.horizon.timezone_name)
    sync = persist_current_season_payloads(
        connection,
        batch.payloads,
        logical_run_id=batch.logical_run_id,
        window_start=window_start,
        window_end=window_end,
        prediction_as_of=started_at,
    )
    completed_at = _as_utc(finished_at or clock(), "finished_at")
    if completed_at < started_at:
        raise ValueError("finished_at cannot precede started_at")
    horizon_json = json.dumps(
        {
            "timezone_name": batch.horizon.timezone_name,
            "local_dates": [item.isoformat() for item in batch.horizon.local_dates],
            "policy_version": batch.horizon.policy_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    changed = connection.execute(
        text(
            """UPDATE engine_runs
            SET scheduled_for=:scheduled_for, finished_at=:finished_at, status=:status,
                schedule_version=:schedule_version, fixture_horizon=CAST(:fixture_horizon AS jsonb)
            WHERE run_id=:run_id AND status='RUNNING'"""
        ),
        {
            "scheduled_for": batch.scheduled_for,
            "finished_at": completed_at,
            "status": sync.terminal_status.value,
            "schedule_version": SCHEDULE_VERSION,
            "fixture_horizon": horizon_json,
            "run_id": sync.run_id,
        },
    ).rowcount
    if changed != 1:
        raise RuntimeError("scheduled refresh run could not be completed")
    attempt = int(
        connection.execute(
            text("SELECT attempt_number FROM engine_runs WHERE run_id=:run_id"),
            {"run_id": sync.run_id},
        ).scalar_one()
    )
    metadata = _event_metadata(batch, sync, attempt)
    for event_type, occurred_at, logical_key in (
        (EventType.FIXTURE_REFRESH_STARTED, started_at, "scheduled-started"),
        (EventType.RUN_SUCCEEDED, completed_at, "scheduled-completed"),
    ):
        event = OperationalEvent(
            OperationalEvent.deterministic_id(
                event_type, sync.run_id, SOURCE_COMPONENT, logical_key
            ),
            event_type,
            EVENT_VERSION,
            occurred_at,
            severity_for(event_type),
            sync.run_id,
            SOURCE_COMPONENT,
            metadata,
            DeliveryVisibility.OPERATIONS,
            run_id=sync.run_id,
            provider_domain="fixtures",
        )
        if not persist_event(connection, event):
            raise RuntimeError("scheduled refresh event evidence could not be persisted")
    return ScheduledRefreshResult(
        batch.scheduled_for.isoformat(),
        batch.logical_run_id,
        sync.run_id,
        attempt,
        tuple(item.isoformat() for item in batch.horizon.local_dates),
        len(batch.horizon.local_dates),
        len(batch.payloads),
        len(sync.match_ids),
        sync.terminal_status.value,
    )


def run_scheduled_refresh(
    database_url: str,
    adapter: FixturePayloadAdapter,
    scheduled_for: datetime,
    *,
    clock: Callable[[], datetime] = _utc_now,
) -> ScheduledRefreshResult:
    """Run one validated scheduled refresh; the workflow is the activation boundary."""
    started_at = _as_utc(clock(), "clock result")
    if started_at < scheduled_for.astimezone(UTC):
        raise ValueError("scheduled_for cannot be in the future")
    batch = collect_scheduled_payloads(adapter, scheduled_for)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            return persist_scheduled_payloads(
                connection,
                batch,
                started_at=started_at,
                clock=clock,
            )
    finally:
        engine.dispose()


def _scheduled_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("scheduled_for must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("scheduled_for must be timezone-aware")
    scheduled = parsed.astimezone(UTC)
    try:
        fixture_horizon(scheduled, FIXTURE_TIMEZONE)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return scheduled


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded Tue/Fri fixture refresh")
    parser.add_argument("--scheduled-for", required=True, type=_scheduled_timestamp)
    args = parser.parse_args()
    settings = load_settings()
    config = load_five_dfa_project_config(os.environ)
    with FiveDfaClient(config) as client:
        result = run_scheduled_refresh(
            settings.database_url,
            FiveDfaFreeAdapter(client),
            args.scheduled_for,
        )
    print(json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
