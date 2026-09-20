"""Read-only public fixture repository and safe response projection."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Connection, RowMapping, text

from pitchvalue.api.fixture_models import (
    DataAvailabilityState,
    FinalCheckState,
    FixtureSummaryResponse,
    FreshnessResponse,
    MarketAvailabilityResponse,
    MatchDetailResponse,
    MatchStatisticsResponse,
    PublicAnalysisState,
    PublicationState,
    PublicMarketState,
    ScoreResponse,
    TeamResponse,
    TodayFixturesResponse,
    TodayState,
)
from pitchvalue.api.predictions import public_prediction
from pitchvalue.operations.metadata import (
    FixtureRefreshMetadata,
    FreshnessState,
    load_fixture_refresh_metadata,
)
from pitchvalue.prediction.persistence import PersistedPrediction
from pitchvalue.prediction.repository import current_predictions

PUBLIC_FIXTURE_CONTRACT_VERSION = "public_fixture_contract_v1"
DEFAULT_FIXTURE_TIMEZONE = "Europe/Istanbul"
FIXTURE_STALE_AFTER = timedelta(days=5)

_MARKETS: tuple[tuple[str, Decimal | None], ...] = (
    ("1X2", None),
    ("O/U 1.5", Decimal("1.5")),
    ("O/U 2.5", Decimal("2.5")),
    ("BTTS", None),
    ("Double Chance", None),
    ("Home Team Goals O/U 0.5", Decimal("0.5")),
    ("Home Team Goals O/U 1.5", Decimal("1.5")),
    ("Away Team Goals O/U 0.5", Decimal("0.5")),
    ("Away Team Goals O/U 1.5", Decimal("1.5")),
)

_FIXTURE_COLUMNS = """
m.match_id,c.canonical_name AS competition,m.kickoff_at_utc,
ht.canonical_name AS home_team,at.canonical_name AS away_team,m.status,
m.home_score,m.away_score,m.result,m.updated_at,
(SELECT max(ser.last_seen_at) FROM source_entity_references ser
 WHERE ser.entity_type='FIXTURE' AND ser.canonical_match_id=m.match_id) AS source_last_seen_at
