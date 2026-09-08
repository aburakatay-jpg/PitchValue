from dataclasses import replace
from decimal import Decimal

import pytest

from pitchvalue.models.elo.config import DEFAULT_ELO_CONFIG, EloValidationError
from pitchvalue.models.elo.rating import (
    actual_home_result,
    expected_scores,
    regress_rating,
    update_ratings,
)

D = Decimal


def test_default_config_is_valid_serializable_and_provisional() -> None:
    assert DEFAULT_ELO_CONFIG.initial_rating == D("1500")
    assert DEFAULT_ELO_CONFIG.k_factor == D("20")
    assert DEFAULT_ELO_CONFIG.rating_scale == D("400")
    assert DEFAULT_ELO_CONFIG.home_advantage == D("100")
    assert DEFAULT_ELO_CONFIG.season_regression_factor == D("0.75")
    assert not DEFAULT_ELO_CONFIG.goal_margin_enabled
    assert DEFAULT_ELO_CONFIG.as_dict()["initial_rating"] == "1500"


@pytest.mark.parametrize("k_factor", [D("0"), D("-1")])
def test_invalid_k_factor_is_rejected(k_factor: Decimal) -> None:
    with pytest.raises(EloValidationError, match="k_factor"):
        replace(DEFAULT_ELO_CONFIG, k_factor=k_factor)


@pytest.mark.parametrize("rating_scale", [D("0"), D("-400")])
def test_invalid_rating_scale_is_rejected(rating_scale: Decimal) -> None:
    with pytest.raises(EloValidationError, match="rating_scale"):
        replace(DEFAULT_ELO_CONFIG, rating_scale=rating_scale)


@pytest.mark.parametrize("factor", [D("-0.01"), D("1.01")])
def test_invalid_season_regression_factor_is_rejected(factor: Decimal) -> None:
    with pytest.raises(EloValidationError, match="season_regression_factor"):
        replace(DEFAULT_ELO_CONFIG, season_regression_factor=factor)


@pytest.mark.parametrize(
    "overrides",
    [
        {"initial_rating": D("0")},
        {"home_advantage": D("-1")},
        {"goal_margin_step": D("-0.1")},
        {"goal_margin_maximum": D("0.9")},
        {"k_factor": 20},
    ],
)
def test_other_invalid_config_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(EloValidationError):
        replace(DEFAULT_ELO_CONFIG, **overrides)  # type: ignore[arg-type]


def test_equal_ratings_with_zero_home_advantage_expect_half_each() -> None:
    config = replace(DEFAULT_ELO_CONFIG, home_advantage=D("0"))
    result = expected_scores(D("1500"), D("1500"), config)
    assert result.expected_home_score == D("0.5")
    assert result.expected_away_score == D("0.5")


def test_home_advantage_changes_expectation_not_stored_rating() -> None:
    result = expected_scores(D("1500"), D("1500"), DEFAULT_ELO_CONFIG)
    assert result.expected_home_score > D("0.5")
    assert result.stored_home_rating == D("1500")
    assert result.effective_home_rating == D("1600")


@pytest.mark.parametrize(
    ("home", "away"),
    [("1500", "1500"), ("1800", "1200"), ("1100", "1900")],
)
def test_expectations_are_exact_complements(home: str, away: str) -> None:
    result = expected_scores(D(home), D(away), DEFAULT_ELO_CONFIG)
    assert result.expected_home_score + result.expected_away_score == 1


def test_expectation_is_monotonic_in_both_ratings() -> None:
    base = expected_scores(D("1500"), D("1500"), DEFAULT_ELO_CONFIG)
    stronger_home = expected_scores(D("1600"), D("1500"), DEFAULT_ELO_CONFIG)
    stronger_away = expected_scores(D("1500"), D("1600"), DEFAULT_ELO_CONFIG)
    assert stronger_home.expected_home_score > base.expected_home_score
    assert stronger_away.expected_home_score < base.expected_home_score


@pytest.mark.parametrize(
    ("home_score", "away_score", "actual"),
    [(1, 0, D("1")), (0, 0, D("0.5")), (0, 1, D("0"))],
)
def test_actual_result_uses_standard_home_score(
    home_score: int, away_score: int, actual: Decimal
) -> None:
    assert actual_home_result(home_score, away_score) == actual


