"""Chronological expanding and rolling walk-forward split construction."""

from __future__ import annotations

from collections.abc import Iterable

from pitchvalue.evaluation.config import EvaluationValidationError, SplitStrategy, WalkForwardConfig
from pitchvalue.evaluation.contracts import (
    EvaluationStatus,
    FoldDiagnosticCode,
    FoldExecution,
    TemporalObservation,
    WalkForwardFold,
)


def canonical_observations(
    observations: Iterable[TemporalObservation],
) -> tuple[TemporalObservation, ...]:
    rows = tuple(observations)
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, TemporalObservation):
            raise EvaluationValidationError("all observations must use TemporalObservation")
        if row.observation_id in seen:
            raise EvaluationValidationError(f"duplicate observation_id: {row.observation_id}")
        seen.add(row.observation_id)
    return tuple(sorted(rows, key=lambda item: (item.kickoff, item.observation_id)))


def create_fold_executions(
    observations: Iterable[TemporalObservation], config: WalkForwardConfig | None = None
) -> tuple[FoldExecution, ...]:
    """Create deterministic half-open folds without executing or training a model."""
    config = config or WalkForwardConfig()
    rows = canonical_observations(observations)
    if not rows:
        return ()
    dataset_start = rows[0].kickoff
    dataset_end = rows[-1].kickoff
    train_end = dataset_start + config.training_window
    executions: list[FoldExecution] = []
    fold_number = 1
    while train_end + config.embargo <= dataset_end:
        train_start = (
            dataset_start
            if config.strategy is SplitStrategy.EXPANDING
            else train_end - config.training_window
        )
        test_start = train_end + config.embargo
        test_end = test_start + config.test_window
        training = tuple(
            row
            for row in rows
            if train_start <= row.kickoff < train_end and row.available_at <= train_end
        )
        testing = tuple(row for row in rows if test_start <= row.kickoff < test_end)
        status, diagnostics = _fold_status(training, testing, config)
        fold = WalkForwardFold(
            fold_id=f"fold-{fold_number:04d}",
            strategy=config.strategy,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            training_observation_ids=tuple(row.observation_id for row in training),
            test_observation_ids=tuple(row.observation_id for row in testing),
            status=status,
            diagnostics=diagnostics,
        )
        executions.append(FoldExecution(fold, training, testing))
        fold_number += 1
        train_end += config.step_size
    return tuple(executions)


def _fold_status(
    training: tuple[TemporalObservation, ...],
    testing: tuple[TemporalObservation, ...],
    config: WalkForwardConfig,
) -> tuple[EvaluationStatus, tuple[FoldDiagnosticCode, ...]]:
    diagnostics: list[FoldDiagnosticCode] = []
    if not training:
        diagnostics.append(FoldDiagnosticCode.EMPTY_TRAINING_WINDOW)
    if not testing:
        diagnostics.append(FoldDiagnosticCode.EMPTY_TEST_WINDOW)
    if training and len(training) < config.minimum_training_samples:
        diagnostics.append(FoldDiagnosticCode.INSUFFICIENT_TRAINING_SAMPLE)
    if testing and len(testing) < config.minimum_test_samples:
        diagnostics.append(FoldDiagnosticCode.INSUFFICIENT_TEST_SAMPLE)
    if FoldDiagnosticCode.EMPTY_TRAINING_WINDOW in diagnostics or (
        FoldDiagnosticCode.EMPTY_TEST_WINDOW in diagnostics
    ):
        return EvaluationStatus.EMPTY_WINDOW, tuple(diagnostics)
    if FoldDiagnosticCode.INSUFFICIENT_TRAINING_SAMPLE in diagnostics:
        return EvaluationStatus.INSUFFICIENT_TRAINING_SAMPLE, tuple(diagnostics)
    if FoldDiagnosticCode.INSUFFICIENT_TEST_SAMPLE in diagnostics:
        return EvaluationStatus.INSUFFICIENT_TEST_SAMPLE, tuple(diagnostics)
    return EvaluationStatus.READY, ()
