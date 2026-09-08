"""Pure Poisson analysis composition and TASK 06 feature adapter."""

from __future__ import annotations

from decimal import Decimal

from pitchvalue.features.contracts import FeatureAvailability, MatchFeatures
from pitchvalue.models.poisson.config import (
    DEFAULT_POISSON_CONFIG,
    PartialHistoryPolicy,
    PoissonConfig,
)
from pitchvalue.models.poisson.contracts import (
    PoissonAnalysis,
    PoissonDiagnostics,
    PoissonModelInput,
    PoissonModelStatus,
)
from pitchvalue.models.poisson.probabilities import (
    build_score_matrix,
    derive_market_probabilities,
)
from pitchvalue.models.poisson.strengths import calculate_strengths
from pitchvalue.prediction.contracts import MarketFamily, Selection


def input_from_match_features(features: MatchFeatures) -> PoissonModelInput:
    """Read only pre-match venue and league rates; never access historical matches."""
    rates = features.raw_scoring_rates
    return PoissonModelInput(
        match_id=features.target.match_id,
        home_team_home_goals_for_per_match=rates.home_team_home_goals_scored_per_match,
        home_team_home_goals_against_per_match=rates.home_team_home_goals_conceded_per_match,
        away_team_away_goals_for_per_match=rates.away_team_away_goals_scored_per_match,
        away_team_away_goals_against_per_match=rates.away_team_away_goals_conceded_per_match,
        league_home_goals_per_match=rates.league_home_goals_per_match,
        league_away_goals_per_match=rates.league_away_goals_per_match,
        home_venue_availability=features.home_team.venue_split.coverage.availability,
        away_venue_availability=features.away_team.venue_split.coverage.availability,
        league_availability=features.league_baseline.coverage.availability,
    )


def analyze_poisson(
    model_input: PoissonModelInput,
    config: PoissonConfig = DEFAULT_POISSON_CONFIG,
) -> PoissonAnalysis:
    reasons = list(model_input.missing_fields)
    availabilities = (
        model_input.home_venue_availability,
        model_input.away_venue_availability,
        model_input.league_availability,
    )
    if config.partial_history_policy is PartialHistoryPolicy.REQUIRE_COMPLETE and any(
        availability is not FeatureAvailability.COMPLETE for availability in availabilities
    ):
        reasons.append("COMPLETE_HISTORY_REQUIRED")
    if reasons:
        return PoissonAnalysis(
            match_id=model_input.match_id,
            status=PoissonModelStatus.INPUT_INSUFFICIENT,
            strengths=None,
            score_matrix=None,
            markets=None,
            diagnostics=None,
            reasons=tuple(reasons),
        )

    strengths = calculate_strengths(model_input, config)
    if strengths is None:  # pragma: no cover - guarded by missing_fields
        raise AssertionError("complete input must produce strengths")
    matrix = build_score_matrix(strengths.lambda_home, strengths.lambda_away, config)
    markets = derive_market_probabilities(
        strengths.lambda_home, strengths.lambda_away, matrix, config
    )
    one_x_two_mass = sum(
        (
            markets.get(MarketFamily.MATCH_RESULT, selection)
            for selection in (Selection.HOME, Selection.DRAW, Selection.AWAY)
        ),
        start=Decimal(0),
    )
    partial_used = any(
        availability is FeatureAvailability.PARTIAL for availability in availabilities
    )
    return PoissonAnalysis(
        match_id=model_input.match_id,
        status=PoissonModelStatus.READY,
        strengths=strengths,
        score_matrix=matrix,
        markets=markets,
        diagnostics=PoissonDiagnostics(
            max_goals=config.max_goals,
            probability_tolerance=config.probability_tolerance,
            matrix_represented_mass=matrix.represented_probability_mass,
            matrix_residual_mass=matrix.residual_probability_mass,
            one_x_two_represented_mass=one_x_two_mass,
            partial_history_used=partial_used,
        ),
        reasons=(),
    )
