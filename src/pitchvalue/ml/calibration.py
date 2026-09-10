"""Deterministic temperature scaling for TASK 16 multinomial logits."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import exp, isfinite, log
from typing import Any

from pitchvalue.ml.config import MLDatasetValidationError
from pitchvalue.ml.model import ML_CLASS_ORDER, MLClassProbability, MLModelStatus, MLPrediction
from pitchvalue.prediction.contracts import Selection


class CalibrationStatus(StrEnum):
    READY = "READY"
    INSUFFICIENT_CALIBRATION_SUPPORT = "INSUFFICIENT_CALIBRATION_SUPPORT"
    INVALID_RAW_PROBABILITY = "INVALID_RAW_PROBABILITY"
    CALIBRATION_FIT_FAILED = "CALIBRATION_FIT_FAILED"
    NUMERICAL_ERROR = "NUMERICAL_ERROR"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class TemperatureScalingConfig:
    version: str = "temperature_scaling_v1"
    minimum_calibration_samples: int = 100
    minimum_class_samples: int = 10
    minimum_temperature: Decimal = Decimal("0.25")
    maximum_temperature: Decimal = Decimal("4")
    optimization_iterations: int = 80

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise MLDatasetValidationError("calibrator version is required")
        if self.minimum_calibration_samples < 1 or self.minimum_class_samples < 1:
            raise MLDatasetValidationError("calibration support minimums must be positive")
        if self.optimization_iterations < 1:
            raise MLDatasetValidationError("optimization_iterations must be positive")
        for value in (self.minimum_temperature, self.maximum_temperature):
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise MLDatasetValidationError(
                    "temperature bounds must be positive finite Decimals"
                )
        if self.minimum_temperature >= self.maximum_temperature:
            raise MLDatasetValidationError("minimum temperature must be below maximum temperature")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "minimum_calibration_samples": self.minimum_calibration_samples,
            "minimum_class_samples": self.minimum_class_samples,
            "minimum_temperature": str(self.minimum_temperature),
            "maximum_temperature": str(self.maximum_temperature),
            "optimization_iterations": self.optimization_iterations,
        }


@dataclass(frozen=True)
class CalibrationFitExample:
    prediction: MLPrediction
    observed: Selection

    def __post_init__(self) -> None:
        if self.observed not in ML_CLASS_ORDER:
            raise MLDatasetValidationError("calibration outcome must be HOME, DRAW, or AWAY")


@dataclass(frozen=True)
class FittedTemperatureCalibrator:
    family: str
    version: str
    base_model_version: str
    feature_profile: str
    class_order: tuple[Selection, ...]
    temperature: Decimal | None
    fit_support: int
    class_support: tuple[tuple[Selection, int], ...]
    trained_through: datetime | None
    status: CalibrationStatus
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "version": self.version,
            "base_model_version": self.base_model_version,
            "feature_profile": self.feature_profile,
            "class_order": [item.value for item in self.class_order],
            "temperature": None if self.temperature is None else str(self.temperature),
            "fit_support": self.fit_support,
            "class_support": {label.value: count for label, count in self.class_support},
            "trained_through": (
                None if self.trained_through is None else self.trained_through.isoformat()
            ),
            "status": self.status.value,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class CalibratedMLPrediction:
    row_id: str
    raw_prediction: MLPrediction
    calibrated_probabilities: tuple[MLClassProbability, ...]
    class_order: tuple[Selection, ...]
    base_model_version: str
    calibrator_version: str
    calibration_support: int
    calibrator_trained_through: datetime
    prediction_as_of: datetime
    status: CalibrationStatus
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status is CalibrationStatus.READY:
            if self.class_order != ML_CLASS_ORDER:
                raise MLDatasetValidationError("calibrated class order must be HOME, DRAW, AWAY")
            values = tuple(item.probability for item in self.calibrated_probabilities)
            if len(values) != 3 or any(value < 0 or value > 1 for value in values):
                raise MLDatasetValidationError("calibrated probabilities must be within [0,1]")
            if sum(values, Decimal(0)) != Decimal(1):
                raise MLDatasetValidationError("calibrated probabilities must sum to one")

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "raw_prediction": self.raw_prediction.to_dict(),
            "calibrated_probabilities": [item.to_dict() for item in self.calibrated_probabilities],
            "class_order": [item.value for item in self.class_order],
            "base_model_version": self.base_model_version,
            "calibrator_version": self.calibrator_version,
            "calibration_support": self.calibration_support,
            "calibrator_trained_through": self.calibrator_trained_through.isoformat(),
            "prediction_as_of": self.prediction_as_of.isoformat(),
            "probability_semantics": "CALIBRATED ML PROBABILITY",
            "status": self.status.value,
            "diagnostics": list(self.diagnostics),
        }


def fit_temperature_scaling(
    examples: tuple[CalibrationFitExample, ...],
    config: TemperatureScalingConfig | None = None,
) -> FittedTemperatureCalibrator:
    config = config or TemperatureScalingConfig()
    ordered = tuple(sorted(examples, key=lambda item: item.prediction.row_id))
    template = ordered[0].prediction if ordered else None
    counts = Counter(item.observed for item in ordered)
    support = tuple((label, counts[label]) for label in ML_CLASS_ORDER)
    base_version = template.model_version if template is not None else "multinomial_logistic_v1"
    profile = template.feature_profile if template is not None else "FOOTBALL_PERFORMANCE_ONLY"
    trained_through = max(item.prediction.prediction_as_of for item in ordered) if ordered else None

    def result(
        temperature: Decimal | None,
        status: CalibrationStatus,
        diagnostics: tuple[str, ...],
    ) -> FittedTemperatureCalibrator:
        return FittedTemperatureCalibrator(
            "TEMPERATURE_SCALING",
            config.version,
            base_version,
            profile,
            ML_CLASS_ORDER,
            temperature,
            len(ordered),
            support,
            trained_through,
            status,
            diagnostics,
        )

    if len(ordered) < config.minimum_calibration_samples or any(
        counts[label] < config.minimum_class_samples for label in ML_CLASS_ORDER
    ):
        return result(
            None,
            CalibrationStatus.INSUFFICIENT_CALIBRATION_SUPPORT,
            ("minimum total or class calibration support unavailable",),
        )
    if template is not None and any(
        item.prediction.model_version != template.model_version
        or item.prediction.feature_profile != template.feature_profile
        or item.prediction.class_order != template.class_order
        for item in ordered
    ):
        return result(
            None,
            CalibrationStatus.UNSUPPORTED,
            ("calibration examples mix model, profile, or class-order semantics",),
        )
    if any(not _valid_prediction(item.prediction) for item in ordered):
        return result(
            None,
            CalibrationStatus.INVALID_RAW_PROBABILITY,
            ("calibration examples contain invalid raw logits or probabilities",),
        )
    lower = log(float(config.minimum_temperature))
    upper = log(float(config.maximum_temperature))
    ratio = (5**0.5 - 1) / 2
    left = upper - ratio * (upper - lower)
    right = lower + ratio * (upper - lower)
    left_loss = _loss(ordered, exp(left))
    right_loss = _loss(ordered, exp(right))
    for _ in range(config.optimization_iterations):
        if left_loss <= right_loss:
            upper, right, right_loss = right, left, left_loss
            left = upper - ratio * (upper - lower)
            left_loss = _loss(ordered, exp(left))
        else:
            lower, left, left_loss = left, right, right_loss
            right = lower + ratio * (upper - lower)
            right_loss = _loss(ordered, exp(right))
    candidates = (
        float(config.minimum_temperature),
        exp((lower + upper) / 2),
        1.0,
        float(config.maximum_temperature),
    )
    temperature = min(candidates, key=lambda value: (_loss(ordered, value), value))
    if not isfinite(temperature) or temperature <= 0:
        return result(
            None,
            CalibrationStatus.NUMERICAL_ERROR,
            ("temperature optimization produced an invalid value",),
        )
    return result(
        Decimal(f"{temperature:.15f}"),
        CalibrationStatus.READY,
        (),
    )


def apply_temperature_scaling(
    calibrator: FittedTemperatureCalibrator,
    predictions: tuple[MLPrediction, ...],
) -> tuple[CalibratedMLPrediction, ...]:
    if calibrator.status is not CalibrationStatus.READY or calibrator.temperature is None:
        raise MLDatasetValidationError("temperature calibrator is not ready")
    if calibrator.trained_through is None:
        raise MLDatasetValidationError("ready calibrator requires trained_through")
    temperature = float(calibrator.temperature)
    results: list[CalibratedMLPrediction] = []
    for prediction in predictions:
        if not _valid_prediction(prediction):
            raise MLDatasetValidationError("invalid raw prediction cannot be calibrated")
        if (
            prediction.model_version != calibrator.base_model_version
            or prediction.feature_profile != calibrator.feature_profile
            or prediction.class_order != calibrator.class_order
        ):
            raise MLDatasetValidationError("raw prediction is incompatible with calibrator")
        if calibrator.trained_through >= prediction.prediction_as_of:
            raise MLDatasetValidationError(
                "calibrator must be trained strictly before prediction_as_of"
            )
        probabilities = _decimal_probabilities(_temperature_softmax(prediction.logits, temperature))
        results.append(
            CalibratedMLPrediction(
                prediction.row_id,
                prediction,
                tuple(
                    MLClassProbability(label, probability)
                    for label, probability in zip(ML_CLASS_ORDER, probabilities, strict=True)
                ),
                prediction.class_order,
                prediction.model_version,
                calibrator.version,
                calibrator.fit_support,
                calibrator.trained_through,
                prediction.prediction_as_of,
                CalibrationStatus.READY,
                (),
            )
        )
    return tuple(results)


def _valid_prediction(prediction: MLPrediction) -> bool:
    probabilities = tuple(item.probability for item in prediction.probabilities)
    return (
        prediction.status is MLModelStatus.READY
        and prediction.class_order == ML_CLASS_ORDER
        and len(prediction.logits) == 3
        and all(isfinite(value) for value in prediction.logits)
        and len(probabilities) == 3
        and all(value.is_finite() and 0 <= value <= 1 for value in probabilities)
        and sum(probabilities, Decimal(0)) == Decimal(1)
    )


def _loss(examples: tuple[CalibrationFitExample, ...], temperature: float) -> float:
    total = 0.0
    for item in examples:
        probabilities = _temperature_softmax(item.prediction.logits, temperature)
        probability = max(probabilities[ML_CLASS_ORDER.index(item.observed)], 1e-15)
        total -= log(probability)
    return total / len(examples)


def _temperature_softmax(logits: tuple[float, ...], temperature: float) -> tuple[float, ...]:
    if not isfinite(temperature) or temperature <= 0:
        raise MLDatasetValidationError("temperature must be positive and finite")
    if len(logits) != 3 or any(not isfinite(value) for value in logits):
        raise MLDatasetValidationError("temperature scaling requires three finite logits")
    scaled = tuple(value / temperature for value in logits)
    maximum = max(scaled)
    exponentials = tuple(exp(value - maximum) for value in scaled)
    total = sum(exponentials)
    return tuple(value / total for value in exponentials)


def _decimal_probabilities(values: tuple[float, ...]) -> tuple[Decimal, Decimal, Decimal]:
    home = Decimal(f"{values[0]:.15f}")
    draw = Decimal(f"{values[1]:.15f}")
    away = Decimal(1) - home - draw
    return home, draw, away
