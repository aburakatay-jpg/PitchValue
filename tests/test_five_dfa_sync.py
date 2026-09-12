from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pitchvalue.providers.five_dfa.fixtures import (
    ExistingFixture,
    FixtureStatus,
    ProviderFixture,
    RefreshAction,
    build_sync_plan,
    parse_fixture,
)
from pitchvalue.providers.five_dfa.mapping import MappingStatus, map_competition, map_team


def _fixture(
    *,
    fixture_id: int = 100,
    status: str = "scheduled",
    kickoff: str = "2026-09-13T15:00:00+00:00",
    goals: object = None,
    competition: str = "Premier League",
    home_mapping: bool = True,
    away_mapping: bool = True,
    statistics: object = None,
) -> ProviderFixture:
    competition_ref = map_competition(3120672213, competition)
    home = map_team(10, "Home FC", {"10": 1} if home_mapping else {}, provenance="test")
    away = map_team(20, "Away FC", {"20": 2} if away_mapping else {}, provenance="test")
    payload = {
        "id": fixture_id,
        "kickoff_utc": kickoff,
        "status": status,
        "status_reason": "kickoff_unconfirmed" if status == "unknown" else None,
        "goals": goals,
        "statistics": statistics,
    }
    return parse_fixture(payload, competition=competition_ref, home_team=home, away_team=away)


def _existing(
    *, fixture_id: str = "100", kickoff: datetime | None = None, status: str = "SCHEDULED"
) -> ExistingFixture:
    return ExistingFixture(
        99,
        frozenset({fixture_id}),
        "Premier League",
        1,
        2,
        kickoff or datetime(2026, 9, 13, 15, tzinfo=UTC),
        status,
    )


def test_competition_mapping_uses_opaque_documented_id_and_rejects_unsupported_scope() -> None:
    supported = map_competition(3120672213, "Premier League")
    assert supported.provider_competition_id == "3120672213"
    assert supported.status is MappingStatus.RESOLVED
    unsupported = map_competition(999, "Serie A")
    assert unsupported.status is MappingStatus.UNSUPPORTED
    assert unsupported.canonical_name is None


def test_team_mapping_requires_explicit_provider_id_mapping_without_fuzzy_fallback() -> None:
    resolved = map_team(10, "Different Display Name", {"10": 55}, provenance="fixture")
    assert resolved.canonical_team_id == 55
    unresolved = map_team(11, "Home FC", {}, provenance="fixture")
    assert unresolved.status is MappingStatus.UNRESOLVED
    assert unresolved.canonical_team_id is None


def test_fixture_parser_preserves_status_score_and_missing_statistics() -> None:
    fixture = _fixture(status="finished", goals={"home": 2, "away": 1})
    assert fixture.status is FixtureStatus.FINISHED
    assert (fixture.home_score, fixture.away_score) == (2, 1)
    assert fixture.statistics.home_shots_on_target is None
    assert fixture.statistics.home_possession is None


def test_statistics_preserve_zero_and_missing_as_distinct() -> None:
    fixture = _fixture(
        statistics={
            "shots_on_target": {"home": 0, "away": 4},
            "possession": {"home": 51, "away": 49},
        }
    )
    assert fixture.statistics.home_shots_on_target == 0
    assert fixture.statistics.away_shots_on_target == 4
    assert fixture.statistics.home_corners is None


@pytest.mark.parametrize(
    ("fixture", "existing", "expected"),
    [
        (_fixture(fixture_id=101), (), RefreshAction.ADD),
        (_fixture(), (_existing(),), RefreshAction.UNCHANGED),
        (
            _fixture(kickoff="2026-09-13T16:00:00+00:00"),
            (_existing(),),
            RefreshAction.KICKOFF_CHANGED,
        ),
        (
            _fixture(status="finished", goals={"home": 1, "away": 1}),
            (_existing(),),
            RefreshAction.FINISHED,
        ),
        (_fixture(status="unknown"), (_existing(),), RefreshAction.UNKNOWN_REVIEW),
        (_fixture(competition="Süper Lig"), (), RefreshAction.UNSUPPORTED_COMPETITION),
        (_fixture(home_mapping=False), (), RefreshAction.TEAM_MAPPING_UNRESOLVED),
        (_fixture(status="finished"), (), RefreshAction.MISSING_SCORE),
    ],
)
def test_refresh_actions_are_explicit(
    fixture: ProviderFixture,
    existing: tuple[ExistingFixture, ...],
    expected: RefreshAction,
) -> None:
    assert build_sync_plan((fixture,), existing).refreshes[0].action is expected


def test_duplicate_provider_row_is_quarantined_locally() -> None:
    fixture = _fixture()
    plan = build_sync_plan((fixture, fixture), ())
    assert plan.refreshes[0].action is RefreshAction.ADD
    assert plan.refreshes[1].action is RefreshAction.DUPLICATE_PROVIDER_ROW
    assert plan.quarantined == 1


def test_valid_empty_schedule_is_a_successful_empty_plan() -> None:
    plan = build_sync_plan((), ())
    assert plan.refreshes == ()
    assert (plan.added, plan.changed_kickoff, plan.finished, plan.unchanged, plan.quarantined) == (
        0,
        0,
        0,
        0,
        0,
    )


def test_new_provider_id_reconciles_only_on_exact_existing_identity() -> None:
    exact = build_sync_plan((_fixture(fixture_id=200),), (_existing(),))
    assert exact.refreshes[0].action is RefreshAction.UNCHANGED
    changed = build_sync_plan(
        (_fixture(fixture_id=200, kickoff="2026-09-14T15:00:00+00:00"),),
        (_existing(),),
    )
    assert changed.refreshes[0].action is RefreshAction.PROVIDER_ID_REPLACEMENT_REVIEW


def test_unknown_is_not_synthesized_into_postponed_or_cancelled() -> None:
    fixture = _fixture(status="unknown")
    refresh = build_sync_plan((fixture,), ()).refreshes[0]
    assert refresh.action is RefreshAction.UNKNOWN_REVIEW
    assert refresh.reason_code is not None
    assert "POSTPONED" not in refresh.reason_code
    assert "CANCELLED" not in refresh.reason_code


def test_invalid_status_and_partial_score_are_rejected() -> None:
    with pytest.raises(ValueError, match="status"):
        _fixture(status="postponed")
    fixture = _fixture()
    with pytest.raises(ValueError, match="scores"):
        replace(fixture, home_score=1, away_score=None)
