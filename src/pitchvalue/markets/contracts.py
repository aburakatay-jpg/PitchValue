"""Immutable auditable contracts for source prices and no-vig results."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pitchvalue.markets.config import MarketMathError, NoVigMethod
from pitchvalue.markets.odds import validate_decimal_odds
from pitchvalue.prediction.contracts import MarketFamily, Selection


class MarketStatus(StrEnum):
    READY = "READY"
    INCOMPLETE_MARKET = "INCOMPLETE_MARKET"
    NON_EXCLUSIVE_MARKET = "NON_EXCLUSIVE_MARKET"
    INVALID_ODDS = "INVALID_ODDS"
    INVALID_MARKET_GROUP = "INVALID_MARKET_GROUP"
    UNSUPPORTED_MARKET = "UNSUPPORTED_MARKET"
    UNSUPPORTED_NORMALIZATION_METHOD = "UNSUPPORTED_NORMALIZATION_METHOD"


class MarketDiagnosticCode(StrEnum):
    SUSPICIOUS_HIGH_OVERROUND = "SUSPICIOUS_HIGH_OVERROUND"
    MATERIAL_UNDERROUND = "MATERIAL_UNDERROUND"


class PriceReferenceType(StrEnum):
    SOURCE_PRICE = "SOURCE_PRICE"
    REFERENCE_MARKET = "REFERENCE_MARKET"
    BEST_AVAILABLE = "BEST_AVAILABLE"
    CONSENSUS = "CONSENSUS"
    OPENING = "OPENING"
    CLOSING = "CLOSING"


@dataclass(frozen=True)
class MarketDiagnostic:
    code: MarketDiagnosticCode
    value: Decimal


@dataclass(frozen=True)
class BookmakerPrice:
    match_id: str
    provider_id: str
    market: MarketFamily
    selection: Selection
    line: Decimal | None
    decimal_odds: Decimal
    observed_at: datetime | None = None
    provider_market_id: str | None = None
    reference_type: PriceReferenceType = PriceReferenceType.SOURCE_PRICE
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("match_id", "provider_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise MarketMathError(f"{name} is required")
        if not isinstance(self.market, MarketFamily) or not isinstance(self.selection, Selection):
            raise MarketMathError("market and selection must use canonical contracts")
        validate_decimal_odds(self.decimal_odds)
        if self.line is not None and (
            not isinstance(self.line, Decimal) or not self.line.is_finite()
        ):
            raise MarketMathError("line must be a finite Decimal")
        if self.observed_at is not None and (
            not isinstance(self.observed_at, datetime)
            or self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() is None
        ):
            raise MarketMathError("observed_at must be timezone-aware when supplied")
        if self.provider_market_id is not None and (
            not isinstance(self.provider_market_id, str) or not self.provider_market_id.strip()
        ):
            raise MarketMathError("provider_market_id cannot be blank")
        if not isinstance(self.reference_type, PriceReferenceType):
            raise MarketMathError("reference_type must use PriceReferenceType")
        if any(not isinstance(item, str) or not item.strip() for item in self.diagnostics):
            raise MarketMathError("price diagnostics must be non-empty strings")
        from pitchvalue.markets.validation import validate_price_contract

        validate_price_contract(self)


@dataclass(frozen=True)
class MarketGroup:
    match_id: str
    provider_id: str
    market: MarketFamily
    line: Decimal | None
    prices: tuple[BookmakerPrice, ...]
    reference_type: PriceReferenceType = PriceReferenceType.SOURCE_PRICE

    def __post_init__(self) -> None:
        from pitchvalue.markets.validation import validate_market_group

        validate_market_group(self)


@dataclass(frozen=True)
class NormalizedMarketPrice:
    source_price: BookmakerPrice
    raw_implied_probability: Decimal
    no_vig_probability: Decimal | None


@dataclass(frozen=True)
class MarketNormalizationResult:
    status: MarketStatus
    match_id: str
    provider_id: str
    market: MarketFamily
    line: Decimal | None
    reference_type: PriceReferenceType
    prices: tuple[NormalizedMarketPrice, ...]
    book_percentage: Decimal | None
    overround: Decimal | None
    normalization_method: NoVigMethod
    diagnostics: tuple[MarketDiagnostic, ...]
    missing_selections: tuple[Selection, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = _primitive(self)
        if not isinstance(value, dict):  # pragma: no cover
            raise TypeError("MarketNormalizationResult must serialize to a mapping")
        return value


def _primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value
