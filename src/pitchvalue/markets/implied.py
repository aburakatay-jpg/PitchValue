"""Book percentage, overround, and explicit no-vig normalization."""

from __future__ import annotations

from decimal import Decimal, localcontext

from pitchvalue.markets.config import (
    DEFAULT_MARKET_MATH_CONFIG,
    MarketMathConfig,
    MarketMathError,
    NoVigMethod,
)
from pitchvalue.markets.contracts import (
    MarketDiagnostic,
    MarketDiagnosticCode,
    MarketGroup,
    MarketNormalizationResult,
    MarketStatus,
    NormalizedMarketPrice,
)
from pitchvalue.markets.odds import raw_implied_probability
from pitchvalue.markets.validation import (
    MARKET_REGISTRY,
    canonical_prices,
    missing_selections,
)


def _diagnostics(
    overround: Decimal,
    config: MarketMathConfig,
) -> tuple[MarketDiagnostic, ...]:
    values: list[MarketDiagnostic] = []
    if overround > config.suspicious_overround_threshold:
        values.append(
            MarketDiagnostic(
                MarketDiagnosticCode.SUSPICIOUS_HIGH_OVERROUND,
                overround,
            )
        )
    if overround < config.suspicious_underround_threshold:
        values.append(MarketDiagnostic(MarketDiagnosticCode.MATERIAL_UNDERROUND, overround))
    return tuple(values)


def normalize_market(
    group: MarketGroup,
    config: MarketMathConfig = DEFAULT_MARKET_MATH_CONFIG,
) -> MarketNormalizationResult:
    ordered = canonical_prices(group)
    raw_values = tuple(raw_implied_probability(price.decimal_odds, config) for price in ordered)
    raw_prices = tuple(
        NormalizedMarketPrice(price, raw, None)
        for price, raw in zip(ordered, raw_values, strict=True)
    )
    definition = MARKET_REGISTRY[group.market]
    if not definition.mutually_exclusive:
        return MarketNormalizationResult(
            MarketStatus.NON_EXCLUSIVE_MARKET,
            group.match_id,
            group.provider_id,
            group.market,
            group.line,
            group.reference_type,
            raw_prices,
            None,
            None,
            config.no_vig_method,
            (),
        )
    missing = missing_selections(group)
    if missing:
        return MarketNormalizationResult(
            MarketStatus.INCOMPLETE_MARKET,
            group.match_id,
            group.provider_id,
            group.market,
            group.line,
            group.reference_type,
            raw_prices,
            None,
            None,
            config.no_vig_method,
            (),
            missing,
        )
    with localcontext() as context:
        context.prec = config.decimal_precision
        book_percentage = sum(raw_values, Decimal(0))
        if book_percentage <= 0:  # pragma: no cover - positive odds make this invariant
            raise MarketMathError("raw implied probability sum must be positive")
        overround = book_percentage - Decimal(1)
        diagnostics = _diagnostics(overround, config)
        if config.no_vig_method is not NoVigMethod.PROPORTIONAL:
            return MarketNormalizationResult(
                MarketStatus.UNSUPPORTED_NORMALIZATION_METHOD,
                group.match_id,
                group.provider_id,
                group.market,
                group.line,
                group.reference_type,
                raw_prices,
                book_percentage,
                overround,
                config.no_vig_method,
                diagnostics,
            )
        normalized = tuple(
            NormalizedMarketPrice(price, raw, raw / book_percentage)
            for price, raw in zip(ordered, raw_values, strict=True)
        )
        normalized_sum = sum(
            (
                price.no_vig_probability
                for price in normalized
                if price.no_vig_probability is not None
            ),
            Decimal(0),
        )
        if abs(normalized_sum - Decimal(1)) > config.probability_sum_tolerance:
            raise MarketMathError("normalized probability sum exceeds configured tolerance")
        if any(
            price.no_vig_probability is None
            or not Decimal(0) <= price.no_vig_probability <= Decimal(1)
            for price in normalized
        ):
            raise MarketMathError("normalized probability escaped 0 to 1")
        return MarketNormalizationResult(
            MarketStatus.READY,
            group.match_id,
            group.provider_id,
            group.market,
            group.line,
            group.reference_type,
            normalized,
            book_percentage,
            overround,
            config.no_vig_method,
            diagnostics,
        )
