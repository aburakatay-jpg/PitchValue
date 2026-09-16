"""Deterministic, provider-independent settlement for canonical V1 markets."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from pitchvalue.prediction.contracts import MarketFamily, Selection


class SettlementError(ValueError):
    """Raised when settlement evidence is invalid or ambiguous."""


class SettlementOutcome(StrEnum):
    WON = "WON"
    LOST = "LOST"
    VOID = "VOID"
    WITHDRAWN = "WITHDRAWN"


@dataclass(frozen=True)
class CanonicalResult:
    status: str
    home_score: int | None
    away_score: int | None
    revision: str | None = None

    @property
    def fingerprint(self) -> str:
        value = f"{self.status}|{self.home_score}|{self.away_score}|{self.revision or ''}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


def settle(
    market: MarketFamily,
    selection: Selection,
    result: CanonicalResult,
    *,
    line: Decimal | None = None,
) -> SettlementOutcome | None:
    """Settle only completed, unambiguous full-time canonical results."""
    status = result.status.upper()
    if status == "CANCELLED":
        return SettlementOutcome.VOID
    if status in {"SCHEDULED", "IN_PLAY", "POSTPONED"}:
        return None
    if status == "ABANDONED":
        raise SettlementError("SETTLEMENT_RULE_REVIEW_REQUIRED")
    if status not in {"FINISHED", "AWARDED"}:
        raise SettlementError("unsupported canonical fixture status")
    if result.home_score is None or result.away_score is None:
        raise SettlementError("completed fixture requires canonical full-time score")
    if result.home_score < 0 or result.away_score < 0:
        raise SettlementError("score cannot be negative")
    home, away = result.home_score, result.away_score
    won: bool
    if market is MarketFamily.MATCH_RESULT:
        expected = (
            Selection.HOME if home > away else Selection.AWAY if away > home else Selection.DRAW
        )
        won = selection is expected
    elif market is MarketFamily.DOUBLE_CHANCE:
        won = _double_chance(selection, home, away)
    elif market is MarketFamily.BTTS:
        actual = home > 0 and away > 0
        won = (
            actual
            if selection is Selection.YES
            else not actual
            if selection is Selection.NO
            else _bad()
        )
    elif market is MarketFamily.TOTAL_GOALS:
        won = _total(selection, Decimal(home + away), _line(line))
    elif market is MarketFamily.HOME_TEAM_TOTAL:
        won = _total(selection, Decimal(home), _line(line))
    elif market is MarketFamily.AWAY_TEAM_TOTAL:
        won = _total(selection, Decimal(away), _line(line))
    else:  # pragma: no cover - exhaustive guard for future enum additions
        raise SettlementError("unsupported market")
    return SettlementOutcome.WON if won else SettlementOutcome.LOST


def _double_chance(selection: Selection, home: int, away: int) -> bool:
    if selection is Selection.ONE_X:
        return home >= away
    if selection is Selection.X_TWO:
        return away >= home
    if selection is Selection.ONE_TWO:
        return home != away
    raise SettlementError("invalid double chance selection")


def _total(selection: Selection, goals: Decimal, line: Decimal) -> bool:
    if selection is Selection.OVER:
        return goals > line
    if selection is Selection.UNDER:
        return goals < line
    raise SettlementError("invalid total selection")


def _line(value: Decimal | None) -> Decimal:
    if value not in {Decimal("0.5"), Decimal("1.5"), Decimal("2.5")}:
        raise SettlementError("unsupported V1 total line")
    return value


def _bad() -> bool:
    raise SettlementError("invalid BTTS selection")
