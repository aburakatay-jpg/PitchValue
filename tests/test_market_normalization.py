from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pitchvalue.markets.config import MarketMathConfig, MarketMathError, NoVigMethod
from pitchvalue.markets.contracts import (
    BookmakerPrice,
    MarketDiagnosticCode,
    MarketStatus,
    PriceReferenceType,
)
from pitchvalue.markets.implied import normalize_market
from pitchvalue.markets.odds import raw_implied_probability
from pitchvalue.markets.validation import create_market_group
from pitchvalue.prediction.contracts import MarketFamily, Selection

D = Decimal


def price(
    selection: Selection,
    odds: str,
    *,
    market: MarketFamily = MarketFamily.MATCH_RESULT,
    line: str | None = None,
    match_id: str = "match",
    provider_id: str = "provider",
    reference_type: PriceReferenceType = PriceReferenceType.SOURCE_PRICE,
    observed_at: datetime | None = None,
) -> BookmakerPrice:
    return BookmakerPrice(
        match_id=match_id,
        provider_id=provider_id,
        market=market,
        selection=selection,
        line=D(line) if line is not None else None,
        decimal_odds=D(odds),
        observed_at=observed_at,
        reference_type=reference_type,
    )


def match_result(
    home: str = "2",
    draw: str = "4",
    away: str = "4",
) -> list[BookmakerPrice]:
    return [
        price(Selection.HOME, home),
        price(Selection.DRAW, draw),
        price(Selection.AWAY, away),
    ]


def binary(
    market: MarketFamily,
    first: Selection,
    second: Selection,
    *,
    line: str | None = None,
    first_odds: str = "2",
    second_odds: str = "2",
) -> list[BookmakerPrice]:
    return [
        price(first, first_odds, market=market, line=line),
        price(second, second_odds, market=market, line=line),
    ]


def test_complete_match_result_is_ready_and_auditable() -> None:
    result = normalize_market(create_market_group(match_result("2", "3", "4")))
    assert result.status is MarketStatus.READY
    assert tuple(item.source_price.selection for item in result.prices) == (
        Selection.HOME,
        Selection.DRAW,
        Selection.AWAY,
    )
    assert result.prices[0].raw_implied_probability == D("0.5")
    assert abs(result.prices[1].raw_implied_probability - D(1) / D(3)) < D("1E-27")
    assert result.prices[2].raw_implied_probability == D("0.25")
    assert result.book_percentage is not None
    expected_book = D("0.5") + D(1) / D(3) + D("0.25")
    assert abs(result.book_percentage - expected_book) < D("1E-27")
    assert result.overround is not None
    assert abs(result.overround - (result.book_percentage - D(1))) < D("1E-27")


def test_proportional_no_vig_formula_and_sum() -> None:
    result = normalize_market(create_market_group(match_result("2", "3", "4")))
    assert result.book_percentage is not None
    for item in result.prices:
        expected = item.raw_implied_probability / result.book_percentage
        assert item.no_vig_probability is not None
        assert abs(item.no_vig_probability - expected) < D("1E-27")
    normalized_sum = sum(
        (item.no_vig_probability for item in result.prices if item.no_vig_probability is not None),
        D(0),
    )
    assert abs(normalized_sum - D(1)) < D("1E-24")
    assert result.normalization_method is NoVigMethod.PROPORTIONAL


def test_normalization_preserves_odds_and_raw_probabilities() -> None:
    inputs = match_result("2", "3", "4")
    before = tuple(inputs)
    result = normalize_market(create_market_group(inputs))
    assert tuple(item.source_price.decimal_odds for item in result.prices) == (
        D("2"),
        D("3"),
        D("4"),
    )
    assert result.prices[0].raw_implied_probability == raw_implied_probability(D("2"))
    assert tuple(inputs) == before