"""


def today_fixtures(
    connection: Connection,
    *,
    fixture_date: date,
    timezone_name: str = DEFAULT_FIXTURE_TIMEZONE,
    now: datetime | None = None,
) -> TodayFixturesResponse:
    zone = _zone(timezone_name)
    checked_at = now or datetime.now(UTC)
    _aware(checked_at)
    rows = connection.execute(
        text(
            f"""SELECT {_FIXTURE_COLUMNS} FROM matches m
            JOIN competitions c ON c.competition_id=m.competition_id
            JOIN teams ht ON ht.team_id=m.home_team_id
            JOIN teams at ON at.team_id=m.away_team_id
            WHERE (m.kickoff_at_utc AT TIME ZONE :timezone)::date=:fixture_date
            ORDER BY m.kickoff_at_utc,m.match_id"""
        ),
        {"timezone": zone.key, "fixture_date": fixture_date},
    ).mappings()
    materialized = tuple(rows)
    match_ids = [int(row["match_id"]) for row in materialized]
    public = current_predictions(connection, match_ids, publication_only=True)
    grouped = _group_predictions(public)
    refresh = load_fixture_refresh_metadata(connection, now=checked_at)
    fixtures = tuple(
        _summary(row, grouped.get(int(row["match_id"]), ()), refresh, checked_at)
        for row in materialized
    )
    if refresh.state is FreshnessState.FAILED:
        state = TodayState.PROVIDER_UNAVAILABLE
    elif any(item.data_availability is DataAvailabilityState.STALE for item in fixtures):
        state = TodayState.STALE_FIXTURE_DATA
    else:
        state = TodayState.FIXTURES_AVAILABLE if fixtures else TodayState.NO_FIXTURES
    return TodayFixturesResponse(
        fixture_date=fixture_date,
        timezone=zone.key,
        state=state,
        fixtures=fixtures,
        count=len(fixtures),
    )


def match_detail(
    connection: Connection,
    match_id: int,
    *,
    now: datetime | None = None,
) -> MatchDetailResponse | None:
    checked_at = now or datetime.now(UTC)
    _aware(checked_at)
    row = (
        connection.execute(
            text(
                f"""SELECT {_FIXTURE_COLUMNS},
                ms.home_shots,ms.away_shots,ms.home_shots_on_target,
                ms.away_shots_on_target,ms.home_possession,ms.away_possession,
                ms.home_corners,ms.away_corners
                FROM matches m
                JOIN competitions c ON c.competition_id=m.competition_id
                JOIN teams ht ON ht.team_id=m.home_team_id
                JOIN teams at ON at.team_id=m.away_team_id
                LEFT JOIN LATERAL (
                    SELECT * FROM match_statistics candidate
                    WHERE candidate.match_id=m.match_id
                    ORDER BY candidate.updated_at DESC,candidate.match_statistics_id DESC LIMIT 1
                ) ms ON true
                WHERE m.match_id=:match_id"""
            ),
            {"match_id": match_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    public = current_predictions(connection, [match_id], publication_only=True)
    refresh = load_fixture_refresh_metadata(connection, now=checked_at)
    summary = _summary(row, public, refresh, checked_at)
    score = (
        ScoreResponse(
            home=int(row["home_score"]), away=int(row["away_score"]), result=row["result"]
        )
        if row["home_score"] is not None and row["away_score"] is not None
        else None
    )
    statistics = _statistics(row)
    markets = market_availability(public)
    return MatchDetailResponse(
        **summary.model_dump(),
        score=score,
        statistics=statistics,
        statistics_state=(
            DataAvailabilityState.AVAILABLE
            if statistics is not None
            else DataAvailabilityState.DATA_INSUFFICIENT
        ),
        markets=markets,
        public_predictions=tuple(public_prediction(item) for item in public),
    )


def market_availability(
    public_predictions: Sequence[PersistedPrediction],
    *,
    fallback_state: PublicMarketState = PublicMarketState.NOT_PUBLISHED,
) -> tuple[MarketAvailabilityResponse, ...]:
    match_result = tuple(item for item in public_predictions if item.market == "match_result")
    score = next((item.bet_score for item in match_result if item.bet_score is not None), None)
    completeness = next((item.bet_score_completeness for item in match_result), "UNAVAILABLE")
    if match_result and score is not None and completeness == "COMPLETE":
        state = PublicMarketState.AVAILABLE_PUBLIC
    elif match_result:
        state = PublicMarketState.SCORE_INCOMPLETE
    else:
        state = fallback_state
    return tuple(
        MarketAvailabilityResponse(
            market=name,
            line=line,
            state=state if name == "1X2" else fallback_state,
            score=score if name == "1X2" else None,
            score_completeness=completeness if name == "1X2" else "UNAVAILABLE",
        )
        for name, line in _MARKETS
    )


def _summary(
    row: RowMapping,
    public: Sequence[PersistedPrediction],
    refresh: FixtureRefreshMetadata,
    checked_at: datetime,
) -> FixtureSummaryResponse:
    source_seen = row["source_last_seen_at"]
    effective = source_seen or refresh.last_success_at
    if refresh.state is FreshnessState.FAILED:
        availability = DataAvailabilityState.PROVIDER_UNAVAILABLE
    elif (
        effective is not None and effective < checked_at - FIXTURE_STALE_AFTER
    ) or (
        row["status"] == "SCHEDULED" and row["kickoff_at_utc"] < checked_at - timedelta(minutes=15)
    ):
        availability = DataAvailabilityState.STALE
    else:
        availability = DataAvailabilityState.AVAILABLE
    public_state = (
        PublicAnalysisState.AVAILABLE_PUBLIC if public else PublicAnalysisState.NO_PUBLIC_ANALYSIS
    )
    publication = PublicationState.PICK if public else PublicationState.NO_PUBLIC_ANALYSIS
    return FixtureSummaryResponse(
        match_id=int(row["match_id"]),
        competition=str(row["competition"]),
        kickoff=row["kickoff_at_utc"],
        home_team=TeamResponse(name=str(row["home_team"])),
        away_team=TeamResponse(name=str(row["away_team"])),
        fixture_status=str(row["status"]),
        home_score=row["home_score"],
        away_score=row["away_score"],
        data_availability=availability,
        public_analysis=public_state,
        publication_state=publication,
        final_check=FinalCheckState.FINAL_CHECK_UNAVAILABLE,
        freshness=FreshnessResponse(
            state=refresh.state.value,
            source_last_seen_at=source_seen,
            fixture_refresh_at=refresh.last_success_at,
            evidence_source=refresh.evidence_source,
        ),
    )


def _statistics(row: RowMapping) -> MatchStatisticsResponse | None:
    names = (
        "home_shots",
        "away_shots",
        "home_shots_on_target",
        "away_shots_on_target",
        "home_possession",
        "away_possession",
        "home_corners",
        "away_corners",
    )
    if all(row[name] is None for name in names):
        return None
    return MatchStatisticsResponse(**{name: row[name] for name in names})


def _group_predictions(
    predictions: Sequence[PersistedPrediction],
) -> dict[int, tuple[PersistedPrediction, ...]]:
    grouped: dict[int, list[PersistedPrediction]] = {}
    for item in predictions:
        grouped.setdefault(item.match_id, []).append(item)
    return {key: tuple(value) for key, value in grouped.items()}


def _zone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise ValueError("unsupported fixture timezone") from error


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("evaluation time must be timezone-aware")
