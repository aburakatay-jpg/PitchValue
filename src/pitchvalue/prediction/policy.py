"""Pure publication policy evaluation for analyzed V1 market candidates."""

from __future__ import annotations

from decimal import Decimal

from pitchvalue.prediction.config import DEFAULT_POLICY, PredictionPolicyConfig
from pitchvalue.prediction.contracts import (
    AnalysisAvailability,
    FailureState,
    MarketCandidate,
    OddsBand,
    PolicyEvaluation,
    PolicyReason,
    PublicationRole,
    QualityClass,
    RankingInputs,
)
from pitchvalue.prediction.scoring import (
    EdgeDisposition,
    agreement_component_score,
    calculate_bet_score,
    calculate_edge,
    classify_bet_score,
    classify_edge,
    edge_component_score,
)


def classify_odds(decimal_odds: Decimal, policy: PredictionPolicyConfig) -> OddsBand:
    if decimal_odds < policy.odds_display_minimum:
        return OddsBand.BELOW_DISPLAY_MINIMUM
    if decimal_odds < policy.low_odds_upper_bound:
        return OddsBand.LOW_ODDS
    if decimal_odds <= policy.ideal_odds_maximum:
        return OddsBand.IDEAL
    if decimal_odds <= policy.v1_main_maximum_odds:
        return OddsBand.HIGHER_RISK
    return OddsBand.ABOVE_V1_MAIN_MAX


def _failure_state(
    candidate: MarketCandidate,
    agreement: Decimal | None,
    publication_eligible: bool,
) -> FailureState | None:
    if (
        candidate.analysis_availability is AnalysisAvailability.UNAVAILABLE
        or candidate.calibration_confidence is None
        or candidate.market_stability_score is None
        or agreement is None
    ):
        return FailureState.ANALYSIS_UNAVAILABLE
    if candidate.data_quality_score is None:
        return FailureState.DATA_INSUFFICIENT
    if not publication_eligible:
        return FailureState.NO_BET
    return None


def evaluate_candidate(
    candidate: MarketCandidate,
    policy: PredictionPolicyConfig = DEFAULT_POLICY,
) -> PolicyEvaluation:
    """Apply deterministic classification and hard publication gates."""
    edge = calculate_edge(candidate.model_probability, candidate.market_implied_probability)
    edge_disposition = classify_edge(edge, policy)
    agreement = candidate.agreement_ratio
    agreement_score = agreement_component_score(
        candidate.model_agreement_count, candidate.model_count
    )
    odds_band = classify_odds(candidate.decimal_odds, policy)
    reasons: list[PolicyReason] = []

    if candidate.analysis_availability is AnalysisAvailability.UNAVAILABLE:
        reasons.append(PolicyReason.ANALYSIS_UNAVAILABLE)
    if candidate.data_quality_score is None:
        reasons.append(PolicyReason.DATA_QUALITY_MISSING)
    if candidate.calibration_confidence is None:
        reasons.append(PolicyReason.CALIBRATION_CONFIDENCE_MISSING)
    if candidate.market_stability_score is None:
        reasons.append(PolicyReason.MARKET_STABILITY_MISSING)
    if agreement is None or agreement < policy.minimum_agreement_ratio:
        reasons.append(PolicyReason.MODEL_AGREEMENT_INSUFFICIENT)
    if edge_disposition is EdgeDisposition.NO_BET:
        reasons.append(PolicyReason.EDGE_BELOW_MINIMUM)
    elif edge_disposition is EdgeDisposition.WATCHLIST:
        reasons.append(PolicyReason.EDGE_WATCHLIST_ONLY)
    if (
        candidate.data_quality_score is not None
        and candidate.data_quality_score < policy.minimum_data_quality_score
    ):
        reasons.append(PolicyReason.DATA_QUALITY_INSUFFICIENT)

    bet_score: Decimal | None = None
    quality_class = QualityClass.NO_BET
    can_score = (
        candidate.analysis_availability is AnalysisAvailability.AVAILABLE
        and agreement_score is not None
        and candidate.data_quality_score is not None
        and candidate.calibration_confidence is not None
        and candidate.market_stability_score is not None
    )
    if can_score:
        assert agreement_score is not None
        assert candidate.data_quality_score is not None
        assert candidate.calibration_confidence is not None
        assert candidate.market_stability_score is not None
        bet_score = calculate_bet_score(
            edge_score=edge_component_score(edge, policy),
            agreement_score=agreement_score,
            data_quality_score=candidate.data_quality_score,
            calibration_confidence=candidate.calibration_confidence,
            market_stability_score=candidate.market_stability_score,
            policy=policy,
        )
        quality_class = classify_bet_score(bet_score, policy)
        if bet_score < policy.score_boundaries.pick:
            reasons.append(PolicyReason.BET_SCORE_BELOW_PUBLICATION)

    base_gates_pass = (
        can_score
        and bet_score is not None
        and edge >= policy.edge_publication_threshold
        and bet_score >= policy.score_boundaries.pick
        and agreement is not None
        and agreement >= policy.minimum_agreement_ratio
        and candidate.data_quality_score is not None
        and candidate.data_quality_score >= policy.minimum_data_quality_score
    )
    eligible_roles: tuple[PublicationRole, ...] = ()
    if odds_band is OddsBand.BELOW_DISPLAY_MINIMUM:
        reasons.append(PolicyReason.ODDS_BELOW_DISPLAY_MINIMUM)
    elif odds_band is OddsBand.LOW_ODDS:
        exceptional_signal = (
            base_gates_pass
            and bet_score is not None
            and bet_score >= policy.low_odds_exception_bet_score
            and edge >= policy.low_odds_exception_edge
            and agreement is not None
            and agreement >= policy.low_odds_exception_agreement_ratio
        )
        if exceptional_signal:
            eligible_roles = (PublicationRole.ALTERNATIVE,)
        else:
            reasons.append(PolicyReason.LOW_ODDS_REQUIRES_STRONGER_SIGNAL)
    elif odds_band in {OddsBand.IDEAL, OddsBand.HIGHER_RISK} and base_gates_pass:
        eligible_roles = (PublicationRole.MAIN, PublicationRole.ALTERNATIVE)
    elif odds_band is OddsBand.ABOVE_V1_MAIN_MAX:
        reasons.append(PolicyReason.ODDS_ABOVE_V1_MAIN_MAX)

    publication_eligible = bool(eligible_roles)
    if publication_eligible:
        reasons.append(PolicyReason.PUBLISHABLE)
    ranking_inputs = None
    if (
        bet_score is not None
        and agreement is not None
        and candidate.market_stability_score is not None
    ):
        ranking_inputs = RankingInputs(
            bet_score=bet_score,
            edge=edge,
            agreement_ratio=agreement,
            market_stability_score=candidate.market_stability_score,
            decimal_odds=candidate.decimal_odds,
            odds_band=odds_band,
        )
    return PolicyEvaluation(
        match_id=candidate.match_id,
        market=candidate.market,
        selection=candidate.selection,
        line=candidate.line,
        quality_class=quality_class,
        bet_score=bet_score,
        publication_eligible=publication_eligible,
        eligible_roles=eligible_roles,
        reasons=tuple(reasons),
        edge=edge,
        agreement_ratio=agreement,
        odds_band=odds_band,
        failure_state=_failure_state(candidate, agreement, publication_eligible),
        ranking_inputs=ranking_inputs,
        correlation_group=candidate.correlation_group,
    )