@pytest.mark.parametrize(
    ("missing", "expected"),
    [
        (Selection.HOME, (Selection.HOME,)),
        (Selection.DRAW, (Selection.DRAW,)),
        (Selection.AWAY, (Selection.AWAY,)),
    ],
)
def test_incomplete_match_result_is_explicit(
    missing: Selection,
    expected: tuple[Selection, ...],
) -> None:
    group = create_market_group([item for item in match_result() if item.selection is not missing])
    result = normalize_market(group)
    assert result.status is MarketStatus.INCOMPLETE_MARKET
    assert result.missing_selections == expected
    assert result.book_percentage is None
    assert result.overround is None
    assert all(item.no_vig_probability is None for item in result.prices)


def test_duplicate_selection_rejected() -> None:
    with pytest.raises(MarketMathError, match="duplicate"):
        create_market_group(
            [
                price(Selection.HOME, "2"),
                price(Selection.HOME, "2.1"),
            ]
        )


@pytest.mark.parametrize(
    ("field", "changed", "message"),
    [
        ("match_id", "other", "match IDs"),
        ("provider_id", "other", "provider IDs"),
    ],
)
def test_mixed_identity_rejected(field: str, changed: str, message: str) -> None:
    inputs = match_result()
    inputs[1] = (
        replace(inputs[1], match_id=changed)
        if field == "match_id"
        else replace(inputs[1], provider_id=changed)
    )
    with pytest.raises(MarketMathError, match=message):
        create_market_group(inputs)


def test_mixed_markets_rejected() -> None:
    with pytest.raises(MarketMathError, match="mix markets"):
        create_market_group(
            [
                price(Selection.HOME, "2"),
                price(Selection.YES, "2", market=MarketFamily.BTTS),
            ]
        )


def test_mixed_valid_lines_rejected() -> None:
    with pytest.raises(MarketMathError, match="mix lines"):
        create_market_group(
            [
                price(
                    Selection.OVER,
                    "2",
                    market=MarketFamily.TOTAL_GOALS,
                    line="1.5",
                ),
                price(
                    Selection.UNDER,
                    "2",
                    market=MarketFamily.TOTAL_GOALS,
                    line="2.5",
                ),
            ]
        )


@pytest.mark.parametrize("line", ["1.5", "2.5"])
def test_over_under_market_ready(line: str) -> None:
    result = normalize_market(
        create_market_group(
            binary(
                MarketFamily.TOTAL_GOALS,
                Selection.OVER,
                Selection.UNDER,
                line=line,
            )
        )
    )
    assert result.status is MarketStatus.READY
    assert result.line == D(line)
    assert tuple(item.source_price.selection for item in result.prices) == (
        Selection.OVER,
        Selection.UNDER,
    )
    normalized_sum = sum(
        (item.no_vig_probability for item in result.prices if item.no_vig_probability is not None),
        D(0),
    )
    assert abs(normalized_sum - D(1)) < D("1E-24")


@pytest.mark.parametrize("missing", [Selection.OVER, Selection.UNDER])
def test_over_under_missing_side_is_incomplete(missing: Selection) -> None:
    inputs = binary(
        MarketFamily.TOTAL_GOALS,
        Selection.OVER,
        Selection.UNDER,
        line="2.5",
    )
    result = normalize_market(
        create_market_group([item for item in inputs if item.selection is not missing])
    )
    assert result.status is MarketStatus.INCOMPLETE_MARKET
    assert result.missing_selections == (missing,)


def test_decimal_equivalent_lines_group_together() -> None:
    inputs = [
        price(
            Selection.OVER,
            "2",
            market=MarketFamily.TOTAL_GOALS,
            line="2.5",
        ),
        price(
            Selection.UNDER,
            "2",
            market=MarketFamily.TOTAL_GOALS,
            line="2.500",
        ),
    ]
    assert normalize_market(create_market_group(inputs)).status is MarketStatus.READY


def test_input_order_does_not_change_canonical_output() -> None:
    forward = normalize_market(create_market_group(match_result("2", "3", "4")))
    reverse = normalize_market(create_market_group(list(reversed(match_result("2", "3", "4")))))
    assert forward == reverse
    assert forward.to_dict() == reverse.to_dict()


