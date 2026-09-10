from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import pitchvalue.ml.calibration_evaluation as evaluation_module
from pitchvalue.evaluation import SplitStrategy, WalkForwardConfig
from pitchvalue.ml import (
    CalibrationCandidateDecision,
    CalibrationStatus,
    DatasetStatus,
    FeatureProfile,
    FeatureProvenance,
    FeatureRecord,
    MLDataset,
    MLTrainingConfig,
    NestedCalibrationConfig,
    RowStatus,
    TemperatureScalingConfig,
    TrainingRow,
    evaluate_nested_temperature_scaling,
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
    labels = (Selection.HOME, Selection.DRAW, Selection.AWAY)
    rows = []
    for index in range(150):
        as_of = start + timedelta(days=index)
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
                f"season-{index // 75}",
                as_of + timedelta(hours=1),
                as_of,
                "v1",
                FeatureProfile.FOOTBALL_PERFORMANCE_ONLY,
                TARGET,
                labels[index % 3],
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
        150,
        150,
        0,
        0,
        0,
        0,
        0,
        DatasetStatus.READY,
    )


def _result(minimum_calibration_samples: int = 6):
    return evaluate_nested_temperature_scaling(
        _dataset(),
        training_config=MLTrainingConfig(
            minimum_training_samples=15,
            minimum_class_samples=2,
            epochs=5,
        ),
        calibration_config=NestedCalibrationConfig(
            calibration_window=timedelta(days=15),
            temperature=TemperatureScalingConfig(
                minimum_calibration_samples=minimum_calibration_samples,
                minimum_class_samples=1,
                optimization_iterations=20,
            ),
        ),
        walk_forward_config=WalkForwardConfig(
            strategy=SplitStrategy.EXPANDING,
            training_window=timedelta(days=45),
            test_window=timedelta(days=15),
            step_size=timedelta(days=15),
            minimum_training_samples=15,
            minimum_test_samples=5,
        ),
    )


def test_nested_periods_are_strictly_chronological() -> None:
    ready = tuple(item for item in _result().fold_results if item.status is CalibrationStatus.READY)
    assert ready
    assert all(item.base_train_end == item.calibration_start for item in ready)
    assert all(item.calibration_end <= item.test_start for item in ready)


def test_raw_and_calibrated_metrics_use_identical_oos_rows() -> None:
    result = _result()
    assert result.calibratable_oos_rows > 0
    assert result.raw_metrics.sample_count == result.calibratable_oos_rows
    assert result.calibrated_metrics.sample_count == result.calibratable_oos_rows
    for fold in result.fold_results:
        if fold.status is CalibrationStatus.READY:
            assert fold.raw_metrics is not None and fold.calibrated_metrics is not None
            assert fold.raw_metrics.sample_count == fold.calibrated_metrics.sample_count


def test_temperature_scaling_preserves_supporting_accuracy() -> None:
    result = _result()
    assert result.raw_metrics.accuracy == result.calibrated_metrics.accuracy


def test_evaluation_is_deterministic() -> None:
    assert _result().to_dict() == _result().to_dict()


def test_skipped_folds_and_excluded_rows_are_explicit() -> None:
    result = _result(minimum_calibration_samples=1000)
    assert result.calibratable_oos_rows == 0
    assert result.excluded_oos_rows == result.raw_oos_rows
    assert all(item.status is not CalibrationStatus.READY for item in result.fold_results)
    assert all(item.diagnostics for item in result.fold_results)
    assert result.decision is CalibrationCandidateDecision.INCONCLUSIVE


def test_global_calibrator_has_diagnostic_only_competition_and_season_slices() -> None:
    result = _result()
    assert tuple(item.scope for item in result.competition_breakdown) == (
        "competition-0",
        "competition-1",
    )
    assert tuple(item.scope for item in result.season_breakdown) == (
        "season-0",
        "season-1",
    )
    assert all(item.sample_count > 0 for item in result.competition_breakdown)


def test_class_comparison_is_canonical_home_draw_away() -> None:
    result = _result()
    assert tuple(item.class_label for item in result.class_comparison) == (
        "home",
        "draw",
        "away",
    )
    assert all(
        item.sample_count == result.calibratable_oos_rows for item in result.class_comparison
    )


def test_calibrator_fit_cutoff_precedes_every_ready_test_period() -> None:
    ready = tuple(item for item in _result().fold_results if item.status is CalibrationStatus.READY)
    assert all(item.calibration_end <= item.test_start for item in ready)
    assert all(item.base_train_rows > 0 and item.calibration_rows > 0 for item in ready)


def test_calibrator_fit_examples_never_include_outer_test_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_cutoffs: list[datetime] = []
    original = evaluation_module.fit_temperature_scaling

    def capture(examples, config):  # type: ignore[no-untyped-def]
        captured_cutoffs.append(max(item.prediction.prediction_as_of for item in examples))
        return original(examples, config)

    monkeypatch.setattr(evaluation_module, "fit_temperature_scaling", capture)
    result = _result()
    ready = tuple(item for item in result.fold_results if item.status is CalibrationStatus.READY)
    assert len(captured_cutoffs) == len(ready)
    assert all(
        cutoff < fold.test_start for cutoff, fold in zip(captured_cutoffs, ready, strict=True)
    )


def test_serialized_result_separates_raw_and_calibrated_semantics() -> None:
    serialized = _result().to_dict()
    assert serialized["probability_semantics"] == {
        "raw": "UNCALIBRATED ML PROBABILITY",
        "calibrated": "CALIBRATED ML PROBABILITY",
    }
    lowered = str(serialized).lower()
    assert "bookmaker" not in lowered
    assert "random_split" not in lowered
    assert "ensemble" not in lowered
