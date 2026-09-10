from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pitchvalue.ml import (
    ML_CLASS_ORDER,
    FeatureKind,
    FeatureProfile,
    FeatureProvenance,
    FeatureRecord,
    MarketFeatureSemantics,
    MissingReason,
    MLDatasetValidationError,
    MLTrainingConfig,
    RowStatus,
    TrainingRow,
    fit_multinomial_logistic,
    fit_preprocessor,
    predict_multinomial_logistic,
    transform_rows,
)
from pitchvalue.ml.baseline import train_prior_probabilities
from pitchvalue.ml.contracts import TargetDefinition, TargetMode
from pitchvalue.ml.provenance import DatasetRowProvenance
from pitchvalue.prediction.contracts import MarketFamily, Selection

TARGET = TargetDefinition(
    MarketFamily.MATCH_RESULT,
    TargetMode.MULTICLASS,
    (Selection.HOME, Selection.DRAW, Selection.AWAY),
)
PROVENANCE = FeatureProvenance("v1", "test", "synthetic-v1", "calculation-v1")


def _row(index: int, target: Selection, value: Decimal | None = None) -> TrainingRow:
    kickoff = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index)
    feature = FeatureRecord(
        "strength_difference",
        value if value is not None else Decimal(index % 7 - 3),
        kickoff - timedelta(days=1),
        "v1",
        PROVENANCE,
        FeatureKind.FOOTBALL_PERFORMANCE,
    )
    return TrainingRow(
        f"row-{index:04d}",
        f"match-{index:04d}",
        "competition",
        "season",
        kickoff,
        kickoff - timedelta(days=1),
        "v1",
        FeatureProfile.FOOTBALL_PERFORMANCE_ONLY,
        TARGET,
        target,
        (feature,),
        DatasetRowProvenance("synthetic-v1"),
        RowStatus.READY,
    )


def _training_rows() -> tuple[TrainingRow, ...]:
    labels = (Selection.HOME, Selection.DRAW, Selection.AWAY)
    return tuple(_row(index, labels[index % 3]) for index in range(30))


def test_training_config_is_valid_immutable_and_deterministic() -> None:
    config = MLTrainingConfig(minimum_training_samples=3, epochs=2)
    assert config.feature_profile is FeatureProfile.FOOTBALL_PERFORMANCE_ONLY
    assert config.to_dict() == config.to_dict()
    with pytest.raises(FrozenInstanceError):
        config.epochs = 3  # type: ignore[misc]


@pytest.mark.parametrize("field,value", [("minimum_training_samples", 0), ("epochs", 0)])
def test_training_config_rejects_invalid_integer(field: str, value: int) -> None:
    values = {field: value}
    with pytest.raises(MLDatasetValidationError):
        MLTrainingConfig(**values)  # type: ignore[arg-type]


def test_training_config_rejects_odds_profile() -> None:
    with pytest.raises(MLDatasetValidationError, match="FOOTBALL_PERFORMANCE_ONLY"):
        MLTrainingConfig(feature_profile=FeatureProfile.ODDS_INCLUSIVE_EXPERIMENT)


def test_preprocessor_fits_only_supplied_training_rows() -> None:
    train = _training_rows()[:20]
    test = (_row(99, Selection.HOME, Decimal("9999")),)
    fitted = fit_preprocessor(train)
    before = fitted.to_dict()
    transform_rows(fitted, test)
    assert fitted.to_dict() == before
    assert fitted.fitted_row_ids == tuple(row.row_id for row in train)


def test_preprocessor_uses_train_mean_and_missing_indicator() -> None:
    present = _row(0, Selection.HOME, Decimal("2"))
    base = _row(1, Selection.DRAW, Decimal("4"))
    missing_feature = FeatureRecord(
        "strength_difference",
        None,
        base.prediction_as_of,
        "v1",
        PROVENANCE,
        missing_reason=MissingReason.INSUFFICIENT_HISTORY,
    )
    missing = TrainingRow(**{**base.__dict__, "features": (missing_feature,)})
    fitted = fit_preprocessor((present, base))
    transformed = transform_rows(fitted, (missing,))[0]
    assert transformed == (0.0, 1.0)


def test_feature_column_and_row_order_are_deterministic() -> None:
    rows = _training_rows()
    first = fit_preprocessor(rows)
    second = fit_preprocessor(tuple(reversed(rows)))
    assert first == second


def test_odds_feature_is_structurally_rejected() -> None:
    row = _row(0, Selection.HOME)
    odds = FeatureRecord(
        "bookmaker_odds",
        Decimal("2.00"),
        row.prediction_as_of,
        "v1",
        PROVENANCE,
        FeatureKind.MARKET_ODDS,
        market_semantics=MarketFeatureSemantics.DECIMAL_ODDS,
    )
    invalid = TrainingRow(**{**row.__dict__, "features": (odds,)})
    with pytest.raises(MLDatasetValidationError):
        fit_preprocessor((invalid,))


