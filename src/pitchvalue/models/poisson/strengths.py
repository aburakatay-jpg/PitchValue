"""Transparent multiplicative scoring-strength and lambda calculations."""

from __future__ import annotations

from pitchvalue.models.poisson.config import PoissonConfig, PoissonValidationError
from pitchvalue.models.poisson.contracts import PoissonModelInput, PoissonStrengths


def calculate_strengths(
    model_input: PoissonModelInput, config: PoissonConfig
) -> PoissonStrengths | None:
    """Apply the initial formula; return None when any required rate is unavailable."""
    if model_input.missing_fields:
        return None
    home_for = model_input.home_team_home_goals_for_per_match
    home_against = model_input.home_team_home_goals_against_per_match
    away_for = model_input.away_team_away_goals_for_per_match
    away_against = model_input.away_team_away_goals_against_per_match
    league_home = model_input.league_home_goals_per_match
    league_away = model_input.league_away_goals_per_match
    assert home_for is not None
    assert home_against is not None
    assert away_for is not None
    assert away_against is not None
    assert league_home is not None
    assert league_away is not None

    home_attack = home_for / league_home
    home_defensive_weakness = home_against / league_away
    away_attack = away_for / league_away
    away_defensive_weakness = away_against / league_home
    lambda_home = league_home * home_attack * away_defensive_weakness
    lambda_away = league_away * away_attack * home_defensive_weakness
    if lambda_home + lambda_away > config.maximum_lambda:
        raise PoissonValidationError("combined lambda exceeds configured maximum_lambda")
    return PoissonStrengths(
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        home_attack_strength=home_attack,
        home_defensive_weakness=home_defensive_weakness,
        away_attack_strength=away_attack,
        away_defensive_weakness=away_defensive_weakness,
        league_home_goal_rate=league_home,
        league_away_goal_rate=league_away,
    )
