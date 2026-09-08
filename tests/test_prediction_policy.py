from dataclasses import replace
from decimal import Decimal

import pytest

from pitchvalue.prediction.config import DEFAULT_POLICY
from pitchvalue.prediction.contracts import (
    AnalysisAvailability,
    FailureState,
    MarketCandidate,
    MarketFamily,
    OddsBand,
    PolicyReason,
    QualityClass,
    Selection,
)
from pitchvalue.prediction.policy import classify_odds, evaluate_candidate

D = Decimal


def candidate(**overrides: object) -> MarketCandidate:
    values: dict[str, object] = {
        "match_id": "00000000-0000-0000-0000-000000000001",
        "market": MarketFamily.MATCH_RESULT,
        "selection": Selection.HOME,
        "line": None,
        "model_probability": D("0.58"),
        "market_implied_probability": D("0.50"),
        "decimal_odds": D("2.00"),
        "model_agreement_count": 4,
        "model_count": 4,
        "data_quality_score": D("90"),
        "calibration_confidence": D("90"),
        "market_stability_score": D("90"),
        "analysis_availability": AnalysisAvailability.AVAILABLE,
        "correlation_group": "home-positive",
    }
    values.update(overrides)
    return MarketCandidate(**values)  # type: ignore[arg-type]


def assert_reason(result_reasons: tuple[PolicyReason, ...], reason: PolicyReason) -> None:
    assert reason in result_reasons


def test_all_publication_gates_pass() -> None:
    result = evaluate_candidate(candidate())

    assert result.quality_class is QualityClass.STRONG_PICK
    assert result.publication_eligible
    assert result.main_pick_eligible
    assert result.alternative_pick_eligible
    assert result.reasons == (PolicyReason.PUBLISHABLE,)
    assert result.failure_state is None


@pytest.mark.parametrize(
    ("overrides", "reason", "failure_state"),
    [
        (
            {"model_probability": D("0.55")},
            PolicyReason.EDGE_WATCHLIST_ONLY,
            FailureState.NO_BET,
        ),
        (
            {
                "model_probability": D("0.56"),
                "data_quality_score": D("70"),
                "calibration_confidence": D("0"),
                "market_stability_score": D("0"),
                "model_agreement_count": 3,
            },
            PolicyReason.BET_SCORE_BELOW_PUBLICATION,
            FailureState.NO_BET,
        ),
        (
            {"model_agreement_count": 2},
            PolicyReason.MODEL_AGREEMENT_INSUFFICIENT,
            FailureState.NO_BET,
        ),
        (
            {"data_quality_score": D("69")},
            PolicyReason.DATA_QUALITY_INSUFFICIENT,
            FailureState.NO_BET,
        ),
        (
            {"data_quality_score": None},
            PolicyReason.DATA_QUALITY_MISSING,
            FailureState.DATA_INSUFFICIENT,
        ),
        (
            {"calibration_confidence": None},
            PolicyReason.CALIBRATION_CONFIDENCE_MISSING,
            FailureState.ANALYSIS_UNAVAILABLE,
        ),
        (
            {"market_stability_score": None},
            PolicyReason.MARKET_STABILITY_MISSING,
            FailureState.ANALYSIS_UNAVAILABLE,
        ),
        (
            {"analysis_availability": AnalysisAvailability.UNAVAILABLE},
            PolicyReason.ANALYSIS_UNAVAILABLE,
            FailureState.ANALYSIS_UNAVAILABLE,
        ),
        (
            {"decimal_odds": D("1.34")},
            PolicyReason.ODDS_BELOW_DISPLAY_MINIMUM,
            FailureState.NO_BET,
        ),
    ],
)
def test_each_publication_gate_fails_independently(
    overrides: dict[str, object],
    reason: PolicyReason,
    failure_state: FailureState,
) -> None:
    result = evaluate_candidate(candidate(**overrides))

    assert not result.publication_eligible
    assert_reason(result.reasons, reason)
    assert result.failure_state is failure_state


def test_edge_below_minimum_uses_specific_reason() -> None:
    result = evaluate_candidate(candidate(model_probability=D("0.539")))

    assert not result.publication_eligible
    assert_reason(result.reasons, PolicyReason.EDGE_BELOW_MINIMUM)


def test_zero_model_count_is_analysis_unavailable() -> None:
    result = evaluate_candidate(candidate(model_agreement_count=0, model_count=0))

    assert not result.publication_eligible
    assert result.agreement_ratio is None
    assert result.bet_score is None
    assert result.failure_state is FailureState.ANALYSIS_UNAVAILABLE
    assert_reason(result.reasons, PolicyReason.MODEL_AGREEMENT_INSUFFICIENT)


