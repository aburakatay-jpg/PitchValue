"""Read-only same-row RAW ML versus historical market evaluation."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from statistics import median
from typing import Any

from pitchvalue.evaluation import ObservationKind, TemporalObservation, plan_walk_forward
from pitchvalue.evaluation.metrics import (
    ClassProbability,
    MetricConfig,
    MetricProvenance,
    MulticlassPrediction,
    evaluate_multiclass_probabilities,
)
from pitchvalue.markets.edge import (
    EDGE_ENGINE_VERSION,
    EdgeOddsBand,
    HistoricalMarketGroup,
    MarketEdgeResult,
    RawMLProbability,
    SelectionEdge,
    build_market_probability,
    calculate_market_edges,
)
from pitchvalue.markets.history.contracts import ObservationRole
from pitchvalue.markets.history.market import HistoricalMarketLoad
from pitchvalue.ml.config import MLTrainingConfig
from pitchvalue.ml.contracts import MLDataset
from pitchvalue.ml.evaluation import DEFAULT_ML_WALK_FORWARD, MetricSummary
from pitchvalue.ml.model import fit_multinomial_logistic, predict_multinomial_logistic
from pitchvalue.prediction.contracts import MarketFamily, Selection


@dataclass(frozen=True)
class RawMLOOSRow:
    fold_id: str
    competition_id: str
    season_id: str
    observed: Selection
    model: RawMLProbability


@dataclass(frozen=True)
class EdgeDistribution:
    count: int
    mean: Decimal | None
    median: Decimal | None
    minimum: Decimal | None
    maximum: Decimal | None
    positive_count: int
    exactly_0_04_count: int
    exactly_0_06_count: int


@dataclass(frozen=True)
class ThresholdCounts:
    below_0_04: int
    from_0_04_below_0_06: int
    exactly_0_06: int
    above_0_06: int


@dataclass(frozen=True)
class SelectionBreakdown:
    selection: Selection
    count: int
    mean_model_probability: Decimal
    mean_market_probability: Decimal
    mean_edge: Decimal
    positive_edge_share: Decimal
    exactly_0_06_share: Decimal
    outcome_rate: Decimal


@dataclass(frozen=True)
class SliceBreakdown:
    scope: str
    sample_count: int
    model_log_loss: Decimal | None
    market_log_loss: Decimal | None
    model_brier: Decimal | None
    market_brier: Decimal | None
    positive_edge_count: int
    exactly_0_06_count: int


@dataclass(frozen=True)
class OddsBandBreakdown:
    band: EdgeOddsBand
    count: int
    mean_edge: Decimal
    positive_edge_count: int


@dataclass(frozen=True)
class EdgeRealizationBreakdown:
    band: str
    count: int
    mean_model_probability: Decimal
    observed_hit_rate: Decimal


@dataclass(frozen=True)
class RoleMarketEvaluation:
    observation_role: ObservationRole
    reference_label: str
    ml_oos_rows: int
    matched_rows: int
    missing_market_rows: int
    model_metrics: MetricSummary
    market_metrics: MetricSummary
    model_minus_market_log_loss: Decimal | None
    model_minus_market_brier: Decimal | None
    edge_distribution: EdgeDistribution
    raw_price_ev_distribution: EdgeDistribution
    threshold_counts: ThresholdCounts
    selection_breakdown: tuple[SelectionBreakdown, ...]
    competition_breakdown: tuple[SliceBreakdown, ...]
    season_breakdown: tuple[SliceBreakdown, ...]
    odds_band_breakdown: tuple[OddsBandBreakdown, ...]
    realization_breakdown: tuple[EdgeRealizationBreakdown, ...]
    comparison_status_counts: tuple[tuple[str, int], ...]
    results: tuple[MarketEdgeResult, ...]


@dataclass(frozen=True)
class MarketValueEvaluationResult:
    edge_engine_version: str
    canonical_model_source: str
    ml_oos_rows: int
    market_raw_rows: int
    market_groups: int
    incomplete_groups: int
    invalid_groups: int
    quality_excluded_groups: int
    ambiguous_groups: int
    quality_counts: tuple[tuple[str, int], ...]
    source_prematch: RoleMarketEvaluation
    closing: RoleMarketEvaluation

    def to_dict(self, *, include_rows: bool = False) -> dict[str, Any]:
        value = _primitive(self)
        if not isinstance(value, dict):  # pragma: no cover
            raise TypeError("market evaluation must serialize to a mapping")
        if not include_rows:
            value["source_prematch"].pop("results", None)
            value["closing"].pop("results", None)
        return value


def generate_raw_ml_oos(
    dataset: MLDataset,
    training_config: MLTrainingConfig | None = None,
) -> tuple[RawMLOOSRow, ...]:
    """Recreate the accepted TASK 16 OOS path without changing its configuration."""
    config = training_config or MLTrainingConfig()
    usable = tuple(
        row for row in dataset.rows if any(item.value is not None for item in row.features)
    )
    by_id = {row.row_id: row for row in usable}
    observations = tuple(
        TemporalObservation(
            row.row_id,
            row.match_id,
            row.competition_id,
            row.season_id,
            row.prediction_as_of,
            row.prediction_as_of,
            ObservationKind.FEATURE,
        )
        for row in usable
    )
    output: list[RawMLOOSRow] = []
    for execution in plan_walk_forward(observations, DEFAULT_ML_WALK_FORWARD):
        if execution.fold.status.value != "READY":
            continue
        train = tuple(by_id[item.observation_id] for item in execution.training_observations)
        test = tuple(by_id[item.observation_id] for item in execution.test_observations)
        model = fit_multinomial_logistic(train, config)
        if model is None:
            continue
        predictions = predict_multinomial_logistic(model, test)
        for row, prediction in zip(test, predictions, strict=True):
            if not isinstance(row.target_value, Selection):
                continue
            output.append(
                RawMLOOSRow(
                    execution.fold.fold_id,
                    row.competition_id,
                    row.season_id,
                    row.target_value,
                    RawMLProbability(
                        row.row_id,
                        row.match_id,
                        prediction.model_version,
                        prediction.feature_profile,
                        prediction.prediction_as_of,
                        prediction.probabilities,
                    ),
                )
            )
    return tuple(output)


def evaluate_market_value(
    oos_rows: tuple[RawMLOOSRow, ...],
    market_load: HistoricalMarketLoad,
    *,
    competition_labels: tuple[tuple[str, str], ...] = (),
    season_labels: tuple[tuple[str, str], ...] = (),
) -> MarketValueEvaluationResult:
    by_role: dict[ObservationRole, dict[str, HistoricalMarketGroup]] = {
        ObservationRole.SOURCE_PREMATCH: {},
        ObservationRole.CLOSING: {},
    }
    for group in market_load.groups:
        role_groups = by_role[group.observation_role]
        if group.match_id in role_groups:
            raise ValueError("ambiguous duplicate market group")
        role_groups[group.match_id] = group
    prematch = _evaluate_role(
        oos_rows,
        by_role[ObservationRole.SOURCE_PREMATCH],
        ObservationRole.SOURCE_PREMATCH,
        "SOURCE_PREMATCH_ROLE_REFERENCE",
        dict(competition_labels),
        dict(season_labels),
    )
    closing = _evaluate_role(
        oos_rows,
        by_role[ObservationRole.CLOSING],
        ObservationRole.CLOSING,
        "CLOSING_REFERENCE_DIAGNOSTIC",
        dict(competition_labels),
        dict(season_labels),
    )
    return MarketValueEvaluationResult(
        EDGE_ENGINE_VERSION,
        "RAW TASK 16 ML",
        len(oos_rows),
        market_load.raw_rows,
        len(market_load.groups),
        market_load.incomplete_groups,
        market_load.invalid_groups,
        market_load.quality_excluded_groups,
        market_load.ambiguous_groups,
        market_load.quality_counts,
        prematch,
        closing,
    )


def _evaluate_role(
    oos_rows: tuple[RawMLOOSRow, ...],
    groups: dict[str, HistoricalMarketGroup],
    role: ObservationRole,
    label: str,
    competition_labels: dict[str, str],
    season_labels: dict[str, str],
) -> RoleMarketEvaluation:
    aligned: list[tuple[RawMLOOSRow, MarketEdgeResult]] = []
    missing = 0
    for row in oos_rows:
        group = groups.get(row.model.match_id)
        if group is None:
            missing += 1
            continue
        market = build_market_probability(group)
        aligned.append((row, calculate_market_edges(row.model, market)))
    values = tuple(aligned)
    model_metrics = _metrics(values, use_market=False, label=f"RAW_ML_{role.value}")
    market_metrics = _metrics(values, use_market=True, label=f"MARKET_{role.value}")
    edges = tuple(edge for _, result in values for edge in result.edges)
    statuses = Counter(result.comparison_status.value for _, result in values)
    return RoleMarketEvaluation(
        role,
        label,
        len(oos_rows),
        len(values),
        missing,
        model_metrics,
        market_metrics,
        _delta(model_metrics.log_loss, market_metrics.log_loss),
        _delta(model_metrics.brier, market_metrics.brier),
        _distribution(tuple(item.edge for item in edges)),
        _distribution(tuple(item.raw_price_ev for item in edges)),
        _thresholds(edges),
        _selection_breakdown(values),
        _slice_breakdown(values, "competition", competition_labels),
        _slice_breakdown(values, "season", season_labels),
        _odds_breakdown(edges),
        _realization(values),
        tuple(sorted(statuses.items())),
        tuple(result for _, result in values),
    )


def _metrics(
    rows: tuple[tuple[RawMLOOSRow, MarketEdgeResult], ...], *, use_market: bool, label: str
) -> MetricSummary:
    records = []
    for row, result in rows:
        probabilities = (
            tuple((edge.selection, edge.market_probability) for edge in result.edges)
            if use_market
            else tuple((item.selection, item.probability) for item in row.model.probabilities)
        )
        records.append(
            MulticlassPrediction(
                row.model.row_id,
                tuple(
                    ClassProbability(selection.value, probability)
                    for selection, probability in probabilities
                ),
                row.observed.value,
            )
        )
    suite = evaluate_multiclass_probabilities(
        tuple(records),
        MetricConfig(minimum_total_samples=1, minimum_bucket_samples=1),
        MetricProvenance(model_name=label, market=MarketFamily.MATCH_RESULT.value),
    )
    return MetricSummary(
        suite.log_loss.usable_count,
        suite.log_loss.value,
        suite.brier.value,
        suite.accuracy.value,
        suite.calibration.macro_ece,
        suite.log_loss.status.value,
    )


def _distribution(values: tuple[Decimal, ...]) -> EdgeDistribution:
    if not values:
        return EdgeDistribution(0, None, None, None, None, 0, 0, 0)
    return EdgeDistribution(
        len(values),
        sum(values, Decimal(0)) / Decimal(len(values)),
        Decimal(str(median(values))),
        min(values),
        max(values),
        sum(value > 0 for value in values),
        values.count(Decimal("0.04")),
        values.count(Decimal("0.06")),
    )


def _thresholds(edges: tuple[SelectionEdge, ...]) -> ThresholdCounts:
    return ThresholdCounts(
        sum(item.edge < Decimal("0.04") for item in edges),
        sum(Decimal("0.04") <= item.edge < Decimal("0.06") for item in edges),
        sum(item.edge == Decimal("0.06") for item in edges),
        sum(item.edge > Decimal("0.06") for item in edges),
    )


def _selection_breakdown(
    rows: tuple[tuple[RawMLOOSRow, MarketEdgeResult], ...],
) -> tuple[SelectionBreakdown, ...]:
    result = []
    for selection in (Selection.HOME, Selection.DRAW, Selection.AWAY):
        items = tuple(
            (row, next(edge for edge in edge_result.edges if edge.selection is selection))
            for row, edge_result in rows
        )
        count = Decimal(len(items))
        result.append(
            SelectionBreakdown(
                selection,
                len(items),
                sum((edge.model_probability for _, edge in items), Decimal(0)) / count,
                sum((edge.market_probability for _, edge in items), Decimal(0)) / count,
                sum((edge.edge for _, edge in items), Decimal(0)) / count,
                Decimal(sum(edge.edge > 0 for _, edge in items)) / count,
                Decimal(sum(edge.edge == Decimal("0.06") for _, edge in items)) / count,
                Decimal(sum(row.observed is selection for row, _ in items)) / count,
            )
        )
    return tuple(result)


def _slice_breakdown(
    rows: tuple[tuple[RawMLOOSRow, MarketEdgeResult], ...],
    dimension: str,
    labels: dict[str, str],
) -> tuple[SliceBreakdown, ...]:
    grouped: dict[str, list[tuple[RawMLOOSRow, MarketEdgeResult]]] = defaultdict(list)
    for item in rows:
        identity = item[0].competition_id if dimension == "competition" else item[0].season_id
        grouped[labels.get(identity, identity)].append(item)
    output = []
    for scope in sorted(grouped):
        values = tuple(grouped[scope])
        model = _metrics(values, use_market=False, label=f"ML_{scope}")
        market = _metrics(values, use_market=True, label=f"MARKET_{scope}")
        edges = tuple(edge for _, result in values for edge in result.edges)
        output.append(
            SliceBreakdown(
                scope,
                len(values),
                model.log_loss,
                market.log_loss,
                model.brier,
                market.brier,
                sum(item.edge > 0 for item in edges),
                sum(item.edge == Decimal("0.06") for item in edges),
            )
        )
    return tuple(output)


def _odds_breakdown(edges: tuple[SelectionEdge, ...]) -> tuple[OddsBandBreakdown, ...]:
    grouped: dict[EdgeOddsBand, list[SelectionEdge]] = defaultdict(list)
    for edge in edges:
        grouped[edge.odds_band].append(edge)
    return tuple(
        OddsBandBreakdown(
            band,
            len(grouped[band]),
            sum((item.edge for item in grouped[band]), Decimal(0)) / Decimal(len(grouped[band])),
            sum(item.edge > 0 for item in grouped[band]),
        )
        for band in EdgeOddsBand
        if grouped[band]
    )


def _realization(
    rows: tuple[tuple[RawMLOOSRow, MarketEdgeResult], ...],
) -> tuple[EdgeRealizationBreakdown, ...]:
    grouped: dict[str, list[tuple[bool, SelectionEdge]]] = defaultdict(list)
    for row, result in rows:
        for edge in result.edges:
            grouped[_edge_bin(edge.edge)].append((row.observed is edge.selection, edge))
    order = (
        "EDGE_NEGATIVE",
        "EDGE_0_TO_0_04",
        "EDGE_0_04_TO_0_06",
        "EDGE_0_06_TO_0_10",
        "EDGE_AT_LEAST_0_10",
    )
    return tuple(
        EdgeRealizationBreakdown(
            band,
            len(grouped[band]),
            sum((item.model_probability for _, item in grouped[band]), Decimal(0))
            / Decimal(len(grouped[band])),
            Decimal(sum(hit for hit, _ in grouped[band])) / Decimal(len(grouped[band])),
        )
        for band in order
        if grouped[band]
    )


def _edge_bin(edge: Decimal) -> str:
    if edge < 0:
        return "EDGE_NEGATIVE"
    if edge < Decimal("0.04"):
        return "EDGE_0_TO_0_04"
    if edge < Decimal("0.06"):
        return "EDGE_0_04_TO_0_06"
    if edge < Decimal("0.10"):
        return "EDGE_0_06_TO_0_10"
    return "EDGE_AT_LEAST_0_10"


def _delta(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    return None if left is None or right is None else left - right


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
