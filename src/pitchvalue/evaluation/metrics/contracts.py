"""Immutable probability, metric, calibration, and provenance contracts."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pitchvalue.evaluation.metrics.config import MetricValidationError


class ProbabilitySemantics(StrEnum):
    MODEL_PROBABILITY = "MODEL_PROBABILITY"
    CALIBRATED_PROBABILITY = "CALIBRATED_PROBABILITY"


class PredictionRecordStatus(StrEnum):
    READY = "READY"
    MISSING_PREDICTION = "MISSING_PREDICTION"
    MISSING_OUTCOME = "MISSING_OUTCOME"
    ANALYSIS_UNAVAILABLE = "ANALYSIS_UNAVAILABLE"


class MetricStatus(StrEnum):
    READY = "READY"
    EMPTY_INPUT = "EMPTY_INPUT"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    INVALID_PROBABILITY = "INVALID_PROBABILITY"
    INVALID_OUTCOME = "INVALID_OUTCOME"


class BucketStatus(StrEnum):
    READY = "READY"
    EMPTY = "EMPTY"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


class MetricName(StrEnum):
    BRIER_BINARY = "BRIER_BINARY"
    BRIER_MULTICLASS = "BRIER_MULTICLASS"
    LOG_LOSS_BINARY = "LOG_LOSS_BINARY"
    LOG_LOSS_MULTICLASS = "LOG_LOSS_MULTICLASS"
    ACCURACY_BINARY = "ACCURACY_BINARY"
    ACCURACY_MULTICLASS = "ACCURACY_MULTICLASS"
    CALIBRATION_ECE = "CALIBRATION_ECE"


class MetricDiagnosticCode(StrEnum):
    MISSING_PREDICTION = "MISSING_PREDICTION"
    MISSING_OUTCOME = "MISSING_OUTCOME"
    ANALYSIS_UNAVAILABLE = "ANALYSIS_UNAVAILABLE"
    INSUFFICIENT_TOTAL_SAMPLE = "INSUFFICIENT_TOTAL_SAMPLE"
    INSUFFICIENT_BUCKET_SAMPLE = "INSUFFICIENT_BUCKET_SAMPLE"
    INVALID_PROBABILITY_SUM = "INVALID_PROBABILITY_SUM"
    CLASS_DOMAIN_MISMATCH = "CLASS_DOMAIN_MISMATCH"
    AMBIGUOUS_TOP_CLASS = "AMBIGUOUS_TOP_CLASS"


CANONICAL_CLASS_ORDER = ("HOME", "DRAW", "AWAY")


def canonical_class_key(label: str) -> tuple[int, str]:
    try:
        return (CANONICAL_CLASS_ORDER.index(label), label)
    except ValueError:
        return (len(CANONICAL_CLASS_ORDER), label)


def _require_identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise MetricValidationError(f"{name} is required")


def _probability(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise MetricValidationError(f"{name} must be a finite Decimal probability")
    if value < Decimal(0) or value > Decimal(1):
        raise MetricValidationError(f"{name} must be between 0 and 1")
    return value


class SerializableMetricContract:
    def to_dict(self) -> dict[str, Any]:
        value = _primitive(self)
        if not isinstance(value, dict):  # pragma: no cover
            raise TypeError("metric contract must serialize to a mapping")
        return value


@dataclass(frozen=True)
class MetricProvenance(SerializableMetricContract):
    fold_id: str | None = None
    model_name: str | None = None
    model_version: str | None = None
    competition_id: str | None = None
    season_id: str | None = None
    market: str | None = None
    class_scope: str | None = None
    line: Decimal | None = None

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name == "line":
                if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
                    raise MetricValidationError("line must be a finite Decimal")
            elif value is not None:
                _require_identifier(value, field.name)


@dataclass(frozen=True)
class BinaryPrediction(SerializableMetricContract):
    prediction_id: str
    probability: Decimal | None
    observed: int | None
    status: PredictionRecordStatus = PredictionRecordStatus.READY
    semantics: ProbabilitySemantics | None = ProbabilitySemantics.MODEL_PROBABILITY

    def __post_init__(self) -> None:
        _require_identifier(self.prediction_id, "prediction_id")
        if not isinstance(self.status, PredictionRecordStatus):
            raise MetricValidationError("status must use PredictionRecordStatus")
        if self.status is PredictionRecordStatus.READY:
            _probability(self.probability, "probability")
            if self.observed not in (0, 1) or isinstance(self.observed, bool):
                raise MetricValidationError("observed must be integer 0 or 1")
            if not isinstance(self.semantics, ProbabilitySemantics):
                raise MetricValidationError("READY records require declared probability semantics")
        elif self.status is PredictionRecordStatus.MISSING_PREDICTION:
            if self.probability is not None:
                raise MetricValidationError("missing prediction must not contain probability")
        elif self.status is PredictionRecordStatus.MISSING_OUTCOME:
            if self.observed is not None:
                raise MetricValidationError("missing outcome must not contain observed outcome")
            if self.probability is not None:
                _probability(self.probability, "probability")
        elif self.probability is not None:
            raise MetricValidationError("unavailable record must not contain probability")


@dataclass(frozen=True)
class ClassProbability(SerializableMetricContract):
    label: str
    probability: Decimal

    def __post_init__(self) -> None:
        _require_identifier(self.label, "label")
        _probability(self.probability, "probability")


@dataclass(frozen=True)
class MulticlassPrediction(SerializableMetricContract):
    prediction_id: str
    probabilities: tuple[ClassProbability, ...]
    observed_class: str | None
    status: PredictionRecordStatus = PredictionRecordStatus.READY
    semantics: ProbabilitySemantics | None = ProbabilitySemantics.MODEL_PROBABILITY

    def __post_init__(self) -> None:
        _require_identifier(self.prediction_id, "prediction_id")
        if not isinstance(self.status, PredictionRecordStatus):
            raise MetricValidationError("status must use PredictionRecordStatus")
        labels = [item.label for item in self.probabilities]
        if len(labels) != len(set(labels)):
            raise MetricValidationError("duplicate class labels are not allowed")
        ordered = tuple(
            sorted(self.probabilities, key=lambda item: canonical_class_key(item.label))
        )
        object.__setattr__(self, "probabilities", ordered)
        if self.status is PredictionRecordStatus.READY:
            if len(ordered) < 2:
                raise MetricValidationError("multiclass prediction requires at least two classes")
            if not isinstance(self.semantics, ProbabilitySemantics):
                raise MetricValidationError("READY records require declared probability semantics")
            if self.observed_class is None or self.observed_class not in labels:
                raise MetricValidationError("observed class must belong to predicted class domain")
        elif self.status is PredictionRecordStatus.MISSING_PREDICTION:
            if ordered:
                raise MetricValidationError("missing prediction must not contain probabilities")
        elif self.status is PredictionRecordStatus.MISSING_OUTCOME:
            if self.observed_class is not None:
                raise MetricValidationError("missing outcome must not contain observed class")
        elif ordered:
            raise MetricValidationError("unavailable record must not contain probabilities")

    def probability_for(self, label: str) -> Decimal:
        for item in self.probabilities:
            if item.label == label:
                return item.probability
        raise MetricValidationError(f"unknown class: {label}")


@dataclass(frozen=True)
class MetricDiagnostic(SerializableMetricContract):
    code: MetricDiagnosticCode
    prediction_id: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class MetricResult(SerializableMetricContract):
    metric: MetricName
    value: Decimal | None
    input_count: int
    usable_count: int
    excluded_count: int
    status: MetricStatus
    diagnostics: tuple[MetricDiagnostic, ...] = ()
    provenance: MetricProvenance | None = None


@dataclass(frozen=True)
class CalibrationBucket(SerializableMetricContract):
    lower_bound: Decimal
    upper_bound: Decimal
    upper_inclusive: bool
    sample_count: int
    mean_predicted_probability: Decimal | None
    observed_frequency: Decimal | None
    signed_calibration_gap: Decimal | None
    absolute_calibration_gap: Decimal | None
    status: BucketStatus


@dataclass(frozen=True)
class BinaryCalibrationResult(SerializableMetricContract):
    status: MetricStatus
    input_count: int
    usable_count: int
    excluded_count: int
    bucket_edges: tuple[Decimal, ...]
    buckets: tuple[CalibrationBucket, ...]
    ece: Decimal | None
    diagnostics: tuple[MetricDiagnostic, ...] = ()
    provenance: MetricProvenance | None = None


@dataclass(frozen=True)
class ClassCalibration(SerializableMetricContract):
    class_label: str
    calibration: BinaryCalibrationResult


@dataclass(frozen=True)
class MulticlassCalibrationResult(SerializableMetricContract):
    status: MetricStatus
    input_count: int
    usable_count: int
    excluded_count: int
    classes: tuple[ClassCalibration, ...]
    macro_ece: Decimal | None
    diagnostics: tuple[MetricDiagnostic, ...] = ()
    provenance: MetricProvenance | None = None


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
