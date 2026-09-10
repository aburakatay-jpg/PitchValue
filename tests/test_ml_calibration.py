from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import nan
from pathlib import Path

import pytest

from pitchvalue.ml import (
    ML_CLASS_ORDER,
    CalibrationFitExample,
    CalibrationStatus,
    FittedTemperatureCalibrator,
    MLClassProbability,
    MLDatasetValidationError,
    MLModelStatus,
    MLPrediction,
    TemperatureScalingConfig,
    apply_temperature_scaling,
    fit_temperature_scaling,
)
from pitchvalue.prediction.contracts import Selection


def _prediction(
    index: int = 0,
    *,
    logits: tuple[float, float, float] = (2.0, 1.0, 0.0),
    status: MLModelStatus = MLModelStatus.READY,
) -> MLPrediction:
    as_of = datetime(2025, 1, 2, tzinfo=UTC) + timedelta(days=index)
    return MLPrediction(
        f"row-{index:03d}",
        "MULTINOMIAL_LOGISTIC",
        "multinomial_logistic_v1",
        "FOOTBALL_PERFORMANCE_ONLY",
        as_of - timedelta(days=1),
        as_of,
        ML_CLASS_ORDER,
        (
            MLClassProbability(Selection.HOME, Decimal("0.665240955774822")),
            MLClassProbability(Selection.DRAW, Decimal("0.244728471054798")),
            MLClassProbability(Selection.AWAY, Decimal("0.090030573170380")),
        ),
        logits,
        status,
        (),
        "v1",
        100,
    )


def _calibrator(temperature: str = "1") -> FittedTemperatureCalibrator:
    return FittedTemperatureCalibrator(
        "TEMPERATURE_SCALING",
        "temperature_scaling_v1",
        "multinomial_logistic_v1",
        "FOOTBALL_PERFORMANCE_ONLY",
        ML_CLASS_ORDER,
        Decimal(temperature),
        30,
        ((Selection.HOME, 10), (Selection.DRAW, 10), (Selection.AWAY, 10)),
        datetime(2025, 1, 1, tzinfo=UTC),
        CalibrationStatus.READY,
        (),
    )


def _fit_examples() -> tuple[CalibrationFitExample, ...]:
    labels = (Selection.HOME, Selection.DRAW, Selection.AWAY)
    logits = ((2.0, 1.0, 0.0), (0.0, 2.0, 1.0), (1.0, 0.0, 2.0))
    return tuple(
        CalibrationFitExample(_prediction(index, logits=logits[index % 3]), labels[index % 3])
        for index in range(30)
    )


def test_temperature_config_is_immutable_and_serializes_deterministically() -> None:
    config = TemperatureScalingConfig()
    assert config.to_dict() == config.to_dict()
    with pytest.raises(FrozenInstanceError):
        config.minimum_calibration_samples = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    "values",
    [
        {"minimum_calibration_samples": 0},
        {"minimum_class_samples": 0},
        {"optimization_iterations": 0},
        {"minimum_temperature": Decimal("0")},
        {"maximum_temperature": Decimal("Infinity")},
        {"minimum_temperature": Decimal("2"), "maximum_temperature": Decimal("1")},
    ],
)
def test_temperature_config_rejects_invalid_values(values: dict[str, object]) -> None:
    with pytest.raises(MLDatasetValidationError):
        TemperatureScalingConfig(**values)  # type: ignore[arg-type]


def test_temperature_one_preserves_distribution_and_raw_prediction() -> None:
    raw = _prediction()
    before = raw.to_dict()
    result = apply_temperature_scaling(_calibrator(), (raw,))[0]
    assert tuple(item.probability for item in result.calibrated_probabilities) == tuple(
        item.probability for item in raw.probabilities
    )
    assert raw.to_dict() == before


def test_high_temperature_softens_and_low_temperature_sharpens() -> None:
    raw = _prediction()
    high = apply_temperature_scaling(_calibrator("2"), (raw,))[0]
    low = apply_temperature_scaling(_calibrator("0.5"), (raw,))[0]
    raw_home = raw.probabilities[0].probability
    assert high.calibrated_probabilities[0].probability < raw_home
    assert low.calibrated_probabilities[0].probability > raw_home


