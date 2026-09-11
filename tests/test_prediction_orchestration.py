from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from pitchvalue.markets.edge import (
    HistoricalMarketGroup,
    HistoricalMarketPrice,
    MarketComparisonStatus,
    RawMLProbability,
    build_market_probability,
    calculate_market_edges,
)
from pitchvalue.markets.history.contracts import (
    ObservationRole,
    OddsQualityStatus,
    TimingSemantics,
)
from pitchvalue.ml.model import MLClassProbability
from pitchvalue.models.signals import ModelFamily, ModelSignal, evaluate_match_result_agreement
from pitchvalue.models.signals.contracts import DirectionalPreference, SignalStatus
from pitchvalue.prediction.config import DEFAULT_POLICY
from pitchvalue.prediction.contracts import MarketFamily, QualityClass, Selection
from pitchvalue.prediction.orchestration import (
    BetScoreCompleteness,
    ComponentStatus,
    GateStatus,
    MatchDecisionStatus,
    PolicyGate,
    orchestrate_match,
    resolve_selection_decisions,
)

D = Decimal
AS_OF = datetime(2025, 1, 2, tzinfo=UTC)
DEFAULT_HOME_PROBABILITY = D("0.60")
DEFAULT_HOME_ODDS = D("2.00")


def _signal(family: ModelFamily, selection: Selection | None) -> ModelSignal:
    direction = (
        DirectionalPreference.HOME
        if selection is Selection.HOME
        else DirectionalPreference.AWAY
        if selection is Selection.AWAY
        else DirectionalPreference.NEUTRAL
        if selection is None
        else None
    )
    return ModelSignal(
        family,
        f"{family.value.lower()}-v1",
        "match-1",
        MarketFamily.MATCH_RESULT,
        selection,
        direction,
        SignalStatus.READY,
        D("0.8"),
        probability=D("0.8") if family in {ModelFamily.ML, ModelFamily.POISSON} else None,
    )


def _signals(selection: Selection = Selection.HOME) -> tuple[ModelSignal, ...]:
    return tuple(_signal(family, selection) for family in ModelFamily)


def _edge_result(
    *,
    role_only: bool = True,
    observed_at: datetime | None = None,
    home_probability: Decimal = DEFAULT_HOME_PROBABILITY,
    home_odds: Decimal = DEFAULT_HOME_ODDS,
):
    timing = TimingSemantics.ROLE_ONLY if role_only else TimingSemantics.EXACT
    role = ObservationRole.SOURCE_PREMATCH
    odds = (home_odds, D("4.00"), D("4.00"))
    prices = tuple(
        HistoricalMarketPrice(
            index,
            "match-1",
            "provider-1",
            "BET365",
            MarketFamily.MATCH_RESULT,
            selection,
            price,
            role,
            timing,
            observed_at,
            OddsQualityStatus.ELIGIBLE,
            (),
            100,
            200,
            source,
            "mapping-v1",
            "normalization-v1",
            "quality-v1",
        )
        for index, selection, price, source in zip(
            (1, 2, 3),
            (Selection.HOME, Selection.DRAW, Selection.AWAY),
            odds,
            ("B365H", "B365D", "B365A"),
            strict=True,
        )
    )
    model = RawMLProbability(
        "row-1",
        "match-1",
        "multinomial_logistic_v1",
        "FOOTBALL_PERFORMANCE_ONLY",
        AS_OF,
        (
            MLClassProbability(Selection.HOME, home_probability),
            MLClassProbability(Selection.DRAW, D("0.25")),
            MLClassProbability(Selection.AWAY, D("0.75") - home_probability),
        ),
    )
    group = HistoricalMarketGroup("match-1", "BET365", role, timing, observed_at, prices)
    return calculate_market_edges(model, build_market_probability(group))


def _agreements(signals: tuple[ModelSignal, ...]):
    return evaluate_match_result_agreement(signals, match_id="match-1")


def _orchestrate(**kwargs: object):
    signals = kwargs.pop("signals", _signals())
    result = kwargs.pop("edge_result", _edge_result())
    agreements = kwargs.pop("agreements") if "agreements" in kwargs else _agreements(signals)
    return orchestrate_match(
        result,
        agreements,
        signals,
        data_quality_score=kwargs.pop("data_quality_score", D("100")),
        calibration_confidence=kwargs.pop("calibration_confidence", D("100")),
        stability_score=kwargs.pop("stability_score", D("100")),
        **kwargs,
    )


def _home(result):
    return next(item for item in result.selection_decisions if item.selection is Selection.HOME)


