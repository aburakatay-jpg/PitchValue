from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pitchvalue.markets.edge import MarketComparisonStatus
from pitchvalue.markets.history.contracts import OddsQualityStatus, TimingSemantics
from pitchvalue.models.signals.contracts import SignalStatus
from pitchvalue.prediction.contracts import MarketFamily, QualityClass, Selection
from pitchvalue.prediction.orchestration import (
    BetScoreCompleteness,
    ComponentEvidence,
    ComponentStatus,
    GateResult,
    GateStatus,
    MarketLineage,
    MatchDecision,
    MatchDecisionStatus,
    PolicyGate,
    SelectionDecision,
)
from pitchvalue.prediction.persistence import (
    PredictionIdentity,
    PredictionPersistenceError,
    PredictionPersistenceRequest,
    payload_hash,
    selection_payload,
)

D = Decimal
AS_OF = datetime(2026, 1, 2, 12, tzinfo=UTC)
GENERATED = AS_OF + timedelta(minutes=1)


def _selection(
    selection: Selection,
    *,
    match_id: str = "1",
    model_version: str = "model-v1",
    exact: bool = False,
    publication_eligible: bool = False,
    bet_score: Decimal | None = None,
    source_staging_row_id: int = 1,
    source_match_provider_ref_id: int = 1,
) -> SelectionDecision:
    components = tuple(
        ComponentEvidence(name, D("0.2"), ComponentStatus.UNAVAILABLE, None, ("MISSING",))
        for name in ("edge", "agreement", "data_quality", "calibration", "stability")
    )
    gates = tuple(GateResult(gate, GateStatus.PASS, f"{gate.value}_PASS") for gate in PolicyGate)
    return SelectionDecision(
        match_id=match_id,
        prediction_as_of=AS_OF,
        market=MarketFamily.MATCH_RESULT,
        selection=selection,
        probability_source="RAW ML",
        model_version=model_version,
        model_probability={
            Selection.HOME: D("0.50"),
            Selection.DRAW: D("0.30"),
            Selection.AWAY: D("0.20"),
        }[selection],
        poisson_status=SignalStatus.READY,
        elo_status=SignalStatus.READY,
        form_status=SignalStatus.READY,
        agreement_support_count=3,
        agreement_usable_count=3,
        agreement_configured_count=4,
        agreement_status=GateStatus.PASS,
        data_quality_score=D("90"),
        data_quality_diagnostics=(),
        decimal_odds={
            Selection.HOME: D("2.10"),
            Selection.DRAW: D("3.40"),
            Selection.AWAY: D("4.20"),
        }[selection],
        no_vig_market_probability={
            Selection.HOME: D("0.45"),
            Selection.DRAW: D("0.30"),
            Selection.AWAY: D("0.25"),
        }[selection],
        edge={
            Selection.HOME: D("0.05"),
            Selection.DRAW: D("0.00"),
            Selection.AWAY: D("-0.05"),
        }[selection],
        observation_role="source_prematch" if not exact else "opening",
        timing_semantics=TimingSemantics.ROLE_ONLY if not exact else TimingSemantics.EXACT,
        observed_at=None if not exact else AS_OF - timedelta(minutes=5),
        comparison_status=(
            MarketComparisonStatus.ROLE_ONLY_COMPARISON
            if not exact
            else MarketComparisonStatus.EXACT_TIME_COMPARISON
        ),
        market_quality=OddsQualityStatus.ELIGIBLE,
        lineage=MarketLineage(
            source_match_provider_ref_id,
            source_staging_row_id,
            {Selection.HOME: "B365H", Selection.DRAW: "B365D", Selection.AWAY: "B365A"}[selection],
            "mapping-v1",
            "normalization-v1",
            "quality-v1",
        ),
        components=components,
        bet_score=bet_score,
        bet_score_completeness=(
            BetScoreCompleteness.PARTIAL if bet_score is None else BetScoreCompleteness.COMPLETE
        ),
        score_class=None if bet_score is None else QualityClass.PICK,
        gates=gates,
        policy_decision=QualityClass.PICK,
        publication_eligible=publication_eligible,
        blockers=() if publication_eligible else ("MARKET_EXACT_TIME_NOT_PROVEN",),
        diagnostics=("MODEL_PROBABILITY_UNCALIBRATED",),
    )


def make_decision(**kwargs: object) -> MatchDecision:
    selections = tuple(
        _selection(item, **kwargs) for item in (Selection.HOME, Selection.DRAW, Selection.AWAY)
    )
    first = selections[0]
    return MatchDecision(
        first.match_id,
        first.prediction_as_of,
        selections,
        MatchDecisionStatus.ONE_POLICY_CANDIDATE,
        (Selection.HOME,),
        Selection.HOME,
        any(item.publication_eligible for item in selections),
        (),
    )


def test_persistence_request_is_immutable_and_requires_aware_generated_at() -> None:
    request = PredictionPersistenceRequest(make_decision(), GENERATED)
    assert request.feature_profile == "FOOTBALL_PERFORMANCE_ONLY"
    with pytest.raises(PredictionPersistenceError, match="timezone-aware"):
        PredictionPersistenceRequest(make_decision(), datetime(2026, 1, 1))


def test_semantic_payload_is_deterministic_and_has_no_user_identity() -> None:
    request = PredictionPersistenceRequest(make_decision(), GENERATED)
    first = selection_payload(request.decision.selection_decisions[0], request)
    second = selection_payload(request.decision.selection_decisions[0], request)
    assert first == second
    assert payload_hash(first) == payload_hash(second)
    assert "user_id" not in first
    assert first["model_probability"] == "0.50"
    assert PredictionIdentity.from_payload(first).match_id == 1


def test_role_only_payload_preserves_null_market_time_and_false_publication() -> None:
    request = PredictionPersistenceRequest(make_decision(), GENERATED)
    payload = selection_payload(request.decision.selection_decisions[0], request)
    assert payload["timing_semantics"] == "role_only"
    assert payload["market_observed_at"] is None
    assert payload["publication_eligible"] is False


def test_exact_time_payload_preserves_supplied_publication_eligibility() -> None:
    request = PredictionPersistenceRequest(
        make_decision(exact=True, publication_eligible=True, bet_score=D("80")), GENERATED
    )
    payload = selection_payload(request.decision.selection_decisions[0], request)
    assert payload["market_observed_at"] == (AS_OF - timedelta(minutes=5)).isoformat()
    assert payload["publication_eligible"] is True
    assert payload["bet_score"] == "80"


def test_partial_bet_score_is_null_not_zero() -> None:
    request = PredictionPersistenceRequest(make_decision(bet_score=None), GENERATED)
    payload = selection_payload(request.decision.selection_decisions[0], request)
    assert payload["bet_score"] is None
    assert payload["bet_score_completeness"] == "PARTIAL"
    assert all(component["score"] is None for component in payload["components"])


def test_versions_change_semantic_payload_without_overwriting_prior_meaning() -> None:
    original = PredictionPersistenceRequest(make_decision(model_version="model-v1"), GENERATED)
    changed = PredictionPersistenceRequest(make_decision(model_version="model-v2"), GENERATED)
    assert (
        selection_payload(original.decision.selection_decisions[0], original)["model_version"]
        != selection_payload(changed.decision.selection_decisions[0], changed)["model_version"]
    )
