from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from pitchvalue.evaluation.metrics import (
    BinaryPrediction,
    ClassProbability,
    MetricConfig,
    MetricProvenance,
    MetricValidationError,
    MulticlassPrediction,
    PredictionRecordStatus,
    ProbabilitySemantics,
)


def test_default_config_is_valid() -> None:
    config = MetricConfig()
    assert config.bucket_edges[0] == Decimal(0)
    assert config.bucket_edges[-1] == Decimal(1)


def test_config_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        MetricConfig().minimum_total_samples = 5  # type: ignore[misc]


def test_valid_custom_epsilon() -> None:
    assert MetricConfig(log_loss_epsilon=Decimal("0.001")).log_loss_epsilon == Decimal("0.001")


@pytest.mark.parametrize(
    "epsilon",
    [Decimal(0), Decimal("-0.1"), Decimal("0.5"), Decimal(1), Decimal("NaN"), Decimal("Infinity")],
)
def test_invalid_epsilon_rejected(epsilon: Decimal) -> None:
    with pytest.raises(MetricValidationError):
        MetricConfig(log_loss_epsilon=epsilon)


@pytest.mark.parametrize(
    "edges",
    [
        (Decimal("0"),),
        (Decimal("0.1"), Decimal("1")),
        (Decimal("0"), Decimal("0.9")),
        (Decimal("0"), Decimal("0.5"), Decimal("0.4"), Decimal("1")),
        (Decimal("0"), Decimal("0.5"), Decimal("0.5"), Decimal("1")),
        (Decimal("-0.1"), Decimal("1")),
        (Decimal("0"), Decimal("1.1"), Decimal("1")),
        (Decimal("0"), Decimal("NaN"), Decimal("1")),
    ],
)
def test_invalid_bucket_edges_rejected(edges: tuple[Decimal, ...]) -> None:
    with pytest.raises(MetricValidationError):
        MetricConfig(bucket_edges=edges)


def test_custom_bucket_edges_preserved() -> None:
    edges = (Decimal(0), Decimal("0.25"), Decimal("0.75"), Decimal(1))
    assert MetricConfig(bucket_edges=edges).bucket_edges == edges


@pytest.mark.parametrize("field", ["minimum_total_samples", "minimum_bucket_samples"])
@pytest.mark.parametrize("value", [0, -1, True])
def test_invalid_minimum_samples_rejected(field: str, value: int) -> None:
    with pytest.raises(MetricValidationError):
        MetricConfig(**{field: value})  # type: ignore[arg-type]


def test_config_serialization_is_deterministic() -> None:
    config = MetricConfig()
    assert config.to_dict() == config.to_dict()
    assert config.to_dict()["bucket_edges"][5] == "0.5"


@pytest.mark.parametrize("probability", [Decimal(0), Decimal("0.5"), Decimal(1)])
def test_valid_binary_probability_contract(probability: Decimal) -> None:
    assert BinaryPrediction("p", probability, 1).probability == probability


@pytest.mark.parametrize(
    "probability", [Decimal("-0.1"), Decimal("1.1"), Decimal("NaN"), Decimal("Infinity")]
)
def test_invalid_binary_probability_rejected(probability: Decimal) -> None:
    with pytest.raises(MetricValidationError):
        BinaryPrediction("p", probability, 1)


@pytest.mark.parametrize("probability", [0.5, "0.5", None])
def test_non_decimal_or_missing_ready_probability_rejected(probability: object) -> None:
    with pytest.raises(MetricValidationError):
        BinaryPrediction("p", probability, 1)  # type: ignore[arg-type]


@pytest.mark.parametrize("outcome", [-1, 2, True, "1", None])
def test_invalid_binary_outcome_rejected(outcome: object) -> None:
    with pytest.raises(MetricValidationError):
        BinaryPrediction("p", Decimal("0.5"), outcome)  # type: ignore[arg-type]


@pytest.mark.parametrize("semantics", ["ELO_EXPECTATION", "FORM_STRENGTH", "SIGNAL_STRENGTH", None])
def test_ambiguous_non_probability_semantics_rejected(semantics: object) -> None:
    with pytest.raises(MetricValidationError):
        BinaryPrediction("p", Decimal("0.6"), 1, semantics=semantics)  # type: ignore[arg-type]


def test_missing_prediction_is_explicit() -> None:
    record = BinaryPrediction("p", None, 1, PredictionRecordStatus.MISSING_PREDICTION, None)
    assert record.status is PredictionRecordStatus.MISSING_PREDICTION


def test_missing_outcome_is_explicit() -> None:
    record = BinaryPrediction("p", Decimal("0.7"), None, PredictionRecordStatus.MISSING_OUTCOME)
    assert record.status is PredictionRecordStatus.MISSING_OUTCOME


def test_duplicate_multiclass_labels_rejected() -> None:
    with pytest.raises(MetricValidationError, match="duplicate"):
        _multi((("HOME", "0.5"), ("HOME", "0.5")), "HOME")


def test_empty_multiclass_vector_rejected() -> None:
    with pytest.raises(MetricValidationError):
        MulticlassPrediction("p", (), "HOME")


def test_single_class_vector_rejected() -> None:
    with pytest.raises(MetricValidationError):
        _multi((("HOME", "1"),), "HOME")


def test_observed_class_must_be_in_domain() -> None:
    with pytest.raises(MetricValidationError):
        _multi((("HOME", "0.5"), ("AWAY", "0.5")), "DRAW")


def test_multiclass_order_is_canonical() -> None:
    record = _multi((("AWAY", "0.2"), ("HOME", "0.6"), ("DRAW", "0.2")), "HOME")
    assert [item.label for item in record.probabilities] == ["HOME", "DRAW", "AWAY"]


def test_probability_contract_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        BinaryPrediction("p", Decimal("0.5"), 1).probability = Decimal("0.4")  # type: ignore[misc]


def test_provenance_preserves_scope() -> None:
    provenance = MetricProvenance(
        "fold-1", "poisson", "v1", "comp", "season", "btts", "YES", Decimal("2.5")
    )
    assert provenance.to_dict() == {
        "fold_id": "fold-1",
        "model_name": "poisson",
        "model_version": "v1",
        "competition_id": "comp",
        "season_id": "season",
        "market": "btts",
        "class_scope": "YES",
        "line": "2.5",
    }


def test_probability_semantics_are_explicit() -> None:
    assert tuple(ProbabilitySemantics) == (
        ProbabilitySemantics.MODEL_PROBABILITY,
        ProbabilitySemantics.CALIBRATED_PROBABILITY,
    )


def _multi(values: tuple[tuple[str, str], ...], observed: str) -> MulticlassPrediction:
    return MulticlassPrediction(
        "p", tuple(ClassProbability(label, Decimal(value)) for label, value in values), observed
    )
