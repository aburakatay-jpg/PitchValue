"""Team-perspective normalization and rolling form aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from pitchvalue.features.contracts import (
    Coverage,
    FeatureAvailability,
    FeatureValidationError,
    HistoricalMatch,
    ScheduleDensity,
    TeamForm,
    TeamMatchPerspective,
    TeamResult,
    TeamSchedule,
)


def normalize_team_perspective(match: HistoricalMatch, team_id: str) -> TeamMatchPerspective:
    """Normalize one finished normal-time score into the requested team's perspective."""
    if match.home_score is None or match.away_score is None:
        raise FeatureValidationError("team perspective requires a scored match")
    if team_id == match.home_team_id:
        goals_for, goals_against, was_home = match.home_score, match.away_score, True
    elif team_id == match.away_team_id:
        goals_for, goals_against, was_home = match.away_score, match.home_score, False
    else:
        raise FeatureValidationError("team did not participate in historical match")
    result = (
        TeamResult.WIN
        if goals_for > goals_against
        else TeamResult.LOSS
        if goals_for < goals_against
        else TeamResult.DRAW
    )
    return TeamMatchPerspective(
        match_id=match.match_id,
        kickoff=match.kickoff,
        was_home=was_home,
        goals_for=goals_for,
        goals_against=goals_against,
        result=result,
    )


def points_for_result(result: TeamResult) -> int:
    if result is TeamResult.WIN:
        return 3
    if result is TeamResult.DRAW:
        return 1
    if result is TeamResult.LOSS:
        return 0
    raise FeatureValidationError("result must use TeamResult")


def _coverage(requested: int, available: int, minimum: int) -> Coverage:
    availability = (
        FeatureAvailability.UNAVAILABLE
        if available == 0
        else FeatureAvailability.COMPLETE
        if available >= requested
        else FeatureAvailability.PARTIAL
    )
    return Coverage(
        requested_matches=requested,
        available_matches=available,
        minimum_rate_observations=minimum,
        availability=availability,
    )


def aggregate_team_form(
    team_id: str,
    matches: tuple[HistoricalMatch, ...],
    *,
    window: int,
    minimum_rate_observations: int,
) -> TeamForm:
    participating = [
        match for match in matches if team_id in {match.home_team_id, match.away_team_id}
    ]
    selected = participating[-window:]
    perspectives = [normalize_team_perspective(match, team_id) for match in selected]
    played = len(perspectives)
    wins = sum(item.result is TeamResult.WIN for item in perspectives)
    draws = sum(item.result is TeamResult.DRAW for item in perspectives)
    losses = sum(item.result is TeamResult.LOSS for item in perspectives)
    points = sum(points_for_result(item.result) for item in perspectives)
    goals_for = sum(item.goals_for for item in perspectives)
    goals_against = sum(item.goals_against for item in perspectives)
    clean_sheets = sum(item.goals_against == 0 for item in perspectives)
    failed_to_score = sum(item.goals_for == 0 for item in perspectives)
    btts = sum(item.goals_for > 0 and item.goals_against > 0 for item in perspectives)
    over_1_5 = sum(item.goals_for + item.goals_against >= 2 for item in perspectives)
    over_2_5 = sum(item.goals_for + item.goals_against >= 3 for item in perspectives)
    rates_available = played >= minimum_rate_observations

    def rate(value: int) -> Decimal | None:
        return Decimal(value) / Decimal(played) if rates_available else None

    return TeamForm(
        coverage=_coverage(window, played, minimum_rate_observations),
        matches_played=played,
        wins=wins,
        draws=draws,
        losses=losses,
        points=points,
        points_per_game=rate(points),
        goals_for=goals_for,
        goals_against=goals_against,
        goals_for_per_game=rate(goals_for),
        goals_against_per_game=rate(goals_against),
        goal_difference=goals_for - goals_against,
        goal_difference_per_game=rate(goals_for - goals_against),
        clean_sheets=clean_sheets,
        clean_sheet_rate=rate(clean_sheets),
        failed_to_score=failed_to_score,
        failed_to_score_rate=rate(failed_to_score),
        btts=btts,
        btts_rate=rate(btts),
        over_1_5=over_1_5,
        over_1_5_rate=rate(over_1_5),
        over_2_5=over_2_5,
        over_2_5_rate=rate(over_2_5),
        match_ids=tuple(item.match_id for item in perspectives),
    )


def calculate_schedule(
    team_id: str,
    matches: tuple[HistoricalMatch, ...],
    *,
    target_kickoff: datetime,
    density_windows_days: tuple[int, ...],
) -> TeamSchedule:
    if not isinstance(target_kickoff, datetime):
        raise FeatureValidationError("target_kickoff must be a datetime")
    team_matches = [
        match for match in matches if team_id in {match.home_team_id, match.away_team_id}
    ]
    previous = team_matches[-1] if team_matches else None
    days_since = None
    if previous is not None:
        seconds = Decimal(str((target_kickoff - previous.kickoff).total_seconds()))
        days_since = seconds / Decimal(86400)
    density = tuple(
        ScheduleDensity(
            window_days=window,
            match_count=sum(
                target_kickoff - timedelta(days=window) <= match.kickoff < target_kickoff
                for match in team_matches
            ),
        )
        for window in density_windows_days
    )
    return TeamSchedule(
        previous_match_kickoff=previous.kickoff if previous is not None else None,
        days_since_previous_match=days_since,
        density=density,
    )
