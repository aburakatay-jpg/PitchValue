"""Deterministic metric-suite composition without temporal or model ownership."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pitchvalue.evaluation.metrics.calibration import binary_calibration, multiclass_calibration
from pitchvalue.evaluation.metrics.config import MetricConfig
from pitchvalue.evaluation.metrics.contracts import (
    BinaryCalibrationResult,
    BinaryPrediction,
    MetricProvenance,
    MetricResult,
    MulticlassCalibrationResult,
    MulticlassPrediction,
)
from pitchvalue.evaluation.metrics.probability import (
    binary_accuracy,
    binary_brier_score,
    binary_log_loss,
    multiclass_accuracy,
    multiclass_brier_score,
    multiclass_log_loss,
)


@dataclass(frozen=True)
class BinaryMetricSuite:
    brier: MetricResult
    log_loss: MetricResult
    accuracy: MetricResult
    calibration: BinaryCalibrationResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "brier": self.brier.to_dict(),
            "log_loss": self.log_loss.to_dict(),
            "accuracy": self.accuracy.to_dict(),
            "calibration": self.calibration.to_dict(),
        }


@dataclass(frozen=True)
class MulticlassMetricSuite:
    brier: MetricResult
    log_loss: MetricResult
    accuracy: MetricResult
    calibration: MulticlassCalibrationResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "brier": self.brier.to_dict(),
            "log_loss": self.log_loss.to_dict(),
            "accuracy": self.accuracy.to_dict(),
            "calibration": self.calibration.to_dict(),
        }


def evaluate_binary_probabilities(
    records: tuple[BinaryPrediction, ...],
    config: MetricConfig | None = None,
    provenance: MetricProvenance | None = None,
) -> BinaryMetricSuite:
    config = config or MetricConfig()
    return BinaryMetricSuite(
        binary_brier_score(records, config, provenance),
        binary_log_loss(records, config, provenance),
        binary_accuracy(records, config, provenance),
        binary_calibration(records, config, provenance),
    )


def evaluate_multiclass_probabilities(
    records: tuple[MulticlassPrediction, ...],
    config: MetricConfig | None = None,
    provenance: MetricProvenance | None = None,
) -> MulticlassMetricSuite:
    config = config or MetricConfig()
    return MulticlassMetricSuite(
        multiclass_brier_score(records, config, provenance),
        multiclass_log_loss(records, config, provenance),
        multiclass_accuracy(records, config, provenance),
        multiclass_calibration(records, config, provenance),
    )