@pytest.mark.parametrize("name", ["target", "result", "final_score"])
def test_target_and_post_match_columns_are_rejected(name: str) -> None:
    row = _row(0, Selection.HOME)
    leaking = FeatureRecord(name, Decimal(1), row.prediction_as_of, "v1", PROVENANCE)
    invalid = TrainingRow(**{**row.__dict__, "features": (leaking,)})
    with pytest.raises(MLDatasetValidationError):
        fit_preprocessor((invalid,))


def test_insufficient_training_support_returns_no_model() -> None:
    assert (
        fit_multinomial_logistic(
            _training_rows()[:2], MLTrainingConfig(minimum_training_samples=3, epochs=2)
        )
        is None
    )


def test_missing_class_support_returns_no_model() -> None:
    rows = tuple(_row(index, Selection.HOME) for index in range(6))
    assert (
        fit_multinomial_logistic(rows, MLTrainingConfig(minimum_training_samples=3, epochs=2))
        is None
    )


def test_fit_and_predict_are_reproducible() -> None:
    config = MLTrainingConfig(minimum_training_samples=3, epochs=5)
    rows = _training_rows()
    first = fit_multinomial_logistic(rows, config)
    second = fit_multinomial_logistic(tuple(reversed(rows)), config)
    assert first == second
    assert first is not None
    assert predict_multinomial_logistic(first, rows[:3]) == predict_multinomial_logistic(
        first, rows[:3]
    )


def test_prediction_contract_is_valid_and_uncalibrated() -> None:
    model = fit_multinomial_logistic(
        _training_rows(), MLTrainingConfig(minimum_training_samples=3, epochs=3)
    )
    assert model is not None
    prediction = predict_multinomial_logistic(model, (_training_rows()[0],))[0]
    assert prediction.class_order == ML_CLASS_ORDER
    assert sum((item.probability for item in prediction.probabilities), Decimal(0)) == Decimal(1)
    assert all(Decimal(0) <= item.probability <= Decimal(1) for item in prediction.probabilities)
    assert prediction.to_dict()["probability_semantics"] == "UNCALIBRATED ML PROBABILITY"


def test_train_prior_uses_train_labels_only() -> None:
    rows = (
        _row(0, Selection.HOME),
        _row(1, Selection.HOME),
        _row(2, Selection.DRAW),
        _row(3, Selection.AWAY),
    )
    prior = train_prior_probabilities(rows)
    assert tuple(item.selection for item in prior) == ML_CLASS_ORDER
    assert tuple(item.probability for item in prior) == (
        Decimal("0.5"),
        Decimal("0.25"),
        Decimal("0.25"),
    )


def test_train_prior_is_order_invariant() -> None:
    rows = _training_rows()
    assert train_prior_probabilities(rows) == train_prior_probabilities(tuple(reversed(rows)))


@pytest.mark.parametrize(
    "values",
    [
        {"learning_rate": Decimal("0")},
        {"learning_rate": Decimal("NaN")},
        {"l2_strength": Decimal("-0.1")},
        {"random_seed": True},
    ],
)
def test_training_config_rejects_invalid_numeric_values(values: dict[str, object]) -> None:
    with pytest.raises(MLDatasetValidationError):
        MLTrainingConfig(**values)  # type: ignore[arg-type]


def test_preprocessor_rejects_schema_order_mismatch() -> None:
    rows = _training_rows()
    fitted = fit_preprocessor(rows)
    base = rows[0]
    extra = FeatureRecord("other", Decimal(1), base.prediction_as_of, "v1", PROVENANCE)
    invalid = TrainingRow(**{**base.__dict__, "features": (extra,)})
    with pytest.raises(MLDatasetValidationError, match="schema"):
        transform_rows(fitted, (invalid,))


def test_preprocessed_values_are_finite() -> None:
    rows = _training_rows()
    fitted = fit_preprocessor(rows)
    assert all(
        value == value and abs(value) != float("inf")
        for row in transform_rows(fitted, rows)
        for value in row
    )


def test_model_metadata_preserves_training_cutoff_and_support() -> None:
    rows = _training_rows()
    model = fit_multinomial_logistic(rows, MLTrainingConfig(minimum_training_samples=3, epochs=2))
    assert model is not None
    assert model.training_support == len(rows)
    assert model.trained_through == max(row.prediction_as_of for row in rows)
    assert model.config.model_version == "multinomial_logistic_v1"
