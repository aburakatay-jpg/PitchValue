from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pitchvalue.markets.config import (
    MarketMathConfig,
    MarketMathError,
    NoVigMethod,
)
from pitchvalue.markets.contracts import BookmakerPrice, PriceReferenceType
from pitchvalue.markets.odds import raw_implied_probability, validate_decimal_odds
from pitchvalue.prediction.contracts import MarketFamily, Selection

D = Decimal


def price(**overrides: object) -> BookmakerPrice:
    values: dict[str, object] = {
        "match_id": "match",
        "provider_id": "provider",
        "market": MarketFamily.MATCH_RESULT,
        "selection": Selection.HOME,
        "line": None,
        "decimal_odds": D("2.00"),
    }
    values.update(overrides)
    return BookmakerPrice(**values)  # type: ignore[arg-type]


def test_default_config_is_valid_and_proportional() -> None:
    config = MarketMathConfig()
    assert config.no_vig_method is NoVigMethod.PROPORTIONAL
    assert config.decimal_precision == 50
    assert config.as_dict()["no_vig_method"] == "PROPORTIONAL"


def test_config_is_immutable_and_override_isolated() -> None:
    original = MarketMathConfig()
    changed = replace(original, decimal_precision=60)
    assert original.decimal_precision == 50
    assert changed.decimal_precision == 60
    with pytest.raises(FrozenInstanceError):
        original.decimal_precision = 30  # type: ignore[misc]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"decimal_precision": 27}, "decimal_precision"),
        ({"probability_sum_tolerance": D("0")}, "probability_sum_tolerance"),
        ({"probability_sum_tolerance": D("1")}, "probability_sum_tolerance"),
        ({"suspicious_overround_threshold": D("0")}, "overround"),
        ({"suspicious_underround_threshold": D("0")}, "underround"),
        ({"no_vig_method": "PROPORTIONAL"}, "NoVigMethod"),
    ],
)
def test_invalid_config_rejected(override: dict[str, object], message: str) -> None:
    with pytest.raises(MarketMathError, match=message):
        MarketMathConfig(**override)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("odds", "expected"),
    [
        (D("2.00"), D("0.5")),
        (D("4.00"), D("0.25")),
        (D("1.50"), D(1) / D("1.5")),
        (D("3.00"), D(1) / D("3")),
    ],
)
def test_raw_implied_probability(odds: Decimal, expected: Decimal) -> None:
    assert abs(raw_implied_probability(odds) - expected) < D("1E-27")


@pytest.mark.parametrize(
    "invalid",
    [
        D("1"),
        D("0"),
        D("-2"),
        D("0.99"),
        D("NaN"),
        D("Infinity"),
        D("-Infinity"),
    ],
)
def test_invalid_decimal_odds_rejected(invalid: Decimal) -> None:
    with pytest.raises(MarketMathError):
        validate_decimal_odds(invalid)


@pytest.mark.parametrize("invalid", ["2.00", 2, 2.0, None, object()])
def test_non_decimal_odds_rejected_without_coercion(invalid: object) -> None:
    with pytest.raises(MarketMathError, match="must use Decimal"):
        raw_implied_probability(invalid)  # type: ignore[arg-type]


def test_raw_probability_precision_is_deterministic_and_configured() -> None:
    config = MarketMathConfig(decimal_precision=35)
    first = raw_implied_probability(D("1.5"), config)
    second = raw_implied_probability(D("1.50"), config)
    assert first == second
    assert len(first.as_tuple().digits) == 35


def test_price_preserves_source_fields_and_timestamp() -> None:
    observed = datetime(2026, 9, 8, 12, tzinfo=UTC)
    value = price(
        observed_at=observed,
        provider_market_id="external-market",
        diagnostics=("SOURCE_VALIDATED",),
    )
    assert value.provider_id == "provider"
    assert value.observed_at is observed
    assert value.provider_market_id == "external-market"


def test_observed_at_is_not_generated() -> None:
    assert price().observed_at is None


def test_naive_observed_at_rejected() -> None:
    with pytest.raises(MarketMathError, match="timezone-aware"):
        price(observed_at=datetime(2026, 9, 8, 12))


@pytest.mark.parametrize(
    ("market", "selection", "line"),
    [
        (MarketFamily.MATCH_RESULT, Selection.HOME, D("1.5")),
        (MarketFamily.BTTS, Selection.YES, D("0.5")),
        (MarketFamily.DOUBLE_CHANCE, Selection.ONE_X, D("1.5")),
        (MarketFamily.TOTAL_GOALS, Selection.OVER, None),
        (MarketFamily.TOTAL_GOALS, Selection.OVER, D("0.5")),
        (MarketFamily.HOME_TEAM_TOTAL, Selection.HOME, D("0.5")),
        (MarketFamily.AWAY_TEAM_TOTAL, Selection.UNDER, D("2.5")),
    ],
)
def test_invalid_selection_or_line_rejected(
    market: MarketFamily,
    selection: Selection,
    line: Decimal | None,
) -> None:
    with pytest.raises(MarketMathError):
        price(market=market, selection=selection, line=line)


@pytest.mark.parametrize("reference_type", list(PriceReferenceType))
def test_reference_price_semantics_are_distinct_and_representable(
    reference_type: PriceReferenceType,
) -> None:
    value = price(reference_type=reference_type)
    assert value.reference_type is reference_type


def test_reference_price_enum_values_do_not_alias() -> None:
    assert len({item.value for item in PriceReferenceType}) == 6


@pytest.mark.parametrize("method", [NoVigMethod.SHIN, NoVigMethod.POWER, NoVigMethod.ADDITIVE])
def test_future_no_vig_methods_are_explicit_not_aliases(method: NoVigMethod) -> None:
    assert method is not NoVigMethod.PROPORTIONAL
