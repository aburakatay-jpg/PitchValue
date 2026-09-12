"""Train-only deterministic numeric preprocessing for TASK 16."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any

from pitchvalue.ml.config import FeatureProfile, MLDatasetValidationError
from pitchvalue.ml.contracts import FeatureKind, PredictionFeatureRow, TrainingRow

type FeatureMatrixRow = TrainingRow | PredictionFeatureRow


@dataclass(frozen=True)
class FittedPreprocessor:
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    output_feature_names: tuple[str, ...]
    fitted_row_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "means": list(self.means),
            "scales": list(self.scales),
            "output_feature_names": list(self.output_feature_names),
            "fitted_row_ids": list(self.fitted_row_ids),
        }


def fit_preprocessor(rows: tuple[TrainingRow, ...]) -> FittedPreprocessor:
    ordered = _validated_rows(rows)
    if not ordered:
        raise MLDatasetValidationError("preprocessor requires training rows")
    feature_names = tuple(feature.name for feature in ordered[0].features)
    values_by_column: list[list[float]] = [[] for _ in feature_names]
    for row in ordered:
        if tuple(feature.name for feature in row.features) != feature_names:
            raise MLDatasetValidationError("training rows must share deterministic feature order")
        for index, feature in enumerate(row.features):
            if feature.value is not None:
                value = float(feature.value)
                if not isfinite(value):
                    raise MLDatasetValidationError("feature matrix values must be finite")
                values_by_column[index].append(value)
    means = tuple(sum(values) / len(values) if values else 0.0 for values in values_by_column)
    scales = tuple(
        _scale(values, mean) for values, mean in zip(values_by_column, means, strict=True)
    )
    output_names = feature_names + tuple(f"{name}__missing" for name in feature_names)
    return FittedPreprocessor(
        feature_names,
        means,
        scales,
        output_names,
        tuple(row.row_id for row in ordered),
    )


def transform_rows(
    preprocessor: FittedPreprocessor, rows: tuple[FeatureMatrixRow, ...]
) -> tuple[tuple[float, ...], ...]:
    ordered = _validated_rows(rows, preserve_input_order=True)
    matrix: list[tuple[float, ...]] = []
    for row in ordered:
        if tuple(feature.name for feature in row.features) != preprocessor.feature_names:
            raise MLDatasetValidationError(
                "prediction row feature schema differs from training schema"
            )
        scaled: list[float] = []
        missing: list[float] = []
        for feature, mean, scale in zip(
            row.features, preprocessor.means, preprocessor.scales, strict=True
        ):
            absent = feature.value is None
            raw = mean if absent else float(feature.value)  # type: ignore[arg-type]
            value = (raw - mean) / scale
            if not isfinite(value):
                raise MLDatasetValidationError("preprocessed feature matrix must be finite")
            scaled.append(value)
            missing.append(1.0 if absent else 0.0)
        matrix.append(tuple(scaled + missing))
    return tuple(matrix)


def _scale(values: list[float], mean: float) -> float:
    if not values:
        return 1.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    scale = sqrt(variance)
    return scale if scale > 0 else 1.0


def _validated_rows(
    rows: tuple[FeatureMatrixRow, ...], *, preserve_input_order: bool = False
) -> tuple[FeatureMatrixRow, ...]:
    for row in rows:
        if row.feature_profile is not FeatureProfile.FOOTBALL_PERFORMANCE_ONLY:
            raise MLDatasetValidationError("baseline preprocessing rejects odds-inclusive rows")
        if any(feature.kind is not FeatureKind.FOOTBALL_PERFORMANCE for feature in row.features):
            raise MLDatasetValidationError("baseline preprocessing rejects odds-derived features")
        if any(
            feature.name.lower() in {"target", "result", "final_score"} for feature in row.features
        ):
            raise MLDatasetValidationError(
                "target or post-match columns cannot enter feature matrix"
            )
    if preserve_input_order:
        return rows
    return tuple(sorted(rows, key=lambda row: (row.prediction_as_of, row.row_id)))
