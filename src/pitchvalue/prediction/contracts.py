"""Typed contracts for deterministic V1 prediction policy inputs and outputs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

type DecimalInput = Decimal | str | int


class ContractValidationError(ValueError):
    """Raised when policy input violates a canonical numeric or market contract."""


def decimal_value(value: DecimalInput) -> Decimal:
    """Convert explicit decimal-compatible input while rejecting binary floats."""
    if isinstance(value, (bool, float)):
        raise ContractValidationError("use Decimal, str, or int for numeric policy values")
    try:
        converted = Decimal(value)
    except Exception as error:
        raise ContractValidationError("invalid decimal value") from error
    if not converted.is_finite():
        raise ContractValidationError("numeric policy values must be finite")
    return converted


def require_probability(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise ContractValidationError(f"{field_name} must use Decimal")
    if value < Decimal(0) or value > Decimal(1):
        raise ContractValidationError(f"{field_name} must be between 0 and 1")


def require_score(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise ContractValidationError(f"{field_name} must use Decimal")
    if value < Decimal(0) or value > Decimal(100):
        raise ContractValidationError(f"{field_name} must be between 0 and 100")


class MarketFamily(StrEnum):
    MATCH_RESULT = "match_result"
    TOTAL_GOALS = "total_goals"
    BTTS = "btts"
    DOUBLE_CHANCE = "double_chance"
    HOME_TEAM_TOTAL = "home_team_total"
    AWAY_TEAM_TOTAL = "away_team_total"


class Selection(StrEnum):
    HOME = "home"
    DRAW = "draw"
    AWAY = "away"
    OVER = "over"
    UNDER = "under"
    YES = "yes"
    NO = "no"
    ONE_X = "1X"
    X_TWO = "X2"
    ONE_TWO = "12"


class AnalysisAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class QualityClass(StrEnum):
    NO_BET = "NO_BET"
    WATCHLIST = "WATCHLIST"
    PICK = "PICK"
    STRONG_PICK = "STRONG_PICK"
    ELITE_PICK = "ELITE_PICK"


class PublicationRole(StrEnum):
    MAIN = "main"
    ALTERNATIVE = "alternative"


class PolicyReason(StrEnum):
    EDGE_BELOW_MINIMUM = "EDGE_BELOW_MINIMUM"
    EDGE_WATCHLIST_ONLY = "EDGE_WATCHLIST_ONLY"
    BET_SCORE_BELOW_PUBLICATION = "BET_SCORE_BELOW_PUBLICATION"
    MODEL_AGREEMENT_INSUFFICIENT = "MODEL_AGREEMENT_INSUFFICIENT"
    DATA_QUALITY_INSUFFICIENT = "DATA_QUALITY_INSUFFICIENT"
    DATA_QUALITY_MISSING = "DATA_QUALITY_MISSING"
    CALIBRATION_CONFIDENCE_MISSING = "CALIBRATION_CONFIDENCE_MISSING"
    MARKET_STABILITY_MISSING = "MARKET_STABILITY_MISSING"
    ANALYSIS_UNAVAILABLE = "ANALYSIS_UNAVAILABLE"
    ODDS_BELOW_DISPLAY_MINIMUM = "ODDS_BELOW_DISPLAY_MINIMUM"
    LOW_ODDS_REQUIRES_STRONGER_SIGNAL = "LOW_ODDS_REQUIRES_STRONGER_SIGNAL"
    ODDS_ABOVE_V1_MAIN_MAX = "ODDS_ABOVE_V1_MAIN_MAX"
    PUBLISHABLE = "PUBLISHABLE"


class FailureState(StrEnum):
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    NO_BET = "NO_BET"
    ANALYSIS_UNAVAILABLE = "ANALYSIS_UNAVAILABLE"


class OddsBand(StrEnum):
    BELOW_DISPLAY_MINIMUM = "below_display_minimum"
    LOW_ODDS = "low_odds"
    IDEAL = "ideal"
    HIGHER_RISK = "higher_risk"
    ABOVE_V1_MAIN_MAX = "above_v1_main_max"


_MARKET_SELECTIONS: dict[MarketFamily, frozenset[Selection]] = {
    MarketFamily.MATCH_RESULT: frozenset({Selection.HOME, Selection.DRAW, Selection.AWAY}),
    MarketFamily.TOTAL_GOALS: frozenset({Selection.OVER, Selection.UNDER}),
    MarketFamily.BTTS: frozenset({Selection.YES, Selection.NO}),
    MarketFamily.DOUBLE_CHANCE: frozenset({Selection.ONE_X, Selection.X_TWO, Selection.ONE_TWO}),
    MarketFamily.HOME_TEAM_TOTAL: frozenset({Selection.OVER, Selection.UNDER}),
    MarketFamily.AWAY_TEAM_TOTAL: frozenset({Selection.OVER, Selection.UNDER}),
}

_MARKET_LINES: dict[MarketFamily, frozenset[Decimal] | None] = {
    MarketFamily.MATCH_RESULT: None,
    MarketFamily.TOTAL_GOALS: frozenset({Decimal("1.5"), Decimal("2.5")}),
    MarketFamily.BTTS: None,
    MarketFamily.DOUBLE_CHANCE: None,
    MarketFamily.HOME_TEAM_TOTAL: frozenset({Decimal("0.5"), Decimal("1.5")}),
    MarketFamily.AWAY_TEAM_TOTAL: frozenset({Decimal("0.5"), Decimal("1.5")}),
}


@dataclass(frozen=True)
class MarketCandidate:
    """A fully analyzed market candidate supplied to policy, never a published pick."""

    match_id: str
    market: MarketFamily
    selection: Selection
    line: Decimal | None
    model_probability: Decimal
    market_implied_probability: Decimal
    decimal_odds: Decimal
    model_agreement_count: int
    model_count: int
    data_quality_score: Decimal | None
    calibration_confidence: Decimal | None
    market_stability_score: Decimal | None
    analysis_availability: AnalysisAvailability = AnalysisAvailability.AVAILABLE
    correlation_group: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.match_id, str) or not self.match_id.strip():
            raise ContractValidationError("match_id is required")
        if not isinstance(self.market, MarketFamily) or not isinstance(self.selection, Selection):
            raise ContractValidationError("market and selection must use canonical identifiers")
        numeric_values = {
            "model_probability": self.model_probability,
            "market_implied_probability": self.market_implied_probability,
            "decimal_odds": self.decimal_odds,
        }
        if self.line is not None:
            numeric_values["line"] = self.line
        for field_name in (
            "data_quality_score",
            "calibration_confidence",
            "market_stability_score",
        ):
            value = getattr(self, field_name)
            if value is not None:
                numeric_values[field_name] = value
        if any(not isinstance(value, Decimal) for value in numeric_values.values()):
            raise ContractValidationError("numeric policy fields must use Decimal")
        if self.selection not in _MARKET_SELECTIONS[self.market]:
            raise ContractValidationError("selection is not valid for market")
        allowed_lines = _MARKET_LINES[self.market]
        if allowed_lines is None and self.line is not None:
            raise ContractValidationError("line must be absent for market")
        if allowed_lines is not None and self.line not in allowed_lines:
            raise ContractValidationError("line is not valid for market")
        require_probability(self.model_probability, "model_probability")
        require_probability(self.market_implied_probability, "market_implied_probability")
        if self.decimal_odds <= Decimal(1):
            raise ContractValidationError("decimal_odds must be greater than 1")
        if (
            not isinstance(self.model_count, int)
            or isinstance(self.model_count, bool)
            or self.model_count < 0
        ):
            raise ContractValidationError("model_count must be a non-negative integer")
        if (
            not isinstance(self.model_agreement_count, int)
            or isinstance(self.model_agreement_count, bool)
            or self.model_agreement_count < 0
        ):
            raise ContractValidationError("model_agreement_count must be a non-negative integer")
        if self.model_agreement_count > self.model_count:
            raise ContractValidationError("model_agreement_count cannot exceed model_count")
        for field_name in (
            "data_quality_score",
            "calibration_confidence",
            "market_stability_score",
        ):
            value = getattr(self, field_name)
            if value is not None:
                require_score(value, field_name)
        if not isinstance(self.analysis_availability, AnalysisAvailability):
            raise ContractValidationError("analysis_availability must use a canonical state")
        if self.correlation_group is not None and (
            not isinstance(self.correlation_group, str) or not self.correlation_group.strip()
        ):
            raise ContractValidationError("correlation_group cannot be blank")

    @property
    def edge(self) -> Decimal:
        """Return model probability minus implied probability in decimal-fraction units."""
        return self.model_probability - self.market_implied_probability

    @property
    def agreement_ratio(self) -> Decimal | None:
        if self.model_count == 0:
            return None
        return Decimal(self.model_agreement_count) / Decimal(self.model_count)


@dataclass(frozen=True)
class RankingInputs:
    """Inputs future same-match ranking may use; no single metric determines rank."""

    bet_score: Decimal
    edge: Decimal
    agreement_ratio: Decimal
    market_stability_score: Decimal
    decimal_odds: Decimal
    odds_band: OddsBand


@dataclass(frozen=True)
class PickSelectionLimits:
    """V1 output limits for future ranking and correlation suppression."""

    maximum_main_picks: int = 1
    maximum_alternative_picks: int = 1


@dataclass(frozen=True)
class PolicyEvaluation:
    """Pure policy result suitable for future persistence, APIs, ranking, and logs."""

    match_id: str
    market: MarketFamily
    selection: Selection
    line: Decimal | None
    quality_class: QualityClass
    bet_score: Decimal | None
    publication_eligible: bool
    eligible_roles: tuple[PublicationRole, ...]
    reasons: tuple[PolicyReason, ...]
    edge: Decimal
    agreement_ratio: Decimal | None
    odds_band: OddsBand
    failure_state: FailureState | None
    ranking_inputs: RankingInputs | None
    correlation_group: str | None

    @property
    def main_pick_eligible(self) -> bool:
        return PublicationRole.MAIN in self.eligible_roles

    @property
    def alternative_pick_eligible(self) -> bool:
        return PublicationRole.ALTERNATIVE in self.eligible_roles

    def decision_data(self) -> dict[str, object]:
        """Return a structured, non-telemetry decision record for callers to log."""
        return {
            "match_id": self.match_id,
            "market": self.market.value,
            "selection": self.selection.value,
            "line": str(self.line) if self.line is not None else None,
            "edge": str(self.edge),
            "bet_score": str(self.bet_score) if self.bet_score is not None else None,
            "quality_class": self.quality_class.value,
            "publication_eligible": self.publication_eligible,
            "eligible_roles": [role.value for role in self.eligible_roles],
            "reasons": [reason.value for reason in self.reasons],
            "failure_state": self.failure_state.value if self.failure_state else None,
            "odds_band": self.odds_band.value,
            "correlation_group": self.correlation_group,
        }
