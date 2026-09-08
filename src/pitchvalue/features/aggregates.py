"""Pure competition-level score aggregates for future model inputs."""

from __future__ import annotations

from decimal import Decimal

from pitchvalue.features.contracts import (
    Coverage,
    FeatureAvailability,
    HistoricalMatch,
    LeagueBaseline,
)


def calculate_league_baseline(
    matches: tuple[HistoricalMatch, ...], minimum_rate_observations: int
) -> LeagueBaseline:
    played = len(matches)
    home_goals = sum(match.home_score or 0 for match in matches)
    away_goals = sum(match.away_score or 0 for match in matches)
    home_wins = sum((match.home_score or 0) > (match.away_score or 0) for match in matches)
    draws = sum(match.home_score == match.away_score for match in matches)
    away_wins = sum((match.home_score or 0) < (match.away_score or 0) for match in matches)
    btts = sum((match.home_score or 0) > 0 and (match.away_score or 0) > 0 for match in matches)
    over_2_5 = sum((match.home_score or 0) + (match.away_score or 0) >= 3 for match in matches)
    rates_available = played >= minimum_rate_observations

    def rate(value: int) -> Decimal | None:
        return Decimal(value) / Decimal(played) if rates_available else None

    availability = FeatureAvailability.UNAVAILABLE if played == 0 else FeatureAvailability.COMPLETE
    return LeagueBaseline(
        coverage=Coverage(
            requested_matches=minimum_rate_observations,
            available_matches=played,
            minimum_rate_observations=minimum_rate_observations,
            availability=availability
            if rates_available or played == 0
            else FeatureAvailability.PARTIAL,
        ),
        matches_played=played,
        home_goals=home_goals,
        away_goals=away_goals,
        home_goals_per_match=rate(home_goals),
        away_goals_per_match=rate(away_goals),
        total_goals_per_match=rate(home_goals + away_goals),
        home_wins=home_wins,
        draws=draws,
        away_wins=away_wins,
        home_win_rate=rate(home_wins),
        draw_rate=rate(draws),
        away_win_rate=rate(away_wins),
        btts=btts,
        btts_rate=rate(btts),
        over_2_5=over_2_5,
        over_2_5_rate=rate(over_2_5),
    )
