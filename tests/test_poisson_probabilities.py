from dataclasses import replace
from decimal import Decimal

import pytest

from pitchvalue.models.poisson.config import DEFAULT_POISSON_CONFIG, PoissonValidationError
from pitchvalue.models.poisson.contracts import MarketProbabilities, ScoreMatrix
from pitchvalue.models.poisson.probabilities import (
    build_score_matrix,
    derive_market_probabilities,
    poisson_pmf,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection

D = Decimal


def markets(
    home: str, away: str, *, max_goals: int = 10
) -> tuple[ScoreMatrix, MarketProbabilities]:
    config = replace(DEFAULT_POISSON_CONFIG, max_goals=max_goals)
    home_lambda, away_lambda = D(home), D(away)
    matrix = build_score_matrix(home_lambda, away_lambda, config)
    return matrix, derive_market_probabilities(home_lambda, away_lambda, matrix, config)


def probability(
    values: MarketProbabilities,
    market: MarketFamily,
    selection: Selection,
    line: str | None = None,
) -> Decimal:
    return values.get(market, selection, D(line) if line is not None else None)


def test_zero_lambda_pmf() -> None:
    assert poisson_pmf(D("0"), 0, DEFAULT_POISSON_CONFIG) == 1
    assert poisson_pmf(D("0"), 1, DEFAULT_POISSON_CONFIG) == 0


def test_normal_pmf_is_nonnegative_and_marginal_sum_approaches_one() -> None:
    values = [poisson_pmf(D("2.4"), goals, DEFAULT_POISSON_CONFIG) for goals in range(25)]
    assert all(value >= 0 for value in values)
    assert abs(sum(values, D("0")) - 1) < D("1e-12")


@pytest.mark.parametrize(
    ("value", "goals"),
    [(D("-1"), 0), (D("NaN"), 0), (D("1"), -1), (D("1"), True)],
)
def test_invalid_pmf_input_is_rejected(value: Decimal, goals: int) -> None:
    with pytest.raises(PoissonValidationError):
        poisson_pmf(value, goals, DEFAULT_POISSON_CONFIG)


def test_matrix_dimensions_cell_product_and_exact_score_lookup() -> None:
    matrix = build_score_matrix(D("1.5"), D("1.0"), DEFAULT_POISSON_CONFIG)
    assert len(matrix.cells) == 11 * 11
    assert matrix.exact_score(2, 1) == poisson_pmf(
        D("1.5"), 2, DEFAULT_POISSON_CONFIG
    ) * poisson_pmf(D("1.0"), 1, DEFAULT_POISSON_CONFIG)
    assert matrix.exact_score(0, 0) == matrix.cells[0].probability


def test_matrix_exposes_represented_and_residual_mass() -> None:
    matrix = build_score_matrix(D("1.8"), D("1.3"), DEFAULT_POISSON_CONFIG)
    assert 0 <= matrix.represented_probability_mass <= 1
    assert matrix.residual_probability_mass >= 0
    assert matrix.represented_probability_mass + matrix.residual_probability_mass == 1


def test_larger_matrix_does_not_reduce_represented_mass() -> None:
    small = build_score_matrix(D("3"), D("2"), replace(DEFAULT_POISSON_CONFIG, max_goals=5))
    large = build_score_matrix(D("3"), D("2"), replace(DEFAULT_POISSON_CONFIG, max_goals=15))
    assert large.represented_probability_mass >= small.represented_probability_mass
    assert large.residual_probability_mass <= small.residual_probability_mass


def test_equal_lambdas_produce_symmetric_matrix() -> None:
    matrix = build_score_matrix(D("1.4"), D("1.4"), DEFAULT_POISSON_CONFIG)
    for home in range(matrix.max_goals + 1):
        for away in range(matrix.max_goals + 1):
            assert matrix.exact_score(home, away) == matrix.exact_score(away, home)


def test_zero_zero_lambda_market_identities() -> None:
    matrix, values = markets("0", "0")
    assert matrix.exact_score(0, 0) == 1
    assert probability(values, MarketFamily.MATCH_RESULT, Selection.HOME) == 0
    assert probability(values, MarketFamily.MATCH_RESULT, Selection.DRAW) == 1
    assert probability(values, MarketFamily.MATCH_RESULT, Selection.AWAY) == 0
    assert probability(values, MarketFamily.TOTAL_GOALS, Selection.UNDER, "1.5") == 1
    assert probability(values, MarketFamily.TOTAL_GOALS, Selection.UNDER, "2.5") == 1
    assert probability(values, MarketFamily.BTTS, Selection.NO) == 1
    assert probability(values, MarketFamily.HOME_TEAM_TOTAL, Selection.UNDER, "0.5") == 1
    assert probability(values, MarketFamily.AWAY_TEAM_TOTAL, Selection.UNDER, "0.5") == 1


def test_symmetric_lambdas_give_equal_home_and_away_win_probabilities() -> None:
    _, values = markets("1.5", "1.5")
    home = probability(values, MarketFamily.MATCH_RESULT, Selection.HOME)
    away = probability(values, MarketFamily.MATCH_RESULT, Selection.AWAY)
    assert abs(home - away) < D("1e-15")


def test_one_x_two_sum_is_honest_represented_matrix_mass() -> None:
    matrix, values = markets("2.5", "2.0", max_goals=5)
    result_sum = sum(
        (
            probability(values, MarketFamily.MATCH_RESULT, selection)
            for selection in (Selection.HOME, Selection.DRAW, Selection.AWAY)
        ),
        D("0"),
    )
    assert result_sum == matrix.represented_probability_mass
    assert result_sum < 1


def test_higher_home_lambda_increases_home_win_and_team_over_probability() -> None:
    _, low = markets("1", "1")
    _, high = markets("2.5", "1")
    assert probability(high, MarketFamily.MATCH_RESULT, Selection.HOME) > probability(
        low, MarketFamily.MATCH_RESULT, Selection.HOME
    )
    assert probability(high, MarketFamily.HOME_TEAM_TOTAL, Selection.OVER, "1.5") > probability(
        low, MarketFamily.HOME_TEAM_TOTAL, Selection.OVER, "1.5"
    )


@pytest.mark.parametrize("line", ["1.5", "2.5"])
def test_total_goal_markets_are_exact_complements(line: str) -> None:
    _, values = markets("1.6", "1.1")
    over = probability(values, MarketFamily.TOTAL_GOALS, Selection.OVER, line)
    under = probability(values, MarketFamily.TOTAL_GOALS, Selection.UNDER, line)
    assert over + under == 1


def test_higher_total_lambda_increases_over_probabilities() -> None:
    _, low = markets("0.5", "0.5")
    _, high = markets("2", "2")
    assert probability(high, MarketFamily.TOTAL_GOALS, Selection.OVER, "2.5") > probability(
        low, MarketFamily.TOTAL_GOALS, Selection.OVER, "2.5"
    )


@pytest.mark.parametrize(("home", "away"), [("0", "1.5"), ("1.5", "0")])
def test_btts_yes_is_zero_when_either_lambda_is_zero(home: str, away: str) -> None:
    _, values = markets(home, away)
    assert probability(values, MarketFamily.BTTS, Selection.YES) == 0
    assert probability(values, MarketFamily.BTTS, Selection.NO) == 1


def test_btts_probabilities_are_exact_complements() -> None:
    _, values = markets("1.7", "1.2")
    yes = probability(values, MarketFamily.BTTS, Selection.YES)
    no = probability(values, MarketFamily.BTTS, Selection.NO)
    assert 0 < yes < 1
    assert yes + no == 1


@pytest.mark.parametrize("market", [MarketFamily.HOME_TEAM_TOTAL, MarketFamily.AWAY_TEAM_TOTAL])
@pytest.mark.parametrize("line", ["0.5", "1.5"])
def test_team_totals_are_exact_complements(market: MarketFamily, line: str) -> None:
    _, values = markets("1.7", "1.2")
    over = probability(values, market, Selection.OVER, line)
    under = probability(values, market, Selection.UNDER, line)
    assert over + under == 1


def test_increasing_away_lambda_raises_away_team_over() -> None:
    _, low = markets("1", "0.5")
    _, high = markets("1", "2")
    assert probability(high, MarketFamily.AWAY_TEAM_TOTAL, Selection.OVER, "0.5") > probability(
        low, MarketFamily.AWAY_TEAM_TOTAL, Selection.OVER, "0.5"
    )


def test_double_chance_is_derived_from_one_x_two() -> None:
    _, values = markets("1.8", "1.0")
    home = probability(values, MarketFamily.MATCH_RESULT, Selection.HOME)
    draw = probability(values, MarketFamily.MATCH_RESULT, Selection.DRAW)
    away = probability(values, MarketFamily.MATCH_RESULT, Selection.AWAY)
    assert probability(values, MarketFamily.DOUBLE_CHANCE, Selection.ONE_X) == home + draw
    assert probability(values, MarketFamily.DOUBLE_CHANCE, Selection.X_TWO) == draw + away
    assert probability(values, MarketFamily.DOUBLE_CHANCE, Selection.ONE_TWO) == home + away


@pytest.mark.parametrize(
    ("home", "away"),
    [("0", "0"), ("0", "2"), ("2", "0"), ("0.3", "0.4"), ("1.5", "1.2"), ("8", "7")],
)
def test_every_exported_market_probability_stays_in_bounds(home: str, away: str) -> None:
    _, values = markets(home, away, max_goals=20)
    assert all(0 <= value.probability <= 1 for value in values.values)
