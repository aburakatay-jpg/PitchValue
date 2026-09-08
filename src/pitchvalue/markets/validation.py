"""Central canonical market registry and source-group validation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from pitchvalue.markets.config import MarketMathError
from pitchvalue.markets.contracts import BookmakerPrice, MarketGroup, PriceReferenceType
from pitchvalue.prediction.contracts import MarketFamily, Selection


@dataclass(frozen=True)
class MarketDefinition:
    required_selections: tuple[Selection, ...]
    allowed_lines: frozenset[Decimal] | None
    mutually_exclusive: bool


MARKET_REGISTRY: dict[MarketFamily, MarketDefinition] = {
    MarketFamily.MATCH_RESULT: MarketDefinition(
        (Selection.HOME, Selection.DRAW, Selection.AWAY),
        None,
        True,
    ),
    MarketFamily.TOTAL_GOALS: MarketDefinition(
        (Selection.OVER, Selection.UNDER),
        frozenset({Decimal("1.5"), Decimal("2.5")}),
        True,
    ),
    MarketFamily.BTTS: MarketDefinition(
        (Selection.YES, Selection.NO),
        None,
        True,
    ),
    MarketFamily.DOUBLE_CHANCE: MarketDefinition(
        (Selection.ONE_X, Selection.X_TWO, Selection.ONE_TWO),
        None,
        False,
    ),
    MarketFamily.HOME_TEAM_TOTAL: MarketDefinition(
        (Selection.OVER, Selection.UNDER),
        frozenset({Decimal("0.5"), Decimal("1.5")}),
        True,
    ),
    MarketFamily.AWAY_TEAM_TOTAL: MarketDefinition(
        (Selection.OVER, Selection.UNDER),
        frozenset({Decimal("0.5"), Decimal("1.5")}),
        True,
    ),
}


def validate_price_contract(price: BookmakerPrice) -> None:
    definition = MARKET_REGISTRY.get(price.market)
    if definition is None:
        raise MarketMathError("unsupported canonical market")
    if price.selection not in definition.required_selections:
        raise MarketMathError("selection is not valid for market")
    if definition.allowed_lines is None:
        if price.line is not None:
            raise MarketMathError("line must be absent for market")
    elif price.line not in definition.allowed_lines:
        raise MarketMathError("line is not valid for market")


def validate_market_group(group: MarketGroup) -> None:
    if not isinstance(group.prices, tuple) or not group.prices:
        raise MarketMathError("market group prices must be a non-empty tuple")
    if not isinstance(group.reference_type, PriceReferenceType):
        raise MarketMathError("group reference_type must use PriceReferenceType")
    seen: set[Selection] = set()
    for price in group.prices:
        if not isinstance(price, BookmakerPrice):
            raise MarketMathError("market group must contain BookmakerPrice values")
        if price.match_id != group.match_id:
            raise MarketMathError("market group cannot mix match IDs")
        if price.provider_id != group.provider_id:
            raise MarketMathError("market group cannot mix provider IDs")
        if price.market is not group.market:
            raise MarketMathError("market group cannot mix markets")
        if price.line != group.line:
            raise MarketMathError("market group cannot mix lines")
        if price.reference_type is not group.reference_type:
            raise MarketMathError("market group cannot mix reference semantics")
        if price.selection in seen:
            raise MarketMathError("market group cannot contain duplicate selections")
        seen.add(price.selection)


def create_market_group(
    prices: Iterable[BookmakerPrice],
    *,
    reference_type: PriceReferenceType | None = None,
) -> MarketGroup:
    preserved = tuple(prices)
    if not preserved:
        raise MarketMathError("at least one source price is required")
    first = preserved[0]
    resolved_reference = first.reference_type if reference_type is None else reference_type
    return MarketGroup(
        match_id=first.match_id,
        provider_id=first.provider_id,
        market=first.market,
        line=first.line,
        prices=preserved,
        reference_type=resolved_reference,
    )


def canonical_prices(group: MarketGroup) -> tuple[BookmakerPrice, ...]:
    definition = MARKET_REGISTRY[group.market]
    order = {selection: index for index, selection in enumerate(definition.required_selections)}
    return tuple(sorted(group.prices, key=lambda price: order[price.selection]))


def missing_selections(group: MarketGroup) -> tuple[Selection, ...]:
    present = {price.selection for price in group.prices}
    return tuple(
        selection
        for selection in MARKET_REGISTRY[group.market].required_selections
        if selection not in present
    )
