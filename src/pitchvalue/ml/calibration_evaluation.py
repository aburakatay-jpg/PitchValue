"""Nested temporal evaluation of TASK 17 temperature scaling."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from statistics import median
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
    ProbabilitySemantics,
    evaluate_multiclass_probabilities,
)
from pitchvalue.ml.calibration import (
    CalibratedMLPrediction,
    CalibrationFitExample,
    CalibrationStatus,
    TemperatureScalingConfig,
    apply_temperature_scaling,
    fit_temperature_scaling,
)
from pitchvalue.ml.config import MLTrainingConfig
from pitchvalue.ml.contracts import MLDataset, TrainingRow
from pitchvalue.ml.evaluation import DEFAULT_ML_WALK_FORWARD, MetricSummary
from pitchvalue.ml.model import (
    ML_CLASS_ORDER,
    MLClassProbability,
    MLPrediction,
    fit_multinomial_logistic,
    predict_multinomial_logistic,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection


class CalibrationCandidateDecision(StrEnum):
    ACCEPT = "CALIBRATION_CANDIDATE_ACCEPT"
    REJECT = "CALIBRATION_CANDIDATE_REJECT"
    INCONCLUSIVE = "CALIBRATION_CANDIDATE_INCONCLUSIVE"


@dataclass(frozen=True)
class NestedCalibrationConfig:
    calibration_window: timedelta = timedelta(days=90)
    temperature: TemperatureScalingConfig = TemperatureScalingConfig()

    def __post_init__(self) -> None:
        if self.calibration_window <= timedelta(0):
            raise ValueError("calibration_window must be positive")


@dataclass(frozen=True)
class PairedPrediction:
    fold_id: str
    competition_id: str
    season_id: str
    observed: Selection
    raw: MLPrediction
    calibrated: CalibratedMLPrediction


@dataclass(frozen=True)
class FoldCalibrationResult:
    fold_id: str
    base_train_start: datetime
    base_train_end: datetime
    calibration_start: datetime
    calibration_end: datetime
    test_start: datetime
    test_end: datetime
    base_train_rows: int
    calibration_rows: int
    test_rows: int
    calibration_class_support: tuple[tuple[str, int], ...]
    raw_metrics: MetricSummary | None
    calibrated_metrics: MetricSummary | None
    temperature: Decimal | None
    status: CalibrationStatus
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "base_train_period": [
                self.base_train_start.isoformat(),
                self.base_train_end.isoformat(),
            ],
            "calibration_period": [
                self.calibration_start.isoformat(),
                self.calibration_end.isoformat(),
            ],
            "test_period": [self.test_start.isoformat(), self.test_end.isoformat()],
            "base_train_rows": self.base_train_rows,
            "calibration_rows": self.calibration_rows,
            "test_rows": self.test_rows,
            "calibration_class_support": dict(self.calibration_class_support),
            "raw_metrics": None if self.raw_metrics is None else self.raw_metrics.to_dict(),
            "calibrated_metrics": (
                None if self.calibrated_metrics is None else self.calibrated_metrics.to_dict()
            ),
            "temperature": None if self.temperature is None else str(self.temperature),
            "status": self.status.value,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class SliceCalibrationResult:
    scope: str
    sample_count: int
    raw: MetricSummary
    calibrated: MetricSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "sample_count": self.sample_count,
            "raw": self.raw.to_dict(),
            "calibrated": self.calibrated.to_dict(),
        }


@dataclass(frozen=True)
class ClassCalibrationComparison:
    class_label: str
    observed_support: int
    sample_count: int
    raw_mean_probability: Decimal
    calibrated_mean_probability: Decimal
    observed_frequency: Decimal
    raw_signed_gap: Decimal
    calibrated_signed_gap: Decimal
    raw_ece: Decimal | None
    calibrated_ece: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": self.class_label,
            "observed_support": self.observed_support,
            "sample_count": self.sample_count,
            "raw_mean_probability": str(self.raw_mean_probability),
            "calibrated_mean_probability": str(self.calibrated_mean_probability),
            "observed_frequency": str(self.observed_frequency),
            "raw_signed_gap": str(self.raw_signed_gap),
            "calibrated_signed_gap": str(self.calibrated_signed_gap),
            "raw_ece": None if self.raw_ece is None else str(self.raw_ece),
            "calibrated_ece": (None if self.calibrated_ece is None else str(self.calibrated_ece)),
        }


@dataclass(frozen=True)
class CalibrationEvaluationResult:
    model_version: str
    calibrator_version: str
    feature_profile: str
    candidate_rows: int
    usable_rows: int
    raw_oos_rows: int
    calibratable_oos_rows: int
    excluded_oos_rows: int
    fold_results: tuple[FoldCalibrationResult, ...]
    raw_metrics: MetricSummary
    calibrated_metrics: MetricSummary
    competition_breakdown: tuple[SliceCalibrationResult, ...]
    season_breakdown: tuple[SliceCalibrationResult, ...]
    class_comparison: tuple[ClassCalibrationComparison, ...]
    temperature_min: Decimal | None
    temperature_median: Decimal | None
    temperature_max: Decimal | None
    decision: CalibrationCandidateDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "calibrator_version": self.calibrator_version,
            "feature_profile": self.feature_profile,
            "probability_semantics": {
                "raw": "UNCALIBRATED ML PROBABILITY",
                "calibrated": "CALIBRATED ML PROBABILITY",
            },
            "candidate_rows": self.candidate_rows,
            "usable_rows": self.usable_rows,
            "raw_oos_rows": self.raw_oos_rows,
            "calibratable_oos_rows": self.calibratable_oos_rows,
            "excluded_oos_rows": self.excluded_oos_rows,
            "fold_results": [item.to_dict() for item in self.fold_results],
            "raw_metrics": self.raw_metrics.to_dict(),
            "calibrated_metrics": self.calibrated_metrics.to_dict(),
            "competition_breakdown": [item.to_dict() for item in self.competition_breakdown],
            "season_breakdown": [item.to_dict() for item in self.season_breakdown],
            "class_comparison": [item.to_dict() for item in self.class_comparison],
            "temperature": {
                "min": None if self.temperature_min is None else str(self.temperature_min),
                "median": (
                    None if self.temperature_median is None else str(self.temperature_median)
                ),
                "max": None if self.temperature_max is None else str(self.temperature_max),
            },
            "decision": self.decision.value,
        }


def evaluate_nested_temperature_scaling(
    dataset: MLDataset,
    *,
    training_config: MLTrainingConfig | None = None,
    calibration_config: NestedCalibrationConfig | None = None,
    walk_forward_config: WalkForwardConfig = DEFAULT_ML_WALK_FORWARD,
    competition_labels: tuple[tuple[str, str], ...] = (),
    season_labels: tuple[tuple[str, str], ...] = (),
) -> CalibrationEvaluationResult:
    training_config = training_config or MLTrainingConfig()
    calibration_config = calibration_config or NestedCalibrationConfig()
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
    folds: list[FoldCalibrationResult] = []
    paired: list[PairedPrediction] = []
    raw_oos_rows = 0
    for execution in executions:
        fold = execution.fold
        outer_train = tuple(by_id[item.observation_id] for item in execution.training_observations)
        test_rows = tuple(by_id[item.observation_id] for item in execution.test_observations)
        calibration_start = fold.train_end - calibration_config.calibration_window
        base_rows = tuple(row for row in outer_train if row.prediction_as_of < calibration_start)
        calibration_rows = tuple(
            row for row in outer_train if calibration_start <= row.prediction_as_of < fold.train_end
        )
        support = _class_counts(calibration_rows)
        if fold.status is not EvaluationStatus.READY:
            folds.append(
                _skipped_fold(
                    fold.fold_id,
                    fold.train_start,
                    calibration_start,
                    fold.train_end,
                    fold.test_start,
                    fold.test_end,
                    base_rows,
                    calibration_rows,
                    test_rows,
                    support,
                    CalibrationStatus.UNSUPPORTED,
                    fold.status.value,
                )
            )
            continue
        raw_oos_rows += len(test_rows)
        if (
            not base_rows
            or not calibration_rows
            or (
                max(row.prediction_as_of for row in base_rows)
                >= min(row.prediction_as_of for row in calibration_rows)
            )
        ):
            folds.append(
                _skipped_fold(
                    fold.fold_id,
                    fold.train_start,
                    calibration_start,
                    fold.train_end,
                    fold.test_start,
                    fold.test_end,
                    base_rows,
                    calibration_rows,
                    test_rows,
                    support,
                    CalibrationStatus.INSUFFICIENT_CALIBRATION_SUPPORT,
                    "strict base-train to calibration chronology unavailable",
                )
            )
            continue
        model = fit_multinomial_logistic(base_rows, training_config)
        if model is None:
            folds.append(
                _skipped_fold(
                    fold.fold_id,
                    fold.train_start,
                    calibration_start,
                    fold.train_end,
                    fold.test_start,
                    fold.test_end,
                    base_rows,
                    calibration_rows,
                    test_rows,
                    support,
                    CalibrationStatus.INSUFFICIENT_CALIBRATION_SUPPORT,
                    "minimum base-training support unavailable",
                )
            )
            continue
        calibration_predictions = predict_multinomial_logistic(model, calibration_rows)
        examples = tuple(
            CalibrationFitExample(prediction, row.target_value)
            for row, prediction in zip(calibration_rows, calibration_predictions, strict=True)
            if isinstance(row.target_value, Selection)
        )
        calibrator = fit_temperature_scaling(examples, calibration_config.temperature)
        if calibrator.status is not CalibrationStatus.READY:
            folds.append(
                _skipped_fold(
                    fold.fold_id,
                    fold.train_start,
                    calibration_start,
                    fold.train_end,
                    fold.test_start,
                    fold.test_end,
                    base_rows,
                    calibration_rows,
                    test_rows,
                    support,
                    calibrator.status,
                    "; ".join(calibrator.diagnostics),
                )
            )
            continue
        raw_predictions = predict_multinomial_logistic(model, test_rows)
        calibrated_predictions = apply_temperature_scaling(calibrator, raw_predictions)
        fold_pairs = tuple(
            PairedPrediction(
                fold.fold_id,
                row.competition_id,
                row.season_id,
                row.target_value,
                raw,
                calibrated,
            )
            for row, raw, calibrated in zip(
                test_rows, raw_predictions, calibrated_predictions, strict=True
            )
            if isinstance(row.target_value, Selection)
        )
        paired.extend(fold_pairs)
        folds.append(
            FoldCalibrationResult(
                fold.fold_id,
                fold.train_start,
                calibration_start,
                calibration_start,
                fold.train_end,
                fold.test_start,
                fold.test_end,
                len(base_rows),
                len(calibration_rows),
                len(test_rows),
                support,
                _summary(_suite(fold_pairs, calibrated=False, fold_id=fold.fold_id)),
                _summary(_suite(fold_pairs, calibrated=True, fold_id=fold.fold_id)),
                calibrator.temperature,
                CalibrationStatus.READY,
                (),
            )
        )
    comparisons = tuple(paired)
    raw_metrics = _summary(_suite(comparisons, calibrated=False))
    calibrated_metrics = _summary(_suite(comparisons, calibrated=True))
    temperatures = tuple(item.temperature for item in folds if item.temperature is not None)
    decision = _decision(folds, raw_metrics, calibrated_metrics, temperatures)
    return CalibrationEvaluationResult(
        training_config.model_version,
        calibration_config.temperature.version,
        training_config.feature_profile.value,
        dataset.input_candidate_count,
        len(usable),
        raw_oos_rows,
        len(comparisons),
        raw_oos_rows - len(comparisons),
        tuple(folds),
        raw_metrics,
        calibrated_metrics,
        _breakdowns(comparisons, "competition", dict(competition_labels)),
        _breakdowns(comparisons, "season", dict(season_labels)),
        _class_comparison(comparisons),
        min(temperatures) if temperatures else None,
        Decimal(str(median(temperatures))) if temperatures else None,
        max(temperatures) if temperatures else None,
        decision,
    )


def _skipped_fold(
    fold_id: str,
    train_start: datetime,
    calibration_start: datetime,
    train_end: datetime,
    test_start: datetime,
    test_end: datetime,
    base_rows: tuple[TrainingRow, ...],
    calibration_rows: tuple[TrainingRow, ...],
    test_rows: tuple[TrainingRow, ...],
    support: tuple[tuple[str, int], ...],
    status: CalibrationStatus,
    diagnostic: str,
) -> FoldCalibrationResult:
    return FoldCalibrationResult(
        fold_id,
        train_start,
        calibration_start,
        calibration_start,
        train_end,
        test_start,
        test_end,
        len(base_rows),
        len(calibration_rows),
        len(test_rows),
        support,
        None,
        None,
        None,
        status,
        (diagnostic,),
    )


def _class_counts(rows: tuple[TrainingRow, ...]) -> tuple[tuple[str, int], ...]:
    counts = Counter(row.target_value for row in rows)
    return tuple((label.value, counts[label]) for label in ML_CLASS_ORDER)


def _suite(
    rows: tuple[PairedPrediction, ...], *, calibrated: bool, fold_id: str | None = None
) -> MulticlassMetricSuite:
    records = tuple(
        MulticlassPrediction(
            row.raw.row_id,
            tuple(
                ClassProbability(item.selection.value, item.probability)
                for item in (
                    row.calibrated.calibrated_probabilities if calibrated else row.raw.probabilities
                )
            ),
            row.observed.value,
            semantics=(
                ProbabilitySemantics.CALIBRATED_PROBABILITY
                if calibrated
                else ProbabilitySemantics.MODEL_PROBABILITY
            ),
        )
        for row in rows
    )
    provenance = MetricProvenance(
        fold_id=fold_id,
        model_name="TEMPERATURE_SCALED_ML" if calibrated else "RAW_ML",
        model_version="temperature_scaling_v1" if calibrated else "multinomial_logistic_v1",
        market=MarketFamily.MATCH_RESULT.value,
    )
    return evaluate_multiclass_probabilities(
        records, MetricConfig(minimum_total_samples=1, minimum_bucket_samples=1), provenance
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
    rows: tuple[PairedPrediction, ...], dimension: str, labels: dict[str, str]
) -> tuple[SliceCalibrationResult, ...]:
    grouped: dict[str, list[PairedPrediction]] = defaultdict(list)
    for row in rows:
        identifier = row.competition_id if dimension == "competition" else row.season_id
        grouped[labels.get(identifier, identifier)].append(row)
    return tuple(
        SliceCalibrationResult(
            scope,
            len(grouped[scope]),
            _summary(_suite(tuple(grouped[scope]), calibrated=False)),
            _summary(_suite(tuple(grouped[scope]), calibrated=True)),
        )
        for scope in sorted(grouped)
    )


def _class_comparison(
    rows: tuple[PairedPrediction, ...],
) -> tuple[ClassCalibrationComparison, ...]:
    if not rows:
        return ()
    raw_calibration = _suite(rows, calibrated=False).calibration
    calibrated_calibration = _suite(rows, calibrated=True).calibration
    raw_ece = {item.class_label: item.calibration.ece for item in raw_calibration.classes}
    calibrated_ece = {
        item.class_label: item.calibration.ece for item in calibrated_calibration.classes
    }
    results = []
    for label in ML_CLASS_ORDER:
        raw_values = tuple(_probability(row.raw.probabilities, label) for row in rows)
        calibrated_values = tuple(
            _probability(row.calibrated.calibrated_probabilities, label) for row in rows
        )
        support = sum(row.observed is label for row in rows)
        count = len(rows)
        raw_mean = sum(raw_values, Decimal(0)) / Decimal(count)
        calibrated_mean = sum(calibrated_values, Decimal(0)) / Decimal(count)
        observed = Decimal(support) / Decimal(count)
        results.append(
            ClassCalibrationComparison(
                label.value,
                support,
                count,
                raw_mean,
                calibrated_mean,
                observed,
                raw_mean - observed,
                calibrated_mean - observed,
                raw_ece[label.value],
                calibrated_ece[label.value],
            )
        )
    return tuple(results)


def _probability(values: tuple[MLClassProbability, ...], label: Selection) -> Decimal:
    return next(item.probability for item in values if item.selection is label)


def _decision(
    folds: list[FoldCalibrationResult],
    raw: MetricSummary,
    calibrated: MetricSummary,
    temperatures: tuple[Decimal, ...],
) -> CalibrationCandidateDecision:
    if any(
        value is None for value in (raw.log_loss, raw.brier, calibrated.log_loss, calibrated.brier)
    ):
        return CalibrationCandidateDecision.INCONCLUSIVE
    assert raw.log_loss is not None and raw.brier is not None
    assert calibrated.log_loss is not None and calibrated.brier is not None
    ready = tuple(item for item in folds if item.status is CalibrationStatus.READY)
    improved_folds = sum(
        item.raw_metrics is not None
        and item.calibrated_metrics is not None
        and item.raw_metrics.log_loss is not None
        and item.calibrated_metrics.log_loss is not None
        and item.calibrated_metrics.log_loss < item.raw_metrics.log_loss
        for item in ready
    )
    ece_not_worse = (
        raw.macro_ece is not None
        and calibrated.macro_ece is not None
        and calibrated.macro_ece <= raw.macro_ece
    )
    if (
        calibrated.log_loss < raw.log_loss
        and calibrated.brier <= raw.brier
        and ece_not_worse
        and improved_folds > len(ready) / 2
        and temperatures
    ):
        return CalibrationCandidateDecision.ACCEPT
    if calibrated.log_loss > raw.log_loss and calibrated.brier > raw.brier:
        return CalibrationCandidateDecision.REJECT
    return CalibrationCandidateDecision.INCONCLUSIVE