def test_fit_is_positive_bounded_and_deterministic() -> None:
    config = TemperatureScalingConfig(
        minimum_calibration_samples=6,
        minimum_class_samples=2,
        optimization_iterations=30,
    )
    first = fit_temperature_scaling(_fit_examples(), config)
    second = fit_temperature_scaling(tuple(reversed(_fit_examples())), config)
    assert first == second
    assert first.status is CalibrationStatus.READY
    assert first.temperature is not None
    assert config.minimum_temperature <= first.temperature <= config.maximum_temperature


def test_insufficient_total_or_class_support_is_explicit() -> None:
    result = fit_temperature_scaling(
        _fit_examples()[:3],
        TemperatureScalingConfig(minimum_calibration_samples=4, minimum_class_samples=1),
    )
    assert result.status is CalibrationStatus.INSUFFICIENT_CALIBRATION_SUPPORT
    assert result.temperature is None
    assert result.diagnostics


def test_invalid_nonfinite_logits_are_rejected_explicitly() -> None:
    invalid = _prediction(logits=(nan, 0.0, 0.0), status=MLModelStatus.INVALID_FEATURES)
    examples = tuple(
        CalibrationFitExample(invalid, label)
        for label in (Selection.HOME, Selection.DRAW, Selection.AWAY)
    )
    result = fit_temperature_scaling(
        examples,
        TemperatureScalingConfig(minimum_calibration_samples=3, minimum_class_samples=1),
    )
    assert result.status is CalibrationStatus.INVALID_RAW_PROBABILITY


def test_calibrated_contract_preserves_metadata_and_probability_semantics() -> None:
    raw = _prediction()
    result = apply_temperature_scaling(_calibrator("1.5"), (raw,))[0]
    values = tuple(item.probability for item in result.calibrated_probabilities)
    assert result.class_order == ML_CLASS_ORDER
    assert all(value.is_finite() and 0 <= value <= 1 for value in values)
    assert sum(values, Decimal(0)) == Decimal(1)
    assert result.raw_prediction is raw
    serialized = result.to_dict()
    assert serialized["probability_semantics"] == "CALIBRATED ML PROBABILITY"
    assert serialized["raw_prediction"]["probability_semantics"] == ("UNCALIBRATED ML PROBABILITY")


def test_unready_calibrator_cannot_silently_fall_back_to_raw() -> None:
    unready = FittedTemperatureCalibrator(
        **{
            **_calibrator().__dict__,
            "temperature": None,
            "status": CalibrationStatus.INSUFFICIENT_CALIBRATION_SUPPORT,
        }
    )
    with pytest.raises(MLDatasetValidationError, match="not ready"):
        apply_temperature_scaling(unready, (_prediction(),))


def test_same_time_calibrator_is_rejected() -> None:
    raw = _prediction()
    same_time = FittedTemperatureCalibrator(
        **{**_calibrator().__dict__, "trained_through": raw.prediction_as_of}
    )
    with pytest.raises(MLDatasetValidationError, match="strictly before"):
        apply_temperature_scaling(same_time, (raw,))


def test_fit_metadata_preserves_support_versions_profile_and_cutoff() -> None:
    result = fit_temperature_scaling(
        _fit_examples(),
        TemperatureScalingConfig(minimum_calibration_samples=6, minimum_class_samples=2),
    )
    assert result.fit_support == 30
    assert result.base_model_version == "multinomial_logistic_v1"
    assert result.feature_profile == "FOOTBALL_PERFORMANCE_ONLY"
    assert result.class_order == ML_CLASS_ORDER
    assert result.trained_through == max(
        item.prediction.prediction_as_of for item in _fit_examples()
    )


def test_calibration_source_has_no_market_odds_or_ensemble_dependency() -> None:
    import pitchvalue.ml.calibration as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    assert "bookmaker" not in source
    assert "odds_snapshot" not in source
    assert "ensemble" not in source
