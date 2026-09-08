"""Typed, leakage-safe contracts for pure football feature computation."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class FeatureValidationError(ValueError):
    """Raised when feature input cannot represent a valid canonical match."""


class MatchStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    FINISHED = "FINISHED"
    AWARDED = "AWARDED"
    ABANDONED = "ABANDONED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"


class TeamResult(StrEnum):
    WIN = "WIN"
    DRAW = "DRAW"
    LOSS = "LOSS"


class FeatureAvailability(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


def _require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise FeatureValidationError(f"{field_name} is required")


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise FeatureValidationError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class OptionalMatchStatistics:
    """Optional normal-time observations; absent values remain unavailable."""

    home_shots: int | None = None
    away_shots: int | None = None
    home_shots_on_target: int | None = None
    away_shots_on_target: int | None = None
    home_corners: int | None = None
    away_corners: int | None = None
    home_fouls: int | None = None
    away_fouls: int | None = None

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise FeatureValidationError(f"{field.name} must be a non-negative integer")


@dataclass(frozen=True)
class HistoricalMatch:
    """Canonical match history supplied by a caller, not loaded by the engine."""

    match_id: str
    competition_id: str
    season_id: str
    kickoff: datetime
    home_team_id: str
    away_team_id: str
    status: MatchStatus
    home_score: int | None
    away_score: int | None
    statistics: OptionalMatchStatistics | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "match_id",
            "competition_id",
            "season_id",
            "home_team_id",
            "away_team_id",
        ):
            _require_identifier(getattr(self, field_name), field_name)
        _require_aware(self.kickoff, "kickoff")
        if self.home_team_id == self.away_team_id:
            raise FeatureValidationError("home and away teams must differ")
        if not isinstance(self.status, MatchStatus):
            raise FeatureValidationError("status must use the canonical match status")
        if (self.home_score is None) != (self.away_score is None):
            raise FeatureValidationError("home and away scores must be present together")
        for field_name in ("home_score", "away_score"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise FeatureValidationError(f"{field_name} must be a non-negative integer")
        if self.status is MatchStatus.FINISHED and self.home_score is None:
            raise FeatureValidationError("FINISHED matches require normal-time scores")
        if self.statistics is not None and not isinstance(self.statistics, OptionalMatchStatistics):
            raise FeatureValidationError("statistics must use OptionalMatchStatistics")


@dataclass(frozen=True)
class TargetFixture:
    """Outcome-free fixture metadata and optional pre-kickoff prediction cutoff."""

    match_id: str
    competition_id: str
    season_id: str
    kickoff: datetime
    home_team_id: str
    away_team_id: str
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "match_id",
            "competition_id",
            "season_id",
            "home_team_id",
            "away_team_id",
        ):
            _require_identifier(getattr(self, field_name), field_name)
        _require_aware(self.kickoff, "kickoff")
        if self.home_team_id == self.away_team_id:
            raise FeatureValidationError("home and away teams must differ")
        if self.as_of is not None:
            _require_aware(self.as_of, "as_of")
            if self.as_of > self.kickoff:
                raise FeatureValidationError("as_of cannot be after target kickoff")

    @property
    def cutoff(self) -> datetime:
        return self.as_of if self.as_of is not None else self.kickoff


@dataclass(frozen=True)
class TeamMatchPerspective:
    match_id: str
    kickoff: datetime
    was_home: bool
    goals_for: int
    goals_against: int
    result: TeamResult


@dataclass(frozen=True)
class Coverage:
    requested_matches: int
    available_matches: int
    minimum_rate_observations: int
    availability: FeatureAvailability


@dataclass(frozen=True)
class TeamForm:
    coverage: Coverage
    matches_played: int
    wins: int
    draws: int
    losses: int
    points: int
    points_per_game: Decimal | None
    goals_for: int
    goals_against: int
    goals_for_per_game: Decimal | None
    goals_against_per_game: Decimal | None
    goal_difference: int
    goal_difference_per_game: Decimal | None
    clean_sheets: int
    clean_sheet_rate: Decimal | None
    failed_to_score: int
    failed_to_score_rate: Decimal | None
    btts: int
    btts_rate: Decimal | None
    over_1_5: int
    over_1_5_rate: Decimal | None
    over_2_5: int
    over_2_5_rate: Decimal | None
    match_ids: tuple[str, ...]


@dataclass(frozen=True)
class ScheduleDensity:
    window_days: int
    match_count: int


@dataclass(frozen=True)
class TeamSchedule:
    previous_match_kickoff: datetime | None
    days_since_previous_match: Decimal | None
    density: tuple[ScheduleDensity, ...]


@dataclass(frozen=True)
class TeamFeatures:
    team_id: str
    recent: TeamForm
    extended: TeamForm
    venue_split: TeamForm
    schedule: TeamSchedule


@dataclass(frozen=True)
class LeagueBaseline:
    coverage: Coverage
    matches_played: int
    home_goals: int
    away_goals: int
    home_goals_per_match: Decimal | None
    away_goals_per_match: Decimal | None
    total_goals_per_match: Decimal | None
    home_wins: int
    draws: int
    away_wins: int
    home_win_rate: Decimal | None
    draw_rate: Decimal | None
    away_win_rate: Decimal | None
    btts: int
    btts_rate: Decimal | None
    over_2_5: int
    over_2_5_rate: Decimal | None


@dataclass(frozen=True)
class RawScoringRates:
    home_team_home_goals_scored_per_match: Decimal | None
    home_team_home_goals_conceded_per_match: Decimal | None
    away_team_away_goals_scored_per_match: Decimal | None
    away_team_away_goals_conceded_per_match: Decimal | None
    league_home_goals_per_match: Decimal | None
    league_away_goals_per_match: Decimal | None


@dataclass(frozen=True)
class FeatureDiagnostics:
    history_rows_received: int
    eligible_rows: int
    target_rows_ignored: int
    future_rows_ignored: int
    same_time_rows_ignored: int
    different_competition_rows_ignored: int
    different_season_rows_ignored: int
    awarded_rows_ignored: int
    non_finished_rows_ignored: int


def _primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value


@dataclass(frozen=True)
class MatchFeatures:
    target: TargetFixture
    home_team: TeamFeatures
    away_team: TeamFeatures
    league_baseline: LeagueBaseline
    raw_scoring_rates: RawScoringRates
    diagnostics: FeatureDiagnostics

    def to_dict(self) -> dict[str, Any]:
        """Return deterministic primitive data without persistence side effects."""
        result = _primitive(self)
        if not isinstance(result, dict):  # pragma: no cover - structural invariant
            raise TypeError("MatchFeatures must serialize to a mapping")
        return result
