"""Read-only V1 fixture and match-detail routes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import Connection

from pitchvalue.api.dependencies import get_connection
from pitchvalue.api.errors import ApiError, ErrorCode
from pitchvalue.api.fixture_models import MatchDetailResponse, TodayFixturesResponse
from pitchvalue.api.fixtures import DEFAULT_FIXTURE_TIMEZONE, match_detail, today_fixtures

router = APIRouter(tags=["fixtures"])


@router.get("/fixtures/today", response_model=TodayFixturesResponse)
def fixtures_today(
    connection: Annotated[Connection, Depends(get_connection)],
    fixture_date: Annotated[date | None, Query(alias="date")] = None,
    timezone: Annotated[str, Query(min_length=1, max_length=64)] = DEFAULT_FIXTURE_TIMEZONE,
) -> TodayFixturesResponse:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR, "Unsupported timezone") from error
    resolved_date = fixture_date or datetime.now(zone).date()
    return today_fixtures(
        connection,
        fixture_date=resolved_date,
        timezone_name=zone.key,
    )


@router.get("/matches/{match_id}", response_model=MatchDetailResponse)
def public_match_detail(
    match_id: Annotated[int, Path(gt=0)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> MatchDetailResponse:
    result = match_detail(connection, match_id)
    if result is None:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Fixture not found")
    return result
