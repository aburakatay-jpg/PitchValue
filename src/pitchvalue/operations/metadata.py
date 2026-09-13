"""Durable operational freshness and report-location metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from sqlalchemy import Connection, text


class FreshnessState(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class ReportLocationState(StrEnum):
    DURABLE = "DURABLE"
    DETERMINISTIC = "DETERMINISTIC"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class FixtureRefreshMetadata:
    state: FreshnessState
    last_success_at: datetime | None
    last_failure_at: datetime | None
    evidence_source: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ReportLocation:
    state: ReportLocationState
    path: str | None
    source: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_fixture_refresh_metadata(
    connection: Connection,
    *,
    now: datetime,
    stale_after: timedelta = timedelta(days=5),
) -> FixtureRefreshMetadata:
    """Derive refresh freshness only from durable source/event evidence."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("refresh evaluation time must be timezone-aware")
    if stale_after <= timedelta(0):
        raise ValueError("stale boundary must be positive")
    events: dict[str, datetime] = {}
    for event_type, occurred_at in connection.execute(
        text(
            """SELECT event_type,max(occurred_at) AS occurred_at
            FROM operational_events
            WHERE event_type IN ('FIXTURE_REFRESH_SUCCEEDED','FIXTURE_REFRESH_FAILED')
            GROUP BY event_type"""
        )
    ):
        if occurred_at is not None:
            events[str(event_type)] = occurred_at
    source_seen = connection.execute(
        text(
            """SELECT max(last_seen_at) FROM source_entity_references
            WHERE entity_type='FIXTURE'"""
        )
    ).scalar_one()
    event_success = events.get("FIXTURE_REFRESH_SUCCEEDED")
    success_candidates = tuple(
        value for value in (event_success, source_seen) if isinstance(value, datetime)
    )
    success = max(success_candidates, default=None)
    failure = events.get("FIXTURE_REFRESH_FAILED")
    if failure is not None and (success is None or failure > success):
        return FixtureRefreshMetadata(FreshnessState.FAILED, success, failure, "operational_event")
    if success is None:
        return FixtureRefreshMetadata(FreshnessState.UNAVAILABLE, None, failure, "none")
    state = FreshnessState.FRESH if success >= now - stale_after else FreshnessState.STALE
    source = "fixture_refresh_event" if success == event_success else "fixture_source_last_seen"
    return FixtureRefreshMetadata(state, success, failure, source)


def resolve_report_location(
    connection: Connection,
    run_id: str,
    *,
    configured_root: Path | None = None,
) -> ReportLocation:
    """Resolve durable event metadata, with an explicit deterministic-root fallback."""
    if not run_id.strip():
        raise ValueError("run_id must be nonblank")
    durable = connection.execute(
        text(
            """SELECT metadata->>'report_directory' FROM operational_events
            WHERE run_id=:run_id AND event_type='REPORT_GENERATION_SUCCEEDED'
              AND length(btrim(metadata->>'report_directory')) > 0
            ORDER BY occurred_at DESC,event_id DESC LIMIT 1"""
        ),
        {"run_id": run_id},
    ).scalar_one_or_none()
    if durable is not None:
        return ReportLocation(ReportLocationState.DURABLE, str(durable), "operational_event")
    if configured_root is None:
        return ReportLocation(ReportLocationState.UNAVAILABLE, None, "not_recorded")
    scheduled_for = connection.execute(
        text("SELECT scheduled_for FROM engine_runs WHERE run_id=:run_id"),
        {"run_id": run_id},
    ).scalar_one_or_none()
    if scheduled_for is None:
        return ReportLocation(ReportLocationState.UNAVAILABLE, None, "run_not_found")
    path = configured_root / str(scheduled_for.year) / run_id
    return ReportLocation(ReportLocationState.DETERMINISTIC, str(path), "configured_root")
