"""Typed inputs and auditable outputs for the Poisson model foundation."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pitchvalue.features.contracts import FeatureAvailability
from pitchvalue.models.poisson.config import PoissonValidationError
from pitchvalue.prediction.contracts import MarketFamily, Selection


class PoissonModelStatus(StrEnum):
    READY = "READY"
    INPUT_INSUFFICIENT = "INPUT_INSUFFICIENT"
    INVALID_INPUT = "INVALID_INPUT"


def _rate(value: Decimal | None, field_name: str, *, league: bool = False) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal) or not value.is_finite():
        raise PoissonValidationError(f"{field_name} must be a finite Decimal or None")
    if value < 0 or (league and value == 0):
        qualifier = "positive" if league else "non-negative"
        raise PoissonValidationError(f"{field_name} must be {qualifier}")


@dataclass(frozen=True)
class PoissonModelInput:
    match_id: str
    home_team_home_goals_for_per_match: Decimal | None
    home_team_home_goals_against_per_match: Decimal | None
    away_team_away_goals_for_per_match: Decimal | None
    away_team_away_goals_against_per_match: Decimal | None
    league_home_goals_per_match: Decimal | None
    league_away_goals_per_match: Decimal | None
    home_venue_availability: FeatureAvailability = FeatureAvailability.COMPLETE
    away_venue_availability: FeatureAvailability = FeatureAvailability.COMPLETE
    league_availability: FeatureAvailability = FeatureAvailability.COMPLETE

    def __post_init__(self) -> None:
        if not isinstance(self.match_id, str) or not self.match_id.strip():
            raise PoissonValidationError("match_id is required")
        _rate(
            self.home_team_home_goals_for_per_match,
            "home_team_home_goals_for_per_match",
        )
        _rate(
            self.home_team_home_goals_against_per_match,
            "home_team_home_goals_against_per_match",
        )
        _rate(
            self.away_team_away_goals_for_per_match,
            "away_team_away_goals_for_per_match",
        )
        _rate(
            self.away_team_away_goals_against_per_match,
            "away_team_away_goals_against_per_match",
        )
        _rate(self.league_home_goals_per_match, "league_home_goals_per_match", league=True)
        _rate(self.league_away_goals_per_match, "league_away_goals_per_match", league=True)
        for field_name in (
            "home_venue_availability",
            "away_venue_availability",
            "league_availability",
        ):
            if not isinstance(getattr(self, field_name), FeatureAvailability):
                raise PoissonValidationError(f"{field_name} must use FeatureAvailability")
        if self.home_venue_availability is FeatureAvailability.UNAVAILABLE and any(
            value is not None
            for value in (
                self.home_team_home_goals_for_per_match,
                self.home_team_home_goals_against_per_match,
            )
        ):
            raise PoissonValidationError("unavailable home coverage cannot contain rates")
        if self.away_venue_availability is FeatureAvailability.UNAVAILABLE and any(
            value is not None
            for value in (
                self.away_team_away_goals_for_per_match,
                self.away_team_away_goals_against_per_match,
            )
        ):
            raise PoissonValidationError("unavailable away coverage cannot contain rates")
        if self.league_availability is FeatureAvailability.UNAVAILABLE and any(
            value is not None
            for value in (
                self.league_home_goals_per_match,
                self.league_away_goals_per_match,
            )
        ):
            raise PoissonValidationError("unavailable league coverage cannot contain rates")

    @property
    def missing_fields(self) -> tuple[str, ...]:
        names = (
            "home_team_home_goals_for_per_match",
            "home_team_home_goals_against_per_match",
            "away_team_away_goals_for_per_match",
            "away_team_away_goals_against_per_match",
            "league_home_goals_per_match",
            "league_away_goals_per_match",
        )
        return tuple(name for name in names if getattr(self, name) is None)


@dataclass(frozen=True)
class PoissonStrengths:
    lambda_home: Decimal
    lambda_away: Decimal
    home_attack_strength: Decimal
    home_defensive_weakness: Decimal
    away_attack_strength: Decimal
    away_defensive_weakness: Decimal
    league_home_goal_rate: Decimal
    league_away_goal_rate: Decimal


@dataclass(frozen=True)
class ScoreProbability:
    home_goals: int
    away_goals: int
    probability: Decimal


@dataclass(frozen=True)
class ScoreMatrix:
    max_goals: int
    cells: tuple[ScoreProbability, ...]
    represented_probability_mass: Decimal
    residual_probability_mass: Decimal

    def exact_score(self, home_goals: int, away_goals: int) -> Decimal:
        if not 0 <= home_goals <= self.max_goals or not 0 <= away_goals <= self.max_goals:
            raise PoissonValidationError("score is outside the configured matrix")
        index = home_goals * (self.max_goals + 1) + away_goals
        return self.cells[index].probability


@dataclass(frozen=True)
class MarketProbability:
    market: MarketFamily
    selection: Selection
    line: Decimal | None
    probability: Decimal


@dataclass(frozen=True)
class MarketProbabilities:
    values: tuple[MarketProbability, ...]

    def get(
        self, market: MarketFamily, selection: Selection, line: Decimal | None = None
    ) -> Decimal:
        for value in self.values:
            if value.market is market and value.selection is selection and value.line == line:
                return value.probability
        raise KeyError((market, selection, line))


@dataclass(frozen=True)
class PoissonDiagnostics:
    max_goals: int
    probability_tolerance: Decimal
    matrix_represented_mass: Decimal
    matrix_residual_mass: Decimal
    one_x_two_represented_mass: Decimal
    partial_history_used: bool


def _primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value


@dataclass(frozen=True)
class PoissonAnalysis:
    match_id: str
    status: PoissonModelStatus
    strengths: PoissonStrengths | None
    score_matrix: ScoreMatrix | None
    markets: MarketProbabilities | None
    diagnostics: PoissonDiagnostics | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = _primitive(self)
        if not isinstance(value, dict):  # pragma: no cover - structural invariant
            raise TypeError("PoissonAnalysis must serialize to a mapping")
        return value
