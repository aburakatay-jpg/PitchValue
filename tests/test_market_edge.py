from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pitchvalue.markets.edge import (
    EdgeOddsBand,
    EdgeThresholdDiagnostic,
    HistoricalMarketGroup,
    HistoricalMarketPrice,
    MarketComparisonStatus,
    MarketEdgeError,
    RawMLProbability,
    build_market_probability,
    calculate_market_edges,
    classify_edge,
    classify_odds,
)
from pitchvalue.markets.history.contracts import (
    ObservationRole,
    OddsQualityStatus,
    TimingSemantics,
)
from pitchvalue.ml.model import MLClassProbability
from pitchvalue.prediction.contracts import MarketFamily, Selection

AS_OF = datetime(2025, 1, 2, tzinfo=UTC)


def _price(
    selection: Selection,
    odds: str,
    *,
    role: ObservationRole = ObservationRole.SOURCE_PREMATCH,
    timing: TimingSemantics = TimingSemantics.ROLE_ONLY,
    observed_at: datetime | None = None,
    quality: OddsQualityStatus = OddsQualityStatus.ELIGIBLE,
    snapshot_id: int | None = None,
) -> HistoricalMarketPrice:
    suffix = {Selection.HOME: "H", Selection.DRAW: "D", Selection.AWAY: "A"}[selection]
    return HistoricalMarketPrice(
        snapshot_id or {Selection.HOME: 1, Selection.DRAW: 2, Selection.AWAY: 3}[selection],
        "match-1",
        "provider-1",
        "BET365",
        MarketFamily.MATCH_RESULT,
        selection,
        Decimal(odds),
        role,
        timing,
        observed_at,
        quality,
        ("timestamp_uncertain",),
        100,
        200,
        f"B365{suffix}",
        "football_data_mapping_v1",
        "historical_odds_normalization_v1",
        "football_data_quality_v1",
    )


def _group(
    *,
    role: ObservationRole = ObservationRole.SOURCE_PREMATCH,
    timing: TimingSemantics = TimingSemantics.ROLE_ONLY,
    observed_at: datetime | None = None,
) -> HistoricalMarketGroup:
    prices = tuple(
        _price(selection, odds, role=role, timing=timing, observed_at=observed_at)
        for selection, odds in (
            (Selection.HOME, "2.00"),
            (Selection.DRAW, "4.00"),
            (Selection.AWAY, "4.00"),
        )
    )
    return HistoricalMarketGroup("match-1", "BET365", role, timing, observed_at, prices)


def _model(*, source: str = "RAW_TASK16_ML") -> RawMLProbability:
    return RawMLProbability(
        "row-1",
        "match-1",
        "multinomial_logistic_v1",
        "FOOTBALL_PERFORMANCE_ONLY",
        AS_OF,
        (
            MLClassProbability(Selection.HOME, Decimal("0.55")),
            MLClassProbability(Selection.DRAW, Decimal("0.25")),
            MLClassProbability(Selection.AWAY, Decimal("0.20")),
        ),
        source,
    )


def test_market_probability_reuses_task11_no_vig_math() -> None:
    result = build_market_probability(_group())
    assert tuple(item.raw_implied_probability for item in result.selections) == (
        Decimal("0.5"),
        Decimal("0.25"),
        Decimal("0.25"),
    )
    assert tuple(item.no_vig_probability for item in result.selections) == (
        Decimal("0.5"),
        Decimal("0.25"),
        Decimal("0.25"),
    )
    assert result.book_percentage == Decimal("1.00")
    assert result.overround == Decimal("0.00")


def test_edges_are_calculated_for_every_selection() -> None:
    result = calculate_market_edges(_model(), build_market_probability(_group()))
    assert tuple(item.selection for item in result.edges) == (
        Selection.HOME,
        Selection.DRAW,
        Selection.AWAY,
    )
    assert tuple(item.edge for item in result.edges) == (
        Decimal("0.05"),
        Decimal("0.00"),
        Decimal("-0.05"),
    )
    assert result.best_edge_selection is Selection.HOME
    assert result.model_top_selection is Selection.HOME


def test_raw_price_ev_is_separate_from_edge() -> None:
    result = calculate_market_edges(_model(), build_market_probability(_group()))
    assert result.edges[0].raw_price_ev == Decimal("0.1000")
    assert result.edges[0].raw_price_ev != result.edges[0].edge


@pytest.mark.parametrize("odds", ["1", "0", "-2", "NaN", "Infinity"])
def test_invalid_decimal_odds_are_rejected(odds: str) -> None:
    with pytest.raises(ValueError):
        _price(Selection.HOME, odds)


def test_complete_group_is_required() -> None:
    prices = _group().prices[:2]
    with pytest.raises(MarketEdgeError, match="exactly HOME"):
        HistoricalMarketGroup(
            "match-1",
            "BET365",
            ObservationRole.SOURCE_PREMATCH,
            TimingSemantics.ROLE_ONLY,
            None,
            prices,
        )


