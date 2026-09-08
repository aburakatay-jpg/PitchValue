"""Leakage-safe temporal evaluation contracts and walk-forward planning."""

from pitchvalue.evaluation.config import (
    BoundaryPolicy,
    EvaluationValidationError,
    SplitStrategy,
    WalkForwardConfig,
)
from pitchvalue.evaluation.contracts import (
    EvaluationProvenance,
    EvaluationStatus,
    EvaluationTarget,
    FoldDiagnosticCode,
    FoldExecution,
    LeakageCode,
    LeakageDiagnostic,
    LeakageValidationResult,
    ObservationKind,
    OddsUse,
    PredictionEvaluationRecord,
    TemporalObservation,
    WalkForwardFold,
)
from pitchvalue.evaluation.leakage import (
    validate_as_of,
    validate_evaluation_record,
    validate_prediction_history,
)
from pitchvalue.evaluation.results import EvaluationRunSummary, FoldSummary
from pitchvalue.evaluation.splits import canonical_observations, create_fold_executions
from pitchvalue.evaluation.walk_forward import (
    iter_walk_forward,
    plan_walk_forward,
    summarize_walk_forward,
)

__all__ = [
    "BoundaryPolicy",
    "EvaluationProvenance",
    "EvaluationRunSummary",
    "EvaluationStatus",
    "EvaluationTarget",
    "EvaluationValidationError",
    "FoldDiagnosticCode",
    "FoldExecution",
    "FoldSummary",
    "LeakageCode",
    "LeakageDiagnostic",
    "LeakageValidationResult",
    "ObservationKind",
    "OddsUse",
    "PredictionEvaluationRecord",
    "SplitStrategy",
    "TemporalObservation",
    "WalkForwardConfig",
    "WalkForwardFold",
    "canonical_observations",
    "create_fold_executions",
    "iter_walk_forward",
    "plan_walk_forward",
    "summarize_walk_forward",
    "validate_as_of",
    "validate_evaluation_record",
    "validate_prediction_history",
]
