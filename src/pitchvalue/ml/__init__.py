"""Leakage-safe ML feature, target, and dataset contracts; no model training."""

from pitchvalue.ml.config import (
    DatasetBuilderConfig,
    FeatureProfile,
    FeatureSchema,
    MissingValuePolicy,
    MLDatasetValidationError,
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
from pitchvalue.ml.features import order_features
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
    "MarketFeatureSemantics",
    "MLDataset",
    "MLDatasetValidationError",
    "MissingReason",
    "MissingValuePolicy",
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
    "order_features",
    "validate_candidate",
]
