from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pitchvalue.features.config import DEFAULT_FEATURE_CONFIG, FeatureConfig, SeasonHistoryScope
from pitchvalue.features.contracts import (
    FeatureAvailability,
    FeatureValidationError,
    HistoricalMatch,
    MatchStatus,
    TargetFixture,
)
from pitchvalue.features.engine import compute_match_features

TARGET_TIME = datetime(2026, 2, 20, 18, tzinfo=UTC)
D = Decimal


def target(**overrides: object) -> TargetFixture:
    values: dict[str, object] = {
        "match_id": "target",
        "competition_id": "league",
        "season_id": "s1",
        "kickoff": TARGET_TIME,
        "home_team_id": "A",
        "away_team_id": "B",
    }
    values.update(overrides)
    return TargetFixture(**values)  # type: ignore[arg-type]


def match(
    match_id: str,
    days_before: int,
    home: str,
    away: str,
    home_score: int = 1,
    away_score: int = 0,
    *,
    competition: str = "league",
    season: str = "s1",
    status: MatchStatus = MatchStatus.FINISHED,
    kickoff: datetime | None = None,
) -> HistoricalMatch:
    return HistoricalMatch(
        match_id=match_id,
        competition_id=competition,
        season_id=season,
        kickoff=kickoff if kickoff is not None else TARGET_TIME - timedelta(days=days_before),
        home_team_id=home,
        away_team_id=away,
        status=status,
        home_score=home_score,
        away_score=away_score,
    )


def test_no_history_returns_unavailable_groups_not_fake_rates() -> None:
    result = compute_match_features(target(), [])

    assert result.home_team.recent.matches_played == 0
    assert result.home_team.recent.points_per_game is None
    assert result.home_team.recent.coverage.availability is FeatureAvailability.UNAVAILABLE
    assert result.away_team.venue_split.coverage.availability is FeatureAvailability.UNAVAILABLE
    assert result.home_team.schedule.days_since_previous_match is None
    assert result.league_baseline.home_goals_per_match is None


def test_one_match_produces_partial_rolling_form() -> None:
    result = compute_match_features(target(), [match("m1", 3, "A", "C", 2, 1)])
    assert result.home_team.recent.matches_played == 1
    assert result.home_team.recent.points == 3
    assert result.home_team.recent.coverage.availability is FeatureAvailability.PARTIAL


@pytest.mark.parametrize(
    ("count", "availability", "expected_count"),
    [
        (3, FeatureAvailability.PARTIAL, 3),
        (5, FeatureAvailability.COMPLETE, 5),
        (7, FeatureAvailability.COMPLETE, 5),
    ],
)
def test_recent_window_partial_exact_and_overfull(
    count: int, availability: FeatureAvailability, expected_count: int
) -> None:
    history = [match(f"m{index}", count - index + 1, "A", f"X{index}") for index in range(count)]
    result = compute_match_features(target(), history)
    assert result.home_team.recent.matches_played == expected_count
    assert result.home_team.recent.coverage.availability is availability


def test_window_selects_latest_n_eligible_matches() -> None:
    config = FeatureConfig(
        recent_window=2, extended_window=4, home_split_window=2, away_split_window=2
    )
    history = [
        match("old", 20, "A", "X", 9, 0),
        match("middle", 10, "A", "Y", 1, 0),
        match("latest", 2, "Z", "A", 0, 2),
    ]
    result = compute_match_features(target(), history, config)

    assert result.home_team.recent.match_ids == ("middle", "latest")
    assert result.home_team.recent.goals_for == 3


def test_extended_window_retains_more_history_than_recent_window() -> None:
    config = FeatureConfig(
        recent_window=2, extended_window=4, home_split_window=2, away_split_window=2
    )
    history = [match(f"m{index}", 10 - index, "A", f"X{index}") for index in range(4)]
    result = compute_match_features(target(), history, config)
    assert result.home_team.recent.matches_played == 2
    assert result.home_team.extended.matches_played == 4
    assert result.home_team.extended.coverage.availability is FeatureAvailability.COMPLETE


