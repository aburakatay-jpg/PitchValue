from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pitchvalue.evaluation import SplitStrategy, WalkForwardConfig
from pitchvalue.ml import (
    DatasetStatus,
    FeatureProfile,
    FeatureProvenance,
    FeatureRecord,
    MLDataset,
    MLEvaluationResult,
    MLTrainingConfig,
    RowStatus,
    TrainingRow,
    evaluate_walk_forward_ml,
)
from pitchvalue.ml.contracts import TargetDefinition, TargetMode
from pitchvalue.ml.provenance import DatasetRowProvenance
from pitchvalue.prediction.contracts import MarketFamily, Selection

TARGET = TargetDefinition(
    MarketFamily.MATCH_RESULT,
    TargetMode.MULTICLASS,
    (Selection.HOME, Selection.DRAW, Selection.AWAY),
)
PROVENANCE = FeatureProvenance("v1", "test", "synthetic", "calculation")


def _dataset() -> MLDataset:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    rows = []
    labels = (Selection.HOME, Selection.DRAW, Selection.AWAY)
    for index in range(90):
        as_of = start + timedelta(days=index)
        label = labels[index % 3]
        feature = FeatureRecord(
            "signal",
            Decimal(index % 3),
            as_of,
            "v1",
            PROVENANCE,
        )
        rows.append(
            TrainingRow(
                f"row-{index:03d}",
                f"match-{index:03d}",
                f"competition-{index % 2}",
                f"season-{index // 60}",
                as_of + timedelta(hours=1),
                as_of,
                "v1",
                FeatureProfile.FOOTBALL_PERFORMANCE_ONLY,
                TARGET,
                label,
                (feature,),
                DatasetRowProvenance("synthetic"),
                RowStatus.READY,
            )
        )
    return MLDataset(
        "v1",
        "v1",
        FeatureProfile.FOOTBALL_PERFORMANCE_ONLY,
        (TARGET,),
        tuple(rows),
        (),
        90,
        90,
        0,
        0,
        0,
        0,
        0,
        DatasetStatus.READY,
    )


def _result() -> MLEvaluationResult:
    return evaluate_walk_forward_ml(
        _dataset(),
        complete_rows=90,
        partial_rows=0,
        unavailable_rows=0,
        training_config=MLTrainingConfig(minimum_training_samples=15, epochs=5),
        walk_forward_config=WalkForwardConfig(
            strategy=SplitStrategy.EXPANDING,
            training_window=timedelta(days=30),
            test_window=timedelta(days=15),
            step_size=timedelta(days=15),
            minimum_training_samples=15,
            minimum_test_samples=5,
        ),
    )


def test_walk_forward_uses_task13_and_produces_oos_only_metrics() -> None:
    result = _result()
    assert result.oos_prediction_count > 0
    assert result.ml_metrics.sample_count == result.oos_prediction_count
    assert result.train_prior_metrics.sample_count == result.oos_prediction_count
    assert all(fold.train_end <= fold.test_start for fold in result.fold_results)


def test_walk_forward_reports_every_fold_and_support() -> None:
    result = _result()
    assert result.fold_results
    assert all(len(fold.class_support) == 3 for fold in result.fold_results)
    assert all(fold.train_rows >= 0 and fold.test_rows >= 0 for fold in result.fold_results)


def test_walk_forward_is_deterministic() -> None:
    assert _result().to_dict() == _result().to_dict()


def test_breakdowns_are_deterministically_ordered() -> None:
    result = _result()
    assert tuple(item.scope for item in result.competition_breakdown) == (
        "competition-0",
        "competition-1",
    )
    assert tuple(item.scope for item in result.season_breakdown) == tuple(
        sorted(item.scope for item in result.season_breakdown)
    )


def test_random_split_is_not_part_of_evaluation_result() -> None:
    serialized = str(_result().to_dict()).lower()
    assert "random_split" not in serialized
    assert "shuffle" not in serialized


def test_fold_test_labels_do_not_affect_training_prior() -> None:
    result = _result()
    first_ready = next(item for item in result.fold_results if item.ml_metrics is not None)
    assert first_ready.train_prior_metrics is not None
    assert first_ready.train_prior_metrics.sample_count == first_ready.test_rows


def test_insufficient_windows_are_reported_not_hidden() -> None:
    result = evaluate_walk_forward_ml(
        _dataset(),
        complete_rows=90,
        partial_rows=0,
        unavailable_rows=0,
        training_config=MLTrainingConfig(minimum_training_samples=100, epochs=2),
        walk_forward_config=WalkForwardConfig(
            training_window=timedelta(days=30),
            test_window=timedelta(days=15),
            step_size=timedelta(days=15),
            minimum_training_samples=100,
            minimum_test_samples=5,
        ),
    )
    assert result.fold_results
    assert result.oos_prediction_count == 0
    assert all(fold.skipped_reason is not None for fold in result.fold_results)


def test_class_distribution_uses_explicit_home_draw_away_order() -> None:
    assert tuple(label for label, _ in _result().class_distribution) == ("home", "draw", "away")


def test_probability_metrics_remain_uncalibrated_diagnostics() -> None:
    serialized = _result().to_dict()
    assert serialized["probability_semantics"] == "UNCALIBRATED ML PROBABILITY"
    assert serialized["ml_metrics"]["macro_ece"] is not None
