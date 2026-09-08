from decimal import Decimal

import pytest

from pitchvalue.evaluation.metrics import (
    BinaryPrediction,
    BucketStatus,
    MetricConfig,
    MetricStatus,
    PredictionRecordStatus,
    binary_calibration,
)


def _row(probability: str, observed: int, identifier: str = "p") -> BinaryPrediction:
    return BinaryPrediction(identifier, Decimal(probability), observed)


def _bucket_for(result: object, probability: Decimal) -> object:
    for bucket in result.buckets:  # type: ignore[attr-defined]
        if bucket.lower_bound <= probability and (
            probability < bucket.upper_bound or bucket.upper_inclusive
        ):
            return bucket
    raise AssertionError("bucket missing")


def test_empty_calibration_is_explicit() -> None:
    result = binary_calibration(())
    assert result.status is MetricStatus.EMPTY_INPUT
    assert result.ece is None
    assert all(bucket.status is BucketStatus.EMPTY for bucket in result.buckets)


@pytest.mark.parametrize(
    ("probability", "expected_index"),
    [("0", 0), ("0.1", 1), ("0.5", 5), ("0.999", 9), ("1", 9)],
)
def test_bucket_boundaries_assign_once(probability: str, expected_index: int) -> None:
    result = binary_calibration((_row(probability, 1),))
    nonempty = [index for index, bucket in enumerate(result.buckets) if bucket.sample_count]
    assert nonempty == [expected_index]


def test_bucket_interval_flags_are_explicit() -> None:
    result = binary_calibration((_row("1", 1),))
    assert result.bucket_edges == MetricConfig().bucket_edges
    assert all(not bucket.upper_inclusive for bucket in result.buckets[:-1])
    assert result.buckets[-1].upper_inclusive


def test_bucket_statistics() -> None:
    result = binary_calibration(
        (_row("0.6", 1, "a"), _row("0.8", 0, "b")),
        MetricConfig(bucket_edges=(Decimal(0), Decimal(1))),
    )
    bucket = result.buckets[0]
    assert bucket.sample_count == 2
    assert bucket.mean_predicted_probability == Decimal("0.7")
    assert bucket.observed_frequency == Decimal("0.5")
    assert bucket.signed_calibration_gap == Decimal("0.2")
    assert bucket.absolute_calibration_gap == Decimal("0.2")


def test_signed_gap_preserves_underconfidence_direction() -> None:
    bucket = binary_calibration(
        (_row("0.2", 1),), MetricConfig(bucket_edges=(Decimal(0), Decimal(1)))
    ).buckets[0]
    assert bucket.signed_calibration_gap == Decimal("-0.8")
    assert bucket.absolute_calibration_gap == Decimal("0.8")


def test_empty_buckets_are_represented_in_edge_order() -> None:
    result = binary_calibration((_row("0.25", 0),))
    assert len(result.buckets) == 10
    assert [bucket.lower_bound for bucket in result.buckets] == sorted(
        bucket.lower_bound for bucket in result.buckets
    )
    assert sum(bucket.sample_count for bucket in result.buckets) == 1


def test_insufficient_bucket_sample_is_explicit() -> None:
    result = binary_calibration((_row("0.2", 0),), MetricConfig(minimum_bucket_samples=2))
    bucket = _bucket_for(result, Decimal("0.2"))
    assert bucket.status is BucketStatus.INSUFFICIENT_SAMPLE  # type: ignore[attr-defined]


def test_perfectly_calibrated_synthetic_groups_have_zero_ece() -> None:
    rows = tuple(
        [_row("0", 0, f"n{i}") for i in range(5)] + [_row("1", 1, f"p{i}") for i in range(5)]
    )
    assert binary_calibration(rows).ece == Decimal(0)


def test_miscalibrated_example_has_positive_ece() -> None:
    rows = tuple(_row("0.9", 0, str(index)) for index in range(4))
    assert binary_calibration(rows).ece == Decimal("0.9")


def test_ece_is_weighted_by_bucket_sample_count() -> None:
    rows = (_row("0.1", 0, "a"), _row("0.1", 0, "b"), _row("0.9", 0, "c"))
    assert binary_calibration(rows).ece == Decimal("0.3666666666666666666666666667")


def test_empty_buckets_do_not_change_ece() -> None:
    rows = (_row("0.2", 0),)
    default = binary_calibration(rows)
    custom = binary_calibration(
        rows, MetricConfig(bucket_edges=(Decimal(0), Decimal("0.5"), Decimal(1)))
    )
    assert default.ece == custom.ece == Decimal("0.2")


def test_bucket_config_can_change_ece_predictably() -> None:
    rows = (_row("0.1", 0, "a"), _row("0.9", 1, "b"))
    fine = binary_calibration(rows)
    one_bucket = binary_calibration(rows, MetricConfig(bucket_edges=(Decimal(0), Decimal(1))))
    assert fine.ece == Decimal("0.1")
    assert one_bucket.ece == Decimal(0)


def test_insufficient_total_sample_preserves_computable_ece() -> None:
    result = binary_calibration((_row("0.8", 1),), MetricConfig(minimum_total_samples=2))
    assert result.status is MetricStatus.INSUFFICIENT_SAMPLE
    assert result.ece == Decimal("0.2")


def test_missing_prediction_is_excluded_not_imputed() -> None:
    missing = BinaryPrediction("missing", None, 1, PredictionRecordStatus.MISSING_PREDICTION, None)
    result = binary_calibration((_row("0.8", 1), missing))
    assert (result.input_count, result.usable_count, result.excluded_count) == (2, 1, 1)
    assert sum(bucket.sample_count for bucket in result.buckets) == 1


def test_all_missing_calibration_is_not_perfect() -> None:
    missing = BinaryPrediction("missing", None, 1, PredictionRecordStatus.MISSING_PREDICTION, None)
    result = binary_calibration((missing,))
    assert result.ece is None
    assert result.status is MetricStatus.INSUFFICIENT_SAMPLE


def test_calibration_input_order_does_not_change_result() -> None:
    rows = (_row("0.2", 0, "b"), _row("0.8", 1, "a"))
    assert binary_calibration(rows).to_dict() == binary_calibration(tuple(reversed(rows))).to_dict()


def test_calibration_does_not_mutate_input() -> None:
    rows = (_row("0.2", 0), _row("0.8", 1, "b"))
    before = [row.to_dict() for row in rows]
    binary_calibration(rows)
    assert [row.to_dict() for row in rows] == before
