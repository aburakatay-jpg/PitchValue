"""User-owned references to immutable canonical prediction evidence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Connection, RowMapping, text

from pitchvalue.prediction.contracts import MarketFamily, Selection
from pitchvalue.product_services.settlement import (
    CanonicalResult,
    SettlementError,
    SettlementOutcome,
    settle,
)


class TrackingError(ValueError):
    """Expected tracking validation or ownership failure."""


class TrackingStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SETTLED = "SETTLED"
    REMOVED = "REMOVED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class SavedSelection:
    saved_selection_id: str
    user_id: str
    match_id: int
    prediction_snapshot_id: int | None
    market: str
    selection: str
    line: Decimal | None
    saved_decimal_odds: Decimal | None
    stake: Decimal | None
    currency: str | None
    tracking_status: TrackingStatus
    outcome: SettlementOutcome | None
    created_at: datetime


@dataclass(frozen=True)
class Performance:
    tracked: int
    wins: int
    losses: int
    voids: int
    withdrawn: int
    total_stake: Decimal | None
    net_return: Decimal | None
    roi: Decimal | None


def save_public_selection(
    connection: Connection,
    *,
    user_id: str,
    prediction_snapshot_id: int,
    line: Decimal | None = None,
    saved_decimal_odds: Decimal | None = None,
    stake: Decimal | None = None,
    currency: str | None = None,
    now: datetime | None = None,
) -> SavedSelection:
    created_at = now or datetime.now(UTC)
    if stake is not None and (stake <= 0 or currency is None or len(currency.strip()) != 3):
        raise TrackingError("positive stake requires ISO currency")
    if stake is None and currency is not None:
        raise TrackingError("currency requires stake")
    if saved_decimal_odds is not None and saved_decimal_odds <= 1:
        raise TrackingError("saved decimal odds must exceed one")
    saved_id = str(uuid.uuid4())
    prediction = (
        connection.execute(
            text(
                "SELECT match_id,market,selection FROM prediction_snapshots "
                "WHERE prediction_snapshot_id=:prediction_id AND record_status='active' "
                "AND publication_eligible=true"
            ),
            {"prediction_id": prediction_snapshot_id},
        )
        .mappings()
        .one_or_none()
    )
    if prediction is None:
        raise TrackingError("public prediction is unavailable")
    try:
        market_family = MarketFamily(str(prediction["market"]))
    except ValueError as error:
        raise TrackingError("unsupported tracked market") from error
    total_markets = {
        MarketFamily.TOTAL_GOALS,
        MarketFamily.HOME_TEAM_TOTAL,
        MarketFamily.AWAY_TEAM_TOTAL,
    }
    if market_family in total_markets and line not in {
        Decimal("0.5"),
        Decimal("1.5"),
        Decimal("2.5"),
    }:
        raise TrackingError("tracked total market requires a supported line")
    if market_family not in total_markets and line is not None:
        raise TrackingError("tracked market does not accept a line")
    existing = (
        connection.execute(
            text(
                "SELECT * FROM saved_selections WHERE user_id=:user_id AND match_id=:match_id "
                "AND market=:market AND selection=:selection "
                "AND COALESCE(line,-999)=COALESCE(:line,-999) AND tracking_status='ACTIVE'"
            ),
            {
                "user_id": user_id,
                "match_id": int(prediction["match_id"]),
                "market": str(prediction["market"]),
                "selection": str(prediction["selection"]),
                "line": line,
            },
        )
        .mappings()
        .one_or_none()
    )
    if existing is not None:
        return _record(existing)
    connection.execute(
        text(
            "INSERT INTO saved_selections "
            "(saved_selection_id,user_id,match_id,prediction_snapshot_id,market,selection,"
            "line,saved_decimal_odds,stake,currency,created_at) VALUES "
            "(:saved_id,:user_id,:match_id,:prediction_id,:market,:selection,"
            ":line,:odds,:stake,:currency,:created_at)"
        ),
        {
            "saved_id": saved_id,
            "user_id": user_id,
            "match_id": int(prediction["match_id"]),
            "prediction_id": prediction_snapshot_id,
            "market": str(prediction["market"]),
            "selection": str(prediction["selection"]),
            "line": line,
            "odds": saved_decimal_odds,
            "stake": stake,
            "currency": None if currency is None else currency.upper(),
            "created_at": created_at,
        },
    )
    return get_saved_selection(connection, user_id, saved_id)


def list_saved_selections(
    connection: Connection,
    user_id: str,
    *,
    history: bool,
) -> tuple[SavedSelection, ...]:
    statuses = ("SETTLED", "REVIEW_REQUIRED") if history else ("ACTIVE",)
    rows = connection.execute(
        text(
            "SELECT * FROM saved_selections WHERE user_id=:user_id "
            "AND tracking_status = ANY(:statuses) ORDER BY created_at DESC,saved_selection_id"
        ),
        {"user_id": user_id, "statuses": list(statuses)},
    ).mappings()
    return tuple(_record(row) for row in rows)


def get_saved_selection(
    connection: Connection, user_id: str, saved_selection_id: str
) -> SavedSelection:
    row = (
        connection.execute(
            text(
                "SELECT * FROM saved_selections "
                "WHERE saved_selection_id=:saved_id AND user_id=:user_id"
            ),
            {"saved_id": saved_selection_id, "user_id": user_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise TrackingError("tracked selection not found")
    return _record(row)


def remove_saved_selection(
    connection: Connection,
    user_id: str,
    saved_selection_id: str,
    *,
    now: datetime | None = None,
) -> bool:
    result = connection.execute(
        text(
            "UPDATE saved_selections SET tracking_status='REMOVED',removed_at=:now "
            "WHERE saved_selection_id=:saved_id AND user_id=:user_id "
            "AND tracking_status='ACTIVE'"
        ),
        {
            "saved_id": saved_selection_id,
            "user_id": user_id,
            "now": now or datetime.now(UTC),
        },
    )
    return bool(result.rowcount)


def withdraw_saved_selection(
    connection: Connection,
    saved_selection_id: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Retain a tracked record when authoritative publication is withdrawn."""
    result = connection.execute(
        text(
            "UPDATE saved_selections SET tracking_status='SETTLED',outcome='WITHDRAWN',"
            "settled_at=:now WHERE saved_selection_id=:saved_id AND tracking_status='ACTIVE'"
        ),
        {"saved_id": saved_selection_id, "now": now or datetime.now(UTC)},
    )
    return bool(result.rowcount)


