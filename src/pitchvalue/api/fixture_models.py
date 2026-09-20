"""Additive, public-safe fixture and match-detail response contracts."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from pitchvalue.api.prediction_models import PublicPredictionResponse


class TodayState(StrEnum):
    FIXTURES_AVAILABLE = "FIXTURES_AVAILABLE"
    NO_FIXTURES = "NO_FIXTURES"
    STALE_FIXTURE_DATA = "STALE_FIXTURE_DATA"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class DataAvailabilityState(StrEnum):
    AVAILABLE = "AVAILABLE"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    STALE = "STALE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class PublicAnalysisState(StrEnum):
    AVAILABLE_PUBLIC = "AVAILABLE_PUBLIC"
    NO_PUBLIC_ANALYSIS = "NO_PUBLIC_ANALYSIS"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class PublicMarketState(StrEnum):
    AVAILABLE_PUBLIC = "AVAILABLE_PUBLIC"
    ANALYSIS_UNAVAILABLE = "ANALYSIS_UNAVAILABLE"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    SCORE_INCOMPLETE = "SCORE_INCOMPLETE"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    NOT_PUBLISHED = "NOT_PUBLISHED"


class FinalCheckState(StrEnum):
    CONFIRMED = "CONFIRMED"
    CHANGED = "CHANGED"
    WITHDRAWN = "WITHDRAWN"
    FINAL_CHECK_UNAVAILABLE = "FINAL_CHECK_UNAVAILABLE"


class PublicationState(StrEnum):
    PICK = "PICK"
    WATCHLIST = "WATCHLIST"
    NO_BET = "NO_BET"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    NO_PUBLIC_ANALYSIS = "NO_PUBLIC_ANALYSIS"


class FreshnessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: str
    source_last_seen_at: datetime | None
    fixture_refresh_at: datetime | None
    evidence_source: str


class TeamResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str


class ScoreResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    home: int
    away: int
    result: str | None


class MatchStatisticsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    home_shots: int | None
    away_shots: int | None
    home_shots_on_target: int | None
    away_shots_on_target: int | None
    home_possession: Decimal | None
    away_possession: Decimal | None
    home_corners: int | None
    away_corners: int | None


class MarketAvailabilityResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    market: str
    line: Decimal | None
    state: PublicMarketState
    score: Decimal | None = None
    score_completeness: str = "UNAVAILABLE"


class FixtureSummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    match_id: int
    competition: str
    kickoff: datetime
    home_team: TeamResponse
    away_team: TeamResponse
    fixture_status: str
    home_score: int | None = None
    away_score: int | None = None
    data_availability: DataAvailabilityState
    public_analysis: PublicAnalysisState
    publication_state: PublicationState
    final_check: FinalCheckState
    freshness: FreshnessResponse


class TodayFixturesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    fixture_date: date
    timezone: str
    state: TodayState
    fixtures: tuple[FixtureSummaryResponse, ...]
    count: int


class MatchDetailResponse(FixtureSummaryResponse):
    score: ScoreResponse | None
    statistics: MatchStatisticsResponse | None
    statistics_state: DataAvailabilityState
    markets: tuple[MarketAvailabilityResponse, ...]
    public_predictions: tuple[PublicPredictionResponse, ...]
