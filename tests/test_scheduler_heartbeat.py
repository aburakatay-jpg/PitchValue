from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pitchvalue.operations.hardening import HealthState
from pitchvalue.operations.heartbeat import (
    FreshnessState,
    HeartbeatCode,
    RunHeartbeatEvidence,
    evaluate_heartbeat,
)
from pitchvalue.operations.schedule import (
    configured_runs_between,
    fixture_horizon,
    previous_configured_run,
    schedule_run_identity,
)

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)
EXPECTED = datetime(2026, 9, 18, 8, tzinfo=UTC)


def test_configured_schedule_is_deterministic_and_duplicate_safe() -> None:
    runs = configured_runs_between(
        datetime(2026, 9, 14, tzinfo=UTC), datetime(2026, 9, 22, tzinfo=UTC)
    )
    assert runs == (
        datetime(2026, 9, 15, 8, tzinfo=UTC),
        datetime(2026, 9, 18, 8, tzinfo=UTC),
    )
    assert previous_configured_run(NOW) == EXPECTED
    assert schedule_run_identity(EXPECTED, "Europe/Istanbul") == schedule_run_identity(
        EXPECTED, "Europe/Istanbul"
    )


def test_utc_trigger_uses_local_calendar_dates_across_dst() -> None:
    winter = fixture_horizon(datetime(2026, 3, 24, 8, tzinfo=UTC), "Europe/London")
    summer = fixture_horizon(datetime(2026, 3, 31, 8, tzinfo=UTC), "Europe/London")
    west = fixture_horizon(datetime(2026, 9, 18, 8, tzinfo=UTC), "Pacific/Honolulu")
    assert winter.local_dates[0].isoformat() == "2026-03-24"
    assert summer.local_dates[0].isoformat() == "2026-03-31"
    assert west.local_dates[0].isoformat() == "2026-09-17"


def test_disabled_scheduler_is_ready_without_fabricating_run_evidence() -> None:
    result = evaluate_heartbeat(
        now=NOW,
        scheduler_enabled=False,
        evidence=(),
        latest_sync=None,
        latest_fixture_refresh=None,
        latest_report_failure=None,
    )
    assert result.state is HealthState.HEALTHY
    assert result.code is HeartbeatCode.SCHEDULER_DISABLED
    assert result.current_season_sync is FreshnessState.UNAVAILABLE


@pytest.mark.parametrize(
    ("evidence", "code", "state"),
    [
        ((), HeartbeatCode.EXPECTED_RUN_NOT_STARTED, HealthState.DEGRADED),
        (
            (RunHeartbeatEvidence("stuck", EXPECTED, "RUNNING", NOW - timedelta(hours=3), None),),
            HeartbeatCode.RUN_STUCK,
            HealthState.UNHEALTHY,
        ),
        (
            (RunHeartbeatEvidence("failed", EXPECTED, "FAILED", NOW, NOW),),
            HeartbeatCode.PREVIOUS_RUN_FAILED,
            HealthState.UNHEALTHY,
        ),
        (
            (RunHeartbeatEvidence("partial", EXPECTED, "PARTIAL_WITH_QUARANTINES", NOW, NOW),),
            HeartbeatCode.RUN_PARTIAL,
            HealthState.DEGRADED,
        ),
        (
            (RunHeartbeatEvidence("ok", EXPECTED, "SUCCEEDED", NOW, NOW),),
            HeartbeatCode.HEALTHY,
            HealthState.HEALTHY,
        ),
    ],
)
def test_heartbeat_classifies_missed_stuck_failed_partial_and_success(
    evidence: tuple[RunHeartbeatEvidence, ...],
    code: HeartbeatCode,
    state: HealthState,
) -> None:
    result = evaluate_heartbeat(
        now=NOW,
        scheduler_enabled=True,
        evidence=evidence,
        latest_sync=NOW,
        latest_fixture_refresh=NOW,
        latest_report_failure=None,
    )
    assert result.code is code
    assert result.state is state


def test_heartbeat_exposes_stale_sync_refresh_and_report_failure() -> None:
    result = evaluate_heartbeat(
        now=NOW,
        scheduler_enabled=True,
        evidence=(RunHeartbeatEvidence("ok", EXPECTED, "SUCCEEDED", NOW, NOW),),
        latest_sync=NOW - timedelta(days=6),
        latest_fixture_refresh=NOW - timedelta(days=6),
        latest_report_failure=NOW - timedelta(hours=1),
    )
    assert result.reasons == (
        "CURRENT_SEASON_SYNC_STALE",
        "FIXTURE_REFRESH_STALE",
        "REPORT_GENERATION_FAILED",
    )
