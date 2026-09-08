import math
from decimal import Decimal

import pytest

from pitchvalue.evaluation.metrics import (
    BinaryPrediction,
    ClassProbability,
    MetricConfig,
    MetricName,
    MetricStatus,
    MulticlassPrediction,
    PredictionRecordStatus,
    binary_accuracy,
    binary_brier_score,
    binary_log_loss,
    evaluate_binary_probabilities,
    evaluate_multiclass_probabilities,
    multiclass_accuracy,
    multiclass_brier_score,
    multiclass_log_loss,
)


def _binary(probability: str, observed: int, identifier: str = "p") -> BinaryPrediction:
    return BinaryPrediction(identifier, Decimal(probability), observed)


def _multi(
    home: str, draw: str, away: str, observed: str, identifier: str = "p"
) -> MulticlassPrediction:
    return MulticlassPrediction(
        identifier,
        (
            ClassProbability("AWAY", Decimal(away)),
            ClassProbability("HOME", Decimal(home)),
            ClassProbability("DRAW", Decimal(draw)),
        ),
        observed,
    )


@pytest.mark.parametrize(
    ("probability", "observed", "expected"),
    [("1", 1, "0"), ("0", 0, "0"), ("0.5", 1, "0.25"), ("1", 0, "1"), ("0", 1, "1")],
)
def test_binary_brier_known_values(probability: str, observed: int, expected: str) -> None:
    result = binary_brier_score((_binary(probability, observed),))
    assert result.value == Decimal(expected)
    assert result.metric is MetricName.BRIER_BINARY


def test_binary_brier_mean_and_counts() -> None:
    result = binary_brier_score((_binary("0.8", 1, "a"), _binary("0.4", 0, "b")))
    assert result.value == Decimal("0.10")
    assert (result.input_count, result.usable_count, result.excluded_count) == (2, 2, 0)


def test_binary_brier_order_invariant_and_bounded() -> None:
    rows = (_binary("0.9", 1, "a"), _binary("0.2", 0, "b"))
    assert binary_brier_score(rows).value == binary_brier_score(tuple(reversed(rows))).value
    assert Decimal(0) <= binary_brier_score(rows).value <= Decimal(1)  # type: ignore[operator]


def test_empty_binary_metric_is_not_perfect() -> None:
    result = binary_brier_score(())
    assert result.status is MetricStatus.EMPTY_INPUT
    assert result.value is None


def test_single_binary_observation_can_be_mathematical_but_insufficient() -> None:
    result = binary_brier_score((_binary("0.8", 1),), MetricConfig(minimum_total_samples=2))
    assert result.value == Decimal("0.04")
    assert result.status is MetricStatus.INSUFFICIENT_SAMPLE


@pytest.mark.parametrize(("probability", "observed"), [("1", 1), ("0", 0)])
def test_perfect_binary_log_loss_is_effectively_zero(probability: str, observed: int) -> None:
    value = binary_log_loss((_binary(probability, observed),)).value
    assert value is not None and value >= 0 and value < Decimal("1e-12")


def test_half_probability_log_loss() -> None:
    value = binary_log_loss((_binary("0.5", 1),)).value
    assert value is not None and float(value) == pytest.approx(math.log(2))


@pytest.mark.parametrize(
    ("probability", "observed"), [("1", 0), ("0", 1), ("0.999999", 0), ("0.000001", 1)]
)
def test_confidently_wrong_binary_log_loss_is_large(probability: str, observed: int) -> None:
    value = binary_log_loss((_binary(probability, observed),)).value
    assert value is not None and value > Decimal(10)


def test_log_loss_epsilon_does_not_mutate_source() -> None:
    row = _binary("0", 1)
    before = row.to_dict()
    binary_log_loss((row,), MetricConfig(log_loss_epsilon=Decimal("0.001")))
    assert row.to_dict() == before


def test_binary_log_loss_mean_is_order_invariant_and_nonnegative() -> None:
    rows = (_binary("0.8", 1, "a"), _binary("0.4", 0, "b"))
    one = binary_log_loss(rows)
    two = binary_log_loss(tuple(reversed(rows)))
    assert one.value == two.value
    assert one.value is not None and one.value >= 0


@pytest.mark.parametrize(
    ("probability", "observed", "expected"),
    [("0.6", 1, "1"), ("0.6", 0, "0"), ("0.5", 1, "1"), ("0.49", 0, "1")],
)
def test_binary_accuracy_threshold(probability: str, observed: int, expected: str) -> None:
    result = binary_accuracy((_binary(probability, observed),))
    assert result.value == Decimal(expected)
    assert result.metric is MetricName.ACCURACY_BINARY


def test_custom_binary_accuracy_threshold() -> None:
    result = binary_accuracy((_binary("0.6", 0),), MetricConfig(binary_threshold=Decimal("0.7")))
    assert result.value == Decimal(1)


def test_missing_prediction_is_excluded_and_counted() -> None:
    missing = BinaryPrediction("missing", None, 1, PredictionRecordStatus.MISSING_PREDICTION, None)
    result = binary_brier_score((_binary("0.8", 1), missing))
    assert (result.input_count, result.usable_count, result.excluded_count) == (2, 1, 1)
    assert result.value == Decimal("0.04")


