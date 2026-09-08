"""Public walk-forward planning boundary; deliberately contains no model execution."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from pitchvalue.evaluation.config import WalkForwardConfig
from pitchvalue.evaluation.contracts import FoldExecution, TemporalObservation
from pitchvalue.evaluation.results import EvaluationRunSummary, summarize_executions
from pitchvalue.evaluation.splits import create_fold_executions


def plan_walk_forward(
    observations: Iterable[TemporalObservation], config: WalkForwardConfig | None = None
) -> tuple[FoldExecution, ...]:
    return create_fold_executions(observations, config)


def iter_walk_forward(
    observations: Iterable[TemporalObservation], config: WalkForwardConfig | None = None
) -> Iterator[FoldExecution]:
    yield from plan_walk_forward(observations, config)


def summarize_walk_forward(
    observations: Iterable[TemporalObservation], config: WalkForwardConfig | None = None
) -> EvaluationRunSummary:
    return summarize_executions(plan_walk_forward(observations, config))
