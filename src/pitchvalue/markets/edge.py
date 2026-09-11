"""Deterministic MATCH_RESULT market probability and edge contracts."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from enum import StrEnum
from typing import Any

from pitchvalue.markets.config import NoVigMethod
from pitchvalue.markets.contracts import BookmakerPrice, MarketStatus, PriceReferenceType
from pitchvalue.markets.history.contracts import (
    ObservationRole,
    OddsQualityStatus,
    TimingSemantics,
)
from pitchvalue.markets.implied import normalize_market
from pitchvalue.markets.odds import validate_decimal_odds
from pitchvalue.markets.validation import create_market_group
from pitchvalue.ml.model import ML_CLASS_ORDER, MLClassProbability
from pitchvalue.prediction.contracts import MarketFamily, Selection

EDGE_ENGINE_VERSION = "match_result_edge_v1"
NO_VIG_VERSION = "task11_proportional_no_vig_v1"
RAW_ML_MODEL_SOURCE = "RAW_TASK16_ML"


class MarketEdgeError(ValueError):
    """Raised when model/market comparison contracts are invalid."""


class MarketComparisonStatus(StrEnum):
    ROLE_ONLY_COMPARISON = "ROLE_ONLY_COMPARISON"
    EXACT_TIME_COMPARISON = "EXACT_TIME_COMPARISON"
    NOT_TEMPORALLY_COMPARABLE = "NOT_TEMPORALLY_COMPARABLE"
    MISSING_MARKET = "MISSING_MARKET"
    INVALID_MARKET = "INVALID_MARKET"
    UNSUPPORTED = "UNSUPPORTED"


class EdgeThresholdDiagnostic(StrEnum):
    BELOW_THRESHOLD = "BELOW_THRESHOLD"
    WATCHLIST_EDGE = "WATCHLIST_EDGE"
    PUBLISHABLE_EDGE = "PUBLISHABLE_EDGE"


class EdgeOddsBand(StrEnum):
    BELOW_1_35 = "BELOW_1_35"
    FROM_1_35_TO_1_49 = "FROM_1_35_TO_1_49"
    FROM_1_50_TO_2_20 = "FROM_1_50_TO_2_20"
    FROM_2_21_TO_3_00 = "FROM_2_21_TO_3_00"
    ABOVE_3_00 = "ABOVE_3_00"


@dataclass(frozen=True)
class RawMLProbability:
    row_id: str
    match_id: str
    model_version: str
    feature_profile: str
    prediction_as_of: datetime
    probabilities: tuple[MLClassProbability, ...]
    source: str = RAW_ML_MODEL_SOURCE

    def __post_init__(self) -> None:
        if self.source != RAW_ML_MODEL_SOURCE:
            raise MarketEdgeError("canonical TASK 19 source must be raw TASK 16 ML")
        if any(not value.strip() for value in (self.row_id, self.match_id, self.model_version)):
            raise MarketEdgeError("model identities must be nonblank")
        if self.prediction_as_of.tzinfo is None or self.prediction_as_of.utcoffset() is None:
            raise MarketEdgeError("prediction_as_of must be timezone-aware")
        if tuple(item.selection for item in self.probabilities) != ML_CLASS_ORDER:
            raise MarketEdgeError("model class order must be HOME, DRAW, AWAY")
        values = tuple(item.probability for item in self.probabilities)
        if any(not value.is_finite() or value < 0 or value > 1 for value in values):
            raise MarketEdgeError("model probabilities must be finite values in [0,1]")
        if sum(values, Decimal(0)) != Decimal(1):
            raise MarketEdgeError("model probabilities must sum exactly to one")


@dataclass(frozen=True)
class HistoricalMarketPrice:
    odds_snapshot_id: int
    match_id: str
    provider_id: str
    bookmaker: str
    market: MarketFamily
    selection: Selection
    decimal_odds: Decimal
    observation_role: ObservationRole
    timing_semantics: TimingSemantics
    observed_at: datetime | None
    quality_status: OddsQualityStatus
    quality_reasons: tuple[str, ...]
    source_match_provider_ref_id: int
    source_staging_row_id: int
    source_field: str
    mapping_version: str
    normalization_version: str
    quality_policy_version: str

    def __post_init__(self) -> None:
        validate_decimal_odds(self.decimal_odds)
        if self.market is not MarketFamily.MATCH_RESULT:
            raise MarketEdgeError("TASK 19 supports MATCH_RESULT only")
        if self.selection not in ML_CLASS_ORDER:
            raise MarketEdgeError("historical market selection must be HOME, DRAW, or AWAY")
        if self.observation_role not in (
            ObservationRole.SOURCE_PREMATCH,
            ObservationRole.CLOSING,
        ):
            raise MarketEdgeError("unsupported historical observation role")
        if self.timing_semantics is TimingSemantics.EXACT and self.observed_at is None:
            raise MarketEdgeError("exact timing requires observed_at")
        if self.observed_at is not None and (
            self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None
        ):
            raise MarketEdgeError("observed_at must be timezone-aware")
        for value in (
            self.match_id,
            self.provider_id,
            self.bookmaker,
            self.source_field,
            self.mapping_version,
            self.normalization_version,
            self.quality_policy_version,
        ):
            if not value.strip():
                raise MarketEdgeError("market identities and versions must be nonblank")


@dataclass(frozen=True)
class HistoricalMarketGroup:
    match_id: str
    bookmaker: str
    observation_role: ObservationRole
    timing_semantics: TimingSemantics
    observed_at: datetime | None
    prices: tuple[HistoricalMarketPrice, ...]

    def __post_init__(self) -> None:
        if tuple(item.selection for item in self.prices) != ML_CLASS_ORDER:
            raise MarketEdgeError("market group requires exactly HOME, DRAW, AWAY")
        for item in self.prices:
            if (
                item.match_id != self.match_id
                or item.bookmaker != self.bookmaker
                or item.observation_role is not self.observation_role
                or item.timing_semantics is not self.timing_semantics
                or item.observed_at != self.observed_at
            ):
                raise MarketEdgeError("market group contains mismatched observations")


@dataclass(frozen=True)
class MarketSelectionProbability:
    price: HistoricalMarketPrice
    raw_implied_probability: Decimal
    no_vig_probability: Decimal


@dataclass(frozen=True)
class MarketProbability:
    match_id: str
    bookmaker: str
    observation_role: ObservationRole
    timing_semantics: TimingSemantics
    observed_at: datetime | None
    selections: tuple[MarketSelectionProbability, ...]
    book_percentage: Decimal
    overround: Decimal
    bookmaker_margin: Decimal
    no_vig_method: NoVigMethod
    no_vig_version: str
    status: MarketComparisonStatus
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(self)


@dataclass(frozen=True)
class SelectionEdge:
    selection: Selection
    model_probability: Decimal
    market_probability: Decimal
    decimal_odds: Decimal
    edge: Decimal
    raw_price_ev: Decimal
    threshold_diagnostic: EdgeThresholdDiagnostic
    odds_band: EdgeOddsBand
    source_field: str
    source_match_provider_ref_id: int
    source_staging_row_id: int


@dataclass(frozen=True)
class MarketEdgeResult:
    row_id: str
    match_id: str
    model_version: str
    feature_profile: str
    edge_engine_version: str
    prediction_as_of: datetime
    market: MarketFamily
    bookmaker: str
    observation_role: ObservationRole
    timing_semantics: TimingSemantics
    observed_at: datetime | None
    comparison_status: MarketComparisonStatus
    no_vig_method: NoVigMethod
    no_vig_version: str
    mapping_version: str
    normalization_version: str
    quality_policy_version: str
    edges: tuple[SelectionEdge, ...]
    best_edge_selection: Selection
    model_top_selection: Selection
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(self)


def build_market_probability(group: HistoricalMarketGroup) -> MarketProbability:
    if any(item.quality_status is not OddsQualityStatus.ELIGIBLE for item in group.prices):
        raise MarketEdgeError("default market evaluation requires eligible observations")
    task11 = normalize_market(
        create_market_group(
            tuple(
                BookmakerPrice(
                    item.match_id,
                    item.provider_id,
                    item.market,
                    item.selection,
                    None,
                    item.decimal_odds,
                    item.observed_at,
                    reference_type=PriceReferenceType.SOURCE_PRICE,
                )
                for item in group.prices
            )
        )
    )
    if task11.status is not MarketStatus.READY:
        raise MarketEdgeError(f"TASK 11 market normalization failed: {task11.status.value}")
    assert task11.book_percentage is not None and task11.overround is not None
    selections = tuple(
        MarketSelectionProbability(
            source,
            normalized.raw_implied_probability,
            _required_probability(normalized.no_vig_probability),
        )
        for source, normalized in zip(group.prices, task11.prices, strict=True)
    )
    status = _comparison_status(group)
    diagnostics = ["MODEL_PROBABILITY_UNCALIBRATED"]
    if status is MarketComparisonStatus.ROLE_ONLY_COMPARISON:
        diagnostics.append("MARKET_EXACT_TIMESTAMP_UNKNOWN")
    if group.observation_role is ObservationRole.CLOSING:
        diagnostics.append("CLOSING_REFERENCE_DIAGNOSTIC")
    else:
        diagnostics.append("SOURCE_PREMATCH_ROLE_REFERENCE")
    return MarketProbability(
        group.match_id,
        group.bookmaker,
        group.observation_role,
        group.timing_semantics,
        group.observed_at,
        selections,
        task11.book_percentage,
        task11.overround,
        task11.overround,
        task11.normalization_method,
        NO_VIG_VERSION,
        status,
        tuple(diagnostics),
    )


def calculate_market_edges(model: RawMLProbability, market: MarketProbability) -> MarketEdgeResult:
    if model.match_id != market.match_id:
        raise MarketEdgeError("model and market match identities differ")
    if market.status not in (
        MarketComparisonStatus.ROLE_ONLY_COMPARISON,
        MarketComparisonStatus.EXACT_TIME_COMPARISON,
    ):
        raise MarketEdgeError("market is not usable for edge comparison")
    if (
        market.status is MarketComparisonStatus.EXACT_TIME_COMPARISON
        and market.observed_at is not None
        and market.observed_at > model.prediction_as_of
    ):
        raise MarketEdgeError("exact market observation is after prediction_as_of")
    model_values = {item.selection: item.probability for item in model.probabilities}
    edges = tuple(
        _selection_edge(model_values[item.price.selection], item) for item in market.selections
    )
    top = max(
        model.probabilities,
        key=lambda item: (item.probability, -ML_CLASS_ORDER.index(item.selection)),
    )
    best = max(edges, key=lambda item: (item.edge, -ML_CLASS_ORDER.index(item.selection)))
    mapping_versions = {item.price.mapping_version for item in market.selections}
    versions = {item.price.normalization_version for item in market.selections}
    quality_versions = {item.price.quality_policy_version for item in market.selections}
    if len(mapping_versions) != 1 or len(versions) != 1 or len(quality_versions) != 1:
        raise MarketEdgeError("market group mixes semantic versions")
    return MarketEdgeResult(
        model.row_id,
        model.match_id,
        model.model_version,
        model.feature_profile,
        EDGE_ENGINE_VERSION,
        model.prediction_as_of,
        MarketFamily.MATCH_RESULT,
        market.bookmaker,
        market.observation_role,
        market.timing_semantics,
        market.observed_at,
        market.status,
        market.no_vig_method,
        market.no_vig_version,
        next(iter(mapping_versions)),
        next(iter(versions)),
        next(iter(quality_versions)),
        edges,
        best.selection,
        top.selection,
        market.diagnostics,
    )


def classify_edge(edge: Decimal) -> EdgeThresholdDiagnostic:
    _finite_decimal(edge, "edge")
    if edge < Decimal("0.04"):
        return EdgeThresholdDiagnostic.BELOW_THRESHOLD
    if edge < Decimal("0.06"):
        return EdgeThresholdDiagnostic.WATCHLIST_EDGE
    return EdgeThresholdDiagnostic.PUBLISHABLE_EDGE


def classify_odds(decimal_odds: Decimal) -> EdgeOddsBand:
    validate_decimal_odds(decimal_odds)
    if decimal_odds < Decimal("1.35"):
        return EdgeOddsBand.BELOW_1_35
    if decimal_odds < Decimal("1.50"):
        return EdgeOddsBand.FROM_1_35_TO_1_49
    if decimal_odds <= Decimal("2.20"):
        return EdgeOddsBand.FROM_1_50_TO_2_20
    if decimal_odds <= Decimal("3.00"):
        return EdgeOddsBand.FROM_2_21_TO_3_00
    return EdgeOddsBand.ABOVE_3_00


def _selection_edge(
    model_probability: Decimal, market: MarketSelectionProbability
) -> SelectionEdge:
    _probability(model_probability, "model_probability")
    with localcontext() as context:
        context.prec = 50
        edge = model_probability - market.no_vig_probability
        raw_ev = model_probability * market.price.decimal_odds - Decimal(1)
    return SelectionEdge(
        market.price.selection,
        model_probability,
        market.no_vig_probability,
        market.price.decimal_odds,
        edge,
        raw_ev,
        classify_edge(edge),
        classify_odds(market.price.decimal_odds),
        market.price.source_field,
        market.price.source_match_provider_ref_id,
        market.price.source_staging_row_id,
    )


def _comparison_status(group: HistoricalMarketGroup) -> MarketComparisonStatus:
    if group.timing_semantics is TimingSemantics.EXACT:
        return MarketComparisonStatus.EXACT_TIME_COMPARISON
    if group.timing_semantics is TimingSemantics.ROLE_ONLY:
        return MarketComparisonStatus.ROLE_ONLY_COMPARISON
    return MarketComparisonStatus.NOT_TEMPORALLY_COMPARABLE


def _required_probability(value: Decimal | None) -> Decimal:
    if value is None:  # pragma: no cover - READY invariant
        raise MarketEdgeError("no-vig probability is required")
    return value


def _probability(value: Decimal, name: str) -> None:
    _finite_decimal(value, name)
    if value < 0 or value > 1:
        raise MarketEdgeError(f"{name} must be in [0,1]")


def _finite_decimal(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise MarketEdgeError(f"{name} must be a finite Decimal")


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


def _as_dict(value: object) -> dict[str, Any]:
    result = _primitive(value)
    if not isinstance(result, dict):  # pragma: no cover
        raise TypeError("contract must serialize to a mapping")
    return result