@pytest.mark.parametrize("scores", [(1, 0), (0, 0), (0, 1)])
def test_rating_updates_conserve_total_rating(scores: tuple[int, int]) -> None:
    update = update_ratings(D("1510"), D("1490"), *scores, DEFAULT_ELO_CONFIG)
    assert update.new_home_rating + update.new_away_rating == D("3000")
    assert (
        update.new_home_rating
        - update.old_home_rating
        + update.new_away_rating
        - update.old_away_rating
        == 0
    )


def test_home_win_draw_and_away_win_move_ratings_in_expected_directions() -> None:
    config = replace(DEFAULT_ELO_CONFIG, home_advantage=D("0"))
    home_win = update_ratings(D("1500"), D("1500"), 1, 0, config)
    draw = update_ratings(D("1500"), D("1500"), 0, 0, config)
    away_win = update_ratings(D("1500"), D("1500"), 0, 1, config)
    assert home_win.new_home_rating > home_win.old_home_rating
    assert draw.adjustment == 0
    assert away_win.new_home_rating < away_win.old_home_rating


def test_draw_penalizes_expected_favorite_and_rewards_underdog() -> None:
    config = replace(DEFAULT_ELO_CONFIG, home_advantage=D("0"))
    result = update_ratings(D("1800"), D("1200"), 1, 1, config)
    assert result.new_home_rating < result.old_home_rating
    assert result.new_away_rating > result.old_away_rating


def test_draw_with_home_advantage_does_not_change_actual_score() -> None:
    result = update_ratings(D("1500"), D("1500"), 0, 0, DEFAULT_ELO_CONFIG)
    assert result.actual_home_score == D("0.5")
    assert result.adjustment < 0


def test_upset_adjustment_exceeds_favorite_win_adjustment() -> None:
    config = replace(DEFAULT_ELO_CONFIG, home_advantage=D("0"))
    favorite_win = update_ratings(D("1800"), D("1200"), 1, 0, config)
    upset = update_ratings(D("1200"), D("1800"), 1, 0, config)
    assert upset.adjustment > favorite_win.adjustment > 0


def test_larger_k_factor_produces_larger_adjustment() -> None:
    low = update_ratings(D("1500"), D("1500"), 1, 0, replace(DEFAULT_ELO_CONFIG, k_factor=D("10")))
    high = update_ratings(D("1500"), D("1500"), 1, 0, replace(DEFAULT_ELO_CONFIG, k_factor=D("40")))
    assert abs(high.adjustment) > abs(low.adjustment)


def test_goal_margin_disabled_makes_one_and_five_goal_wins_identical() -> None:
    one_goal = update_ratings(D("1500"), D("1500"), 1, 0, DEFAULT_ELO_CONFIG)
    five_goal = update_ratings(D("1500"), D("1500"), 5, 0, DEFAULT_ELO_CONFIG)
    high_scoring_away = update_ratings(D("1500"), D("1500"), 2, 6, DEFAULT_ELO_CONFIG)
    one_goal_away = update_ratings(D("1500"), D("1500"), 0, 1, DEFAULT_ELO_CONFIG)
    assert one_goal.adjustment == five_goal.adjustment
    assert high_scoring_away.adjustment == one_goal_away.adjustment
    assert one_goal.goal_margin_multiplier == 1


def test_optional_goal_margin_policy_is_bounded_and_explicit() -> None:
    config = replace(DEFAULT_ELO_CONFIG, goal_margin_enabled=True)
    result = update_ratings(D("1500"), D("1500"), 10, 0, config)
    assert result.goal_margin_multiplier == config.goal_margin_maximum


@pytest.mark.parametrize(
    ("factor", "expected"),
    [("1", "1700"), ("0", "1500"), ("0.5", "1600")],
)
def test_season_regression_factors(factor: str, expected: str) -> None:
    config = replace(DEFAULT_ELO_CONFIG, season_regression_factor=D(factor))
    assert regress_rating(D("1700"), config) == D(expected)


def test_expectation_and_update_serialization_are_deterministic() -> None:
    expectation = expected_scores(D("1500"), D("1500"), DEFAULT_ELO_CONFIG)
    update = update_ratings(D("1500"), D("1500"), 1, 0, DEFAULT_ELO_CONFIG)
    assert expectation.to_dict() == expectation.to_dict()
    assert expectation.to_dict()["stored_home_rating"] == "1500"
    assert update.to_dict()["actual_home_score"] == "1"