def test_btts_complete_and_fair() -> None:
    result = normalize_market(
        create_market_group(binary(MarketFamily.BTTS, Selection.YES, Selection.NO))
    )
    assert result.status is MarketStatus.READY
    assert tuple(item.no_vig_probability for item in result.prices) == (
        D("0.5"),
        D("0.5"),
    )


@pytest.mark.parametrize("missing", [Selection.YES, Selection.NO])
def test_btts_missing_side_is_incomplete(missing: Selection) -> None:
    inputs = binary(MarketFamily.BTTS, Selection.YES, Selection.NO)
    result = normalize_market(
        create_market_group([item for item in inputs if item.selection is not missing])
    )
    assert result.status is MarketStatus.INCOMPLETE_MARKET
    assert result.missing_selections == (missing,)


@pytest.mark.parametrize(
    ("market", "line"),
    [
        (MarketFamily.HOME_TEAM_TOTAL, "0.5"),
        (MarketFamily.HOME_TEAM_TOTAL, "1.5"),
        (MarketFamily.AWAY_TEAM_TOTAL, "0.5"),
        (MarketFamily.AWAY_TEAM_TOTAL, "1.5"),
    ],
)
def test_team_total_markets_ready(market: MarketFamily, line: str) -> None:
    result = normalize_market(
        create_market_group(binary(market, Selection.OVER, Selection.UNDER, line=line))
    )
    assert result.status is MarketStatus.READY
    assert result.line == D(line)
    assert tuple(item.no_vig_probability for item in result.prices) == (
        D("0.5"),
        D("0.5"),
    )


@pytest.mark.parametrize(
    ("market", "line", "missing"),
    [
        (MarketFamily.HOME_TEAM_TOTAL, "0.5", Selection.OVER),
        (MarketFamily.HOME_TEAM_TOTAL, "1.5", Selection.UNDER),
        (MarketFamily.AWAY_TEAM_TOTAL, "0.5", Selection.OVER),
        (MarketFamily.AWAY_TEAM_TOTAL, "1.5", Selection.UNDER),
    ],
)
def test_team_total_missing_side_is_incomplete(
    market: MarketFamily,
    line: str,
    missing: Selection,
) -> None:
    inputs = binary(market, Selection.OVER, Selection.UNDER, line=line)
    result = normalize_market(
        create_market_group([item for item in inputs if item.selection is not missing])
    )
    assert result.status is MarketStatus.INCOMPLETE_MARKET
    assert result.missing_selections == (missing,)


@pytest.mark.parametrize(
    "selection",
    [Selection.ONE_X, Selection.X_TWO, Selection.ONE_TWO],
)
def test_double_chance_individual_raw_probability_is_valid(
    selection: Selection,
) -> None:
    value = price(
        selection,
        "1.4",
        market=MarketFamily.DOUBLE_CHANCE,
    )
    assert abs(raw_implied_probability(value.decimal_odds) - D(1) / D("1.4")) < D("1E-27")


def test_double_chance_group_is_nonexclusive_and_not_normalized() -> None:
    inputs = [
        price(Selection.ONE_X, "1.4", market=MarketFamily.DOUBLE_CHANCE),
        price(Selection.X_TWO, "1.5", market=MarketFamily.DOUBLE_CHANCE),
        price(Selection.ONE_TWO, "1.6", market=MarketFamily.DOUBLE_CHANCE),
    ]
    result = normalize_market(create_market_group(inputs))
    assert result.status is MarketStatus.NON_EXCLUSIVE_MARKET
    assert result.book_percentage is None
    assert result.overround is None
    assert all(item.no_vig_probability is None for item in result.prices)
    assert all(item.raw_implied_probability > 0 for item in result.prices)


def test_zero_overround_market_preserved() -> None:
    result = normalize_market(
        create_market_group(binary(MarketFamily.BTTS, Selection.YES, Selection.NO))
    )
    assert result.book_percentage == 1
    assert result.overround == 0
    assert result.diagnostics == ()