def _gate(result, gate: PolicyGate):
    return next(item for item in result.gates if item.gate is gate)


def test_role_only_is_policy_simulation_but_never_publication() -> None:
    result = _orchestrate()
    home = _home(result)
    assert home.policy_decision is QualityClass.ELITE_PICK
    assert not home.publication_eligible
    assert _gate(home, PolicyGate.MARKET_TEMPORAL_GATE).status is GateStatus.FAIL
    assert "MARKET_EXACT_TIME_NOT_PROVEN" in home.blockers


def test_edge_alone_does_not_create_pick_when_agreement_fails() -> None:
    signals = _signals(Selection.AWAY)
    result = _orchestrate(signals=signals, agreements=_agreements(signals))
    assert _home(result).edge >= D("0.06")
    assert _home(result).policy_decision is QualityClass.NO_BET


def test_bet_score_alone_does_not_override_low_edge() -> None:
    result = _orchestrate(edge_result=_edge_result(home_probability=D("0.53")))
    home = _home(result)
    assert home.bet_score is not None
    assert home.edge < D("0.04")
    assert home.policy_decision is QualityClass.NO_BET


def test_watchlist_requires_complete_policy_evidence() -> None:
    edge = _edge_result(home_probability=D("0.55"))
    complete = _home(_orchestrate(edge_result=edge))
    incomplete = _home(_orchestrate(edge_result=edge, calibration_confidence=None))
    assert complete.policy_decision is QualityClass.WATCHLIST
    assert incomplete.policy_decision is QualityClass.NO_BET
    assert not complete.publication_eligible


def test_insufficient_data_quality_blocks_pick() -> None:
    home = _home(_orchestrate(data_quality_score=D("69")))
    assert _gate(home, PolicyGate.DATA_QUALITY_GATE).status is GateStatus.FAIL
    assert home.policy_decision is QualityClass.NO_BET


@pytest.mark.parametrize("missing", ["calibration_confidence", "stability_score"])
def test_missing_score_component_is_explicit_without_reweighting(missing: str) -> None:
    result = _orchestrate(**{missing: None})
    home = _home(result)
    assert home.bet_score is None
    assert home.bet_score_completeness is BetScoreCompleteness.PARTIAL
    assert _gate(home, PolicyGate.BET_SCORE_GATE).status is GateStatus.UNAVAILABLE
    assert sum(component.weight for component in home.components) == D("1.00")
    assert (
        next(component for component in home.components if component.score is None).status
        is ComponentStatus.UNAVAILABLE
    )


def test_missing_data_quality_is_unavailable_not_zero() -> None:
    home = _home(_orchestrate(data_quality_score=None))
    assert home.data_quality_score is None
    assert home.bet_score is None
    assert _gate(home, PolicyGate.DATA_QUALITY_GATE).status is GateStatus.UNAVAILABLE


def test_exact_time_evidence_can_pass_temporal_and_publication_gates() -> None:
    edge = _edge_result(role_only=False, observed_at=AS_OF - timedelta(minutes=1))
    home = _home(_orchestrate(edge_result=edge))
    assert _gate(home, PolicyGate.MARKET_TEMPORAL_GATE).status is GateStatus.PASS
    assert home.publication_eligible


def test_future_exact_market_observation_fails_temporal_gate() -> None:
    legal = _edge_result(role_only=False, observed_at=AS_OF - timedelta(minutes=1))
    future = replace(legal, observed_at=AS_OF + timedelta(minutes=1))
    home = _home(_orchestrate(edge_result=future))
    assert _gate(home, PolicyGate.MARKET_TEMPORAL_GATE).status is GateStatus.FAIL
    assert not home.publication_eligible


def test_raw_ml_remains_canonical_and_warnings_are_preserved() -> None:
    home = _home(_orchestrate())
    assert home.probability_source == "RAW ML"
    assert "MODEL_PROBABILITY_UNCALIBRATED" in home.diagnostics


@pytest.mark.parametrize("source", ["TEMPERATURE_CALIBRATED_ML", "ML_POISSON_ENSEMBLE"])
def test_rejected_probability_sources_cannot_enter_orchestration(source: str) -> None:
    with pytest.raises(ValueError, match="RAW ML"):
        _orchestrate(probability_source=source)


def test_market_quality_must_be_eligible() -> None:
    home = _home(_orchestrate(market_quality=OddsQualityStatus.SUSPECT))
    assert _gate(home, PolicyGate.MARKET_QUALITY_GATE).status is GateStatus.FAIL
    assert home.policy_decision is QualityClass.NO_BET


