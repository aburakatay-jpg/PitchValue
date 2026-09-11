from decimal import Decimal

from pitchvalue.prediction.contracts import QualityClass
from pitchvalue.prediction.orchestration import MatchDecisionStatus
from pitchvalue.prediction.orchestration_evaluation import summarize_policy_simulation
from test_prediction_orchestration import _edge_result, _home, _orchestrate

D = Decimal


def test_summary_counts_edge_and_policy_states_separately() -> None:
    below = _orchestrate(edge_result=_edge_result(home_probability=D("0.53")))
    role_only = _orchestrate()
    summary = summarize_policy_simulation(
        (below, role_only), "ROLE_ONLY HISTORICAL POLICY SIMULATION"
    )
    assert summary.matches_evaluated == 2
    assert summary.selections_evaluated == 6
    assert summary.publishable_edge >= 1
    assert summary.publication_eligible_matches == 0


def test_summary_reports_missing_component_availability() -> None:
    summary = summarize_policy_simulation(
        (_orchestrate(calibration_confidence=None, stability_score=None),), "test"
    )
    available = dict(summary.component_available_counts)
    assert available == {"AGREEMENT": 3, "DATA_QUALITY": 3, "EDGE": 3}
    assert summary.bet_score_partial == 3
    assert summary.bet_score_complete == 0


def test_summary_blockers_allow_multiple_reasons_per_selection() -> None:
    summary = summarize_policy_simulation(
        (_orchestrate(data_quality_score=None, calibration_confidence=None, stability_score=None),),
        "test",
    )
    blockers = dict(summary.blocker_counts)
    assert blockers["DATA_QUALITY_UNAVAILABLE"] == 3
    assert blockers["POLICY_COMPONENTS_INCOMPLETE"] == 3
    assert blockers["MARKET_EXACT_TIME_NOT_PROVEN"] == 3


def test_summary_is_deterministic() -> None:
    decisions = (_orchestrate(),)
    left = summarize_policy_simulation(decisions, "test")
    right = summarize_policy_simulation(decisions, "test")
    assert left == right
    assert left.to_dict() == right.to_dict()


def test_no_bet_and_unavailable_match_are_not_engine_errors() -> None:
    unavailable = _orchestrate(calibration_confidence=None, stability_score=None)
    assert unavailable.status is MatchDecisionStatus.UNAVAILABLE
    assert all(
        item.policy_decision in {QualityClass.NO_BET, QualityClass.WATCHLIST}
        for item in unavailable.selection_decisions
    )
    summary = summarize_policy_simulation((unavailable,), "test")
    assert summary.unavailable_matches == 1


def test_summary_does_not_contain_roi_or_staking_fields() -> None:
    payload = summarize_policy_simulation((_orchestrate(),), "test").to_dict()
    assert "roi" not in payload
    assert "kelly" not in payload
    assert "stake" not in payload


def test_policy_class_counts_are_exhaustive() -> None:
    summary = summarize_policy_simulation((_orchestrate(),), "test")
    assert (
        summary.provisional_no_bet
        + summary.provisional_watchlist
        + summary.provisional_pick
        + summary.provisional_strong
        + summary.provisional_elite
        == summary.selections_evaluated
    )


def test_role_only_candidate_remains_non_publishable_in_summary() -> None:
    decision = _orchestrate()
    assert _home(decision).policy_decision is QualityClass.ELITE_PICK
    summary = summarize_policy_simulation((decision,), "test")
    assert summary.provisional_elite == 1
    assert summary.publication_eligible_selections == 0
