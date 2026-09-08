"""Reusable temporal leakage checks for prediction-time inputs."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from pitchvalue.evaluation.config import EvaluationValidationError
from pitchvalue.evaluation.contracts import (
    EvaluationStatus,
    EvaluationTarget,
    LeakageCode,
    LeakageDiagnostic,
    LeakageValidationResult,
    ObservationKind,
    PredictionEvaluationRecord,
    TemporalObservation,
)


def validate_as_of(prediction_as_of: datetime, kickoff: datetime) -> LeakageValidationResult:
    """Validate raw temporal order without correcting caller timestamps."""
    aware = all(
        isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
        for value in (prediction_as_of, kickoff)
    )
    if aware and prediction_as_of < kickoff:
        return LeakageValidationResult(EvaluationStatus.READY, ())
    diagnostic = LeakageDiagnostic(
        LeakageCode.INVALID_AS_OF,
        None,
        "prediction_as_of must be timezone-aware and strictly before kickoff",
    )
    return LeakageValidationResult(EvaluationStatus.INVALID_TEMPORAL_ORDER, (diagnostic,))


def validate_prediction_history(
    target: EvaluationTarget, observations: Iterable[TemporalObservation]
) -> LeakageValidationResult:
    """Report every deterministic leakage violation in prediction-time material."""
    rows = tuple(observations)
    _reject_duplicate_ids(rows)
    diagnostics: list[LeakageDiagnostic] = []
    for row in sorted(rows, key=lambda item: (item.kickoff, item.observation_id)):
        if row.match_id == target.match_id:
            diagnostics.append(_diagnostic(LeakageCode.TARGET_SELF_LEAKAGE, row))
        if row.contains_target_outcome:
            diagnostics.append(_diagnostic(LeakageCode.TARGET_RESULT_IN_FEATURES, row))
        if row.kickoff == target.kickoff:
            diagnostics.append(_diagnostic(LeakageCode.SAME_TIME_OBSERVATION, row))
        elif row.kickoff >= target.prediction_as_of:
            diagnostics.append(_diagnostic(LeakageCode.FUTURE_OBSERVATION, row))
        if row.available_at > target.prediction_as_of:
            if row.kind is ObservationKind.FEATURE:
                code = LeakageCode.FEATURE_AVAILABLE_AFTER_AS_OF
            elif row.kind is ObservationKind.ODDS:
                code = LeakageCode.ODDS_AVAILABLE_AFTER_AS_OF
            else:
                code = LeakageCode.FUTURE_OBSERVATION
            diagnostics.append(_diagnostic(code, row))
        if row.kind is ObservationKind.OUTCOME and row.available_at < row.kickoff:
            diagnostics.append(_diagnostic(LeakageCode.OUTCOME_AVAILABLE_TOO_EARLY, row))
    ordered = tuple(
        sorted(diagnostics, key=lambda item: ((item.observation_id or ""), item.code.value))
    )
    status = EvaluationStatus.LEAKAGE_DETECTED if ordered else EvaluationStatus.READY
    return LeakageValidationResult(status, ordered)


def validate_evaluation_record(record: PredictionEvaluationRecord) -> LeakageValidationResult:
    if (
        record.outcome_available_at is not None
        and record.outcome_available_at < record.target.kickoff
    ):
        diagnostic = LeakageDiagnostic(
            LeakageCode.OUTCOME_AVAILABLE_TOO_EARLY,
            record.record_id,
            "evaluation truth cannot be available before target kickoff",
        )
        return LeakageValidationResult(EvaluationStatus.LEAKAGE_DETECTED, (diagnostic,))
    return LeakageValidationResult(EvaluationStatus.READY, ())


def _reject_duplicate_ids(rows: tuple[TemporalObservation, ...]) -> None:
    seen: set[str] = set()
    for row in rows:
        if row.observation_id in seen:
            raise EvaluationValidationError(f"duplicate observation_id: {row.observation_id}")
        seen.add(row.observation_id)


def _diagnostic(code: LeakageCode, row: TemporalObservation) -> LeakageDiagnostic:
    return LeakageDiagnostic(code, row.observation_id, code.value.lower().replace("_", " "))