def test_positive_overround_market_preserved() -> None:
    result = normalize_market(create_market_group(match_result("2", "3", "4")))
    assert result.book_percentage is not None and result.book_percentage > 1
    assert result.overround is not None and result.overround > 0


def test_underround_is_negative_visible_and_still_normalized() -> None:
    inputs = binary(
        MarketFamily.BTTS,
        Selection.YES,
        Selection.NO,
        first_odds="2.1",
        second_odds="2.1",
    )
    result = normalize_market(create_market_group(inputs))
    assert result.status is MarketStatus.READY
    assert result.book_percentage is not None and result.book_percentage < 1
    assert result.overround is not None and result.overround < 0
    normalized_sum = sum(
        (item.no_vig_probability for item in result.prices if item.no_vig_probability is not None),
        D(0),
    )
    assert abs(normalized_sum - D(1)) < D("1E-24")


@pytest.mark.parametrize(
    ("odds", "diagnostic"),
    [
        (("1.5", "2", "3"), MarketDiagnosticCode.SUSPICIOUS_HIGH_OVERROUND),
        (("2.1", "4.2", "4.2"), MarketDiagnosticCode.MATERIAL_UNDERROUND),
    ],
)
def test_suspicious_diagnostic_does_not_change_math(
    odds: tuple[str, str, str],
    diagnostic: MarketDiagnosticCode,
) -> None:
    inputs = match_result(*odds)
    result = normalize_market(create_market_group(inputs))
    assert diagnostic in tuple(item.code for item in result.diagnostics)
    assert tuple(item.source_price.decimal_odds for item in result.prices) == tuple(
        D(value) for value in odds
    )
    normalized_sum = sum(
        (item.no_vig_probability for item in result.prices if item.no_vig_probability is not None),
        D(0),
    )
    assert abs(normalized_sum - D(1)) < D("1E-24")


@pytest.mark.parametrize(
    "method",
    [NoVigMethod.SHIN, NoVigMethod.POWER, NoVigMethod.ADDITIVE],
)
def test_unimplemented_method_never_falls_back_to_proportional(
    method: NoVigMethod,
) -> None:
    result = normalize_market(
        create_market_group(match_result()),
        MarketMathConfig(no_vig_method=method),
    )
    assert result.status is MarketStatus.UNSUPPORTED_NORMALIZATION_METHOD
    assert result.normalization_method is method
    assert result.book_percentage == 1
    assert all(item.no_vig_probability is None for item in result.prices)


def test_provider_and_observed_at_are_preserved() -> None:
    observed = datetime(2026, 9, 8, 10, tzinfo=UTC)
    inputs = [
        price(Selection.YES, "2", market=MarketFamily.BTTS, observed_at=observed),
        price(Selection.NO, "2", market=MarketFamily.BTTS, observed_at=observed),
    ]
    result = normalize_market(create_market_group(inputs))
    assert result.provider_id == "provider"
    assert all(item.source_price.observed_at is observed for item in result.prices)


def test_reference_type_is_preserved_without_aggregation() -> None:
    inputs = [
        price(
            Selection.YES,
            "2",
            market=MarketFamily.BTTS,
            reference_type=PriceReferenceType.REFERENCE_MARKET,
        ),
        price(
            Selection.NO,
            "2",
            market=MarketFamily.BTTS,
            reference_type=PriceReferenceType.REFERENCE_MARKET,
        ),
    ]
    result = normalize_market(create_market_group(inputs))
    assert result.reference_type is PriceReferenceType.REFERENCE_MARKET


def test_repeated_normalization_is_deterministic_and_does_not_mutate_inputs() -> None:
    inputs = match_result("2", "3", "4")
    before = tuple(inputs)
    group = create_market_group(inputs)
    first = normalize_market(group)
    second = normalize_market(group)
    assert first == second
    assert first.to_dict() == second.to_dict()
    assert tuple(inputs) == before
