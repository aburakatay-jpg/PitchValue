"""Composition root for deterministic pre-match football feature computation."""

from __future__ import annotations

from pitchvalue.features.aggregates import calculate_league_baseline
from pitchvalue.features.config import DEFAULT_FEATURE_CONFIG, FeatureConfig
from pitchvalue.features.contracts import (
    HistoricalMatch,
    MatchFeatures,
    RawScoringRates,
    TargetFixture,
    TeamFeatures,
)
from pitchvalue.features.form import aggregate_team_form, calculate_schedule
from pitchvalue.features.history import select_eligible_history


def compute_match_features(
    target: TargetFixture,
    history: tuple[HistoricalMatch, ...] | list[HistoricalMatch],
    config: FeatureConfig = DEFAULT_FEATURE_CONFIG,
) -> MatchFeatures:
    """Compute score-only pre-match features from explicitly supplied history."""
    selected = select_eligible_history(target, history, config)
    matches = selected.matches
    home_matches = tuple(match for match in matches if match.home_team_id == target.home_team_id)
    away_matches = tuple(match for match in matches if match.away_team_id == target.away_team_id)
    home_recent = aggregate_team_form(
        target.home_team_id,
        matches,
        window=config.recent_window,
        minimum_rate_observations=config.minimum_rate_observations,
    )
    home_extended = aggregate_team_form(
        target.home_team_id,
        matches,
        window=config.extended_window,
        minimum_rate_observations=config.minimum_rate_observations,
    )
    home_split = aggregate_team_form(
        target.home_team_id,
        home_matches,
        window=config.home_split_window,
        minimum_rate_observations=config.minimum_rate_observations,
    )
    away_recent = aggregate_team_form(
        target.away_team_id,
        matches,
        window=config.recent_window,
        minimum_rate_observations=config.minimum_rate_observations,
    )
    away_extended = aggregate_team_form(
        target.away_team_id,
        matches,
        window=config.extended_window,
        minimum_rate_observations=config.minimum_rate_observations,
    )
    away_split = aggregate_team_form(
        target.away_team_id,
        away_matches,
        window=config.away_split_window,
        minimum_rate_observations=config.minimum_rate_observations,
    )
    home = TeamFeatures(
        team_id=target.home_team_id,
        recent=home_recent,
        extended=home_extended,
        venue_split=home_split,
        schedule=calculate_schedule(
            target.home_team_id,
            matches,
            target_kickoff=target.kickoff,
            density_windows_days=config.schedule_density_windows_days,
        ),
    )
    away = TeamFeatures(
        team_id=target.away_team_id,
        recent=away_recent,
        extended=away_extended,
        venue_split=away_split,
        schedule=calculate_schedule(
            target.away_team_id,
            matches,
            target_kickoff=target.kickoff,
            density_windows_days=config.schedule_density_windows_days,
        ),
    )
    league = calculate_league_baseline(matches, config.minimum_rate_observations)
    raw_rates = RawScoringRates(
        home_team_home_goals_scored_per_match=home_split.goals_for_per_game,
        home_team_home_goals_conceded_per_match=home_split.goals_against_per_game,
        away_team_away_goals_scored_per_match=away_split.goals_for_per_game,
        away_team_away_goals_conceded_per_match=away_split.goals_against_per_game,
        league_home_goals_per_match=league.home_goals_per_match,
        league_away_goals_per_match=league.away_goals_per_match,
    )
    return MatchFeatures(
        target=target,
        home_team=home,
        away_team=away,
        league_baseline=league,
        raw_scoring_rates=raw_rates,
        diagnostics=selected.diagnostics,
    )
