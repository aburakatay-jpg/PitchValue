"""Immutable, centrally validated V1 prediction policy configuration."""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Any

from pitchvalue.prediction.contracts import ContractValidationError


def _validate_decimal_fields(instance: object, field_names: tuple[str, ...]) -> None:
    if any(not isinstance(getattr(instance, name), Decimal) for name in field_names):
        raise ContractValidationError("prediction policy numeric fields must use Decimal")


@dataclass(frozen=True)
class BetScoreWeights:
    edge: Decimal = Decimal("0.35")
    model_agreement: Decimal = Decimal("0.25")
    data_quality: Decimal = Decimal("0.15")
    calibration_confidence: Decimal = Decimal("0.15")
    market_stability: Decimal = Decimal("0.10")

    def __post_init__(self) -> None:
        names = tuple(field.name for field in fields(self))
        _validate_decimal_fields(self, names)
        values = tuple(getattr(self, name) for name in names)
        if any(value < 0 or value > 1 for value in values):
            raise ContractValidationError("Bet Score weights must be between 0 and 1")
        if sum(values, Decimal(0)) != Decimal(1):
            raise ContractValidationError("Bet Score weights must total 1.0")


@dataclass(frozen=True)
class BetScoreBoundaries:
    watchlist: Decimal = Decimal("60")
    pick: Decimal = Decimal("70")
    strong_pick: Decimal = Decimal("80")
    elite_pick: Decimal = Decimal("90")

    def __post_init__(self) -> None:
        _validate_decimal_fields(self, tuple(field.name for field in fields(self)))
        if not (
            Decimal(0)
            <= self.watchlist
            < self.pick
            < self.strong_pick
            < self.elite_pick
            <= Decimal(100)
        ):
            raise ContractValidationError("Bet Score boundaries must be ordered within 0 to 100")


@dataclass(frozen=True)
class EdgeScoreMapping:
    """INITIAL HEURISTIC — SUBJECT TO BACKTEST CALIBRATION."""

    watchlist_score: Decimal = Decimal("50")
    publication_score: Decimal = Decimal("70")
    maximum_edge: Decimal = Decimal("0.12")
    maximum_score: Decimal = Decimal("100")

    def __post_init__(self) -> None:
        _validate_decimal_fields(self, tuple(field.name for field in fields(self)))
        if not (
            Decimal(0)
            < self.watchlist_score
            < self.publication_score
            < self.maximum_score
            <= Decimal(100)
        ):
            raise ContractValidationError("edge-score mapping scores must be ordered")
        if self.maximum_edge <= 0:
            raise ContractValidationError("edge-score maximum edge must be positive")


@dataclass(frozen=True)
class PredictionPolicyConfig:
    """Canonical initial V1 policy, subject to backtest calibration."""

    edge_watchlist_threshold: Decimal = Decimal("0.04")
    edge_publication_threshold: Decimal = Decimal("0.06")
    score_boundaries: BetScoreBoundaries = BetScoreBoundaries()
    weights: BetScoreWeights = BetScoreWeights()
    minimum_agreement_ratio: Decimal = Decimal("0.75")
    minimum_data_quality_score: Decimal = Decimal("70")
    odds_display_minimum: Decimal = Decimal("1.35")
    low_odds_upper_bound: Decimal = Decimal("1.50")
    ideal_odds_minimum: Decimal = Decimal("1.50")
    ideal_odds_maximum: Decimal = Decimal("2.20")
    v1_main_maximum_odds: Decimal = Decimal("3.00")
    low_odds_exception_bet_score: Decimal = Decimal("85")
    low_odds_exception_edge: Decimal = Decimal("0.08")
    low_odds_exception_agreement_ratio: Decimal = Decimal("0.90")
    edge_score_mapping: EdgeScoreMapping = EdgeScoreMapping()

    def __post_init__(self) -> None:
        if not isinstance(self.score_boundaries, BetScoreBoundaries):
            raise ContractValidationError("score_boundaries must use BetScoreBoundaries")
        if not isinstance(self.weights, BetScoreWeights):
            raise ContractValidationError("weights must use BetScoreWeights")
        if not isinstance(self.edge_score_mapping, EdgeScoreMapping):
            raise ContractValidationError("edge_score_mapping must use EdgeScoreMapping")
        _validate_decimal_fields(
            self,
            (
                "edge_watchlist_threshold",
                "edge_publication_threshold",
                "minimum_agreement_ratio",
                "minimum_data_quality_score",
                "odds_display_minimum",
                "low_odds_upper_bound",
                "ideal_odds_minimum",
                "ideal_odds_maximum",
                "v1_main_maximum_odds",
                "low_odds_exception_bet_score",
                "low_odds_exception_edge",
                "low_odds_exception_agreement_ratio",
            ),
        )
        if not (
            Decimal(0)
            <= self.edge_watchlist_threshold
            < self.edge_publication_threshold
            <= Decimal(1)
        ):
            raise ContractValidationError("edge thresholds must be ordered within 0 to 1")
        if self.edge_score_mapping.maximum_edge <= self.edge_publication_threshold:
            raise ContractValidationError("edge-score maximum must exceed publication threshold")
        if not Decimal(0) <= self.minimum_agreement_ratio <= Decimal(1):
            raise ContractValidationError("minimum agreement ratio must be within 0 to 1")
        if not Decimal(0) <= self.minimum_data_quality_score <= Decimal(100):
            raise ContractValidationError("minimum data quality must be within 0 to 100")
        if not (
            Decimal(1)
            < self.odds_display_minimum
            < self.low_odds_upper_bound
            == self.ideal_odds_minimum
            <= self.ideal_odds_maximum
            < self.v1_main_maximum_odds
        ):
            raise ContractValidationError("odds boundaries must be consistently ordered")
        if not (self.score_boundaries.pick <= self.low_odds_exception_bet_score <= Decimal(100)):
            raise ContractValidationError("low-odds exceptional Bet Score is impossible")
        if not (
            self.edge_publication_threshold
            <= self.low_odds_exception_edge
            <= self.edge_score_mapping.maximum_edge
        ):
            raise ContractValidationError("low-odds exceptional edge is impossible")
        if not (
            self.minimum_agreement_ratio <= self.low_odds_exception_agreement_ratio <= Decimal(1)
        ):
            raise ContractValidationError("low-odds exceptional agreement is impossible")

    def as_serializable_dict(self) -> dict[str, Any]:
        """Return a stable debug representation with decimal values encoded as strings."""

        def serialize(value: object) -> object:
            if isinstance(value, Decimal):
                return str(value)
            if hasattr(value, "__dataclass_fields__"):
                return {
                    field.name: serialize(getattr(value, field.name))
                    for field in fields(value)  # type: ignore[arg-type]
                }
            return value

        return {field.name: serialize(getattr(self, field.name)) for field in fields(self)}


DEFAULT_POLICY = PredictionPolicyConfig()
