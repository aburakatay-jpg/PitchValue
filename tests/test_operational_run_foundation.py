from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from pitchvalue.operations import (
    EngineRun,
    Quarantine,
    QuarantineScope,
    QuarantineStatus,
    RunStatus,
    RunType,
    fixture_horizon,
    includes_kickoff,
)
from pitchvalue.operations.schedule import next_configured_run


def _run() -> EngineRun:
    scheduled = datetime(2026, 9, 15, 8, tzinfo=UTC)
    return EngineRun(
        run_id="run-2026-09-15",
        run_type=RunType.FULL,
        scheduled_for=scheduled,
        started_at=None,
        finished_at=None,
        status=RunStatus.SCHEDULED,
        schedule_version="provider_neutral_schedule_v1",
        fixture_horizon=fixture_horizon(scheduled, "Europe/Istanbul"),
        model_version="raw_ml_v1",
        feature_profile="FOOTBALL_PERFORMANCE_ONLY",
        orchestrator_version="orchestrator_v1",
        policy_version="policy_v1",
        dq_version="dq_evidence_v1",
        market_stability_version="market_stability_evidence_v1",
        calibration_confidence_version="calibration_confidence_research_v1",
        no_vig_version="task11_proportional_no_vig_v1",
        provider_contract_version="provider_contract_placeholder_v1",
    )


def test_run_contract_is_immutable_and_provider_neutral() -> None:
    run = _run()
    assert run.status is RunStatus.SCHEDULED
    assert run.fixture_horizon.local_dates[0].isoformat() == "2026-09-15"
    with pytest.raises(FrozenInstanceError):
        run.run_id = "changed"  # type: ignore[misc]


def test_tuesday_and_friday_local_fixture_horizons() -> None:
    tuesday = fixture_horizon(datetime(2026, 9, 15, 8, tzinfo=UTC), "Europe/Istanbul")
    friday = fixture_horizon(datetime(2026, 9, 18, 8, tzinfo=UTC), "Europe/Istanbul")
    assert [item.isoformat() for item in tuesday.local_dates] == [
        "2026-09-15",
        "2026-09-16",
        "2026-09-17",
    ]
    assert [item.isoformat() for item in friday.local_dates] == [
        "2026-09-18",
        "2026-09-19",
        "2026-09-20",
        "2026-09-21",
    ]


def test_fixture_inclusion_uses_local_date_not_utc_date() -> None:
    horizon = fixture_horizon(datetime(2026, 9, 18, 8, tzinfo=UTC), "Europe/Istanbul")
    assert includes_kickoff(horizon, datetime(2026, 9, 17, 21, 30, tzinfo=UTC))
    assert not includes_kickoff(horizon, datetime(2026, 9, 21, 21, 30, tzinfo=UTC))


def test_dst_and_kickoff_revision_crossing_local_date_are_explicit() -> None:
    horizon = fixture_horizon(datetime(2026, 10, 23, 8, tzinfo=UTC), "Europe/London")
    before_revision = datetime(2026, 10, 26, 0, 30, tzinfo=UTC)
    after_revision = datetime(2026, 10, 27, 0, 30, tzinfo=UTC)
    assert includes_kickoff(horizon, before_revision)
    assert not includes_kickoff(horizon, after_revision)


def test_next_run_is_configured_only_and_no_scheduler_is_activated() -> None:
    assert next_configured_run(datetime(2026, 9, 15, 8, tzinfo=UTC)) == datetime(
        2026, 9, 18, 8, tzinfo=UTC
    )


def test_quarantine_scope_preserves_independent_market_families() -> None:
    quarantine = Quarantine(
        Quarantine.deterministic_id(
            "run-1", 7, QuarantineScope.MARKET_FAMILY, "BTTS", "MARKET_FAMILY_INCOMPLETE"
        ),
        "run-1",
        7,
        "BTTS",
        QuarantineScope.MARKET_FAMILY,
        "MARKET_FAMILY_INCOMPLETE",
        datetime(2026, 9, 12, tzinfo=UTC),
        {"selection": "NO"},
        QuarantineStatus.ACTIVE,
    )
    assert quarantine.market_family == "BTTS"
    assert replace(quarantine, status=QuarantineStatus.RESOLVED).status is QuarantineStatus.RESOLVED
    with pytest.raises(ValueError, match="match quarantine"):
        replace(quarantine, scope=QuarantineScope.MATCH)


def test_naive_run_and_invalid_schedule_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(_run(), scheduled_for=datetime(2026, 9, 15, 8))
    with pytest.raises(ValueError, match="configured run"):
        fixture_horizon(datetime(2026, 9, 16, 8, tzinfo=UTC), "Europe/Istanbul")
