"""Leakage-safe ML datasets and the uncalibrated TASK 16 baseline."""

from pitchvalue.ml.config import (
    DatasetBuilderConfig,
    FeatureProfile,
    FeatureSchema,
    MissingValuePolicy,
    MLDatasetValidationError,
    MLTrainingConfig,
    PreprocessingPolicy,
)
from pitchvalue.ml.contracts import (
    DatasetDiagnostic,
    DatasetStatus,
    DiagnosticCode,
    FeatureKind,
    FeatureRecord,
    MarketFeatureSemantics,
    MissingReason,
    MLDataset,
    RejectedTrainingRow,
    ResolvedMatchOutcome,
    RowStatus,
    TargetDefinition,
    TargetMode,
    TrainingCandidate,
    TrainingRow,
)
from pitchvalue.ml.dataset import build_dataset
from pitchvalue.ml.evaluation import MLEvaluationResult, evaluate_walk_forward_ml
from pitchvalue.ml.features import order_features
from pitchvalue.ml.model import (
    ML_CLASS_ORDER,
    FittedMultinomialLogistic,
    MLClassProbability,
    MLModelStatus,
    MLPrediction,
    fit_multinomial_logistic,
    predict_multinomial_logistic,
)
from pitchvalue.ml.preprocessing import FittedPreprocessor, fit_preprocessor, transform_rows
from pitchvalue.ml.provenance import (
    DatasetRowProvenance,
    FeatureProvenance,
    SourceMatchReference,
)
from pitchvalue.ml.targets import TargetDerivation, derive_target
from pitchvalue.ml.validation import validate_candidate

__all__ = [
    "DatasetBuilderConfig",
    "DatasetDiagnostic",
    "DatasetRowProvenance",
    "DatasetStatus",
    "DiagnosticCode",
    "FeatureKind",
    "FeatureProfile",
    "FeatureProvenance",
    "FeatureRecord",
    "FeatureSchema",
    "FittedMultinomialLogistic",
    "FittedPreprocessor",
    "MarketFeatureSemantics",
    "MLDataset",
    "MLDatasetValidationError",
    "MLEvaluationResult",
    "MLTrainingConfig",
    "MLClassProbability",
    "MLModelStatus",
    "MLPrediction",
    "ML_CLASS_ORDER",
    "MissingReason",
    "MissingValuePolicy",
    "PreprocessingPolicy",
    "RejectedTrainingRow",
    "ResolvedMatchOutcome",
    "RowStatus",
    "SourceMatchReference",
    "TargetDefinition",
    "TargetDerivation",
    "TargetMode",
    "TrainingCandidate",
    "TrainingRow",
    "build_dataset",
    "derive_target",
    "evaluate_walk_forward_ml",
    "fit_multinomial_logistic",
    "fit_preprocessor",
    "order_features",
    "predict_multinomial_logistic",
    "transform_rows",
    "validate_candidate",
]
