"""Deterministic TASK 20 prediction orchestration without publication side effects."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pitchvalue.markets.edge import (
    MarketComparisonStatus,
    MarketEdgeResult,
    SelectionEdge,
)
from pitchvalue.markets.history.contracts import OddsQualityStatus, TimingSemantics
from pitchvalue.models.signals.config import ModelFamily
from pitchvalue.models.signals.contracts import AgreementResult, ModelSignal, SignalStatus
from pitchvalue.prediction.config import DEFAULT_POLICY, PredictionPolicyConfig
from pitchvalue.prediction.contracts import (
    AnalysisAvailability,
    MarketCandidate,
    MarketFamily,
    OddsBand,
    QualityClass,
    Selection,
)
from pitchvalue.prediction.policy import classify_odds, evaluate_candidate
from pitchvalue.prediction.scoring import (
    agreement_component_score,
    edge_component_score,
)

ORCHESTRATOR_VERSION = "prediction_orchestrator_v1"
POLICY_VERSION = "task05_prediction_policy_v1"
CANONICAL_MODEL_SOURCE = "RAW ML"


class OrchestrationError(ValueError):
    """Raised when orchestration evidence is inconsistent."""


class ComponentStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class BetScoreCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class GateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PolicyGate(StrEnum):
    EDGE_GATE = "EDGE_GATE"
    BET_SCORE_GATE = "BET_SCORE_GATE"
    AGREEMENT_GATE = "AGREEMENT_GATE"
    DATA_QUALITY_GATE = "DATA_QUALITY_GATE"
    MARKET_TEMPORAL_GATE = "MARKET_TEMPORAL_GATE"
    MARKET_QUALITY_GATE = "MARKET_QUALITY_GATE"
    COMPONENT_COMPLETENESS_GATE = "COMPONENT_COMPLETENESS_GATE"
    ODDS_PRESENTATION_GATE = "ODDS_PRESENTATION_GATE"


class MatchDecisionStatus(StrEnum):
    NO_CANDIDATE = "NO_CANDIDATE"
    ONE_POLICY_CANDIDATE = "ONE_POLICY_CANDIDATE"
    MULTIPLE_POLICY_CANDIDATES = "MULTIPLE_POLICY_CANDIDATES"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class ComponentEvidence:
    name: str
    weight: Decimal
    status: ComponentStatus
    score: Decimal | None
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateResult:
    gate: PolicyGate
    status: GateStatus
    diagnostic: str


@dataclass(frozen=True)
class MarketLineage:
    source_match_provider_ref_id: int
    source_staging_row_id: int
    source_field: str
    mapping_version: str
    normalization_version: str
    quality_policy_version: str


@dataclass(frozen=True)
class SelectionDecision:
    match_id: str
    prediction_as_of: datetime
    market: MarketFamily
    selection: Selection
    probability_source: str
    model_version: str
    model_probability: Decimal
    poisson_status: SignalStatus | None
    elo_status: SignalStatus | None
    form_status: SignalStatus | None
    agreement_support_count: int
    agreement_usable_count: int
    agreement_configured_count: int
    agreement_status: GateStatus
    data_quality_score: Decimal | None
    data_quality_diagnostics: tuple[str, ...]
    decimal_odds: Decimal
    no_vig_market_probability: Decimal
    edge: Decimal
    observation_role: str
    timing_semantics: TimingSemantics
    observed_at: datetime | None
    comparison_status: MarketComparisonStatus
    market_quality: OddsQualityStatus
    lineage: MarketLineage
    components: tuple[ComponentEvidence, ...]
    bet_score: Decimal | None
    bet_score_completeness: BetScoreCompleteness
    score_class: QualityClass | None
    gates: tuple[GateResult, ...]
    policy_decision: QualityClass
    publication_eligible: bool
    blockers: tuple[str, ...]
    diagnostics: tuple[str, ...]
    orchestrator_version: str = ORCHESTRATOR_VERSION
    policy_version: str = POLICY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(self)


@dataclass(frozen=True)
class MatchDecision:
    match_id: str
    prediction_as_of: datetime
    selection_decisions: tuple[SelectionDecision, ...]
    status: MatchDecisionStatus
    candidate_selections: tuple[Selection, ...]
    selected_policy_candidate: Selection | None
    publication_eligible: bool
    diagnostics: tuple[str, ...]
    orchestrator_version: str = ORCHESTRATOR_VERSION
    policy_version: str = POLICY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(self)


def orchestrate_match(
    edge_result: MarketEdgeResult,
    agreements: tuple[AgreementResult, ...],
    signals: tuple[ModelSignal, ...],
    *,
    data_quality_score: Decimal | None,
    data_quality_diagnostics: tuple[str, ...] = (),
    calibration_confidence: Decimal | None = None,
    stability_score: Decimal | None = None,
    market_quality: OddsQualityStatus = OddsQualityStatus.ELIGIBLE,
    probability_source: str = CANONICAL_MODEL_SOURCE,
    policy: PredictionPolicyConfig = DEFAULT_POLICY,
) -> MatchDecision:
    """Evaluate all MATCH_RESULT selections and resolve only unambiguous candidates."""
    if probability_source != CANONICAL_MODEL_SOURCE:
        raise OrchestrationError("canonical probability source must remain RAW ML")
    _validate_match_inputs(edge_result, agreements, signals)
    decisions = tuple(
        _orchestrate_selection(
            edge_result,
            edge,
            next(item for item in agreements if item.candidate_selection is edge.selection),
            signals,
            data_quality_score=data_quality_score,
            data_quality_diagnostics=data_quality_diagnostics,
            calibration_confidence=calibration_confidence,
            stability_score=stability_score,
            market_quality=market_quality,
            probability_source=probability_source,
            policy=policy,
        )
        for edge in edge_result.edges
    )
    return resolve_selection_decisions(decisions)


def resolve_selection_decisions(
    decisions: tuple[SelectionDecision, ...],
) -> MatchDecision:
    """Resolve a set without inventing a tie-break for multiple policy candidates."""
    if not decisions:
        raise OrchestrationError("selection decisions are required")
    match_id = decisions[0].match_id
    prediction_as_of = decisions[0].prediction_as_of
    if any(
        item.match_id != match_id or item.prediction_as_of != prediction_as_of for item in decisions
    ):
        raise OrchestrationError("selection decisions must share match identity and as_of")
    candidates = tuple(
        item.selection
        for item in decisions
        if item.policy_decision
        in {
            QualityClass.PICK,
            QualityClass.STRONG_PICK,
            QualityClass.ELITE_PICK,
        }
    )
    unavailable = all(
        item.bet_score_completeness is not BetScoreCompleteness.COMPLETE for item in decisions
    )
    diagnostics: tuple[str, ...]
    if len(candidates) > 1:
        status = MatchDecisionStatus.MULTIPLE_POLICY_CANDIDATES
        selected = None
        diagnostics = ("MULTIPLE_POLICY_CANDIDATES",)
    elif len(candidates) == 1:
        status = MatchDecisionStatus.ONE_POLICY_CANDIDATE
        selected = candidates[0]
        diagnostics = ()
    elif unavailable:
        status = MatchDecisionStatus.UNAVAILABLE
        selected = None
        diagnostics = ("POLICY_COMPONENTS_INCOMPLETE",)
    else:
        status = MatchDecisionStatus.NO_CANDIDATE
        selected = None
        diagnostics = ()
    publication = (
        selected is not None
        and next(item for item in decisions if item.selection is selected).publication_eligible
    )
    return MatchDecision(
        match_id,
        prediction_as_of,
        decisions,
        status,
        candidates,
        selected,
        publication,
        diagnostics,
    )


def _orchestrate_selection(
    result: MarketEdgeResult,
    edge: SelectionEdge,
    agreement: AgreementResult,
    signals: tuple[ModelSignal, ...],
    *,
    data_quality_score: Decimal | None,
    data_quality_diagnostics: tuple[str, ...],
    calibration_confidence: Decimal | None,
    stability_score: Decimal | None,
    market_quality: OddsQualityStatus,
    probability_source: str,
    policy: PredictionPolicyConfig,
) -> SelectionDecision:
    agreement_score = agreement_component_score(
        agreement.supporting_model_count, agreement.configured_model_count
    )
    components = (
        ComponentEvidence(
            "EDGE",
            policy.weights.edge,
            ComponentStatus.AVAILABLE,
            edge_component_score(edge.edge, policy),
        ),
        ComponentEvidence(
            "AGREEMENT", policy.weights.model_agreement, ComponentStatus.AVAILABLE, agreement_score
        ),
        _optional_component(
            "DATA_QUALITY",
            policy.weights.data_quality,
            data_quality_score,
            data_quality_diagnostics,
        ),
        _optional_component(
            "CALIBRATION",
            policy.weights.calibration_confidence,
            calibration_confidence,
            ("MODEL_PROBABILITY_UNCALIBRATED",) if calibration_confidence is None else (),
        ),
        _optional_component(
            "STABILITY",
            policy.weights.market_stability,
            stability_score,
            ("STABILITY_SCORE_NOT_DEFINED",) if stability_score is None else (),
        ),
    )
    available = sum(item.status is ComponentStatus.AVAILABLE for item in components)
    completeness = (
        BetScoreCompleteness.COMPLETE
        if available == len(components)
        else BetScoreCompleteness.UNAVAILABLE
        if available == 0
        else BetScoreCompleteness.PARTIAL
    )
    candidate = MarketCandidate(
        result.match_id,
        result.market,
        edge.selection,
        None,
        edge.model_probability,
        edge.market_probability,
        edge.decimal_odds,
        agreement.supporting_model_count,
        agreement.configured_model_count,
        data_quality_score,
        calibration_confidence,
        stability_score,
        AnalysisAvailability.AVAILABLE,
    )
    evaluated = evaluate_candidate(candidate, policy)
    gates = _gates(
        result,
        edge,
        agreement,
        evaluated.bet_score,
        completeness,
        data_quality_score,
        market_quality,
        policy,
    )
    by_gate = {item.gate: item.status for item in gates}
    mandatory_simulation = (
        PolicyGate.EDGE_GATE,
        PolicyGate.BET_SCORE_GATE,
        PolicyGate.AGREEMENT_GATE,
        PolicyGate.DATA_QUALITY_GATE,
        PolicyGate.MARKET_QUALITY_GATE,
        PolicyGate.COMPONENT_COMPLETENESS_GATE,
        PolicyGate.ODDS_PRESENTATION_GATE,
    )
    non_edge_watchlist_gates = (
        PolicyGate.AGREEMENT_GATE,
        PolicyGate.DATA_QUALITY_GATE,
        PolicyGate.MARKET_QUALITY_GATE,
        PolicyGate.COMPONENT_COMPLETENESS_GATE,
        PolicyGate.ODDS_PRESENTATION_GATE,
    )
    if edge.edge < policy.edge_watchlist_threshold:
        decision = QualityClass.NO_BET
    elif edge.edge < policy.edge_publication_threshold:
        watchlist_score = (
            evaluated.bet_score is not None
            and evaluated.bet_score >= policy.score_boundaries.watchlist
        )
        decision = (
            QualityClass.WATCHLIST
            if watchlist_score
            and all(by_gate[gate] is GateStatus.PASS for gate in non_edge_watchlist_gates)
            else QualityClass.NO_BET
        )
    elif evaluated.publication_eligible and all(
        by_gate[gate] is GateStatus.PASS for gate in mandatory_simulation
    ):
        decision = evaluated.quality_class
    else:
        decision = QualityClass.NO_BET
    publication = decision in {
        QualityClass.PICK,
        QualityClass.STRONG_PICK,
        QualityClass.ELITE_PICK,
    } and all(item.status is GateStatus.PASS for item in gates)
    blockers = tuple(item.diagnostic for item in gates if item.status is not GateStatus.PASS)
    signal_statuses = {item.model_family: item.signal_status for item in signals}
    lineage_edge = edge
    return SelectionDecision(
        result.match_id,
        result.prediction_as_of,
        result.market,
        edge.selection,
        probability_source,
        result.model_version,
        edge.model_probability,
        signal_statuses.get(ModelFamily.POISSON),
        signal_statuses.get(ModelFamily.ELO),
        signal_statuses.get(ModelFamily.FORM),
        agreement.supporting_model_count,
        agreement.usable_model_count,
        agreement.configured_model_count,
        by_gate[PolicyGate.AGREEMENT_GATE],
        data_quality_score,
        data_quality_diagnostics,
        edge.decimal_odds,
        edge.market_probability,
        edge.edge,
        result.observation_role.value,
        result.timing_semantics,
        result.observed_at,
        result.comparison_status,
        market_quality,
        MarketLineage(
            lineage_edge.source_match_provider_ref_id,
            lineage_edge.source_staging_row_id,
            lineage_edge.source_field,
            result.mapping_version,
            result.normalization_version,
            result.quality_policy_version,
        ),
        components,
        evaluated.bet_score,
        completeness,
        evaluated.quality_class if evaluated.bet_score is not None else None,
        gates,
        decision,
        publication,
        blockers,
        tuple(dict.fromkeys((*result.diagnostics, *data_quality_diagnostics))),
    )


def _gates(
    result: MarketEdgeResult,
    edge: SelectionEdge,
    agreement: AgreementResult,
    bet_score: Decimal | None,
    completeness: BetScoreCompleteness,
    data_quality_score: Decimal | None,
    market_quality: OddsQualityStatus,
    policy: PredictionPolicyConfig,
) -> tuple[GateResult, ...]:
    exact_legal = (
        result.comparison_status is MarketComparisonStatus.EXACT_TIME_COMPARISON
        and result.timing_semantics is TimingSemantics.EXACT
        and result.observed_at is not None
        and result.observed_at <= result.prediction_as_of
    )
    odds_band = classify_odds(edge.decimal_odds, policy)
    odds_pass = odds_band not in {
        OddsBand.BELOW_DISPLAY_MINIMUM,
        OddsBand.ABOVE_V1_MAIN_MAX,
    }
    return (
        _gate(
            PolicyGate.EDGE_GATE,
            edge.edge >= policy.edge_publication_threshold,
            "EDGE_BELOW_PICK_THRESHOLD",
        ),
        GateResult(
            PolicyGate.BET_SCORE_GATE,
            GateStatus.UNAVAILABLE
            if bet_score is None
            else GateStatus.PASS
            if bet_score >= policy.score_boundaries.pick
            else GateStatus.FAIL,
            "BET_SCORE_UNAVAILABLE" if bet_score is None else "BET_SCORE_BELOW_PICK_THRESHOLD",
        ),
        _gate(
            PolicyGate.AGREEMENT_GATE,
            agreement.sufficient_usable_models and agreement.meets_configured_agreement_ratio,
            "AGREEMENT_BELOW_3_OF_4",
        ),
        GateResult(
            PolicyGate.DATA_QUALITY_GATE,
            GateStatus.UNAVAILABLE
            if data_quality_score is None
            else GateStatus.PASS
            if data_quality_score >= policy.minimum_data_quality_score
            else GateStatus.FAIL,
            "DATA_QUALITY_UNAVAILABLE"
            if data_quality_score is None
            else "DATA_QUALITY_BELOW_MINIMUM",
        ),
        _gate(
            PolicyGate.MARKET_TEMPORAL_GATE,
            exact_legal,
            "MARKET_EXACT_TIME_NOT_PROVEN"
            if result.comparison_status is MarketComparisonStatus.ROLE_ONLY_COMPARISON
            else "MARKET_OBSERVED_AFTER_AS_OF",
        ),
        _gate(
            PolicyGate.MARKET_QUALITY_GATE,
            market_quality is OddsQualityStatus.ELIGIBLE,
            "MARKET_QUALITY_NOT_ELIGIBLE",
        ),
        _gate(
            PolicyGate.COMPONENT_COMPLETENESS_GATE,
            completeness is BetScoreCompleteness.COMPLETE,
            "POLICY_COMPONENTS_INCOMPLETE",
        ),
        _gate(PolicyGate.ODDS_PRESENTATION_GATE, odds_pass, "ODDS_PRESENTATION_POLICY_BLOCK"),
    )


def _gate(gate: PolicyGate, passed: bool, failure: str) -> GateResult:
    return GateResult(
        gate, GateStatus.PASS if passed else GateStatus.FAIL, "PASS" if passed else failure
    )


def _optional_component(
    name: str, weight: Decimal, score: Decimal | None, diagnostics: tuple[str, ...]
) -> ComponentEvidence:
    return ComponentEvidence(
        name,
        weight,
        ComponentStatus.AVAILABLE if score is not None else ComponentStatus.UNAVAILABLE,
        score,
        diagnostics,
    )


def _validate_match_inputs(
    result: MarketEdgeResult,
    agreements: tuple[AgreementResult, ...],
    signals: tuple[ModelSignal, ...],
) -> None:
    if result.market is not MarketFamily.MATCH_RESULT:
        raise OrchestrationError("TASK 20 supports MATCH_RESULT only")
    selections = tuple(item.candidate_selection for item in agreements)
    if selections != tuple(item.selection for item in result.edges):
        raise OrchestrationError("agreements must align with edge selection order")
    if any(
        item.match_id != result.match_id or item.market is not result.market for item in agreements
    ):
        raise OrchestrationError("agreement identity does not match market evidence")
    if any(
        item.match_id != result.match_id or item.market is not result.market for item in signals
    ):
        raise OrchestrationError("signal identity does not match market evidence")
    families = tuple(item.model_family for item in signals)
    if len(set(families)) != len(families):
        raise OrchestrationError("signals must contain at most one item per family")


def _primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value


def _as_dict(value: object) -> dict[str, Any]:
    result = _primitive(value)
    if not isinstance(result, dict):  # pragma: no cover
        raise TypeError("orchestration contract must serialize to a mapping")
    return result
