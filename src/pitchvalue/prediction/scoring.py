"""Pure numeric helpers for edge and Bet Score calculation."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pitchvalue.prediction.config import PredictionPolicyConfig
from pitchvalue.prediction.contracts import (
    ContractValidationError,
    QualityClass,
    require_probability,
    require_score,
)


class EdgeDisposition(StrEnum):
    NO_BET = "NO_BET"
    WATCHLIST = "WATCHLIST"
    PUBLICATION_CANDIDATE = "PUBLICATION_CANDIDATE"


def calculate_edge(model_probability: Decimal, market_implied_probability: Decimal) -> Decimal:
    """Return decimal-fraction percentage-point edge, never relative uplift."""
    require_probability(model_probability, "model_probability")
    require_probability(market_implied_probability, "market_implied_probability")
    return model_probability - market_implied_probability


def classify_edge(edge: Decimal, policy: PredictionPolicyConfig) -> EdgeDisposition:
    if edge < policy.edge_watchlist_threshold:
        return EdgeDisposition.NO_BET
    if edge < policy.edge_publication_threshold:
        return EdgeDisposition.WATCHLIST
    return EdgeDisposition.PUBLICATION_CANDIDATE


def _interpolate(
    value: Decimal,
    start_x: Decimal,
    end_x: Decimal,
    start_y: Decimal,
    end_y: Decimal,
) -> Decimal:
    position = (value - start_x) / (end_x - start_x)
    return start_y + position * (end_y - start_y)


def edge_component_score(edge: Decimal, policy: PredictionPolicyConfig) -> Decimal:
    """Apply the explicit initial heuristic piecewise-linear edge mapping."""
    mapping = policy.edge_score_mapping
    if edge <= 0:
        return Decimal(0)
    if edge < policy.edge_watchlist_threshold:
        return _interpolate(
            edge,
            Decimal(0),
            policy.edge_watchlist_threshold,
            Decimal(0),
            mapping.watchlist_score,
        )
    if edge < policy.edge_publication_threshold:
        return _interpolate(
            edge,
            policy.edge_watchlist_threshold,
            policy.edge_publication_threshold,
            mapping.watchlist_score,
            mapping.publication_score,
        )
    if edge < mapping.maximum_edge:
        return _interpolate(
            edge,
            policy.edge_publication_threshold,
            mapping.maximum_edge,
            mapping.publication_score,
            mapping.maximum_score,
        )
    return mapping.maximum_score


def agreement_ratio(agreement_count: int, total_model_count: int) -> Decimal | None:
    if (
        isinstance(agreement_count, bool)
        or isinstance(total_model_count, bool)
        or not isinstance(agreement_count, int)
        or not isinstance(total_model_count, int)
        or agreement_count < 0
        or total_model_count < 0
        or agreement_count > total_model_count
    ):
        raise ContractValidationError("model agreement counts are invalid")
    if total_model_count == 0:
        return None
    return Decimal(agreement_count) / Decimal(total_model_count)


def agreement_component_score(agreement_count: int, total_model_count: int) -> Decimal | None:
    ratio = agreement_ratio(agreement_count, total_model_count)
    return ratio * Decimal(100) if ratio is not None else None


def calculate_bet_score(
    *,
    edge_score: Decimal,
    agreement_score: Decimal,
    data_quality_score: Decimal,
    calibration_confidence: Decimal,
    market_stability_score: Decimal,
    policy: PredictionPolicyConfig,
) -> Decimal:
    """Combine validated normalized components using configured weights."""
    components = {
        "edge_score": edge_score,
        "agreement_score": agreement_score,
        "data_quality_score": data_quality_score,
        "calibration_confidence": calibration_confidence,
        "market_stability_score": market_stability_score,
    }
    for field_name, value in components.items():
        require_score(value, field_name)
    weights = policy.weights
    return (
        edge_score * weights.edge
        + agreement_score * weights.model_agreement
        + data_quality_score * weights.data_quality
        + calibration_confidence * weights.calibration_confidence
        + market_stability_score * weights.market_stability
    )


def classify_bet_score(score: Decimal, policy: PredictionPolicyConfig) -> QualityClass:
    """Classify an exact 0–100 Bet Score at canonical boundaries."""
    require_score(score, "bet_score")
    boundaries = policy.score_boundaries
    if score < boundaries.watchlist:
        return QualityClass.NO_BET
    if score < boundaries.pick:
        return QualityClass.WATCHLIST
    if score < boundaries.strong_pick:
        return QualityClass.PICK
    if score < boundaries.elite_pick:
        return QualityClass.STRONG_PICK
    return QualityClass.ELITE_PICK
