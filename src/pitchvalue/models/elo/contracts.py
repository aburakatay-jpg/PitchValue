"""Typed outputs for deterministic Elo rating and replay operations."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


def _primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value


class SerializableEloResult:
    def to_dict(self) -> dict[str, Any]:
        value = _primitive(self)
        if not isinstance(value, dict):  # pragma: no cover - structural invariant
            raise TypeError("Elo result must serialize to a mapping")
        return value


@dataclass(frozen=True)
class EloExpectation(SerializableEloResult):
    stored_home_rating: Decimal
    stored_away_rating: Decimal
    effective_home_rating: Decimal
    expected_home_score: Decimal
    expected_away_score: Decimal


@dataclass(frozen=True)
class EloRatingUpdate(SerializableEloResult):
    old_home_rating: Decimal
    old_away_rating: Decimal
    new_home_rating: Decimal
    new_away_rating: Decimal
    actual_home_score: Decimal
    expected_home_score: Decimal
    adjustment: Decimal
    goal_margin_multiplier: Decimal


@dataclass(frozen=True)
class EloSnapshot(SerializableEloResult):
    target_match_id: str
    competition_id: str
    season_id: str
    home_team_id: str
    away_team_id: str
    home_pre_match_rating: Decimal
    away_pre_match_rating: Decimal
    raw_rating_difference: Decimal
    effective_home_rating: Decimal
    home_adjusted_rating_difference: Decimal
    expected_home_score: Decimal
    expected_away_score: Decimal
    home_prior_match_count: int
    away_prior_match_count: int
    as_of: datetime


@dataclass(frozen=True)
class TeamEloState(SerializableEloResult):
    team_id: str
    rating: Decimal
    match_count: int


@dataclass(frozen=True)
class EloReplayDiagnostics(SerializableEloResult):
    history_rows_received: int
    matches_processed: int
    matches_ignored: int
    target_rows_ignored: int
    future_rows_ignored: int
    same_time_rows_ignored: int
    different_competition_rows_ignored: int
    awarded_rows_ignored: int
    non_finished_rows_ignored: int
    season_transitions_applied: int


@dataclass(frozen=True)
class EloReplayResult(SerializableEloResult):
    competition_id: str
    as_of: datetime
    final_team_states: tuple[TeamEloState, ...]
    diagnostics: EloReplayDiagnostics
    pre_match_snapshots: tuple[EloSnapshot, ...]

    def state_for(self, team_id: str) -> TeamEloState | None:
        return next((state for state in self.final_team_states if state.team_id == team_id), None)
