from dataclasses import replace
from decimal import Decimal

import pytest

from pitchvalue.prediction.config import (
    DEFAULT_POLICY,
    BetScoreBoundaries,
    BetScoreWeights,
    PredictionPolicyConfig,
)
from pitchvalue.prediction.contracts import ContractValidationError

D = Decimal


def test_default_policy_is_valid_and_serializable() -> None:
    policy = PredictionPolicyConfig()
    serialized = policy.as_serializable_dict()

    assert policy == DEFAULT_POLICY
    assert serialized["edge_publication_threshold"] == "0.06"
    assert serialized["weights"]["edge"] == "0.35"


def test_invalid_weight_total_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="total 1.0"):
        BetScoreWeights(edge=D("0.34"))


def test_invalid_score_boundary_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="boundaries"):
        BetScoreBoundaries(pick=D("59"))


def test_invalid_edge_boundary_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="edge thresholds"):
        replace(DEFAULT_POLICY, edge_watchlist_threshold=D("0.06"))


def test_invalid_odds_ordering_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="odds boundaries"):
        replace(DEFAULT_POLICY, ideal_odds_maximum=D("3.10"))


@pytest.mark.parametrize("ratio", [D("-0.01"), D("1.01")])
def test_invalid_agreement_threshold_is_rejected(ratio: Decimal) -> None:
    with pytest.raises(ContractValidationError, match="agreement ratio"):
        replace(DEFAULT_POLICY, minimum_agreement_ratio=ratio)


@pytest.mark.parametrize("score", [D("-0.01"), D("100.01")])
def test_invalid_data_quality_threshold_is_rejected(score: Decimal) -> None:
    with pytest.raises(ContractValidationError, match="data quality"):
        replace(DEFAULT_POLICY, minimum_data_quality_score=score)


def test_impossible_low_odds_exception_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="exceptional agreement"):
        replace(DEFAULT_POLICY, low_odds_exception_agreement_ratio=D("0.70"))


def test_policy_override_does_not_mutate_default() -> None:
    override = replace(DEFAULT_POLICY, minimum_data_quality_score=D("95"))

    assert override.minimum_data_quality_score == D("95")
    assert DEFAULT_POLICY.minimum_data_quality_score == D("70")


def test_policy_rejects_non_decimal_thresholds() -> None:
    with pytest.raises(ContractValidationError, match="must use Decimal"):
        replace(DEFAULT_POLICY, minimum_data_quality_score=70)  # type: ignore[arg-type]
