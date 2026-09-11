"""Leakage-safe temporal evaluation for the TASK 18 ensemble candidate."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
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
    MulticlassPrediction,
    ProbabilitySemantics,
    evaluate_multiclass_probabilities,
)
from pitchvalue.ml.baseline import train_prior_probabilities
from pitchvalue.ml.config import MLTrainingConfig
from pitchvalue.ml.contracts import MLDataset
from pitchvalue.ml.ensemble import (
    EnsembleCandidateDecision,
    EnsembleConfig,
    EnsemblePrediction,
    EnsembleStatus,
    ProbabilityModelPrediction,
    WeightEvidence,
    blend_probabilities,
    decide_ensemble_candidate,
    select_temporal_weight,
    weight_distribution,
)
from pitchvalue.ml.evaluation import DEFAULT_ML_WALK_FORWARD, MetricSummary
from pitchvalue.ml.model import (
    ML_CLASS_ORDER,
    MLClassProbability,
    fit_multinomial_logistic,
    predict_multinomial_logistic,
)
from pitchvalue.models.signals.contracts import (
    DirectionalPreference,
    ModelSignal,
    SignalStatus,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection


@dataclass(frozen=True)
class EnsembleModelEvidence:
    row_id: str
    match_id: str
    prediction_as_of: datetime
    poisson: ProbabilityModelPrediction | None
    elo: ModelSignal
    form: ModelSignal
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlignedOOSPrediction:
    fold_id: str
    competition_id: str
    season_id: str
    observed: Selection
    ml: ProbabilityModelPrediction
    poisson: ProbabilityModelPrediction
    prior: tuple[MLClassProbability, ...]
    elo: ModelSignal
    form: ModelSignal


@dataclass(frozen=True)
class TemporalEnsemblePrediction:
    aligned: AlignedOOSPrediction
    ensemble: EnsemblePrediction


@dataclass(frozen=True)
class ComparativeMetrics:
    sample_count: int
    ml: MetricSummary
    poisson: MetricSummary
    ensemble: MetricSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "ml": self.ml.to_dict(),
            "poisson": self.poisson.to_dict(),
            "ensemble": self.ensemble.to_dict(),
        }


@dataclass(frozen=True)
class StaticWeightBenchmark:
    ml_weight: Decimal
    poisson_weight: Decimal
    metrics: MetricSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "ml_weight": str(self.ml_weight),
            "poisson_weight": str(self.poisson_weight),
            "metrics": self.metrics.to_dict(),
        }


@dataclass(frozen=True)
class FoldEnsembleResult:
    fold_id: str
    test_start: datetime
    test_end: datetime
    matched_rows: int
    prior_weight_evidence: int
    ml_weight: Decimal | None
    poisson_weight: Decimal | None
    ml_metrics: MetricSummary | None
    poisson_metrics: MetricSummary | None
    ensemble_metrics: MetricSummary | None
    winning_model: str | None
    status: EnsembleStatus
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "test_period": [self.test_start.isoformat(), self.test_end.isoformat()],
            "matched_rows": self.matched_rows,
            "prior_weight_evidence": self.prior_weight_evidence,
            "ml_weight": None if self.ml_weight is None else str(self.ml_weight),
            "poisson_weight": (None if self.poisson_weight is None else str(self.poisson_weight)),
            "ml_metrics": None if self.ml_metrics is None else self.ml_metrics.to_dict(),
            "poisson_metrics": (
                None if self.poisson_metrics is None else self.poisson_metrics.to_dict()
            ),
            "ensemble_metrics": (
                None if self.ensemble_metrics is None else self.ensemble_metrics.to_dict()
            ),
            "winning_model": self.winning_model,
            "status": self.status.value,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class ClassEnsembleDiagnostic:
    class_label: str
    observed_support: int
    observed_frequency: Decimal
    ml_mean_probability: Decimal
    poisson_mean_probability: Decimal
    ensemble_mean_probability: Decimal
    ml_signed_gap: Decimal
    poisson_signed_gap: Decimal
    ensemble_signed_gap: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in self.__dict__.items()
        }


@dataclass(frozen=True)
class AgreementDiagnostic:
    dimension: str
    state: str
    sample_count: int
    ensemble_metrics: MetricSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "state": self.state,
            "sample_count": self.sample_count,
            "ensemble_metrics": self.ensemble_metrics.to_dict(),
        }


@dataclass(frozen=True)
class EnsembleEvaluationResult:
    ensemble_version: str
    raw_ml_rows: int
    poisson_rows: int
    matched_rows: int
    excluded_rows: int
    exclusion_reasons: tuple[tuple[str, int], ...]
    temporal_ensemble_rows: int
    fold_results: tuple[FoldEnsembleResult, ...]
    static_benchmarks: tuple[StaticWeightBenchmark, ...]
    comparable_metrics: ComparativeMetrics
    train_prior_metrics: MetricSummary
    competition_breakdown: tuple[tuple[str, ComparativeMetrics], ...]
    season_breakdown: tuple[tuple[str, ComparativeMetrics], ...]
    class_diagnostics: tuple[ClassEnsembleDiagnostic, ...]
    agreement_diagnostics: tuple[AgreementDiagnostic, ...]
    ml_weight_min: Decimal | None
    ml_weight_median: Decimal | None
    ml_weight_max: Decimal | None
    boundary_weight_count: int
    decision: EnsembleCandidateDecision
    preferred_probability_model: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ensemble_version": self.ensemble_version,
            "raw_ml_rows": self.raw_ml_rows,
            "poisson_rows": self.poisson_rows,
            "matched_rows": self.matched_rows,
            "excluded_rows": self.excluded_rows,
            "exclusion_reasons": dict(self.exclusion_reasons),
            "temporal_ensemble_rows": self.temporal_ensemble_rows,
            "fold_results": [item.to_dict() for item in self.fold_results],
            "static_benchmarks": [item.to_dict() for item in self.static_benchmarks],
            "comparable_metrics": self.comparable_metrics.to_dict(),
            "train_prior_metrics": self.train_prior_metrics.to_dict(),
            "competition_breakdown": [
                {"scope": scope, **metrics.to_dict()}
                for scope, metrics in self.competition_breakdown
            ],
            "season_breakdown": [
                {"scope": scope, **metrics.to_dict()} for scope, metrics in self.season_breakdown
            ],
            "class_diagnostics": [item.to_dict() for item in self.class_diagnostics],
            "agreement_diagnostics": [item.to_dict() for item in self.agreement_diagnostics],
            "ml_weight_distribution": {
                "min": None if self.ml_weight_min is None else str(self.ml_weight_min),
                "median": None if self.ml_weight_median is None else str(self.ml_weight_median),
                "max": None if self.ml_weight_max is None else str(self.ml_weight_max),
                "boundary_count": self.boundary_weight_count,
            },
            "decision": self.decision.value,
            "preferred_probability_model": self.preferred_probability_model,
        }


def evaluate_temporal_ensemble(
    dataset: MLDataset,
    evidence: tuple[EnsembleModelEvidence, ...],
    *,
    training_config: MLTrainingConfig | None = None,
    ensemble_config: EnsembleConfig | None = None,
    walk_forward_config: WalkForwardConfig = DEFAULT_ML_WALK_FORWARD,
    competition_labels: tuple[tuple[str, str], ...] = (),
    season_labels: tuple[tuple[str, str], ...] = (),
) -> EnsembleEvaluationResult:
    training_config = training_config or MLTrainingConfig()
    ensemble_config = ensemble_config or EnsembleConfig()
    usable = tuple(
        row for row in dataset.rows if any(item.value is not None for item in row.features)
    )
    by_id = {row.row_id: row for row in usable}
    evidence_by_id = {item.row_id: item for item in evidence}
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
    folds: list[FoldEnsembleResult] = []
    all_aligned: list[AlignedOOSPrediction] = []
    temporal: list[TemporalEnsemblePrediction] = []
    past_evidence: list[WeightEvidence] = []
    raw_ml_rows = 0
    poisson_rows = 0
    exclusion_reasons: Counter[str] = Counter()
    for execution in executions:
        fold = execution.fold
        train_rows = tuple(by_id[item.observation_id] for item in execution.training_observations)
        test_rows = tuple(by_id[item.observation_id] for item in execution.test_observations)
        if fold.status is not EvaluationStatus.READY:
            folds.append(
                _skipped_fold(
                    fold.fold_id,
                    fold.test_start,
                    fold.test_end,
                    len(test_rows),
                    fold.status.value,
                )
            )
            continue
        model = fit_multinomial_logistic(train_rows, training_config)
        if model is None:
            folds.append(
                _skipped_fold(
                    fold.fold_id,
                    fold.test_start,
                    fold.test_end,
                    len(test_rows),
                    "base model support unavailable",
                )
            )
            continue
        ml_predictions = predict_multinomial_logistic(model, test_rows)
        prior = train_prior_probabilities(train_rows)
        raw_ml_rows += len(ml_predictions)
        aligned: list[AlignedOOSPrediction] = []
        for row, ml_prediction in zip(test_rows, ml_predictions, strict=True):
            model_evidence = evidence_by_id.get(row.row_id)
            if model_evidence is None or model_evidence.poisson is None:
                reasons = (
                    ("MISSING_MODEL_EVIDENCE",)
                    if model_evidence is None
                    else model_evidence.diagnostics or ("POISSON_UNAVAILABLE",)
                )
                exclusion_reasons.update(reasons)
                continue
            poisson_rows += 1
            if (
                model_evidence.match_id != row.match_id
                or model_evidence.prediction_as_of != row.prediction_as_of
            ):
                exclusion_reasons.update(("MODEL_EVIDENCE_IDENTITY_MISMATCH",))
                continue
            ml = ProbabilityModelPrediction(
                row.row_id,
                row.match_id,
                row.prediction_as_of,
                "ML",
                ml_prediction.model_version,
                ml_prediction.class_order,
                ml_prediction.probabilities,
            )
            ml.validate(ensemble_config.probability_sum_tolerance)
            model_evidence.poisson.validate(ensemble_config.probability_sum_tolerance)
            assert isinstance(row.target_value, Selection)
            aligned.append(
                AlignedOOSPrediction(
                    fold.fold_id,
                    row.competition_id,
                    row.season_id,
                    row.target_value,
                    ml,
                    model_evidence.poisson,
                    prior,
                    model_evidence.elo,
                    model_evidence.form,
                )
            )
        all_aligned.extend(aligned)
        selection = select_temporal_weight(tuple(past_evidence), fold.test_start, ensemble_config)
        ml_metrics = _metrics(tuple(aligned), "ml", ensemble_config)
        poisson_metrics = _metrics(tuple(aligned), "poisson", ensemble_config)
        if selection.status is not EnsembleStatus.READY:
            folds.append(
                FoldEnsembleResult(
                    fold.fold_id,
                    fold.test_start,
                    fold.test_end,
                    len(aligned),
                    selection.evidence_support,
                    None,
                    None,
                    ml_metrics,
                    poisson_metrics,
                    None,
                    _winner(ml_metrics, poisson_metrics, None),
                    selection.status,
                    selection.diagnostics,
                )
            )
        else:
            assert selection.ml_weight is not None and selection.poisson_weight is not None
            assert selection.evidence_through is not None
            fold_temporal = tuple(
                TemporalEnsemblePrediction(
                    item,
                    blend_probabilities(
                        item.ml,
                        item.poisson,
                        selection.ml_weight,
                        config=ensemble_config,
                        evidence_support=selection.evidence_support,
                        evidence_through=selection.evidence_through,
                    ),
                )
                for item in aligned
            )
            temporal.extend(fold_temporal)
            ensemble_metrics = _metrics_temporal(fold_temporal, "ensemble", ensemble_config)
            folds.append(
                FoldEnsembleResult(
                    fold.fold_id,
                    fold.test_start,
                    fold.test_end,
                    len(aligned),
                    selection.evidence_support,
                    selection.ml_weight,
                    selection.poisson_weight,
                    ml_metrics,
                    poisson_metrics,
                    ensemble_metrics,
                    _winner(ml_metrics, poisson_metrics, ensemble_metrics),
                    EnsembleStatus.READY,
                    (),
                )
            )
        past_evidence.extend(
            WeightEvidence(item.ml.prediction_as_of, item.observed, item.ml, item.poisson)
            for item in aligned
        )
    aligned_rows = tuple(all_aligned)
    temporal_rows = tuple(temporal)
    comparable = _comparative(temporal_rows, ensemble_config)
    weights = tuple(fold.ml_weight for fold in folds if fold.ml_weight is not None)
    distribution = weight_distribution(weights) if weights else (None, None, None, 0)
    improved_folds = sum(
        fold.status is EnsembleStatus.READY
        and fold.ensemble_metrics is not None
        and fold.ml_metrics is not None
        and fold.poisson_metrics is not None
        and fold.ensemble_metrics.log_loss is not None
        and fold.ml_metrics.log_loss is not None
        and fold.poisson_metrics.log_loss is not None
        and fold.ensemble_metrics.log_loss
        < min(fold.ml_metrics.log_loss, fold.poisson_metrics.log_loss)
        for fold in folds
    )
    strongest_name, strongest = min(
        (("RAW ML", comparable.ml), ("RAW POISSON", comparable.poisson)),
        key=lambda item: item[1].log_loss if item[1].log_loss is not None else Decimal("Infinity"),
    )
    decision = decide_ensemble_candidate(
        ensemble_log_loss=comparable.ensemble.log_loss,
        ensemble_brier=comparable.ensemble.brier,
        strongest_log_loss=strongest.log_loss,
        strongest_brier=strongest.brier,
        improved_folds=improved_folds,
        evaluated_folds=sum(fold.status is EnsembleStatus.READY for fold in folds),
        weights=weights,
    )
    preferred = (
        "ACCEPTED ENSEMBLE" if decision is EnsembleCandidateDecision.ACCEPT else strongest_name
    )
    return EnsembleEvaluationResult(
        ensemble_config.version,
        raw_ml_rows,
        poisson_rows,
        len(aligned_rows),
        raw_ml_rows - len(aligned_rows),
        tuple(sorted(exclusion_reasons.items())),
        len(temporal_rows),
        tuple(folds),
        _static_benchmarks(aligned_rows, ensemble_config),
        comparable,
        _metrics_temporal(temporal_rows, "prior", ensemble_config),
        _breakdowns(temporal_rows, "competition", dict(competition_labels), ensemble_config),
        _breakdowns(temporal_rows, "season", dict(season_labels), ensemble_config),
        _class_diagnostics(temporal_rows),
        _agreement_diagnostics(temporal_rows, ensemble_config),
        distribution[0],
        distribution[1],
        distribution[2],
        distribution[3],
        decision,
        preferred,
    )


def _skipped_fold(
    fold_id: str, test_start: datetime, test_end: datetime, rows: int, reason: str
) -> FoldEnsembleResult:
    return FoldEnsembleResult(
        fold_id,
        test_start,
        test_end,
        rows,
        0,
        None,
        None,
        None,
        None,
        None,
        None,
        EnsembleStatus.UNSUPPORTED,
        (reason,),
    )


def _metrics(
    rows: tuple[AlignedOOSPrediction, ...], source: str, config: EnsembleConfig
) -> MetricSummary:
    return _metric_summary(
        tuple((item.ml if source == "ml" else item.poisson).probabilities for item in rows),
        tuple(item.observed for item in rows),
        source,
        config,
    )


def _metrics_temporal(
    rows: tuple[TemporalEnsemblePrediction, ...], source: str, config: EnsembleConfig
) -> MetricSummary:
    if source == "ensemble":
        probabilities = tuple(item.ensemble.probabilities for item in rows)
    elif source == "ml":
        probabilities = tuple(item.aligned.ml.probabilities for item in rows)
    elif source == "poisson":
        probabilities = tuple(item.aligned.poisson.probabilities for item in rows)
    else:
        probabilities = tuple(item.aligned.prior for item in rows)
    return _metric_summary(
        probabilities,
        tuple(item.aligned.observed for item in rows),
        source,
        config,
    )


def _metric_summary(
    probabilities: tuple[tuple[MLClassProbability, ...], ...],
    observed: tuple[Selection, ...],
    source: str,
    config: EnsembleConfig,
) -> MetricSummary:
    records = tuple(
        MulticlassPrediction(
            f"{source}-{index:05d}",
            tuple(ClassProbability(item.selection.value, item.probability) for item in values),
            outcome.value,
            semantics=ProbabilitySemantics.MODEL_PROBABILITY,
        )
        for index, (values, outcome) in enumerate(zip(probabilities, observed, strict=True))
    )
    suite = evaluate_multiclass_probabilities(
        records,
        MetricConfig(
            probability_sum_tolerance=config.probability_sum_tolerance,
            minimum_total_samples=1,
            minimum_bucket_samples=1,
        ),
        MetricProvenance(
            model_name=source.upper(),
            market=MarketFamily.MATCH_RESULT.value,
        ),
    )
    return MetricSummary(
        suite.log_loss.usable_count,
        suite.log_loss.value,
        suite.brier.value,
        suite.accuracy.value,
        suite.calibration.macro_ece,
        suite.log_loss.status.value,
    )


def _comparative(
    rows: tuple[TemporalEnsemblePrediction, ...], config: EnsembleConfig
) -> ComparativeMetrics:
    return ComparativeMetrics(
        len(rows),
        _metrics_temporal(rows, "ml", config),
        _metrics_temporal(rows, "poisson", config),
        _metrics_temporal(rows, "ensemble", config),
    )


def _static_benchmarks(
    rows: tuple[AlignedOOSPrediction, ...], config: EnsembleConfig
) -> tuple[StaticWeightBenchmark, ...]:
    result = []
    for weight in map(Decimal, ("0", "0.25", "0.5", "0.75", "1")):
        values = tuple(
            tuple(
                MLClassProbability(
                    selection,
                    ml.probability * weight + poisson.probability * (Decimal(1) - weight),
                )
                for selection, ml, poisson in zip(
                    ML_CLASS_ORDER, row.ml.probabilities, row.poisson.probabilities, strict=True
                )
            )
            for row in rows
        )
        result.append(
            StaticWeightBenchmark(
                weight,
                Decimal(1) - weight,
                _metric_summary(
                    values,
                    tuple(row.observed for row in rows),
                    f"static-{weight}",
                    config,
                ),
            )
        )
    return tuple(result)


def _winner(
    ml: MetricSummary | None,
    poisson: MetricSummary | None,
    ensemble: MetricSummary | None,
) -> str | None:
    candidates = tuple(
        (name, metrics.log_loss)
        for name, metrics in (("ML", ml), ("POISSON", poisson), ("ENSEMBLE", ensemble))
        if metrics is not None and metrics.log_loss is not None
    )
    return min(candidates, key=lambda item: item[1])[0] if candidates else None


def _breakdowns(
    rows: tuple[TemporalEnsemblePrediction, ...],
    dimension: str,
    labels: dict[str, str],
    config: EnsembleConfig,
) -> tuple[tuple[str, ComparativeMetrics], ...]:
    grouped: dict[str, list[TemporalEnsemblePrediction]] = defaultdict(list)
    for row in rows:
        identifier = (
            row.aligned.competition_id if dimension == "competition" else row.aligned.season_id
        )
        grouped[labels.get(identifier, identifier)].append(row)
    return tuple((scope, _comparative(tuple(grouped[scope]), config)) for scope in sorted(grouped))


def _class_diagnostics(
    rows: tuple[TemporalEnsemblePrediction, ...],
) -> tuple[ClassEnsembleDiagnostic, ...]:
    if not rows:
        return ()
    count = Decimal(len(rows))
    result = []
    for label in ML_CLASS_ORDER:
        support = sum(item.aligned.observed is label for item in rows)
        observed = Decimal(support) / count
        means = tuple(
            sum(
                (_probability(values, label) for values in source),
                Decimal(0),
            )
            / count
            for source in (
                tuple(item.aligned.ml.probabilities for item in rows),
                tuple(item.aligned.poisson.probabilities for item in rows),
                tuple(item.ensemble.probabilities for item in rows),
            )
        )
        result.append(
            ClassEnsembleDiagnostic(
                label.value,
                support,
                observed,
                means[0],
                means[1],
                means[2],
                means[0] - observed,
                means[1] - observed,
                means[2] - observed,
            )
        )
    return tuple(result)


def _agreement_diagnostics(
    rows: tuple[TemporalEnsemblePrediction, ...], config: EnsembleConfig
) -> tuple[AgreementDiagnostic, ...]:
    grouped: dict[tuple[str, str], list[TemporalEnsemblePrediction]] = defaultdict(list)
    for row in rows:
        ml_top = max(row.aligned.ml.probabilities, key=lambda item: item.probability).selection
        poisson_top = max(
            row.aligned.poisson.probabilities, key=lambda item: item.probability
        ).selection
        grouped[("ML_POISSON", "AGREE" if ml_top is poisson_top else "CONFLICT")].append(row)
        for name, signal in (("ELO", row.aligned.elo), ("FORM", row.aligned.form)):
            state = _signal_state(signal, ml_top)
            grouped[(name, state)].append(row)
    return tuple(
        AgreementDiagnostic(
            dimension,
            state,
            len(grouped[(dimension, state)]),
            _metrics_temporal(tuple(grouped[(dimension, state)]), "ensemble", config),
        )
        for dimension, state in sorted(grouped)
    )


def _signal_state(signal: ModelSignal, candidate: Selection) -> str:
    if signal.signal_status is not SignalStatus.READY:
        return "UNAVAILABLE"
    if signal.direction is DirectionalPreference.NEUTRAL:
        return "NEUTRAL"
    return "SUPPORT" if signal.selection is candidate else "CONFLICT"


def _probability(values: tuple[MLClassProbability, ...], label: Selection) -> Decimal:
    return next(item.probability for item in values if item.selection is label)
