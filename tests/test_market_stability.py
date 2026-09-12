from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pitchvalue.markets.stability import (
    ContinuityState,
    StabilityObservation,
    StabilityStatus,
    calculate_market_stability,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection

D = Decimal
BASE = datetime(2026, 9, 12, 8, tzinfo=UTC)


def _observation(hours: int, odds: str = "2.00") -> StabilityObservation:
    return StabilityObservation(
        "match-1",
        "BET365",
        MarketFamily.MATCH_RESULT,
        Selection.HOME,
        None,
        "normalization_v1",
        D(odds),
        BASE + timedelta(hours=hours),
        True,
    )


def test_one_observation_proves_existence_freshness_but_not_stability() -> None:
    result = calculate_market_stability(
        (_observation(0),), as_of=BASE + timedelta(hours=2), maximum_expected_gap=timedelta(hours=3)
    )
    assert result.status is StabilityStatus.UNAVAILABLE
    assert result.observation_count == 1
    assert result.market_family_complete
    assert result.freshness == timedelta(hours=2)
    assert result.absolute_implied_probability_movement is None


def test_comparable_series_reports_movement_reversals_gap_and_freshness() -> None:
    result = calculate_market_stability(
        (_observation(0, "2.00"), _observation(1, "2.20"), _observation(2, "2.10")),
        as_of=BASE + timedelta(hours=3),
        maximum_expected_gap=timedelta(hours=2),
    )
    assert result.status is StabilityStatus.AVAILABLE
    assert result.observation_count == 3
    assert result.directional_reversal_count == 1
    assert result.maximum_single_step_movement is not None
    assert result.continuity is ContinuityState.CONTINUOUS
    assert result.freshness == timedelta(hours=1)


@pytest.mark.parametrize(
    ("replacement", "diagnostic"),
    [
        ({"line": D("2.5")}, "INCOMPARABLE_SERIES"),
        ({"bookmaker": "OTHER"}, "INCOMPARABLE_SERIES"),
        ({"normalization_version": "v2"}, "INCOMPARABLE_SERIES"),
        ({"market_family_complete": False}, "MARKET_FAMILY_INCOMPLETE"),
    ],
)
def test_incomparable_or_incomplete_series_is_hard_invalid(
    replacement: dict[str, object], diagnostic: str
) -> None:
    observations = (_observation(0), replace(_observation(1), **replacement))  # type: ignore[arg-type]
    result = calculate_market_stability(
        observations, as_of=BASE + timedelta(hours=2), maximum_expected_gap=timedelta(hours=2)
    )
    assert result.status is StabilityStatus.HARD_INVALID
    assert result.diagnostics == (diagnostic,)


def test_duplicate_or_future_observation_is_hard_invalid() -> None:
    duplicate = calculate_market_stability(
        (_observation(0), _observation(0, "2.10")),
        as_of=BASE + timedelta(hours=1),
        maximum_expected_gap=timedelta(hours=2),
    )
    future = calculate_market_stability(
        (_observation(0), _observation(2)),
        as_of=BASE + timedelta(hours=1),
        maximum_expected_gap=timedelta(hours=2),
    )
    assert duplicate.diagnostics == ("CONFLICTING_OBSERVATION_TIME",)
    assert future.diagnostics == ("FUTURE_OBSERVATION",)


def test_empty_series_and_naive_as_of_are_explicit() -> None:
    empty = calculate_market_stability((), as_of=BASE, maximum_expected_gap=timedelta(hours=1))
    assert empty.status is StabilityStatus.UNAVAILABLE
    with pytest.raises(ValueError, match="timezone-aware"):
        calculate_market_stability(
            (_observation(0),),
            as_of=datetime(2026, 9, 12),
            maximum_expected_gap=timedelta(hours=1),
        )
