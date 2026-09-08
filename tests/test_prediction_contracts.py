from dataclasses import replace
from decimal import Decimal

import pytest

from pitchvalue.prediction.contracts import (
    AnalysisAvailability,
    ContractValidationError,
    MarketCandidate,
    MarketFamily,
    PickSelectionLimits,
    Selection,
    decimal_value,
)

D = Decimal


def candidate_for(
    market: MarketFamily,
    selection: Selection,
    line: Decimal | None,
) -> MarketCandidate:
    return MarketCandidate(
        match_id="00000000-0000-0000-0000-000000000001",
        market=market,
        selection=selection,
        line=line,
        model_probability=D("0.58"),
        market_implied_probability=D("0.50"),
        decimal_odds=D("2.00"),
        model_agreement_count=3,
        model_count=4,
        data_quality_score=D("85"),
        calibration_confidence=D("80"),
        market_stability_score=D("75"),
        analysis_availability=AnalysisAvailability.AVAILABLE,
    )


@pytest.mark.parametrize(
    ("market", "selection", "line"),
    [
        (MarketFamily.MATCH_RESULT, Selection.HOME, None),
        (MarketFamily.MATCH_RESULT, Selection.DRAW, None),
        (MarketFamily.MATCH_RESULT, Selection.AWAY, None),
        (MarketFamily.TOTAL_GOALS, Selection.OVER, D("1.5")),
        (MarketFamily.TOTAL_GOALS, Selection.UNDER, D("2.5")),
        (MarketFamily.BTTS, Selection.YES, None),
        (MarketFamily.BTTS, Selection.NO, None),
        (MarketFamily.DOUBLE_CHANCE, Selection.ONE_X, None),
        (MarketFamily.DOUBLE_CHANCE, Selection.X_TWO, None),
        (MarketFamily.DOUBLE_CHANCE, Selection.ONE_TWO, None),
        (MarketFamily.HOME_TEAM_TOTAL, Selection.OVER, D("0.5")),
        (MarketFamily.HOME_TEAM_TOTAL, Selection.UNDER, D("1.5")),
        (MarketFamily.AWAY_TEAM_TOTAL, Selection.OVER, D("0.5")),
        (MarketFamily.AWAY_TEAM_TOTAL, Selection.UNDER, D("1.5")),
    ],
)
def test_v1_market_selection_contracts(
    market: MarketFamily,
    selection: Selection,
    line: Decimal | None,
) -> None:
    value = candidate_for(market, selection, line)
    assert (value.market, value.selection, value.line) == (market, selection, line)


@pytest.mark.parametrize(
    ("market", "selection", "line"),
    [
        (MarketFamily.MATCH_RESULT, Selection.OVER, None),
        (MarketFamily.BTTS, Selection.HOME, None),
        (MarketFamily.TOTAL_GOALS, Selection.OVER, D("3.5")),
        (MarketFamily.HOME_TEAM_TOTAL, Selection.UNDER, D("2.5")),
        (MarketFamily.DOUBLE_CHANCE, Selection.ONE_X, D("0.5")),
    ],
)
def test_invalid_market_selection_or_line_is_rejected(
    market: MarketFamily,
    selection: Selection,
    line: Decimal | None,
) -> None:
    with pytest.raises(ContractValidationError):
        candidate_for(market, selection, line)


@pytest.mark.parametrize("unsupported", ["corners", "cards", "correct_score", "first_half"])
def test_v2_markets_are_not_canonical_v1_identifiers(unsupported: str) -> None:
    with pytest.raises(ValueError):
        MarketFamily(unsupported)


def test_edge_is_derived_and_cannot_drift_from_probabilities() -> None:
    value = candidate_for(MarketFamily.MATCH_RESULT, Selection.HOME, None)
    assert value.edge == D("0.08")


def test_missing_components_remain_none() -> None:
    base = candidate_for(MarketFamily.MATCH_RESULT, Selection.HOME, None)
    value = replace(
        base,
        data_quality_score=None,
        calibration_confidence=None,
        market_stability_score=None,
    )
    assert value.data_quality_score is None
    assert value.calibration_confidence is None
    assert value.market_stability_score is None


def test_float_policy_input_is_rejected_at_explicit_boundary() -> None:
    with pytest.raises(ContractValidationError, match="Decimal"):
        decimal_value(0.54)  # type: ignore[arg-type]


def test_decimal_conversion_boundary_is_explicit() -> None:
    assert decimal_value("0.54") == D("0.54")


def test_candidate_rejects_non_decimal_numeric_fields() -> None:
    base = candidate_for(MarketFamily.MATCH_RESULT, Selection.HOME, None)
    values = {**base.__dict__, "decimal_odds": 2.0}
    with pytest.raises(ContractValidationError, match="must use Decimal"):
        MarketCandidate(**values)


def test_future_ranking_output_limits_are_one_per_role() -> None:
    limits = PickSelectionLimits()
    assert limits.maximum_main_picks == 1
    assert limits.maximum_alternative_picks == 1
