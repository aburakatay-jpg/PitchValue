from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pitchvalue.evaluation import (
    BoundaryPolicy,
    EvaluationProvenance,
    EvaluationTarget,
    EvaluationValidationError,
    OddsUse,
    PredictionEvaluationRecord,
    SplitStrategy,
    TemporalObservation,
    WalkForwardConfig,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def test_default_expanding_config_is_valid() -> None:
    config = WalkForwardConfig()
    assert config.strategy is SplitStrategy.EXPANDING
    assert config.boundary_policy is BoundaryPolicy.HALF_OPEN


def test_rolling_config_is_valid() -> None:
    assert WalkForwardConfig(strategy=SplitStrategy.ROLLING).strategy is SplitStrategy.ROLLING


def test_config_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        WalkForwardConfig().minimum_training_samples = 4  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("training_window", timedelta(0)),
        ("training_window", timedelta(days=-1)),
        ("test_window", timedelta(0)),
        ("test_window", timedelta(days=-1)),
        ("step_size", timedelta(0)),
        ("step_size", timedelta(days=-1)),
        ("embargo", timedelta(seconds=-1)),
        ("minimum_training_samples", 0),
        ("minimum_training_samples", -1),
        ("minimum_test_samples", 0),
        ("minimum_test_samples", -1),
    ],
)
def test_invalid_config_values_are_rejected(field: str, value: object) -> None:
    with pytest.raises(EvaluationValidationError):
        WalkForwardConfig(**{field: value})  # type: ignore[arg-type]


def test_unknown_strategy_is_rejected() -> None:
    with pytest.raises(EvaluationValidationError):
        WalkForwardConfig(strategy="RANDOM")  # type: ignore[arg-type]


def test_config_serialization_is_deterministic() -> None:
    config = WalkForwardConfig(embargo=timedelta(hours=12))
    assert config.to_dict() == config.to_dict()
    assert config.to_dict()["embargo_seconds"] == 43200.0


def test_timezone_aware_target_is_accepted_and_serialized() -> None:
    target = _target()
    assert target.to_dict()["prediction_as_of"] == "2026-01-01T09:00:00+00:00"


@pytest.mark.parametrize("field", ["kickoff", "prediction_as_of"])
def test_naive_target_timestamp_is_rejected(field: str) -> None:
    values = {
        "match_id": "target",
        "competition_id": "comp",
        "season_id": "season",
        "kickoff": BASE + timedelta(hours=12),
        "prediction_as_of": BASE + timedelta(hours=9),
    }
    timestamp = values[field]
    assert isinstance(timestamp, datetime)
    values[field] = timestamp.replace(tzinfo=None)
    with pytest.raises(EvaluationValidationError):
        EvaluationTarget(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("offset", [12, 13])
def test_as_of_equal_to_or_after_kickoff_is_rejected(offset: int) -> None:
    with pytest.raises(EvaluationValidationError):
        EvaluationTarget(
            "target", "comp", "season", BASE + timedelta(hours=12), BASE + timedelta(hours=offset)
        )


def test_observation_preserves_scope_availability_and_market() -> None:
    row = _observation()
    assert row.available_at == BASE + timedelta(hours=3)
    assert row.market is MarketFamily.TOTAL_GOALS
    assert row.selection is Selection.OVER
    assert row.line == Decimal("2.50")


def test_observation_requires_aware_timestamps() -> None:
    with pytest.raises(EvaluationValidationError):
        _observation(available_at=BASE.replace(tzinfo=None))


def test_observation_contract_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        _observation().match_id = "changed"  # type: ignore[misc]


def test_outcome_truth_is_separate_from_prediction_reference() -> None:
    record = _record(outcome_reference="HOME", outcome_available_at=BASE + timedelta(hours=13))
    assert record.prediction_reference == "prediction-blob"
    assert record.outcome_reference == "HOME"


def test_outcome_fields_must_be_supplied_together() -> None:
    with pytest.raises(EvaluationValidationError):
        _record(outcome_reference="HOME")


def test_provenance_preserves_versions_and_sources() -> None:
    provenance = EvaluationProvenance("ensemble", "1.2", "features-v3", ("feed-a",))
    assert provenance.to_dict()["source_ids"] == ["feed-a"]


def test_market_scope_is_not_one_x_two_only() -> None:
    target = _target(market=MarketFamily.BTTS, selection=Selection.YES)
    assert target.market is MarketFamily.BTTS


def test_selection_requires_market() -> None:
    with pytest.raises(EvaluationValidationError):
        _target(selection=Selection.HOME)


def test_line_must_be_finite_decimal() -> None:
    with pytest.raises(EvaluationValidationError):
        _target(line=Decimal("NaN"))


def test_odds_use_only_applies_to_odds_observations() -> None:
    with pytest.raises(EvaluationValidationError):
        _observation(odds_use=OddsUse.CLOSING_REFERENCE)


def test_prediction_and_reference_odds_semantics_are_distinct() -> None:
    values = tuple(item.value for item in OddsUse)
    assert len(values) == 3
    assert len(set(values)) == len(values)


def _target(**changes: object) -> EvaluationTarget:
    values: dict[str, object] = {
        "match_id": "target",
        "competition_id": "comp",
        "season_id": "season",
        "kickoff": BASE + timedelta(hours=12),
        "prediction_as_of": BASE + timedelta(hours=9),
    }
    values.update(changes)
    return EvaluationTarget(**values)  # type: ignore[arg-type]


def _observation(**changes: object) -> TemporalObservation:
    values: dict[str, object] = {
        "observation_id": "obs-1",
        "match_id": "match-1",
        "competition_id": "comp",
        "season_id": "season",
        "kickoff": BASE,
        "available_at": BASE + timedelta(hours=3),
        "market": MarketFamily.TOTAL_GOALS,
        "selection": Selection.OVER,
        "line": Decimal("2.50"),
    }
    values.update(changes)
    return TemporalObservation(**values)  # type: ignore[arg-type]


def _record(**changes: object) -> PredictionEvaluationRecord:
    values: dict[str, object] = {
        "record_id": "record-1",
        "target": _target(),
        "fold_id": "fold-0001",
        "provenance": EvaluationProvenance("model", "v1"),
        "prediction_reference": "prediction-blob",
    }
    values.update(changes)
    return PredictionEvaluationRecord(**values)  # type: ignore[arg-type]
