"""Isolated Poisson PMF, finite matrix, and V1 market probability calculations."""

from __future__ import annotations

import math
from decimal import Decimal

from pitchvalue.models.poisson.config import PoissonConfig, PoissonValidationError
from pitchvalue.models.poisson.contracts import (
    MarketProbabilities,
    MarketProbability,
    ScoreMatrix,
    ScoreProbability,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection


def _lambda(value: Decimal, config: PoissonConfig) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise PoissonValidationError("lambda must be a non-negative finite Decimal")
    if value > config.maximum_lambda:
        raise PoissonValidationError("lambda exceeds configured maximum_lambda")
    return value


def poisson_pmf(value: Decimal, goals: int, config: PoissonConfig) -> Decimal:
    """Evaluate one PMF point with all float math isolated here."""
    value = _lambda(value, config)
    if not isinstance(goals, int) or isinstance(goals, bool) or goals < 0:
        raise PoissonValidationError("goals must be a non-negative integer")
    if value == 0:
        return Decimal(1) if goals == 0 else Decimal(0)
    numeric = float(value)
    log_probability = -numeric + goals * math.log(numeric) - math.lgamma(goals + 1)
    probability = Decimal(str(math.exp(log_probability)))
    if not Decimal(0) <= probability <= Decimal(1):  # pragma: no cover - math invariant
        raise ArithmeticError("Poisson PMF escaped probability bounds")
    return probability


def build_score_matrix(
    lambda_home: Decimal, lambda_away: Decimal, config: PoissonConfig
) -> ScoreMatrix:
    home = tuple(poisson_pmf(lambda_home, goals, config) for goals in range(config.max_goals + 1))
    away = tuple(poisson_pmf(lambda_away, goals, config) for goals in range(config.max_goals + 1))
    cells = tuple(
        ScoreProbability(home_goals, away_goals, home_probability * away_probability)
        for home_goals, home_probability in enumerate(home)
        for away_goals, away_probability in enumerate(away)
    )
    represented = sum((cell.probability for cell in cells), Decimal(0))
    residual = Decimal(1) - represented
    if residual < 0 and abs(residual) <= config.probability_tolerance:
        represented = Decimal(1)
        residual = Decimal(0)
    if residual < 0:
        raise ArithmeticError("score matrix represented mass exceeds one")
    return ScoreMatrix(
        max_goals=config.max_goals,
        cells=cells,
        represented_probability_mass=represented,
        residual_probability_mass=residual,
    )


def _bounded(value: Decimal, tolerance: Decimal) -> Decimal:
    if value < 0 and abs(value) <= tolerance:
        return Decimal(0)
    if value > 1 and value - 1 <= tolerance:
        return Decimal(1)
    if not Decimal(0) <= value <= Decimal(1):
        raise ArithmeticError("derived market probability escaped bounds")
    return value


def derive_market_probabilities(
    lambda_home: Decimal,
    lambda_away: Decimal,
    matrix: ScoreMatrix,
    config: PoissonConfig,
) -> MarketProbabilities:
    home_win = sum(
        (cell.probability for cell in matrix.cells if cell.home_goals > cell.away_goals),
        Decimal(0),
    )
    draw = sum(
        (cell.probability for cell in matrix.cells if cell.home_goals == cell.away_goals),
        Decimal(0),
    )
    # Use the represented-mass remainder to make the three disjoint matrix
    # partitions sum exactly despite Decimal aggregation-order rounding.
    away_win = matrix.represented_probability_mass - home_win - draw
    home_zero = poisson_pmf(lambda_home, 0, config)
    home_one = poisson_pmf(lambda_home, 1, config)
    away_zero = poisson_pmf(lambda_away, 0, config)
    away_one = poisson_pmf(lambda_away, 1, config)
    total_lambda = lambda_home + lambda_away
    total_zero = poisson_pmf(total_lambda, 0, config)
    total_one = poisson_pmf(total_lambda, 1, config)
    total_two = poisson_pmf(total_lambda, 2, config)
    under_1_5 = total_zero + total_one
    under_2_5 = under_1_5 + total_two
    btts_yes = Decimal(1) - home_zero - away_zero + home_zero * away_zero

    entries = (
        MarketProbability(MarketFamily.MATCH_RESULT, Selection.HOME, None, home_win),
        MarketProbability(MarketFamily.MATCH_RESULT, Selection.DRAW, None, draw),
        MarketProbability(MarketFamily.MATCH_RESULT, Selection.AWAY, None, away_win),
        MarketProbability(MarketFamily.TOTAL_GOALS, Selection.OVER, Decimal("1.5"), 1 - under_1_5),
        MarketProbability(MarketFamily.TOTAL_GOALS, Selection.UNDER, Decimal("1.5"), under_1_5),
        MarketProbability(MarketFamily.TOTAL_GOALS, Selection.OVER, Decimal("2.5"), 1 - under_2_5),
        MarketProbability(MarketFamily.TOTAL_GOALS, Selection.UNDER, Decimal("2.5"), under_2_5),
        MarketProbability(MarketFamily.BTTS, Selection.YES, None, btts_yes),
        MarketProbability(MarketFamily.BTTS, Selection.NO, None, 1 - btts_yes),
        MarketProbability(MarketFamily.DOUBLE_CHANCE, Selection.ONE_X, None, home_win + draw),
        MarketProbability(MarketFamily.DOUBLE_CHANCE, Selection.X_TWO, None, draw + away_win),
        MarketProbability(MarketFamily.DOUBLE_CHANCE, Selection.ONE_TWO, None, home_win + away_win),
        MarketProbability(
            MarketFamily.HOME_TEAM_TOTAL, Selection.OVER, Decimal("0.5"), 1 - home_zero
        ),
        MarketProbability(MarketFamily.HOME_TEAM_TOTAL, Selection.UNDER, Decimal("0.5"), home_zero),
        MarketProbability(
            MarketFamily.HOME_TEAM_TOTAL, Selection.OVER, Decimal("1.5"), 1 - home_zero - home_one
        ),
        MarketProbability(
            MarketFamily.HOME_TEAM_TOTAL, Selection.UNDER, Decimal("1.5"), home_zero + home_one
        ),
        MarketProbability(
            MarketFamily.AWAY_TEAM_TOTAL, Selection.OVER, Decimal("0.5"), 1 - away_zero
        ),
        MarketProbability(MarketFamily.AWAY_TEAM_TOTAL, Selection.UNDER, Decimal("0.5"), away_zero),
        MarketProbability(
            MarketFamily.AWAY_TEAM_TOTAL, Selection.OVER, Decimal("1.5"), 1 - away_zero - away_one
        ),
        MarketProbability(
            MarketFamily.AWAY_TEAM_TOTAL, Selection.UNDER, Decimal("1.5"), away_zero + away_one
        ),
    )
    return MarketProbabilities(
        tuple(
            MarketProbability(
                entry.market,
                entry.selection,
                entry.line,
                _bounded(entry.probability, config.probability_tolerance),
            )
            for entry in entries
        )
    )
