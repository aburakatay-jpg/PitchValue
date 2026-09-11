"""Persistence-only mapping service for public prediction responses."""

from __future__ import annotations

from pitchvalue.api.prediction_models import (
    PredictionComponentResponse,
    PredictionListResponse,
    PublicPredictionResponse,
)
from pitchvalue.prediction.persistence import PersistedPrediction


def public_prediction(record: PersistedPrediction) -> PublicPredictionResponse:
    """Project an already persisted record without recalculating its evidence."""
    return PublicPredictionResponse(
        match_id=record.match_id,
        market=record.market,
        selection=record.selection,
        model_probability=record.model_probability,
        probability_source=record.probability_source,
        prediction_as_of=record.prediction_as_of,
        generated_at=record.generated_at,
        decimal_odds=record.decimal_odds,
        no_vig_market_probability=record.no_vig_market_probability,
        edge=record.edge,
        observation_role=record.observation_role,
        timing_semantics=record.timing_semantics,
        market_observed_at=record.market_observed_at,
        comparison_status=record.comparison_status,
        market_quality=record.market_quality,
        policy_decision=record.policy_decision,
        score_class=record.score_class,
        bet_score=record.bet_score,
        bet_score_completeness=record.bet_score_completeness,
        publication_eligible=record.publication_eligible,
        components=tuple(
            PredictionComponentResponse(
                name=str(component["name"]),
                status=str(component["status"]),
                score=(None if component["score"] is None else component["score"]),
            )
            for component in record.components
        ),
        blockers=record.blockers,
        model_version=record.model_version,
        orchestrator_version=record.orchestrator_version,
        policy_version=record.policy_version,
    )


def public_prediction_list(
    records: tuple[PersistedPrediction, ...],
) -> PredictionListResponse:
    predictions = tuple(public_prediction(record) for record in records)
    return PredictionListResponse(predictions=predictions, count=len(predictions))
