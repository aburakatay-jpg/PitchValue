"""Decimal bookmaker-odds validation and raw implied probability."""

from __future__ import annotations

from decimal import Decimal, localcontext

from pitchvalue.markets.config import (
    DEFAULT_MARKET_MATH_CONFIG,
    MarketMathConfig,
    MarketMathError,
)


def validate_decimal_odds(decimal_odds: Decimal) -> None:
    if not isinstance(decimal_odds, Decimal):
        raise MarketMathError("decimal_odds must use Decimal")
    if not decimal_odds.is_finite():
        raise MarketMathError("decimal_odds must be finite")
    if decimal_odds <= Decimal(1):
        raise MarketMathError("decimal_odds must be strictly greater than 1")


def raw_implied_probability(
    decimal_odds: Decimal,
    config: MarketMathConfig = DEFAULT_MARKET_MATH_CONFIG,
) -> Decimal:
    """Return raw bookmaker-implied probability (1 / odds), not no-vig probability."""
    validate_decimal_odds(decimal_odds)
    with localcontext() as context:
        context.prec = config.decimal_precision
        return Decimal(1) / decimal_odds