def test_home_and_away_splits_exclude_opposite_venues() -> None:
    history = [
        match("a-home-1", 12, "A", "X", 3, 0),
        match("a-away", 10, "Y", "A", 4, 0),
        match("a-home-2", 8, "A", "Z", 2, 0),
        match("b-home", 7, "B", "Q", 0, 5),
        match("b-away-1", 6, "R", "B", 0, 2),
        match("b-away-2", 4, "S", "B", 1, 3),
    ]
    result = compute_match_features(target(), history)

    assert result.home_team.venue_split.match_ids == ("a-home-1", "a-home-2")
    assert result.home_team.venue_split.wins == 2
    assert result.home_team.venue_split.goals_for_per_game == D("2.5")
    assert result.away_team.venue_split.match_ids == ("b-away-1", "b-away-2")
    assert result.away_team.venue_split.wins == 2
    assert result.away_team.venue_split.goals_for_per_game == D("2.5")


@pytest.mark.parametrize("days", [3, 7])
def test_rest_days_use_immediately_previous_match(days: int) -> None:
    result = compute_match_features(target(), [match("previous", days, "A", "X")])
    assert result.home_team.schedule.previous_match_kickoff == TARGET_TIME - timedelta(days=days)
    assert result.home_team.schedule.days_since_previous_match == D(str(days))


def test_schedule_density_uses_inclusive_lower_and_exclusive_upper_bounds() -> None:
    history = [
        match("d3", 3, "A", "X"),
        match("d7", 7, "A", "Y"),
        match("d8", 8, "A", "Z"),
        match("d14", 14, "Q", "A"),
        match("d15", 15, "A", "R"),
    ]
    density = compute_match_features(target(), history).home_team.schedule.density
    assert [(item.window_days, item.match_count) for item in density] == [(7, 2), (14, 4)]


def test_future_same_time_target_other_competition_and_awarded_are_excluded() -> None:
    history = [
        match("valid", 2, "A", "X"),
        match("future", -1, "A", "X", 99, 0),
        match("same", 0, "A", "X", 99, 0),
        match("target", 0, "A", "B", 99, 0),
        match("other-comp", 2, "A", "X", 99, 0, competition="cup"),
        match("other-season", 2, "A", "X", 99, 0, season="s0"),
        match("awarded", 2, "A", "X", 3, 0, status=MatchStatus.AWARDED),
        match("scheduled", 2, "A", "X", 3, 0, status=MatchStatus.SCHEDULED),
    ]
    result = compute_match_features(target(), history)

    assert result.home_team.recent.match_ids == ("valid",)
    assert result.diagnostics.eligible_rows == 1
    assert result.diagnostics.future_rows_ignored == 1
    assert result.diagnostics.same_time_rows_ignored == 1
    assert result.diagnostics.target_rows_ignored == 1
    assert result.diagnostics.different_competition_rows_ignored == 1
    assert result.diagnostics.different_season_rows_ignored == 1
    assert result.diagnostics.awarded_rows_ignored == 1
    assert result.diagnostics.non_finished_rows_ignored == 1
    assert result.home_team.schedule.previous_match_kickoff == TARGET_TIME - timedelta(days=2)
    assert result.home_team.schedule.days_since_previous_match == 2


def test_target_id_that_could_contaminate_history_is_rejected() -> None:
    with pytest.raises(FeatureValidationError, match="target match_id"):
        compute_match_features(target(), [match("target", 2, "A", "B")])


def test_prediction_as_of_excludes_matches_between_cutoff_and_kickoff() -> None:
    value = target(as_of=TARGET_TIME - timedelta(days=2))
    result = compute_match_features(
        value,
        [match("before", 3, "A", "X"), match("after-cutoff", 1, "A", "Y")],
    )
    assert result.home_team.recent.match_ids == ("before",)
    assert result.diagnostics.future_rows_ignored == 1


def test_duplicate_history_is_rejected() -> None:
    duplicate = match("same-id", 2, "A", "X")
    with pytest.raises(FeatureValidationError, match="duplicate historical match_id"):
        compute_match_features(target(), [duplicate, duplicate])


