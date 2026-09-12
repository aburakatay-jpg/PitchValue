"""Configured run windows without activating a scheduler."""

from __future__ import annotations

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
