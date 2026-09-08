"""Pure probability-quality and calibration diagnostics."""

from pitchvalue.evaluation.metrics.aggregation import (
    BinaryMetricSuite,
    MulticlassMetricSuite,
    evaluate_binary_probabilities,
    evaluate_multiclass_probabilities,
)
from pitchvalue.evaluation.metrics.calibration import binary_calibration, multiclass_calibration
from pitchvalue.evaluation.metrics.config import MetricConfig, MetricValidationError
from pitchvalue.evaluation.metrics.contracts import (
    BinaryCalibrationResult,
    BinaryPrediction,
    BucketStatus,
    CalibrationBucket,
    ClassCalibration,
    ClassProbability,
    MetricDiagnostic,
    MetricDiagnosticCode,
    MetricName,
    MetricProvenance,
    MetricResult,
    MetricStatus,
    MulticlassCalibrationResult,
    MulticlassPrediction,
    PredictionRecordStatus,
    ProbabilitySemantics,
)
from pitchvalue.evaluation.metrics.probability import (
    binary_accuracy,
    binary_brier_score,
    binary_log_loss,
    multiclass_accuracy,
    multiclass_brier_score,
    multiclass_log_loss,
)

__all__ = [
    "BinaryCalibrationResult",
    "BinaryMetricSuite",
    "BinaryPrediction",
    "BucketStatus",
    "CalibrationBucket",
    "ClassCalibration",
    "ClassProbability",
    "MetricConfig",
    "MetricDiagnostic",
    "MetricDiagnosticCode",
    "MetricName",
    "MetricProvenance",
    "MetricResult",
    "MetricStatus",
    "MetricValidationError",
    "MulticlassCalibrationResult",
    "MulticlassMetricSuite",
    "MulticlassPrediction",
    "PredictionRecordStatus",
    "ProbabilitySemantics",
    "binary_accuracy",
    "binary_brier_score",
    "binary_calibration",
    "binary_log_loss",
    "evaluate_binary_probabilities",
    "evaluate_multiclass_probabilities",
    "multiclass_accuracy",
    "multiclass_brier_score",
    "multiclass_calibration",
    "multiclass_log_loss",
]