@pytest.mark.parametrize(
    ("odds", "band"),
    [
        ("1.34", OddsBand.BELOW_DISPLAY_MINIMUM),
        ("1.35", OddsBand.LOW_ODDS),
        ("1.49", OddsBand.LOW_ODDS),
        ("1.50", OddsBand.IDEAL),
        ("2.20", OddsBand.IDEAL),
        ("2.21", OddsBand.HIGHER_RISK),
        ("3.00", OddsBand.HIGHER_RISK),
        ("3.01", OddsBand.ABOVE_V1_MAIN_MAX),
    ],
)
def test_odds_band_boundaries(odds: str, band: OddsBand) -> None:
    assert classify_odds(D(odds), DEFAULT_POLICY) is band


@pytest.mark.parametrize(
    ("odds", "main_eligible", "alternative_eligible"),
    [
        ("1.34", False, False),
        ("1.35", False, True),
        ("1.49", False, True),
        ("1.50", True, True),
        ("2.20", True, True),
        ("2.21", True, True),
        ("3.00", True, True),
        ("3.01", False, False),
    ],
)
def test_main_and_alternative_eligibility_at_odds_boundaries(
    odds: str,
    main_eligible: bool,
    alternative_eligible: bool,
) -> None:
    result = evaluate_candidate(
        candidate(
            model_probability=D("0.62"),
            decimal_odds=D(odds),
            data_quality_score=D("100"),
            calibration_confidence=D("100"),
            market_stability_score=D("100"),
        )
    )

    assert result.main_pick_eligible is main_eligible
    assert result.alternative_pick_eligible is alternative_eligible


def test_exceptionally_strong_low_odds_candidate_is_alternative_only() -> None:
    result = evaluate_candidate(
        candidate(
            model_probability=D("0.62"),
            decimal_odds=D("1.35"),
            data_quality_score=D("100"),
            calibration_confidence=D("100"),
            market_stability_score=D("100"),
        )
    )

    assert result.publication_eligible
    assert not result.main_pick_eligible
    assert result.alternative_pick_eligible
    assert result.reasons == (PolicyReason.PUBLISHABLE,)


def test_low_odds_base_gates_are_not_enough_for_exception() -> None:
    result = evaluate_candidate(candidate(decimal_odds=D("1.49"), model_agreement_count=3))

    assert not result.publication_eligible
    assert_reason(result.reasons, PolicyReason.LOW_ODDS_REQUIRES_STRONGER_SIGNAL)


def test_strong_quality_remains_separate_from_above_max_odds_ineligibility() -> None:
    result = evaluate_candidate(candidate(decimal_odds=D("3.01")))

    assert result.quality_class is QualityClass.STRONG_PICK
    assert not result.publication_eligible
    assert not result.main_pick_eligible
    assert_reason(result.reasons, PolicyReason.ODDS_ABOVE_V1_MAIN_MAX)


@pytest.mark.parametrize(
    ("field", "reason", "failure_state"),
    [
        ("data_quality_score", PolicyReason.DATA_QUALITY_MISSING, FailureState.DATA_INSUFFICIENT),
        (
            "calibration_confidence",
            PolicyReason.CALIBRATION_CONFIDENCE_MISSING,
            FailureState.ANALYSIS_UNAVAILABLE,
        ),
        (
            "market_stability_score",
            PolicyReason.MARKET_STABILITY_MISSING,
            FailureState.ANALYSIS_UNAVAILABLE,
        ),
    ],
)
def test_missing_components_are_not_fabricated(
    field: str,
    reason: PolicyReason,
    failure_state: FailureState,
) -> None:
    result = evaluate_candidate(candidate(**{field: None}))

    assert result.bet_score is None
    assert result.quality_class is QualityClass.NO_BET
    assert not result.publication_eligible
    assert result.failure_state is failure_state
    assert_reason(result.reasons, reason)


def test_failure_state_distinguishes_completed_no_bet_from_unavailable_analysis() -> None:
    completed = evaluate_candidate(candidate(model_probability=D("0.53")))
    unavailable = evaluate_candidate(
        candidate(analysis_availability=AnalysisAvailability.UNAVAILABLE)
    )

    assert completed.failure_state is FailureState.NO_BET
    assert unavailable.failure_state is FailureState.ANALYSIS_UNAVAILABLE


def test_policy_override_changes_result_without_global_mutation() -> None:
    stricter = replace(DEFAULT_POLICY, minimum_data_quality_score=D("95"))

    assert evaluate_candidate(candidate()).publication_eligible
    overridden = evaluate_candidate(candidate(), stricter)
    assert not overridden.publication_eligible
    assert_reason(overridden.reasons, PolicyReason.DATA_QUALITY_INSUFFICIENT)
    assert DEFAULT_POLICY.minimum_data_quality_score == D("70")


def test_result_exposes_ranking_correlation_and_structured_decision_data() -> None:
    result = evaluate_candidate(candidate())
    decision = result.decision_data()

    assert result.ranking_inputs is not None
    assert result.ranking_inputs.bet_score == result.bet_score
    assert result.correlation_group == "home-positive"
    assert decision["match_id"] == result.match_id
    assert decision["quality_class"] == "STRONG_PICK"
    assert decision["reasons"] == ["PUBLISHABLE"]


def test_evaluation_is_deterministic() -> None:
    value = candidate()
    assert evaluate_candidate(value) == evaluate_candidate(value)