def test_shuffled_input_produces_identical_output() -> None:
    history = [
        match("m1", 9, "A", "X", 2, 0),
        match("m2", 6, "Y", "B", 1, 2),
        match("m3", 3, "Z", "A", 1, 1),
    ]
    assert compute_match_features(target(), history) == compute_match_features(
        target(), [history[2], history[0], history[1]]
    )


def test_target_and_future_extreme_scores_do_not_change_target_features() -> None:
    base_history = [match("m1", 5, "A", "X", 2, 0), match("m2", 4, "Y", "B", 0, 1)]
    baseline = compute_match_features(target(), base_history)
    contaminated = compute_match_features(
        target(),
        base_history
        + [
            match("target", 0, "A", "B", 99, 98),
            match("future-extreme", -5, "A", "B", 1000, 0),
        ],
    )

    assert contaminated.home_team == baseline.home_team
    assert contaminated.away_team == baseline.away_team
    assert contaminated.league_baseline == baseline.league_baseline
    assert contaminated.raw_scoring_rates == baseline.raw_scoring_rates


def test_known_league_baseline_rates_and_future_leakage_prevention() -> None:
    history = [
        match("m1", 9, "A", "X", 2, 1),
        match("m2", 6, "Y", "B", 0, 0),
        match("m3", 3, "Z", "Q", 1, 3),
    ]
    baseline = compute_match_features(target(), history).league_baseline
    with_future = compute_match_features(
        target(), history + [match("future", -1, "A", "B", 99, 0)]
    ).league_baseline

    assert baseline.matches_played == 3
    assert baseline.home_goals_per_match == D("1")
    assert baseline.away_goals_per_match == D("1.333333333333333333333333333")
    assert baseline.total_goals_per_match == D("2.333333333333333333333333333")
    assert baseline.home_win_rate == D("0.3333333333333333333333333333")
    assert baseline.draw_rate == D("0.3333333333333333333333333333")
    assert baseline.away_win_rate == D("0.3333333333333333333333333333")
    assert baseline.btts_rate == D("0.6666666666666666666666666667")
    assert baseline.over_2_5_rate == D("0.6666666666666666666666666667")
    assert with_future == baseline


def test_league_rates_respect_minimum_observations() -> None:
    config = FeatureConfig(minimum_rate_observations=2)
    baseline = compute_match_features(target(), [match("m1", 3, "X", "Y")], config).league_baseline
    assert baseline.matches_played == 1
    assert baseline.home_goals == 1
    assert baseline.home_goals_per_match is None
    assert baseline.coverage.availability is FeatureAvailability.PARTIAL


def test_raw_scoring_rates_are_exposed_without_poisson_strengths() -> None:
    history = [match("home", 5, "A", "X", 2, 1), match("away", 4, "Y", "B", 0, 3)]
    rates = compute_match_features(target(), history).raw_scoring_rates
    assert rates.home_team_home_goals_scored_per_match == 2
    assert rates.home_team_home_goals_conceded_per_match == 1
    assert rates.away_team_away_goals_scored_per_match == 3
    assert rates.away_team_away_goals_conceded_per_match == 0


def test_explicit_previous_season_scope_never_infers_from_ids() -> None:
    previous = match("previous", 20, "A", "X", season="s0")
    current_only = compute_match_features(target(), [previous])
    config = replace(
        DEFAULT_FEATURE_CONFIG,
        season_history_scope=SeasonHistoryScope.CURRENT_AND_PREVIOUS_SEASON,
        previous_season_id="s0",
    )
    included = compute_match_features(target(), [previous], config)
    assert current_only.home_team.recent.matches_played == 0
    assert included.home_team.recent.matches_played == 1


def test_serialization_is_deterministic_and_primitive() -> None:
    result = compute_match_features(target(), [match("m1", 3, "A", "X", 2, 0)])
    first = result.to_dict()
    second = result.to_dict()
    assert first == second
    assert first["target"]["kickoff"] == TARGET_TIME.isoformat()
    assert first["home_team"]["recent"]["points_per_game"] == "3"
