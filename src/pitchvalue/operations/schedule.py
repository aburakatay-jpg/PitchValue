"""Configured run windows without activating a scheduler."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pitchvalue.operations.contracts import FixtureHorizon

SCHEDULE_VERSION = "provider_neutral_schedule_v1"
FIXTURE_HORIZON_POLICY_VERSION = "local_fixture_date_window_v1"


@dataclass(frozen=True)
class ScheduleDefinition:
    weekday: int
    at_utc: time
    covered_day_offsets: tuple[int, ...]


TUESDAY_RUN = ScheduleDefinition(1, time(8, tzinfo=UTC), (0, 1, 2))
FRIDAY_RUN = ScheduleDefinition(4, time(8, tzinfo=UTC), (0, 1, 2, 3))
RUN_SCHEDULE = (TUESDAY_RUN, FRIDAY_RUN)


def fixture_horizon(scheduled_for: datetime, fixture_timezone: str) -> FixtureHorizon:
    """Resolve configured coverage using fixture-local dates, including DST rules."""
    if scheduled_for.tzinfo is None or scheduled_for.utcoffset() is None:
        raise ValueError("scheduled_for must be timezone-aware")
    scheduled_utc = scheduled_for.astimezone(UTC)
    definition = next(
        (
            item
            for item in RUN_SCHEDULE
            if item.weekday == scheduled_utc.weekday()
            and item.at_utc.replace(tzinfo=None) == scheduled_utc.timetz().replace(tzinfo=None)
        ),
        None,
    )
    if definition is None:
        raise ValueError("scheduled_for is not a configured run time")
    local_start = scheduled_utc.astimezone(ZoneInfo(fixture_timezone)).date()
    return FixtureHorizon(
        fixture_timezone,
        tuple(local_start + timedelta(days=offset) for offset in definition.covered_day_offsets),
        FIXTURE_HORIZON_POLICY_VERSION,
    )


def includes_kickoff(horizon: FixtureHorizon, kickoff: datetime) -> bool:
    if kickoff.tzinfo is None or kickoff.utcoffset() is None:
        raise ValueError("kickoff must be timezone-aware")
    return kickoff.astimezone(ZoneInfo(horizon.timezone_name)).date() in horizon.local_dates


def next_configured_run(after: datetime) -> datetime:
    if after.tzinfo is None or after.utcoffset() is None:
        raise ValueError("after must be timezone-aware")
    cursor = after.astimezone(UTC)
    candidates: list[datetime] = []
    for days in range(8):
        candidate_date: date = cursor.date() + timedelta(days=days)
        for definition in RUN_SCHEDULE:
            if candidate_date.weekday() == definition.weekday:
                candidate = datetime.combine(candidate_date, definition.at_utc)
                if candidate > cursor:
                    candidates.append(candidate)
    return min(candidates)


def previous_configured_run(at_or_before: datetime) -> datetime:
    if at_or_before.tzinfo is None or at_or_before.utcoffset() is None:
        raise ValueError("at_or_before must be timezone-aware")
    cursor = at_or_before.astimezone(UTC)
    candidates: list[datetime] = []
    for days in range(8):
        candidate_date = cursor.date() - timedelta(days=days)
        for definition in RUN_SCHEDULE:
            if candidate_date.weekday() == definition.weekday:
                candidate = datetime.combine(candidate_date, definition.at_utc)
                if candidate <= cursor:
                    candidates.append(candidate)
    return max(candidates)


def configured_runs_between(start: datetime, end: datetime) -> tuple[datetime, ...]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("schedule boundaries must be timezone-aware")
    if end <= start:
        raise ValueError("schedule interval must be positive")
    cursor = start.astimezone(UTC)
    stop = end.astimezone(UTC)
    runs: list[datetime] = []
    candidate = next_configured_run(cursor - timedelta(microseconds=1))
    while candidate < stop:
        if candidate >= cursor:
            runs.append(candidate)
        candidate = next_configured_run(candidate)
    return tuple(runs)


def schedule_run_identity(scheduled_for: datetime, fixture_timezone: str) -> str:
    horizon = fixture_horizon(scheduled_for, fixture_timezone)
    value = "|".join(
        (
            SCHEDULE_VERSION,
            scheduled_for.astimezone(UTC).isoformat(),
            horizon.timezone_name,
            *(item.isoformat() for item in horizon.local_dates),
        )
    )
    return "scheduled-shadow-" + hashlib.sha256(value.encode()).hexdigest()[:16]
