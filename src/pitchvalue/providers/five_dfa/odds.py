"""Free-plan Bet365 snapshot normalization with conservative time semantics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from pitchvalue.markets.history.contracts import ObservationRole, TimingSemantics
from pitchvalue.markets.odds import validate_decimal_odds
from pitchvalue.prediction.contracts import MarketFamily, Selection

ODDS_NORMALIZATION_VERSION = "five_dfa_free_bet365_snapshot_v1"
SUPPORTED_FIXED_GOAL_LINES = frozenset({Decimal("1.5"), Decimal("2.5")})


class OddsDiagnosticCode(StrEnum):
    MISSING_MARKET = "MISSING_MARKET"
    MISSING_SELECTION = "MISSING_SELECTION"
    INVALID_PRICE = "INVALID_PRICE"
    UNSUPPORTED_MARKET = "UNSUPPORTED_MARKET"
    UNSUPPORTED_GOAL_LINE = "UNSUPPORTED_GOAL_LINE"
    UNSUPPORTED_BOOKMAKER = "UNSUPPORTED_BOOKMAKER"
    TIMESTAMP_SEMANTICS_UNPROVEN = "TIMESTAMP_SEMANTICS_UNPROVEN"


@dataclass(frozen=True)
class LiveOddsObservation:
    provider_fixture_id: str
    bookmaker: str
    market: MarketFamily
    selection: Selection
    line: Decimal | None
    decimal_odds: Decimal
    observation_role: ObservationRole
    timing_semantics: TimingSemantics
    observed_at: None
    source_timestamp_evidence: tuple[tuple[str, str], ...]
    normalization_version: str = ODDS_NORMALIZATION_VERSION
    publication_safe: bool = False


@dataclass(frozen=True)
class OddsDiagnostic:
    code: OddsDiagnosticCode
    market: str
    role: str | None = None
    selection: str | None = None
    source_value: str | None = None


@dataclass(frozen=True)
class OddsNormalizationResult:
    observations: tuple[LiveOddsObservation, ...]
    diagnostics: tuple[OddsDiagnostic, ...]
    timestamp_gate: str = "PENDING"
    market_stability: str = "UNAVAILABLE"


def normalize_bet365_snapshot(payload: object) -> OddsNormalizationResult:
    """Normalize only 1X2, BTTS, and supported fixed goal lines from Bet365."""
    if not isinstance(payload, dict):
        raise ValueError("odds payload must be an object")
    fixture_id = _source_id(payload.get("fixture_id"))
    books = payload.get("bookmakers")
    if not isinstance(books, list):
        raise ValueError("bookmakers must be a list")
    observations: list[LiveOddsObservation] = []
    diagnostics: list[OddsDiagnostic] = []
    for raw_book in books:
        if not isinstance(raw_book, dict):
            diagnostics.append(OddsDiagnostic(OddsDiagnosticCode.UNSUPPORTED_BOOKMAKER, "*"))
            continue
        if raw_book.get("slug") != "bet365":
            diagnostics.append(
                OddsDiagnostic(
                    OddsDiagnosticCode.UNSUPPORTED_BOOKMAKER,
                    "*",
                    source_value=str(raw_book.get("slug")),
                )
            )
            continue
        markets = raw_book.get("odds")
        if not isinstance(markets, dict):
            raise ValueError("bookmaker odds must be an object")
        timestamp_evidence = _timestamp_evidence(raw_book)
        _normalize_market(
            fixture_id,
            markets.get("1x2"),
            "1x2",
            MarketFamily.MATCH_RESULT,
            (("home", Selection.HOME), ("draw", Selection.DRAW), ("away", Selection.AWAY)),
            None,
            timestamp_evidence,
            observations,
            diagnostics,
        )
        _normalize_market(
            fixture_id,
            markets.get("btts"),
            "btts",
            MarketFamily.BTTS,
            (("yes", Selection.YES), ("no", Selection.NO)),
            None,
            timestamp_evidence,
            observations,
            diagnostics,
        )
        _normalize_goal_line(
            fixture_id,
            markets.get("goal_line"),
            timestamp_evidence,
            observations,
            diagnostics,
        )
        for unsupported in ("double_chance", "home_team_total", "away_team_total"):
            if unsupported in markets:
                diagnostics.append(
                    OddsDiagnostic(OddsDiagnosticCode.UNSUPPORTED_MARKET, unsupported)
                )
    diagnostics.append(OddsDiagnostic(OddsDiagnosticCode.TIMESTAMP_SEMANTICS_UNPROVEN, "*"))
    return OddsNormalizationResult(tuple(observations), tuple(diagnostics))


def _normalize_goal_line(
    fixture_id: str,
    market: object,
    timestamp_evidence: tuple[tuple[str, str], ...],
    observations: list[LiveOddsObservation],
    diagnostics: list[OddsDiagnostic],
) -> None:
    if market is None:
        diagnostics.append(OddsDiagnostic(OddsDiagnosticCode.MISSING_MARKET, "goal_line"))
        return
    if not isinstance(market, dict):
        raise ValueError("goal_line must be an object")
    for role_name, role in (
        ("opening", ObservationRole.OPENING),
        ("closing", ObservationRole.CLOSING),
    ):
        snapshot = market.get(role_name)
        if snapshot is None:
            continue
        if not isinstance(snapshot, dict):
            diagnostics.append(
                OddsDiagnostic(OddsDiagnosticCode.MISSING_MARKET, "goal_line", role_name)
            )
            continue
        line = _decimal(snapshot.get("line"))
        if line not in SUPPORTED_FIXED_GOAL_LINES:
            diagnostics.append(
                OddsDiagnostic(
                    OddsDiagnosticCode.UNSUPPORTED_GOAL_LINE,
                    "goal_line",
                    role_name,
                    source_value=str(snapshot.get("line")),
                )
            )
            continue
        _append_selections(
            fixture_id,
            snapshot,
            "goal_line",
            MarketFamily.TOTAL_GOALS,
            (("over", Selection.OVER), ("under", Selection.UNDER)),
            line,
            role,
            timestamp_evidence,
            observations,
            diagnostics,
        )


def _normalize_market(
    fixture_id: str,
    market: object,
    source_market: str,
    canonical_market: MarketFamily,
    selections: tuple[tuple[str, Selection], ...],
    line: Decimal | None,
    timestamp_evidence: tuple[tuple[str, str], ...],
    observations: list[LiveOddsObservation],
    diagnostics: list[OddsDiagnostic],
) -> None:
    if market is None:
        diagnostics.append(OddsDiagnostic(OddsDiagnosticCode.MISSING_MARKET, source_market))
        return
    if not isinstance(market, dict):
        raise ValueError(f"{source_market} must be an object")
    for role_name, role in (
        ("opening", ObservationRole.OPENING),
        ("closing", ObservationRole.CLOSING),
    ):
        snapshot = market.get(role_name)
        if snapshot is None:
            continue
        if not isinstance(snapshot, dict):
            diagnostics.append(
                OddsDiagnostic(OddsDiagnosticCode.MISSING_MARKET, source_market, role_name)
            )
            continue
        _append_selections(
            fixture_id,
            snapshot,
            source_market,
            canonical_market,
            selections,
            line,
            role,
            timestamp_evidence,
            observations,
            diagnostics,
        )


def _append_selections(
    fixture_id: str,
    snapshot: dict[object, object],
    source_market: str,
    market: MarketFamily,
    selections: tuple[tuple[str, Selection], ...],
    line: Decimal | None,
    role: ObservationRole,
    timestamp_evidence: tuple[tuple[str, str], ...],
    observations: list[LiveOddsObservation],
    diagnostics: list[OddsDiagnostic],
) -> None:
    parsed: list[tuple[Selection, Decimal]] = []
    for source_selection, selection in selections:
        raw = snapshot.get(source_selection)
        if raw is None:
            diagnostics.append(
                OddsDiagnostic(
                    OddsDiagnosticCode.MISSING_SELECTION,
                    source_market,
                    role.value,
                    selection.value,
                )
            )
            return
        try:
            price = _decimal(raw)
            validate_decimal_odds(price)
        except (InvalidOperation, ValueError):
            diagnostics.append(
                OddsDiagnostic(
                    OddsDiagnosticCode.INVALID_PRICE,
                    source_market,
                    role.value,
                    selection.value,
                    str(raw),
                )
            )
            return
        parsed.append((selection, price))
    observations.extend(
        LiveOddsObservation(
            fixture_id,
            "BET365",
            market,
            selection,
            line,
            price,
            role,
            TimingSemantics.ROLE_ONLY,
            None,
            timestamp_evidence,
        )
        for selection, price in parsed
    )


def _timestamp_evidence(book: dict[object, object]) -> tuple[tuple[str, str], ...]:
    """Retain source-named evidence without interpreting it as observed_at."""
    return tuple(
        sorted(
            (str(key), str(value))
            for key, value in book.items()
            if key in {"recorded_at", "updated_at", "last_update"} and value is not None
        )
    )


def _source_id(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
        raise ValueError("fixture_id must be a nonblank source identity")
    return str(value).strip()


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("decimal value is invalid")
    if isinstance(value, float):
        value = str(value)
    if not isinstance(value, (Decimal, int, str)):
        raise ValueError("decimal value is invalid")
    return Decimal(value)