def test_all_missing_is_not_reported_as_perfect() -> None:
    missing = BinaryPrediction("missing", None, 1, PredictionRecordStatus.MISSING_PREDICTION, None)
    result = binary_brier_score((missing,))
    assert result.value is None
    assert result.status is MetricStatus.INSUFFICIENT_SAMPLE


@pytest.mark.parametrize("observed", ["HOME", "DRAW", "AWAY"])
def test_perfect_multiclass_brier_is_zero(observed: str) -> None:
    probabilities = {"HOME": "0", "DRAW": "0", "AWAY": "0"}
    probabilities[observed] = "1"
    result = multiclass_brier_score(
        (_multi(probabilities["HOME"], probabilities["DRAW"], probabilities["AWAY"], observed),)
    )
    assert result.value == Decimal(0)


def test_raw_multiclass_brier_formula() -> None:
    result = multiclass_brier_score((_multi("0.6", "0.3", "0.1", "HOME"),))
    assert result.value == Decimal("0.26")


def test_wrong_multiclass_brier_can_approach_raw_maximum_two() -> None:
    assert multiclass_brier_score((_multi("0", "0", "1", "HOME"),)).value == Decimal(2)


def test_balanced_multiclass_brier() -> None:
    third = Decimal(1) / Decimal(3)
    record = MulticlassPrediction(
        "p", tuple(ClassProbability(label, third) for label in ("HOME", "DRAW", "AWAY")), "HOME"
    )
    assert float(multiclass_brier_score((record,)).value) == pytest.approx(2 / 3)  # type: ignore[arg-type]


def test_multiclass_brier_mean_and_order_invariance() -> None:
    rows = (_multi("0.7", "0.2", "0.1", "HOME", "a"), _multi("0.2", "0.2", "0.6", "AWAY", "b"))
    one = multiclass_brier_score(rows)
    two = multiclass_brier_score(tuple(reversed(rows)))
    assert one.value == two.value
    assert one.usable_count == 2


def test_invalid_multiclass_sum_returns_explicit_status_without_renormalizing() -> None:
    record = _multi("0.4", "0.3", "0.2", "HOME")
    before = record.to_dict()
    result = multiclass_brier_score((record,))
    assert result.status is MetricStatus.INVALID_PROBABILITY
    assert result.value is None
    assert record.to_dict() == before


def test_sum_within_tolerance_is_accepted() -> None:
    config = MetricConfig(probability_sum_tolerance=Decimal("0.001"))
    result = multiclass_brier_score((_multi("0.4", "0.3", "0.2995", "HOME"),), config)
    assert result.status is MetricStatus.READY


def test_poisson_residual_vector_is_not_hidden_or_renormalized() -> None:
    result = multiclass_log_loss((_multi("0.4", "0.3", "0.29", "HOME"),))
    assert result.status is MetricStatus.INVALID_PROBABILITY
    assert result.value is None


def test_balanced_multiclass_log_loss() -> None:
    third = Decimal(1) / Decimal(3)
    record = MulticlassPrediction(
        "p", tuple(ClassProbability(label, third) for label in ("HOME", "DRAW", "AWAY")), "DRAW"
    )
    value = multiclass_log_loss((record,)).value
    assert value is not None and float(value) == pytest.approx(math.log(3))


def test_confident_wrong_multiclass_log_loss_is_large() -> None:
    value = multiclass_log_loss((_multi("0.999999", "0.000001", "0", "AWAY"),)).value
    assert value is not None and value > Decimal(30)


def test_multiclass_log_loss_preserves_input_and_order() -> None:
    rows = (_multi("0.7", "0.2", "0.1", "HOME", "a"), _multi("0.2", "0.2", "0.6", "AWAY", "b"))
    before = [row.to_dict() for row in rows]
    assert multiclass_log_loss(rows).value == multiclass_log_loss(tuple(reversed(rows))).value
    assert [row.to_dict() for row in rows] == before


@pytest.mark.parametrize(("observed", "expected"), [("HOME", "1"), ("AWAY", "0")])
def test_multiclass_accuracy_clear_winner(observed: str, expected: str) -> None:
    assert multiclass_accuracy((_multi("0.7", "0.2", "0.1", observed),)).value == Decimal(expected)


def test_multiclass_accuracy_tie_is_excluded_but_probability_metrics_remain_valid() -> None:
    record = _multi("0.4", "0.4", "0.2", "HOME")
    accuracy = multiclass_accuracy((record,))
    assert accuracy.value is None
    assert accuracy.excluded_count == 1
    assert multiclass_brier_score((record,)).value is not None
    assert multiclass_log_loss((record,)).value is not None


def test_metric_suites_are_deterministic_and_accuracy_is_separate() -> None:
    binary = evaluate_binary_probabilities((_binary("0.8", 1),))
    multi = evaluate_multiclass_probabilities((_multi("0.7", "0.2", "0.1", "HOME"),))
    assert binary.to_dict() == binary.to_dict()
    assert multi.to_dict() == multi.to_dict()
    assert binary.accuracy.metric is MetricName.ACCURACY_BINARY
    assert multi.accuracy.metric is MetricName.ACCURACY_MULTICLASS
