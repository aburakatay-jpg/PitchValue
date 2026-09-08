from dataclasses import replace
from decimal import Decimal

import pytest

from pitchvalue.prediction.config import DEFAULT_POLICY
from pitchvalue.prediction.contracts import ContractValidationError, QualityClass
from pitchvalue.prediction.scoring import (
    EdgeDisposition,
    agreement_component_score,
    agreement_ratio,
    calculate_bet_score,
    calculate_edge,
    classify_bet_score,
    classify_edge,
    edge_component_score,
)

D = Decimal


def test_edge_is_probability_point_difference_not_relative_uplift() -> None:
    assert calculate_edge(D("0.56"), D("0.50")) == D("0.06")


@pytest.mark.parametrize(
    ("edge", "expected"),
    [
        ("0.039", EdgeDisposition.NO_BET),
        ("0.04", EdgeDisposition.WATCHLIST),
        ("0.05", EdgeDisposition.WATCHLIST),
        ("0.059999", EdgeDisposition.WATCHLIST),
        ("0.06", EdgeDisposition.PUBLICATION_CANDIDATE),
        ("0.09", EdgeDisposition.PUBLICATION_CANDIDATE),
        ("-0.02", EdgeDisposition.NO_BET),
    ],
)
def test_edge_policy_boundaries(edge: str, expected: EdgeDisposition) -> None:
    assert classify_edge(D(edge), DEFAULT_POLICY) is expected


def test_initial_edge_score_mapping_has_explicit_knots_and_cap() -> None:
    assert edge_component_score(D("-0.01"), DEFAULT_POLICY) == 0
    assert edge_component_score(D("0.04"), DEFAULT_POLICY) == 50
    assert edge_component_score(D("0.06"), DEFAULT_POLICY) == 70
    assert edge_component_score(D("0.12"), DEFAULT_POLICY) == 100
    assert edge_component_score(D("0.25"), DEFAULT_POLICY) == 100


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        ("0", QualityClass.NO_BET),
        ("59.999", QualityClass.NO_BET),
        ("60", QualityClass.WATCHLIST),
        ("69.999", QualityClass.WATCHLIST),
        ("70", QualityClass.PICK),
        ("79.999", QualityClass.PICK),
        ("80", QualityClass.STRONG_PICK),
        ("89.999", QualityClass.STRONG_PICK),
        ("90", QualityClass.ELITE_PICK),
        ("100", QualityClass.ELITE_PICK),
    ],
)
def test_bet_score_class_boundaries(score: str, expected: QualityClass) -> None:
    assert classify_bet_score(D(score), DEFAULT_POLICY) is expected


@pytest.mark.parametrize("score", [D("-0.001"), D("100.001")])
def test_component_scores_outside_normalized_range_are_rejected(score: Decimal) -> None:
    with pytest.raises(ContractValidationError, match="between 0 and 100"):
        calculate_bet_score(
            edge_score=score,
            agreement_score=D("80"),
            data_quality_score=D("80"),
            calibration_confidence=D("80"),
            market_stability_score=D("80"),
            policy=DEFAULT_POLICY,
        )


@pytest.mark.parametrize(
    ("agreed", "total", "expected"),
    [
        (0, 4, D("0")),
        (2, 4, D("0.5")),
        (3, 4, D("0.75")),
        (4, 4, D("1")),
        (6, 8, D("0.75")),
    ],
)
def test_agreement_ratios(agreed: int, total: int, expected: Decimal) -> None:
    assert agreement_ratio(agreed, total) == expected


def test_zero_total_models_is_unavailable_not_fabricated() -> None:
    assert agreement_ratio(0, 0) is None
    assert agreement_component_score(0, 0) is None


@pytest.mark.parametrize(("agreed", "total"), [(-1, 4), (5, 4), (1, -1)])
def test_invalid_agreement_counts_are_rejected(agreed: int, total: int) -> None:
    with pytest.raises(ContractValidationError, match="agreement counts"):
        agreement_ratio(agreed, total)


def test_bet_score_uses_configured_weights() -> None:
    score = calculate_bet_score(
        edge_score=D("80"),
        agreement_score=D("75"),
        data_quality_score=D("90"),
        calibration_confidence=D("80"),
        market_stability_score=D("70"),
        policy=DEFAULT_POLICY,
    )
    assert score == D("79.25")

    changed = replace(
        DEFAULT_POLICY,
        weights=replace(
            DEFAULT_POLICY.weights,
            edge=D("0.40"),
            model_agreement=D("0.20"),
        ),
    )
    assert calculate_bet_score(
        edge_score=D("80"),
        agreement_score=D("75"),
        data_quality_score=D("90"),
        calibration_confidence=D("80"),
        market_stability_score=D("70"),
        policy=changed,
    ) == D("79.50")
