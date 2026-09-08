"""Pure Elo expectation, result, update, and season-regression arithmetic."""

from __future__ import annotations

from decimal import Decimal

from pitchvalue.models.elo.config import EloConfig, EloValidationError
from pitchvalue.models.elo.contracts import EloExpectation, EloRatingUpdate


def _rating(value: Decimal, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise EloValidationError(f"{field_name} must be a finite Decimal")
    return value


def expected_scores(
    home_rating: Decimal,
    away_rating: Decimal,
    config: EloConfig,
) -> EloExpectation:
    """Return continuous two-team strength expectation, not football 1X2 probabilities."""
    home_rating = _rating(home_rating, "home_rating")
    away_rating = _rating(away_rating, "away_rating")
    effective_home = home_rating + config.home_advantage
    rating_difference = effective_home - away_rating

    # Standard Elo exponentiation is isolated at this boundary. Decimal(str(...))
    # restores a stable decimal representation; away is derived as the exact complement.
    exponent = float(-rating_difference / config.rating_scale)
    expected_home = Decimal(str(1 / (1 + 10**exponent)))
    expected_away = Decimal(1) - expected_home
    return EloExpectation(
        stored_home_rating=home_rating,
        stored_away_rating=away_rating,
        effective_home_rating=effective_home,
        expected_home_score=expected_home,
        expected_away_score=expected_away,
    )


def actual_home_result(home_score: int, away_score: int) -> Decimal:
    if (
        not isinstance(home_score, int)
        or isinstance(home_score, bool)
        or not isinstance(away_score, int)
        or isinstance(away_score, bool)
        or home_score < 0
        or away_score < 0
    ):
        raise EloValidationError("scores must be non-negative integers")
    if home_score > away_score:
        return Decimal(1)
    if home_score < away_score:
        return Decimal(0)
    return Decimal("0.5")


def goal_margin_multiplier(home_score: int, away_score: int, config: EloConfig) -> Decimal:
    """Return a bounded provisional multiplier, disabled by default."""
    actual_home_result(home_score, away_score)
    if not config.goal_margin_enabled:
        return Decimal(1)
    extra_goals = max(abs(home_score - away_score) - 1, 0)
    return min(
        Decimal(1) + Decimal(extra_goals) * config.goal_margin_step,
        config.goal_margin_maximum,
    )


def update_ratings(
    home_rating: Decimal,
    away_rating: Decimal,
    home_score: int,
    away_score: int,
    config: EloConfig,
) -> EloRatingUpdate:
    expectation = expected_scores(home_rating, away_rating, config)
    actual_home = actual_home_result(home_score, away_score)
    multiplier = goal_margin_multiplier(home_score, away_score, config)
    adjustment = config.k_factor * multiplier * (actual_home - expectation.expected_home_score)
    return EloRatingUpdate(
        old_home_rating=home_rating,
        old_away_rating=away_rating,
        new_home_rating=home_rating + adjustment,
        new_away_rating=away_rating - adjustment,
        actual_home_score=actual_home,
        expected_home_score=expectation.expected_home_score,
        adjustment=adjustment,
        goal_margin_multiplier=multiplier,
    )


def regress_rating(
    rating: Decimal,
    config: EloConfig,
    league_baseline: Decimal | None = None,
) -> Decimal:
    rating = _rating(rating, "rating")
    baseline = (
        config.initial_rating
        if league_baseline is None
        else _rating(league_baseline, "league_baseline")
    )
    return baseline + config.season_regression_factor * (rating - baseline)