def test_duplicate_selection_is_rejected() -> None:
    group = _group()
    with pytest.raises(MarketEdgeError):
        replace(group, prices=(group.prices[0], group.prices[0], group.prices[2]))


def test_mismatched_match_is_rejected() -> None:
    group = _group()
    with pytest.raises(MarketEdgeError, match="mismatched"):
        replace(
            group,
            prices=(group.prices[0], replace(group.prices[1], match_id="other"), group.prices[2]),
        )


def test_wrong_market_and_role_are_rejected() -> None:
    with pytest.raises(MarketEdgeError, match="MATCH_RESULT"):
        replace(_price(Selection.HOME, "2"), market=MarketFamily.TOTAL_GOALS)
    with pytest.raises(MarketEdgeError, match="role"):
        replace(_price(Selection.HOME, "2"), observation_role=ObservationRole.LIVE)


def test_ineligible_quality_is_excluded_by_default() -> None:
    group = _group()
    suspect = replace(group.prices[0], quality_status=OddsQualityStatus.SUSPECT)
    with pytest.raises(MarketEdgeError, match="eligible"):
        build_market_probability(replace(group, prices=(suspect, *group.prices[1:])))


def test_role_only_prematch_is_not_exact_time() -> None:
    result = build_market_probability(_group())
    assert result.status is MarketComparisonStatus.ROLE_ONLY_COMPARISON
    assert result.observed_at is None
    assert "SOURCE_PREMATCH_ROLE_REFERENCE" in result.diagnostics


def test_role_only_closing_is_hindsight_reference() -> None:
    result = build_market_probability(_group(role=ObservationRole.CLOSING))
    assert result.status is MarketComparisonStatus.ROLE_ONLY_COMPARISON
    assert "CLOSING_REFERENCE_DIAGNOSTIC" in result.diagnostics


def test_exact_future_quote_is_not_legal_at_prediction_time() -> None:
    group = _group(timing=TimingSemantics.EXACT, observed_at=AS_OF + timedelta(hours=1))
    with pytest.raises(MarketEdgeError, match="after prediction_as_of"):
        calculate_market_edges(_model(), build_market_probability(group))


def test_role_only_timestamp_is_never_synthesized() -> None:
    market = build_market_probability(_group())
    result = calculate_market_edges(_model(), market)
    assert result.observed_at is None
    assert result.prediction_as_of == AS_OF
    assert result.comparison_status is MarketComparisonStatus.ROLE_ONLY_COMPARISON


@pytest.mark.parametrize("source", ["TEMPERATURE_CALIBRATED_ML", "ACCEPTED_ENSEMBLE"])
def test_rejected_model_sources_cannot_be_canonical(source: str) -> None:
    with pytest.raises(MarketEdgeError, match="raw TASK 16"):
        _model(source=source)


@pytest.mark.parametrize(
    ("edge", "expected"),
    [
        ("0.0399", EdgeThresholdDiagnostic.BELOW_THRESHOLD),
        ("0.04", EdgeThresholdDiagnostic.WATCHLIST_EDGE),
        ("0.0599", EdgeThresholdDiagnostic.WATCHLIST_EDGE),
        ("0.06", EdgeThresholdDiagnostic.PUBLISHABLE_EDGE),
    ],
)
def test_edge_threshold_diagnostics_are_not_pick_decisions(
    edge: str, expected: EdgeThresholdDiagnostic
) -> None:
    assert classify_edge(Decimal(edge)) is expected


@pytest.mark.parametrize(
    ("odds", "expected"),
    [
        ("1.34", EdgeOddsBand.BELOW_1_35),
        ("1.35", EdgeOddsBand.FROM_1_35_TO_1_49),
        ("1.50", EdgeOddsBand.FROM_1_50_TO_2_20),
        ("2.20", EdgeOddsBand.FROM_1_50_TO_2_20),
        ("2.21", EdgeOddsBand.FROM_2_21_TO_3_00),
        ("3.00", EdgeOddsBand.FROM_2_21_TO_3_00),
        ("3.01", EdgeOddsBand.ABOVE_3_00),
    ],
)
def test_odds_band_does_not_change_edge_math(odds: str, expected: EdgeOddsBand) -> None:
    assert classify_odds(Decimal(odds)) is expected


def test_contracts_are_immutable_and_deterministic() -> None:
    result = calculate_market_edges(_model(), build_market_probability(_group()))
    assert result.to_dict() == result.to_dict()
    with pytest.raises(FrozenInstanceError):
        result.bookmaker = "OTHER"  # type: ignore[misc]


def test_lineage_and_versions_are_preserved() -> None:
    result = calculate_market_edges(_model(), build_market_probability(_group()))
    edge = result.edges[0]
    assert edge.source_match_provider_ref_id == 100
    assert edge.source_staging_row_id == 200
    assert edge.source_field == "B365H"
    assert result.normalization_version == "historical_odds_normalization_v1"
    assert result.quality_policy_version == "football_data_quality_v1"
