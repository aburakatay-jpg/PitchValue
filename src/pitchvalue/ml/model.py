"""Deterministic standard-library multinomial logistic regression baseline."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import exp, isfinite
from typing import Any

from pitchvalue.ml.config import MLDatasetValidationError, MLTrainingConfig
from pitchvalue.ml.contracts import TrainingRow
from pitchvalue.ml.preprocessing import FittedPreprocessor, fit_preprocessor, transform_rows
from pitchvalue.prediction.contracts import Selection

ML_CLASS_ORDER = (Selection.HOME, Selection.DRAW, Selection.AWAY)


class MLModelStatus(StrEnum):
    READY = "READY"
    INSUFFICIENT_TRAINING_SAMPLE = "INSUFFICIENT_TRAINING_SAMPLE"
    INVALID_FEATURES = "INVALID_FEATURES"


@dataclass(frozen=True)
class MLClassProbability:
    selection: Selection
    probability: Decimal

    def to_dict(self) -> dict[str, str]:
        return {"selection": self.selection.value, "probability": str(self.probability)}


@dataclass(frozen=True)
class MLPrediction:
    row_id: str
    model_family: str
    model_version: str
    feature_profile: str
    trained_through: datetime
    prediction_as_of: datetime
    class_order: tuple[Selection, ...]
    probabilities: tuple[MLClassProbability, ...]
    status: MLModelStatus
    diagnostics: tuple[str, ...]
    feature_schema_version: str
    training_support: int

    def __post_init__(self) -> None:
        if self.status is MLModelStatus.READY:
            if self.class_order != ML_CLASS_ORDER:
                raise MLDatasetValidationError("ML class order must be HOME, DRAW, AWAY")
            values = [item.probability for item in self.probabilities]
            if len(values) != 3 or any(value < 0 or value > 1 for value in values):
                raise MLDatasetValidationError("ML probabilities must be within [0,1]")
            if sum(values, Decimal(0)) != Decimal(1):
                raise MLDatasetValidationError("ML probabilities must sum to one")

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "model_family": self.model_family,
            "model_version": self.model_version,
            "feature_profile": self.feature_profile,
            "trained_through": self.trained_through.isoformat(),
            "prediction_as_of": self.prediction_as_of.isoformat(),
            "class_order": [item.value for item in self.class_order],
            "probabilities": [item.to_dict() for item in self.probabilities],
            "probability_semantics": "UNCALIBRATED ML PROBABILITY",
            "status": self.status.value,
            "diagnostics": list(self.diagnostics),
            "feature_schema_version": self.feature_schema_version,
            "training_support": self.training_support,
        }


@dataclass(frozen=True)
class FittedMultinomialLogistic:
    config: MLTrainingConfig
    preprocessor: FittedPreprocessor
    weights: tuple[tuple[float, ...], ...]
    trained_through: datetime
    training_support: int
    class_counts: tuple[int, int, int]
    status: MLModelStatus = MLModelStatus.READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "preprocessor": self.preprocessor.to_dict(),
            "weights": [list(row) for row in self.weights],
            "trained_through": self.trained_through.isoformat(),
            "training_support": self.training_support,
            "class_order": [item.value for item in ML_CLASS_ORDER],
            "class_counts": list(self.class_counts),
            "status": self.status.value,
        }


def fit_multinomial_logistic(
    rows: tuple[TrainingRow, ...], config: MLTrainingConfig | None = None
) -> FittedMultinomialLogistic | None:
    config = config or MLTrainingConfig()
    ordered = tuple(sorted(rows, key=lambda row: (row.prediction_as_of, row.row_id)))
    if len(ordered) < config.minimum_training_samples:
        return None
    counts = Counter(row.target_value for row in ordered)
    if any(counts[item] < config.minimum_class_samples for item in ML_CLASS_ORDER):
        return None
    preprocessor = fit_preprocessor(ordered)
    matrix = transform_rows(preprocessor, ordered)
    labels = tuple(ML_CLASS_ORDER.index(row.target_value) for row in ordered)
    width = len(matrix[0]) + 1
    weights = [[0.0 for _ in range(width)] for _ in ML_CLASS_ORDER]
    rate = float(config.learning_rate)
    regularization = float(config.l2_strength)
    sample_count = len(matrix)
    for _ in range(config.epochs):
        gradient = [[0.0 for _ in range(width)] for _ in ML_CLASS_ORDER]
        for values, observed in zip(matrix, labels, strict=True):
            augmented = (1.0,) + values
            probabilities = _softmax(
                [
                    sum(weight * value for weight, value in zip(row, augmented, strict=True))
                    for row in weights
                ]
            )
            for class_index in range(len(ML_CLASS_ORDER)):
                error = probabilities[class_index] - float(class_index == observed)
                for column, value in enumerate(augmented):
                    gradient[class_index][column] += error * value
        for class_index in range(len(ML_CLASS_ORDER)):
            for column in range(width):
                penalty = 0.0 if column == 0 else regularization * weights[class_index][column]
                weights[class_index][column] -= rate * (
                    gradient[class_index][column] / sample_count + penalty
                )
    if any(not isfinite(value) for row in weights for value in row):
        raise MLDatasetValidationError("training produced non-finite weights")
    return FittedMultinomialLogistic(
        config,
        preprocessor,
        tuple(tuple(value for value in row) for row in weights),
        max(row.prediction_as_of for row in ordered),
        len(ordered),
        tuple(counts[item] for item in ML_CLASS_ORDER),  # type: ignore[arg-type]
    )


def predict_multinomial_logistic(
    model: FittedMultinomialLogistic, rows: tuple[TrainingRow, ...]
) -> tuple[MLPrediction, ...]:
    matrix = transform_rows(model.preprocessor, rows)
    predictions: list[MLPrediction] = []
    for row, values in zip(rows, matrix, strict=True):
        augmented = (1.0,) + values
        raw = _softmax(
            [
                sum(weight * value for weight, value in zip(class_weights, augmented, strict=True))
                for class_weights in model.weights
            ]
        )
        probabilities = _decimal_probabilities(raw)
        predictions.append(
            MLPrediction(
                row.row_id,
                "MULTINOMIAL_LOGISTIC_REGRESSION",
                model.config.model_version,
                row.feature_profile.value,
                model.trained_through,
                row.prediction_as_of,
                ML_CLASS_ORDER,
                tuple(
                    MLClassProbability(selection, probability)
                    for selection, probability in zip(ML_CLASS_ORDER, probabilities, strict=True)
                ),
                MLModelStatus.READY,
                (),
                row.feature_schema_version,
                model.training_support,
            )
        )
    return tuple(predictions)


def _softmax(logits: list[float]) -> tuple[float, ...]:
    maximum = max(logits)
    exponentials = [exp(value - maximum) for value in logits]
    total = sum(exponentials)
    return tuple(value / total for value in exponentials)


def _decimal_probabilities(values: tuple[float, ...]) -> tuple[Decimal, Decimal, Decimal]:
    home = Decimal(f"{values[0]:.15f}")
    draw = Decimal(f"{values[1]:.15f}")
    away = Decimal(1) - home - draw
    return home, draw, away
