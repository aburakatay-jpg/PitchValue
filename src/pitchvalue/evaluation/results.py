"""Metric-free summaries for walk-forward evaluation plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pitchvalue.evaluation.contracts import EvaluationStatus, FoldExecution


@dataclass(frozen=True)
class FoldSummary:
    fold_id: str
    status: EvaluationStatus
    training_observation_count: int
    evaluation_observation_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "status": self.status.value,
            "training_observation_count": self.training_observation_count,
            "evaluation_observation_count": self.evaluation_observation_count,
        }


@dataclass(frozen=True)
class EvaluationRunSummary:
    fold_count: int
    valid_fold_count: int
    skipped_or_insufficient_fold_count: int
    total_training_observations: int
    total_evaluation_observations: int
    folds: tuple[FoldSummary, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_count": self.fold_count,
            "valid_fold_count": self.valid_fold_count,
            "skipped_or_insufficient_fold_count": self.skipped_or_insufficient_fold_count,
            "total_training_observations": self.total_training_observations,
            "total_evaluation_observations": self.total_evaluation_observations,
            "folds": [fold.to_dict() for fold in self.folds],
        }


def summarize_executions(executions: tuple[FoldExecution, ...]) -> EvaluationRunSummary:
    folds = tuple(
        FoldSummary(
            fold_id=item.fold.fold_id,
            status=item.fold.status,
            training_observation_count=item.fold.training_observation_count,
            evaluation_observation_count=item.fold.test_observation_count,
        )
        for item in executions
    )
    valid = sum(fold.status is EvaluationStatus.READY for fold in folds)
    return EvaluationRunSummary(
        fold_count=len(folds),
        valid_fold_count=valid,
        skipped_or_insufficient_fold_count=len(folds) - valid,
        total_training_observations=sum(fold.training_observation_count for fold in folds),
        total_evaluation_observations=sum(fold.evaluation_observation_count for fold in folds),
        folds=folds,
    )
