"""Read-only V1 prediction routes backed exclusively by TASK 21 persistence."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import Connection

from pitchvalue.api.dependencies import get_connection
from pitchvalue.api.prediction_models import PredictionListResponse
from pitchvalue.api.predictions import public_prediction_list
from pitchvalue.prediction.repository import current_predictions, published_predictions

router = APIRouter(tags=["predictions"])


@router.get(
    "/matches/{match_id}/predictions",
    response_model=PredictionListResponse,
    summary="Current published predictions for one match",
)
def match_predictions(
    match_id: Annotated[int, Path(gt=0)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> PredictionListResponse:
    records = current_predictions(connection, [match_id], publication_only=True)
    return public_prediction_list(records)


@router.get(
    "/predictions",
    response_model=PredictionListResponse,
    summary="Current publication-eligible predictions",
)
def current_published_predictions(
    connection: Annotated[Connection, Depends(get_connection)],
    match_id: Annotated[list[int] | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PredictionListResponse:
    records = published_predictions(
        connection,
        match_ids=match_id,
        limit=limit,
        offset=offset,
    )
    return public_prediction_list(records)