def settle_saved_selection(
    connection: Connection,
    saved_selection_id: str,
    *,
    now: datetime | None = None,
) -> SettlementOutcome | None:
    settled_at = now or datetime.now(UTC)
    row = (
        connection.execute(
            text(
                "SELECT s.*,m.status AS fixture_status,m.home_score,m.away_score,m.updated_at "
                "FROM saved_selections s JOIN matches m ON m.match_id=s.match_id "
                "WHERE s.saved_selection_id=:saved_id FOR UPDATE"
            ),
            {"saved_id": saved_selection_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise TrackingError("tracked selection not found")
    result = CanonicalResult(
        str(row["fixture_status"]),
        row["home_score"],
        row["away_score"],
        row["updated_at"].isoformat(),
    )
    existing_fingerprint = row["result_fingerprint"]
    if row["tracking_status"] in {"SETTLED", "REVIEW_REQUIRED"}:
        if existing_fingerprint == result.fingerprint:
            return None
        connection.execute(
            text(
                "UPDATE saved_selections SET tracking_status='REVIEW_REQUIRED' "
                "WHERE saved_selection_id=:saved_id"
            ),
            {"saved_id": saved_selection_id},
        )
        raise SettlementError("corrected result requires explicit review")
    if row["tracking_status"] != "ACTIVE":
        return None
    outcome = settle(
        MarketFamily(str(row["market"])),
        Selection(str(row["selection"])),
        result,
        line=row["line"],
    )
    if outcome is None:
        return None
    connection.execute(
        text(
            "UPDATE saved_selections SET tracking_status='SETTLED',outcome=:outcome,"
            "settled_at=:settled_at,result_fingerprint=:fingerprint "
            "WHERE saved_selection_id=:saved_id"
        ),
        {
            "outcome": outcome.value,
            "settled_at": settled_at,
            "fingerprint": result.fingerprint,
            "saved_id": saved_selection_id,
        },
    )
    return outcome


def performance(connection: Connection, user_id: str) -> Performance:
    row = (
        connection.execute(
            text(
                "SELECT count(*) FILTER (WHERE tracking_status <> 'REMOVED') AS tracked,"
                "count(*) FILTER (WHERE outcome='WON') AS wins,"
                "count(*) FILTER (WHERE outcome='LOST') AS losses,"
                "count(*) FILTER (WHERE outcome='VOID') AS voids,"
                "count(*) FILTER (WHERE outcome='WITHDRAWN') AS withdrawn,"
                "count(*) FILTER (WHERE tracking_status='SETTLED' "
                "AND stake IS NULL) AS missing_stake,"
                "count(*) FILTER (WHERE tracking_status='SETTLED' AND ("
                "(outcome='WON' AND saved_decimal_odds IS NULL) "
                "OR outcome='WITHDRAWN')) AS missing_return_evidence,"
                "count(DISTINCT currency) FILTER (WHERE tracking_status='SETTLED' "
                "AND stake IS NOT NULL) AS currency_count,"
                "sum(stake) FILTER (WHERE tracking_status='SETTLED') AS total_stake,"
                "sum(CASE WHEN outcome='WON' THEN stake*saved_decimal_odds-stake "
                "WHEN outcome='LOST' THEN -stake WHEN outcome='VOID' THEN 0 END) "
                "FILTER (WHERE tracking_status='SETTLED') AS net_return "
                "FROM saved_selections WHERE user_id=:user_id"
            ),
            {"user_id": user_id},
        )
        .mappings()
        .one()
    )
    complete = (
        int(row["missing_stake"] or 0) == 0
        and int(row["missing_return_evidence"] or 0) == 0
        and int(row["currency_count"] or 0) == 1
        and row["total_stake"] not in {None, 0}
        and row["net_return"] is not None
    )
    total = row["total_stake"] if complete else None
    net = row["net_return"] if complete else None
    roi = None if total is None or net is None else (net / total) * Decimal(100)
    return Performance(
        int(row["tracked"]),
        int(row["wins"]),
        int(row["losses"]),
        int(row["voids"]),
        int(row["withdrawn"]),
        total,
        net,
        roi,
    )


def _record(row: RowMapping) -> SavedSelection:
    return SavedSelection(
        str(row["saved_selection_id"]),
        str(row["user_id"]),
        int(row["match_id"]),
        None if row["prediction_snapshot_id"] is None else int(row["prediction_snapshot_id"]),
        str(row["market"]),
        str(row["selection"]),
        row["line"],
        row["saved_decimal_odds"],
        row["stake"],
        None if row["currency"] is None else str(row["currency"]),
        TrackingStatus(str(row["tracking_status"])),
        None if row["outcome"] is None else SettlementOutcome(str(row["outcome"])),
        row["created_at"],
    )
