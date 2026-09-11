"""Immutable probability-blend contracts and temporal weight selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite, log
from statistics import median
from typing import Any

from pitchvalue.ml.config import MLDatasetValidationError
from pitchvalue.ml.model import ML_CLASS_ORDER, MLClassProbability
from pitchvalue.prediction.contracts import MarketFamily, Selection


class EnsembleStatus(StrEnum):
    READY = "READY"
    INSUFFICIENT_ENSEMBLE_SUPPORT = "INSUFFICIENT_ENSEMBLE_SUPPORT"
    MISSING_MODEL_INPUT = "MISSING_MODEL_INPUT"
    INVALID_PROBABILITY = "INVALID_PROBABILITY"
    WEIGHT_SELECTION_FAILED = "WEIGHT_SELECTION_FAILED"
    UNSUPPORTED = "UNSUPPORTED"


class EnsembleCandidateDecision(StrEnum):
    ACCEPT = "ENSEMBLE_CANDIDATE_ACCEPT"
    REJECT = "ENSEMBLE_CANDIDATE_REJECT"
    INCONCLUSIVE = "ENSEMBLE_CANDIDATE_INCONCLUSIVE"


@dataclass(frozen=True)
class EnsembleConfig:
    version: str = "ml_poisson_linear_blend_v1"
    weight_grid: tuple[Decimal, ...] = tuple(Decimal(index) / Decimal(10) for index in range(11))
    minimum_weight_evidence: int = 200
    probability_sum_tolerance: Decimal = Decimal("0.001")

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise MLDatasetValidationError("ensemble version is required")
        if self.minimum_weight_evidence < 1:
            raise MLDatasetValidationError("minimum_weight_evidence must be positive")
        if (
            not isinstance(self.probability_sum_tolerance, Decimal)
            or not self.probability_sum_tolerance.is_finite()
            or self.probability_sum_tolerance <= 0
        ):
            raise MLDatasetValidationError("probability_sum_tolerance must be positive")
        if len(self.weight_grid) < 2:
            raise MLDatasetValidationError("weight_grid requires at least two values")
        if any(
            not isinstance(weight, Decimal) or not weight.is_finite() or weight < 0 or weight > 1
            for weight in self.weight_grid
        ):
            raise MLDatasetValidationError("ensemble weights must be finite Decimals in [0,1]")
        if tuple(sorted(set(self.weight_grid))) != self.weight_grid:
            raise MLDatasetValidationError("weight_grid must be unique and sorted")
        if self.weight_grid[0] != 0 or self.weight_grid[-1] != 1:
            raise MLDatasetValidationError("weight_grid must include zero and one")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "weight_grid": [str(weight) for weight in self.weight_grid],
            "minimum_weight_evidence": self.minimum_weight_evidence,
            "probability_sum_tolerance": str(self.probability_sum_tolerance),
        }


@dataclass(frozen=True)
class ProbabilityModelPrediction:
    row_id: str
    match_id: str
    prediction_as_of: datetime
    model_family: str
    model_version: str
    class_order: tuple[Selection, ...]
    probabilities: tuple[MLClassProbability, ...]
    unallocated_probability_mass: Decimal = Decimal(0)
    target_market: MarketFamily = MarketFamily.MATCH_RESULT

    def validate(self, tolerance: Decimal) -> None:
        if not self.row_id.strip() or not self.match_id.strip():
            raise MLDatasetValidationError("prediction row and match identities are required")
        if self.prediction_as_of.tzinfo is None or self.prediction_as_of.utcoffset() is None:
            raise MLDatasetValidationError("prediction_as_of must be timezone-aware")
        if self.class_order != ML_CLASS_ORDER:
            raise MLDatasetValidationError("probability class order must be HOME, DRAW, AWAY")
        if self.target_market is not MarketFamily.MATCH_RESULT:
            raise MLDatasetValidationError("TASK 18 supports MATCH_RESULT probability rows only")
        if tuple(item.selection for item in self.probabilities) != self.class_order:
            raise MLDatasetValidationError("probability values must follow class order")
        values = tuple(item.probability for item in self.probabilities)
        if len(values) != 3 or any(
            not value.is_finite() or value < 0 or value > 1 for value in values
        ):
            raise MLDatasetValidationError("probabilities must be finite and within [0,1]")
        if (
            not isinstance(self.unallocated_probability_mass, Decimal)
            or not self.unallocated_probability_mass.is_finite()
            or self.unallocated_probability_mass < 0
        ):
            raise MLDatasetValidationError("unallocated probability mass must be non-negative")
        represented = sum(values, Decimal(0))
        if abs(Decimal(1) - represented) > tolerance:
            raise MLDatasetValidationError("probability sum is outside configured tolerance")
        if abs(Decimal(1) - represented - self.unallocated_probability_mass) > tolerance:
            raise MLDatasetValidationError("unallocated probability mass is inconsistent")


@dataclass(frozen=True)
class EnsemblePrediction:
    row_id: str
    match_id: str
    ensemble_family: str
    ensemble_version: str
    contributing_models: tuple[tuple[str, str, Decimal], ...]
    class_order: tuple[Selection, ...]
    prediction_as_of: datetime
    probabilities: tuple[MLClassProbability, ...]
    unallocated_probability_mass: Decimal
    weight_evidence_support: int
    weight_trained_through: datetime
    status: EnsembleStatus
    diagnostics: tuple[str, ...]
    target_market: MarketFamily = MarketFamily.MATCH_RESULT

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "match_id": self.match_id,
            "target_market": self.target_market.value,
            "ensemble_family": self.ensemble_family,
            "ensemble_version": self.ensemble_version,
            "contributing_models": [
                {"family": family, "version": version, "weight": str(weight)}
                for family, version, weight in self.contributing_models
            ],
            "class_order": [item.value for item in self.class_order],
            "prediction_as_of": self.prediction_as_of.isoformat(),
            "probabilities": [item.to_dict() for item in self.probabilities],
            "unallocated_probability_mass": str(self.unallocated_probability_mass),
            "weight_evidence_support": self.weight_evidence_support,
            "weight_trained_through": self.weight_trained_through.isoformat(),
            "probability_semantics": "UNCALIBRATED LINEAR ENSEMBLE PROBABILITY",
            "status": self.status.value,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class WeightEvidence:
    prediction_as_of: datetime
    observed: Selection
    ml: ProbabilityModelPrediction
    poisson: ProbabilityModelPrediction


@dataclass(frozen=True)
class WeightSelection:
    ml_weight: Decimal | None
    poisson_weight: Decimal | None
    evidence_support: int
    evidence_through: datetime | None
    status: EnsembleStatus
    diagnostics: tuple[str, ...]


def blend_probabilities(
    ml: ProbabilityModelPrediction,
    poisson: ProbabilityModelPrediction,
    ml_weight: Decimal,
    *,
    config: EnsembleConfig | None = None,
    evidence_support: int,
    evidence_through: datetime,
) -> EnsemblePrediction:
    config = config or EnsembleConfig()
    if not isinstance(ml_weight, Decimal) or not ml_weight.is_finite() or not 0 <= ml_weight <= 1:
        raise MLDatasetValidationError("ML weight must be a finite Decimal in [0,1]")
    ml.validate(config.probability_sum_tolerance)
    poisson.validate(config.probability_sum_tolerance)
    if (
        ml.row_id != poisson.row_id
        or ml.match_id != poisson.match_id
        or ml.prediction_as_of != poisson.prediction_as_of
        or ml.class_order != poisson.class_order
        or ml.target_market is not poisson.target_market
    ):
        raise MLDatasetValidationError("model predictions are not aligned")
    if evidence_through >= ml.prediction_as_of:
        raise MLDatasetValidationError("weight evidence must strictly precede prediction_as_of")
    poisson_weight = Decimal(1) - ml_weight
    values = tuple(
        ml_value.probability * ml_weight + poisson_value.probability * poisson_weight
        for ml_value, poisson_value in zip(ml.probabilities, poisson.probabilities, strict=True)
    )
    residual = (
        ml.unallocated_probability_mass * ml_weight
        + poisson.unallocated_probability_mass * poisson_weight
    )
    result = EnsemblePrediction(
        ml.row_id,
        ml.match_id,
        "ML_POISSON_LINEAR_BLEND",
        config.version,
        (
            ("ML", ml.model_version, ml_weight),
            ("POISSON", poisson.model_version, poisson_weight),
        ),
        ML_CLASS_ORDER,
        ml.prediction_as_of,
        tuple(
            MLClassProbability(selection, value)
            for selection, value in zip(ML_CLASS_ORDER, values, strict=True)
        ),
        residual,
        evidence_support,
        evidence_through,
        EnsembleStatus.READY,
        ("poisson residual mass preserved; no hidden renormalization",),
        ml.target_market,
    )
    _validate_ensemble(result, config.probability_sum_tolerance)
    return result


def select_temporal_weight(
    evidence: tuple[WeightEvidence, ...],
    test_start: datetime,
    config: EnsembleConfig | None = None,
) -> WeightSelection:
    config = config or EnsembleConfig()
    if test_start.tzinfo is None or test_start.utcoffset() is None:
        raise MLDatasetValidationError("test_start must be timezone-aware")
    ordered = tuple(sorted(evidence, key=lambda item: (item.prediction_as_of, item.ml.row_id)))
    if any(item.prediction_as_of >= test_start for item in ordered):
        return WeightSelection(
            None,
            None,
            len(ordered),
            None,
            EnsembleStatus.WEIGHT_SELECTION_FAILED,
            ("weight evidence must strictly precede the future test period",),
        )
    if len(ordered) < config.minimum_weight_evidence:
        return WeightSelection(
            None,
            None,
            len(ordered),
            max((item.prediction_as_of for item in ordered), default=None),
            EnsembleStatus.INSUFFICIENT_ENSEMBLE_SUPPORT,
            ("minimum prior OOS weight evidence unavailable",),
        )
    scored = tuple(
        (_log_loss(ordered, weight, config), _brier(ordered, weight, config), weight)
        for weight in config.weight_grid
    )
    if any(not isfinite(float(loss)) for loss, _, _ in scored):
        return WeightSelection(
            None,
            None,
            len(ordered),
            None,
            EnsembleStatus.WEIGHT_SELECTION_FAILED,
            ("weight grid produced a non-finite objective",),
        )
    selected = min(scored, key=lambda item: (item[0], item[1], item[2]))[2]
    return WeightSelection(
        selected,
        Decimal(1) - selected,
        len(ordered),
        max(item.prediction_as_of for item in ordered),
        EnsembleStatus.READY,
        (),
    )


def decide_ensemble_candidate(
    *,
    ensemble_log_loss: Decimal | None,
    ensemble_brier: Decimal | None,
    strongest_log_loss: Decimal | None,
    strongest_brier: Decimal | None,
    improved_folds: int,
    evaluated_folds: int,
    weights: tuple[Decimal, ...],
) -> EnsembleCandidateDecision:
    if (
        ensemble_log_loss is None
        or ensemble_brier is None
        or strongest_log_loss is None
        or strongest_brier is None
        or evaluated_folds == 0
        or not weights
    ):
        return EnsembleCandidateDecision.INCONCLUSIVE
    if (
        ensemble_log_loss < strongest_log_loss
        and ensemble_brier <= strongest_brier
        and improved_folds > evaluated_folds / 2
    ):
        return EnsembleCandidateDecision.ACCEPT
    if ensemble_log_loss >= strongest_log_loss and ensemble_brier >= strongest_brier:
        return EnsembleCandidateDecision.REJECT
    return EnsembleCandidateDecision.INCONCLUSIVE


def weight_distribution(weights: tuple[Decimal, ...]) -> tuple[Decimal, Decimal, Decimal, int]:
    if not weights:
        raise MLDatasetValidationError("weight distribution requires observations")
    return (
        min(weights),
        Decimal(str(median(weights))),
        max(weights),
        sum(weight in (Decimal(0), Decimal(1)) for weight in weights),
    )


def _log_loss(
    evidence: tuple[WeightEvidence, ...], weight: Decimal, config: EnsembleConfig
) -> Decimal:
    total = 0.0
    for item in evidence:
        probabilities = _blend_values(item, weight, config)
        probability = max(float(probabilities[ML_CLASS_ORDER.index(item.observed)]), 1e-15)
        total -= log(probability)
    return Decimal(str(total / len(evidence)))


def _brier(
    evidence: tuple[WeightEvidence, ...], weight: Decimal, config: EnsembleConfig
) -> Decimal:
    total = Decimal(0)
    for item in evidence:
        probabilities = _blend_values(item, weight, config)
        total += sum(
            (probability - Decimal(selection is item.observed)) ** 2
            for selection, probability in zip(ML_CLASS_ORDER, probabilities, strict=True)
        )
    return total / Decimal(len(evidence))


def _blend_values(
    item: WeightEvidence, weight: Decimal, config: EnsembleConfig
) -> tuple[Decimal, ...]:
    item.ml.validate(config.probability_sum_tolerance)
    item.poisson.validate(config.probability_sum_tolerance)
    if (
        item.ml.row_id != item.poisson.row_id
        or item.ml.match_id != item.poisson.match_id
        or item.ml.prediction_as_of != item.poisson.prediction_as_of
        or item.ml.target_market is not item.poisson.target_market
    ):
        raise MLDatasetValidationError("weight evidence contains misaligned rows")
    poisson_weight = Decimal(1) - weight
    return tuple(
        ml.probability * weight + poisson.probability * poisson_weight
        for ml, poisson in zip(item.ml.probabilities, item.poisson.probabilities, strict=True)
    )


def _validate_ensemble(prediction: EnsemblePrediction, tolerance: Decimal) -> None:
    values = tuple(item.probability for item in prediction.probabilities)
    if (
        prediction.class_order != ML_CLASS_ORDER
        or tuple(item.selection for item in prediction.probabilities) != ML_CLASS_ORDER
    ):
        raise MLDatasetValidationError("ensemble class order must be HOME, DRAW, AWAY")
    if any(not value.is_finite() or value < 0 or value > 1 for value in values):
        raise MLDatasetValidationError("ensemble probabilities are invalid")
    if abs(Decimal(1) - sum(values, Decimal(0))) > tolerance:
        raise MLDatasetValidationError("ensemble probability sum is outside tolerance")
