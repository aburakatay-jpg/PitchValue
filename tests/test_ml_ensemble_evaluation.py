from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pitchvalue.evaluation import SplitStrategy, WalkForwardConfig
from pitchvalue.ml import (
    ML_CLASS_ORDER,
    DatasetStatus,
    EnsembleConfig,
    EnsembleModelEvidence,
    EnsembleStatus,
    FeatureProfile,
    FeatureProvenance,
    FeatureRecord,
    MLClassProbability,
    MLDataset,
    MLTrainingConfig,
    ProbabilityModelPrediction,
    RowStatus,
    TrainingRow,
    evaluate_temporal_ensemble,
)
from pitchvalue.ml.contracts import TargetDefinition, TargetMode
from pitchvalue.ml.provenance import DatasetRowProvenance
from pitchvalue.models.signals.config import ModelFamily
from pitchvalue.models.signals.contracts import (
    DirectionalPreference,
    ModelSignal,
    SignalStatus,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection

TARGET = TargetDefinition(
    MarketFamily.MATCH_RESULT,
    TargetMode.MULTICLASS,
    ML_CLASS_ORDER,
)
PROVENANCE = FeatureProvenance("v1", "test", "synthetic", "calculation")


def _signal(family: ModelFamily, match_id: str, direction: DirectionalPreference) -> ModelSignal:
    selection = (
        Selection.HOME
        if direction is DirectionalPreference.HOME
        else Selection.AWAY
        if direction is DirectionalPreference.AWAY
        else None
    )
    return ModelSignal(
        family,
        f"{family.value.lower()}-v1",
        match_id,
        MarketFamily.MATCH_RESULT,
        selection,
        direction,
        SignalStatus.READY,
        Decimal("0.5"),
    )


def _inputs() -> tuple[MLDataset, tuple[EnsembleModelEvidence, ...]]:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    labels = (Selection.HOME, Selection.DRAW, Selection.AWAY)
    rows = []
    evidence = []
    for index in range(150):
        as_of = start + timedelta(days=index)
        label = labels[index % 3]
        row_id = f"row-{index:03d}"
        match_id = f"match-{index:03d}"
        rows.append(
            TrainingRow(
                row_id,
                match_id,
                f"competition-{index % 2}",
                f"season-{index // 75}",
                as_of + timedelta(hours=1),
                as_of,
                "v1",
                FeatureProfile.FOOTBALL_PERFORMANCE_ONLY,
                TARGET,
                label,
                (FeatureRecord("signal", Decimal(index % 3), as_of, "v1", PROVENANCE),),
                DatasetRowProvenance("synthetic"),
                RowStatus.READY,
            )
        )
        poisson_values = {
            Selection.HOME: ("0.55", "0.25", "0.20"),
            Selection.DRAW: ("0.25", "0.50", "0.25"),
            Selection.AWAY: ("0.20", "0.25", "0.55"),
        }[label]
        poisson = ProbabilityModelPrediction(
            row_id,
            match_id,
            as_of,
            "POISSON",
            "poisson_v1",
            ML_CLASS_ORDER,
            tuple(
                MLClassProbability(selection, Decimal(value))
                for selection, value in zip(ML_CLASS_ORDER, poisson_values, strict=True)
            ),
        )
        direction = (
            DirectionalPreference.HOME
            if label is Selection.HOME
            else DirectionalPreference.AWAY
            if label is Selection.AWAY
            else DirectionalPreference.NEUTRAL
        )
        evidence.append(
            EnsembleModelEvidence(
                row_id,
                match_id,
                as_of,
                poisson,
                _signal(ModelFamily.ELO, match_id, direction),
                _signal(ModelFamily.FORM, match_id, direction),
            )
        )
    dataset = MLDataset(
        "v1",
        "v1",
        FeatureProfile.FOOTBALL_PERFORMANCE_ONLY,
        (TARGET,),
        tuple(rows),
        (),
        150,
        150,
        0,
        0,
        0,
        0,
        0,
        DatasetStatus.READY,
    )
    return dataset, tuple(evidence)


def _result():
    dataset, evidence = _inputs()
    return evaluate_temporal_ensemble(
        dataset,
        evidence,
        training_config=MLTrainingConfig(
            minimum_training_samples=15, minimum_class_samples=2, epochs=5
        ),
        ensemble_config=EnsembleConfig(minimum_weight_evidence=10),
        walk_forward_config=WalkForwardConfig(
            strategy=SplitStrategy.EXPANDING,
            training_window=timedelta(days=45),
            test_window=timedelta(days=15),
            step_size=timedelta(days=15),
            minimum_training_samples=15,
            minimum_test_samples=5,
        ),
    )


def test_models_align_on_identical_match_asof_and_target_rows() -> None:
    result = _result()
    assert result.raw_ml_rows == result.matched_rows
    assert result.excluded_rows == 0
    assert result.temporal_ensemble_rows < result.matched_rows


def test_first_fold_has_explicit_insufficient_past_evidence() -> None:
    first_ready_outer = next(fold for fold in _result().fold_results if fold.matched_rows)
    assert first_ready_outer.status is EnsembleStatus.INSUFFICIENT_ENSEMBLE_SUPPORT
    assert first_ready_outer.diagnostics


def test_future_weights_use_only_prior_oos_evidence() -> None:
    ready = tuple(fold for fold in _result().fold_results if fold.status is EnsembleStatus.READY)
    assert ready
    assert all(fold.prior_weight_evidence > 0 for fold in ready)


def test_comparable_metrics_have_identical_denominators() -> None:
    result = _result()
    metrics = result.comparable_metrics
    assert metrics.sample_count == result.temporal_ensemble_rows
    assert metrics.ml.sample_count == metrics.poisson.sample_count == metrics.ensemble.sample_count


def test_static_benchmarks_include_required_weights() -> None:
    assert tuple(item.ml_weight for item in _result().static_benchmarks) == tuple(
        map(Decimal, ("0", "0.25", "0.5", "0.75", "1"))
    )


def test_evaluation_is_deterministic() -> None:
    assert _result().to_dict() == _result().to_dict()


def test_competition_season_and_class_diagnostics_are_canonical() -> None:
    result = _result()
    assert tuple(scope for scope, _ in result.competition_breakdown) == (
        "competition-0",
        "competition-1",
    )
    assert tuple(scope for scope, _ in result.season_breakdown) == ("season-0", "season-1")
    assert tuple(item.class_label for item in result.class_diagnostics) == (
        "home",
        "draw",
        "away",
    )


def test_elo_form_remain_signal_diagnostics_not_probabilities() -> None:
    _, evidence = _inputs()
    assert all(item.elo.probability is None and item.form.probability is None for item in evidence)
    neutral = tuple(
        item for item in evidence if item.elo.direction is DirectionalPreference.NEUTRAL
    )
    assert neutral and all(item.elo.selection is None for item in neutral)
    states = {(item.dimension, item.state) for item in _result().agreement_diagnostics}
    assert ("ELO", "NEUTRAL") in states and ("FORM", "NEUTRAL") in states


def test_train_prior_is_reported_but_not_ensemble_acceptance_target() -> None:
    result = _result()
    assert result.train_prior_metrics.sample_count == result.temporal_ensemble_rows
    assert result.preferred_probability_model in {
        "RAW ML",
        "RAW POISSON",
        "ACCEPTED ENSEMBLE",
    }
