"""Chronological, competition-scoped and leakage-safe Elo replay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from pitchvalue.features.contracts import (
    FeatureValidationError,
    HistoricalMatch,
    MatchStatus,
    TargetFixture,
)
from pitchvalue.models.elo.config import DEFAULT_ELO_CONFIG, EloConfig, EloValidationError
from pitchvalue.models.elo.contracts import (
    EloReplayDiagnostics,
    EloReplayResult,
    EloSnapshot,
    TeamEloState,
)
from pitchvalue.models.elo.rating import expected_scores, regress_rating, update_ratings


@dataclass
class _MutableTeamState:
    rating: Decimal
    match_count: int = 0


def _validate_season_order(season_order: tuple[str, ...]) -> dict[str, int]:
    if not isinstance(season_order, tuple) or not season_order:
        raise EloValidationError("season_order must be a non-empty tuple")
    if any(not isinstance(season, str) or not season.strip() for season in season_order):
        raise EloValidationError("season_order identifiers must be non-empty strings")
    if len(set(season_order)) != len(season_order):
        raise EloValidationError("season_order cannot contain duplicates")
    return {season: index for index, season in enumerate(season_order)}


def _snapshot(
    *,
    match_id: str,
    competition_id: str,
    season_id: str,
    home_team_id: str,
    away_team_id: str,
    as_of: datetime,
    states: dict[str, _MutableTeamState],
    config: EloConfig,
) -> EloSnapshot:
    home_state = states.get(home_team_id)
    away_state = states.get(away_team_id)
    home_rating = config.initial_rating if home_state is None else home_state.rating
    away_rating = config.initial_rating if away_state is None else away_state.rating
    expectation = expected_scores(home_rating, away_rating, config)
    return EloSnapshot(
        target_match_id=match_id,
        competition_id=competition_id,
        season_id=season_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_pre_match_rating=home_rating,
        away_pre_match_rating=away_rating,
        raw_rating_difference=home_rating - away_rating,
        effective_home_rating=expectation.effective_home_rating,
        home_adjusted_rating_difference=expectation.effective_home_rating - away_rating,
        expected_home_score=expectation.expected_home_score,
        expected_away_score=expectation.expected_away_score,
        home_prior_match_count=0 if home_state is None else home_state.match_count,
        away_prior_match_count=0 if away_state is None else away_state.match_count,
        as_of=as_of,
    )


def replay_elo(
    history: tuple[HistoricalMatch, ...] | list[HistoricalMatch],
    *,
    competition_id: str,
    as_of: datetime,
    season_order: tuple[str, ...],
    target_match_id: str | None = None,
    terminal_season_id: str | None = None,
    include_pre_match_snapshots: bool = False,
    config: EloConfig = DEFAULT_ELO_CONFIG,
) -> EloReplayResult:
    """Replay eligible scores in explicit season order without mutating caller inputs."""
    if not isinstance(competition_id, str) or not competition_id.strip():
        raise EloValidationError("competition_id is required")
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise EloValidationError("as_of must be timezone-aware")
    order = _validate_season_order(season_order)
    if terminal_season_id is not None and terminal_season_id not in order:
        raise EloValidationError("terminal season is absent from explicit season_order")
    seen: set[str] = set()
    for match in history:
        if not isinstance(match, HistoricalMatch):
            raise FeatureValidationError("history entries must use HistoricalMatch")
        if match.match_id in seen:
            raise EloValidationError(f"duplicate historical match_id: {match.match_id}")
        seen.add(match.match_id)

    eligible: list[HistoricalMatch] = []
    target_ignored = future_ignored = same_ignored = competition_ignored = 0
    awarded_ignored = non_finished_ignored = 0
    for match in history:
        if target_match_id is not None and match.match_id == target_match_id:
            if match.kickoff < as_of:
                raise EloValidationError("target match_id appears before Elo cutoff")
            target_ignored += 1
            continue
        if match.competition_id != competition_id:
            competition_ignored += 1
            continue
        if match.kickoff > as_of:
            future_ignored += 1
            continue
        if match.kickoff == as_of:
            same_ignored += 1
            continue
        if match.status is MatchStatus.AWARDED:
            awarded_ignored += 1
            continue
        if match.status is not MatchStatus.FINISHED:
            non_finished_ignored += 1
            continue
        if match.season_id not in order:
            raise EloValidationError(
                f"season {match.season_id!r} is absent from explicit season_order"
            )
        eligible.append(match)
    eligible.sort(key=lambda match: (match.kickoff, match.match_id))

    states: dict[str, _MutableTeamState] = {}
    snapshots: list[EloSnapshot] = []
    active_season: str | None = None
    transitions = 0

    def transition_to(season_id: str) -> None:
        nonlocal active_season, transitions
        if active_season is None:
            active_season = season_id
            return
        if season_id == active_season:
            return
        if order[season_id] <= order[active_season]:
            raise EloValidationError("match chronology conflicts with explicit season_order")
        for state in states.values():
            state.rating = regress_rating(state.rating, config)
        active_season = season_id
        transitions += 1

    for match in eligible:
        transition_to(match.season_id)
        before = _snapshot(
            match_id=match.match_id,
            competition_id=match.competition_id,
            season_id=match.season_id,
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
            as_of=match.kickoff,
            states=states,
            config=config,
        )
        if include_pre_match_snapshots:
            snapshots.append(before)
        assert match.home_score is not None and match.away_score is not None
        updated = update_ratings(
            before.home_pre_match_rating,
            before.away_pre_match_rating,
            match.home_score,
            match.away_score,
            config,
        )
        home_state = states.setdefault(match.home_team_id, _MutableTeamState(config.initial_rating))
        away_state = states.setdefault(match.away_team_id, _MutableTeamState(config.initial_rating))
        home_state.rating = updated.new_home_rating
        away_state.rating = updated.new_away_rating
        home_state.match_count += 1
        away_state.match_count += 1

    if terminal_season_id is not None:
        transition_to(terminal_season_id)
    final_states = tuple(
        TeamEloState(
            team_id=team_id,
            rating=state.rating,
            match_count=state.match_count,
        )
        for team_id, state in sorted(states.items())
    )
    ignored = (
        target_ignored
        + future_ignored
        + same_ignored
        + competition_ignored
        + awarded_ignored
        + non_finished_ignored
    )
    return EloReplayResult(
        competition_id=competition_id,
        as_of=as_of,
        final_team_states=final_states,
        diagnostics=EloReplayDiagnostics(
            history_rows_received=len(history),
            matches_processed=len(eligible),
            matches_ignored=ignored,
            target_rows_ignored=target_ignored,
            future_rows_ignored=future_ignored,
            same_time_rows_ignored=same_ignored,
            different_competition_rows_ignored=competition_ignored,
            awarded_rows_ignored=awarded_ignored,
            non_finished_rows_ignored=non_finished_ignored,
            season_transitions_applied=transitions,
        ),
        pre_match_snapshots=tuple(snapshots),
    )


def target_elo_snapshot(
    target: TargetFixture,
    history: tuple[HistoricalMatch, ...] | list[HistoricalMatch],
    *,
    season_order: tuple[str, ...],
    config: EloConfig = DEFAULT_ELO_CONFIG,
) -> EloSnapshot:
    """Return target ratings and strength expectation using only pre-cutoff history."""
    replay = replay_elo(
        history,
        competition_id=target.competition_id,
        as_of=target.cutoff,
        season_order=season_order,
        target_match_id=target.match_id,
        terminal_season_id=target.season_id,
        config=config,
    )
    states = {
        state.team_id: _MutableTeamState(state.rating, state.match_count)
        for state in replay.final_team_states
    }
    return _snapshot(
        match_id=target.match_id,
        competition_id=target.competition_id,
        season_id=target.season_id,
        home_team_id=target.home_team_id,
        away_team_id=target.away_team_id,
        as_of=target.cutoff,
        states=states,
        config=config,
    )
