"""Explicit public response schemas for persisted predictions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PredictionComponentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: str
    score: Decimal | None


class PublicPredictionResponse(BaseModel):
    """Consumer-safe projection with no persistence IDs or ingestion lineage."""

    model_config = ConfigDict(frozen=True)

    match_id: int
    market: str
    selection: str
    model_probability: Decimal
    probability_source: str
    prediction_as_of: datetime
    generated_at: datetime
    decimal_odds: Decimal
    no_vig_market_probability: Decimal
    edge: Decimal
    observation_role: str
    timing_semantics: str
    market_observed_at: datetime | None
    comparison_status: str
    market_quality: str
    policy_decision: str
    score_class: str | None
    bet_score: Decimal | None
    bet_score_completeness: str
    publication_eligible: bool
    components: tuple[PredictionComponentResponse, ...]
    blockers: tuple[str, ...]
    model_version: str
    orchestrator_version: str
    policy_version: str


class PredictionListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    predictions: tuple[PublicPredictionResponse, ...]
    count: int
