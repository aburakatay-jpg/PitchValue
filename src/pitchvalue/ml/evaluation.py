"""TASK 13 walk-forward execution with TASK 14 OOS-only metrics."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pitchvalue.evaluation import (
    EvaluationStatus,
    ObservationKind,
    TemporalObservation,
    WalkForwardConfig,
    plan_walk_forward,
)
from pitchvalue.evaluation.metrics import (
    ClassProbability,
    MetricConfig,
    MetricProvenance,
    MulticlassMetricSuite,
    MulticlassPrediction,
    evaluate_multiclass_probabilities,
)
from pitchvalue.ml.baseline import train_prior_probabilities
from pitchvalue.ml.config import MLTrainingConfig
from pitchvalue.ml.contracts import MLDataset, TrainingRow
from pitchvalue.ml.model import (
    ML_CLASS_ORDER,
    MLPrediction,
    fit_multinomial_logistic,
    predict_multinomial_logistic,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection


class FoldFitStatus(StrEnum):
    READY = "READY"
    SKIPPED_EVALUATION_WINDOW = "SKIPPED_EVALUATION_WINDOW"
    SKIPPED_MINIMUM_SUPPORT = "SKIPPED_MINIMUM_SUPPORT"


@dataclass(frozen=True)
class MetricSummary:
    sample_count: int
    log_loss: Decimal | None
    brier: Decimal | None
    accuracy: Decimal | None
    macro_ece: Decimal | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "log_loss": None if self.log_loss is None else str(self.log_loss),
            "brier": None if self.brier is None else str(self.brier),
            "accuracy": None if self.accuracy is None else str(self.accuracy),
            "macro_ece": None if self.macro_ece is None else str(self.macro_ece),
            "status": self.status,
        }


@dataclass(frozen=True)
class FoldMLResult:
    fold_id: str
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_rows: int
    test_rows: int
    class_support: tuple[tuple[str, int], ...]
    status: FoldFitStatus
    skipped_reason: str | None
    ml_metrics: MetricSummary | None
    train_prior_metrics: MetricSummary | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
            "train_rows": self.train_rows,
            "test_rows": self.test_rows,
            "class_support": dict(self.class_support),
            "status": self.status.value,
            "skipped_reason": self.skipped_reason,
            "ml_metrics": None if self.ml_metrics is None else self.ml_metrics.to_dict(),
            "train_prior_metrics": (
                None if self.train_prior_metrics is None else self.train_prior_metrics.to_dict()
            ),
        }


@dataclass(frozen=True)
class OOSPrediction:
    fold_id: str
    competition_id: str
    season_id: str
    observed: Selection
    ml: MLPrediction
    prior_probabilities: tuple[tuple[Selection, Decimal], ...]


@dataclass(frozen=True)
class SliceResult:
    scope: str
    metrics: MetricSummary

    def to_dict(self) -> dict[str, Any]:
        return {"scope": self.scope, "metrics": self.metrics.to_dict()}


@dataclass(frozen=True)
class MLEvaluationResult:
    model_version: str
    feature_profile: str
    candidate_rows: int
    usable_rows: int
    skipped_rows: int
    complete_rows: int
    partial_rows: int
    unavailable_rows: int
    class_distribution: tuple[tuple[str, int], ...]
    fold_results: tuple[FoldMLResult, ...]
    oos_prediction_count: int
    ml_metrics: MetricSummary
    train_prior_metrics: MetricSummary
    competition_breakdown: tuple[SliceResult, ...]
    season_breakdown: tuple[SliceResult, ...]

    def to_dict(self) -> dict[str, Any]:
        total = sum(count for _, count in self.class_distribution)
        return {
            "model_version": self.model_version,
            "feature_profile": self.feature_profile,
            "probability_semantics": "UNCALIBRATED ML PROBABILITY",
            "candidate_rows": self.candidate_rows,
            "usable_rows": self.usable_rows,
            "skipped_rows": self.skipped_rows,
            "coverage": {
                "COMPLETE": self.complete_rows,
                "PARTIAL": self.partial_rows,
                "UNAVAILABLE": self.unavailable_rows,
            },
            "class_distribution": [
                {
                    "class": label,
                    "count": count,
                    "share": str(Decimal(count) / Decimal(total)) if total else None,
                }
                for label, count in self.class_distribution
            ],
            "fold_results": [item.to_dict() for item in self.fold_results],
            "oos_prediction_count": self.oos_prediction_count,
            "ml_metrics": self.ml_metrics.to_dict(),
            "train_prior_metrics": self.train_prior_metrics.to_dict(),
            "competition_breakdown": [item.to_dict() for item in self.competition_breakdown],
            "season_breakdown": [item.to_dict() for item in self.season_breakdown],
        }


DEFAULT_ML_WALK_FORWARD = WalkForwardConfig(
    training_window=timedelta(days=240),
    test_window=timedelta(days=30),
    step_size=timedelta(days=30),
    minimum_training_samples=500,
    minimum_test_samples=25,
)


def evaluate_walk_forward_ml(
    dataset: MLDataset,
    *,
    complete_rows: int,
    partial_rows: int,
    unavailable_rows: int,
    training_config: MLTrainingConfig | None = None,
    walk_forward_config: WalkForwardConfig = DEFAULT_ML_WALK_FORWARD,
    competition_labels: tuple[tuple[str, str], ...] = (),
    season_labels: tuple[tuple[str, str], ...] = (),
) -> MLEvaluationResult:
    training_config = training_config or MLTrainingConfig()
    usable = tuple(
        row for row in dataset.rows if any(item.value is not None for item in row.features)
    )
    by_id = {row.row_id: row for row in usable}
    observations = tuple(
        TemporalObservation(
            row.row_id,
            row.match_id,
            row.competition_id,
            row.season_id,
            row.prediction_as_of,
            row.prediction_as_of,
            ObservationKind.FEATURE,
        )
        for row in usable
    )
    executions = plan_walk_forward(observations, walk_forward_config)
    fold_results: list[FoldMLResult] = []
    oos: list[OOSPrediction] = []
    for execution in executions:
        fold = execution.fold
        train_rows = tuple(by_id[item.observation_id] for item in execution.training_observations)
        test_rows = tuple(by_id[item.observation_id] for item in execution.test_observations)
        support = _class_counts(train_rows)
        if fold.status is not EvaluationStatus.READY:
            fold_results.append(
                FoldMLResult(
                    fold.fold_id,
                    fold.train_start,
                    fold.train_end,
                    fold.test_start,
                    fold.test_end,
                    len(train_rows),
                    len(test_rows),
                    support,
                    FoldFitStatus.SKIPPED_EVALUATION_WINDOW,
                    fold.status.value,
                    None,
                    None,
                )
            )
            continue
        model = fit_multinomial_logistic(train_rows, training_config)
        if model is None:
            fold_results.append(
                FoldMLResult(
                    fold.fold_id,
                    fold.train_start,
                    fold.train_end,
                    fold.test_start,
                    fold.test_end,
                    len(train_rows),
                    len(test_rows),
                    support,
                    FoldFitStatus.SKIPPED_MINIMUM_SUPPORT,
                    "minimum training or class support unavailable",
                    None,
                    None,
                )
            )
            continue
        predictions = predict_multinomial_logistic(model, test_rows)
        prior = train_prior_probabilities(train_rows)
        fold_oos = tuple(
            OOSPrediction(
                fold.fold_id,
                row.competition_id,
                row.season_id,
                row.target_value,
                prediction,
                tuple((item.selection, item.probability) for item in prior),
            )
            for row, prediction in zip(test_rows, predictions, strict=True)
            if isinstance(row.target_value, Selection)
        )
        oos.extend(fold_oos)
        ml_suite = _suite(fold_oos, use_prior=False, fold_id=fold.fold_id)
        prior_suite = _suite(fold_oos, use_prior=True, fold_id=fold.fold_id)
        fold_results.append(
            FoldMLResult(
                fold.fold_id,
                fold.train_start,
                fold.train_end,
                fold.test_start,
                fold.test_end,
                len(train_rows),
                len(test_rows),
                support,
                FoldFitStatus.READY,
                None,
                _summary(ml_suite),
                _summary(prior_suite),
            )
        )
    all_oos = tuple(oos)
    return MLEvaluationResult(
        training_config.model_version,
        training_config.feature_profile.value,
        dataset.input_candidate_count,
        len(usable),
        dataset.input_candidate_count - len(usable),
        complete_rows,
        partial_rows,
        unavailable_rows,
        _class_counts(usable),
        tuple(fold_results),
        len(all_oos),
        _summary(_suite(all_oos, use_prior=False)),
        _summary(_suite(all_oos, use_prior=True)),
        _breakdowns(all_oos, "competition", dict(competition_labels)),
        _breakdowns(all_oos, "season", dict(season_labels)),
    )


def _class_counts(rows: tuple[TrainingRow, ...]) -> tuple[tuple[str, int], ...]:
    counts = Counter(row.target_value for row in rows)
    return tuple((selection.value, counts[selection]) for selection in ML_CLASS_ORDER)


def _suite(
    rows: tuple[OOSPrediction, ...],
    *,
    use_prior: bool,
    fold_id: str | None = None,
    scope: str | None = None,
) -> MulticlassMetricSuite:
    records: list[MulticlassPrediction] = []
    for row in rows:
        values = (
            row.prior_probabilities
            if use_prior
            else tuple((item.selection, item.probability) for item in row.ml.probabilities)
        )
        records.append(
            MulticlassPrediction(
                row.ml.row_id,
                tuple(
                    ClassProbability(selection.value, probability)
                    for selection, probability in values
                ),
                row.observed.value,
            )
        )
    provenance = MetricProvenance(
        fold_id=fold_id,
        model_name="TRAIN_PRIOR" if use_prior else "MULTINOMIAL_LOGISTIC_REGRESSION",
        model_version="train_prior_v1" if use_prior else "multinomial_logistic_v1",
        market=MarketFamily.MATCH_RESULT.value,
        class_scope=scope,
    )
    return evaluate_multiclass_probabilities(
        tuple(records), MetricConfig(minimum_total_samples=1, minimum_bucket_samples=1), provenance
    )


def _summary(suite: MulticlassMetricSuite) -> MetricSummary:
    return MetricSummary(
        suite.log_loss.usable_count,
        suite.log_loss.value,
        suite.brier.value,
        suite.accuracy.value,
        suite.calibration.macro_ece,
        suite.log_loss.status.value,
    )


def _breakdowns(
    rows: tuple[OOSPrediction, ...], dimension: str, labels: dict[str, str]
) -> tuple[SliceResult, ...]:
    grouped: dict[str, list[OOSPrediction]] = defaultdict(list)
    for row in rows:
        identifier = row.competition_id if dimension == "competition" else row.season_id
        key = labels.get(identifier, identifier)
        grouped[key].append(row)
    return tuple(
        SliceResult(key, _summary(_suite(tuple(grouped[key]), use_prior=False, scope=key)))
        for key in sorted(grouped)
    )
