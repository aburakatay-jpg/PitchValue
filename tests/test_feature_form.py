from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pitchvalue.features.contracts import (
    FeatureAvailability,
    FeatureValidationError,
    HistoricalMatch,
    MatchStatus,
    TeamResult,
)
from pitchvalue.features.form import (
    aggregate_team_form,
    normalize_team_perspective,
    points_for_result,
)

KICKOFF = datetime(2026, 1, 1, 15, tzinfo=UTC)
D = Decimal


def match(
    match_id: str,
    home: str,
    away: str,
    home_score: int,
    away_score: int,
) -> HistoricalMatch:
    return HistoricalMatch(
        match_id,
        "c1",
        "s1",
        KICKOFF,
        home,
        away,
        MatchStatus.FINISHED,
        home_score,
        away_score,
    )


def test_home_and_away_perspective_normalization() -> None:
    value = match("m1", "A", "B", 2, 1)
    home = normalize_team_perspective(value, "A")
    away = normalize_team_perspective(value, "B")

    assert (home.goals_for, home.goals_against, home.result, home.was_home) == (
        2,
        1,
        TeamResult.WIN,
        True,
    )
    assert (away.goals_for, away.goals_against, away.result, away.was_home) == (
        1,
        2,
        TeamResult.LOSS,
        False,
    )


def test_perspective_rejects_nonparticipant() -> None:
    with pytest.raises(FeatureValidationError, match="did not participate"):
        normalize_team_perspective(match("m1", "A", "B", 0, 0), "C")


@pytest.mark.parametrize(
    ("result", "points"),
    [(TeamResult.WIN, 3), (TeamResult.DRAW, 1), (TeamResult.LOSS, 0)],
)
def test_standard_points(result: TeamResult, points: int) -> None:
    assert points_for_result(result) == points


def test_all_team_form_counts_and_rates() -> None:
    history = (
        match("m1", "A", "B", 2, 0),
        match("m2", "C", "A", 1, 1),
        match("m3", "A", "D", 0, 3),
        match("m4", "E", "A", 2, 1),
    )
    form = aggregate_team_form("A", history, window=4, minimum_rate_observations=1)

    assert form.coverage.availability is FeatureAvailability.COMPLETE
    assert (form.wins, form.draws, form.losses, form.points) == (1, 1, 2, 4)
    assert (form.goals_for, form.goals_against, form.goal_difference) == (4, 6, -2)
    assert form.points_per_game == D("1")
    assert form.goals_for_per_game == D("1")
    assert form.goals_against_per_game == D("1.5")
    assert form.goal_difference_per_game == D("-0.5")
    assert (form.clean_sheets, form.clean_sheet_rate) == (1, D("0.25"))
    assert (form.failed_to_score, form.failed_to_score_rate) == (1, D("0.25"))
    assert (form.btts, form.btts_rate) == (2, D("0.5"))
    assert (form.over_1_5, form.over_1_5_rate) == (4, D("1"))
    assert (form.over_2_5, form.over_2_5_rate) == (2, D("0.5"))


def test_true_score_zero_differs_from_missing_history() -> None:
    known_zero = aggregate_team_form(
        "A", (match("m1", "A", "B", 0, 0),), window=5, minimum_rate_observations=1
    )
    missing = aggregate_team_form("A", (), window=5, minimum_rate_observations=1)

    assert known_zero.goals_for_per_game == 0
    assert known_zero.coverage.availability is FeatureAvailability.PARTIAL
    assert missing.goals_for == 0
    assert missing.goals_for_per_game is None
    assert missing.coverage.availability is FeatureAvailability.UNAVAILABLE


def test_minimum_observation_policy_withholds_rates_without_fabricating_them() -> None:
    form = aggregate_team_form(
        "A", (match("m1", "A", "B", 2, 0),), window=5, minimum_rate_observations=2
    )
    assert form.matches_played == 1
    assert form.goals_for == 2
    assert form.goals_for_per_game is None
    assert form.points_per_game is None