def test_agreement_preserves_configured_and_usable_counts() -> None:
    signals = _signals()[:-1]
    home = _home(_orchestrate(signals=signals, agreements=_agreements(signals)))
    assert home.agreement_support_count == 3
    assert home.agreement_usable_count == 3
    assert home.agreement_configured_count == 4
    assert home.agreement_status is GateStatus.PASS


def test_neutral_is_not_draw_support() -> None:
    signals = tuple(_signal(family, None) for family in ModelFamily)
    draw = next(
        item
        for item in _orchestrate(
            signals=signals, agreements=_agreements(signals)
        ).selection_decisions
        if item.selection is Selection.DRAW
    )
    assert draw.agreement_support_count == 0
    assert draw.agreement_status is GateStatus.FAIL


def test_multiple_candidates_are_not_arbitrarily_resolved() -> None:
    home = _home(_orchestrate())
    multiple = (
        home,
        replace(home, selection=Selection.DRAW),
    )
    result = resolve_selection_decisions(multiple)
    assert result.status is MatchDecisionStatus.MULTIPLE_POLICY_CANDIDATES
    assert result.selected_policy_candidate is None
    assert not result.publication_eligible


def test_above_three_odds_is_policy_only_and_preserves_edge() -> None:
    edge = _edge_result(home_probability=D("0.40"), home_odds=D("3.20"))
    home = _home(_orchestrate(edge_result=edge))
    assert home.edge == edge.edges[0].edge
    assert _gate(home, PolicyGate.ODDS_PRESENTATION_GATE).status is GateStatus.FAIL


def test_completed_no_bet_is_valid_not_an_error() -> None:
    result = _orchestrate(edge_result=_edge_result(home_probability=D("0.53")))
    assert _home(result).policy_decision is QualityClass.NO_BET
    assert "INVALID" not in _home(result).diagnostics


def test_lineage_is_preserved() -> None:
    lineage = _home(_orchestrate()).lineage
    assert lineage.source_match_provider_ref_id == 100
    assert lineage.source_staging_row_id == 200
    assert lineage.source_field == "B365H"
    assert lineage.mapping_version == "mapping-v1"
    assert lineage.normalization_version == "normalization-v1"
    assert lineage.quality_policy_version == "quality-v1"


def test_contracts_are_immutable_and_serialization_is_deterministic() -> None:
    result = _orchestrate()
    assert result.to_dict() == result.to_dict()
    with pytest.raises(FrozenInstanceError):
        result.status = MatchDecisionStatus.NO_CANDIDATE  # type: ignore[misc]


def test_policy_defaults_are_reused() -> None:
    assert DEFAULT_POLICY.edge_watchlist_threshold == D("0.04")
    assert DEFAULT_POLICY.edge_publication_threshold == D("0.06")
    assert DEFAULT_POLICY.score_boundaries.pick == D("70")
    assert DEFAULT_POLICY.minimum_agreement_ratio == D("0.75")


def test_orchestration_module_has_no_llm_or_roi_behavior() -> None:
    import pitchvalue.prediction.orchestration as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "openai" not in source.lower()
    assert "langchain" not in source.lower()
    assert "kelly" not in source.lower()
    assert "realized_roi" not in source.lower()


def test_input_order_must_align_and_duplicate_signal_families_fail() -> None:
    signals = _signals()
    with pytest.raises(ValueError, match="align"):
        _orchestrate(agreements=tuple(reversed(_agreements(signals))))
    with pytest.raises(ValueError, match="one item"):
        _orchestrate(signals=signals + (signals[0],), agreements=_agreements(signals))


def test_wrong_match_signal_is_rejected() -> None:
    signals = _signals()
    bad = (replace(signals[0], match_id="other"), *signals[1:])
    with pytest.raises(ValueError, match="signal identity"):
        _orchestrate(signals=bad, agreements=_agreements(signals))


def test_weights_are_not_changed_by_component_availability() -> None:
    full = _home(_orchestrate())
    partial = _home(_orchestrate(calibration_confidence=None, stability_score=None))
    assert tuple(item.weight for item in full.components) == tuple(
        item.weight for item in partial.components
    )


def test_role_only_status_is_retained_in_result() -> None:
    home = _home(_orchestrate())
    assert home.comparison_status is MarketComparisonStatus.ROLE_ONLY_COMPARISON
    assert home.observed_at is None
    assert home.timing_semantics is TimingSemantics.ROLE_ONLY
