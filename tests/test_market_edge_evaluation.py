from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from pitchvalue.markets.edge import HistoricalMarketGroup, HistoricalMarketPrice, RawMLProbability
from pitchvalue.markets.edge_evaluation import RawMLOOSRow, evaluate_market_value
from pitchvalue.markets.history.contracts import ObservationRole, OddsQualityStatus, TimingSemantics
from pitchvalue.markets.history.market import HistoricalMarketLoad
from pitchvalue.ml.model import MLClassProbability
from pitchvalue.prediction.contracts import MarketFamily, Selection


def _inputs() -> tuple[tuple[RawMLOOSRow, ...], HistoricalMarketLoad]:
    rows = []
    groups = []
    for index in range(6):
        match_id = f"match-{index}"
        observed = (Selection.HOME, Selection.DRAW, Selection.AWAY)[index % 3]
        model = RawMLProbability(
            f"row-{index}",
            match_id,
            "multinomial_logistic_v1",
            "FOOTBALL_PERFORMANCE_ONLY",
            datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index),
            (
                MLClassProbability(Selection.HOME, Decimal("0.5")),
                MLClassProbability(Selection.DRAW, Decimal("0.3")),
                MLClassProbability(Selection.AWAY, Decimal("0.2")),
            ),
        )
        rows.append(RawMLOOSRow("fold-1", f"comp-{index % 2}", "season-1", observed, model))
        for role in (ObservationRole.SOURCE_PREMATCH, ObservationRole.CLOSING):
            prices = tuple(
                HistoricalMarketPrice(
                    index * 10 + position,
                    match_id,
                    "provider-1",
                    "BET365",
                    MarketFamily.MATCH_RESULT,
                    selection,
                    Decimal(odds),
                    role,
                    TimingSemantics.ROLE_ONLY,
                    None,
                    OddsQualityStatus.ELIGIBLE,
                    ("timestamp_uncertain",),
                    1000 + index,
                    2000 + index,
                    f"B365{'C' if role is ObservationRole.CLOSING else ''}{suffix}",
                    "mapping-v1",
                    "normalization-v1",
                    "quality-v1",
                )
                for position, (selection, odds, suffix) in enumerate(
                    (
                        (Selection.HOME, "2.10", "H"),
                        (Selection.DRAW, "3.40", "D"),
                        (Selection.AWAY, "3.60", "A"),
                    ),
                    start=1,
                )
            )
            groups.append(
                HistoricalMarketGroup(
                    match_id, "BET365", role, TimingSemantics.ROLE_ONLY, None, prices
                )
            )
    return tuple(rows), HistoricalMarketLoad(tuple(groups), 36, 0, 0, 0, 0, (("eligible", 36),))


def test_same_row_market_metrics_have_equal_denominators() -> None:
    rows, markets = _inputs()
    result = evaluate_market_value(rows, markets)
    for role in (result.source_prematch, result.closing):
        assert role.matched_rows == 6
        assert role.model_metrics.sample_count == role.market_metrics.sample_count == 6


def test_roles_are_evaluated_separately() -> None:
    rows, markets = _inputs()
    result = evaluate_market_value(rows, markets)
    assert result.source_prematch.reference_label == "SOURCE_PREMATCH_ROLE_REFERENCE"
    assert result.closing.reference_label == "CLOSING_REFERENCE_DIAGNOSTIC"
    assert result.source_prematch.results is not result.closing.results


def test_edge_distributions_cover_all_three_selections() -> None:
    rows, markets = _inputs()
    result = evaluate_market_value(rows, markets)
    assert result.source_prematch.edge_distribution.count == len(rows) * 3
    assert sum(item.count for item in result.source_prematch.selection_breakdown) == len(rows) * 3


def test_competition_season_selection_and_odds_breakdowns_exist() -> None:
    rows, markets = _inputs()
    role = evaluate_market_value(rows, markets).source_prematch
    assert tuple(item.scope for item in role.competition_breakdown) == ("comp-0", "comp-1")
    assert tuple(item.scope for item in role.season_breakdown) == ("season-1",)
    assert tuple(item.selection for item in role.selection_breakdown) == (
        Selection.HOME,
        Selection.DRAW,
        Selection.AWAY,
    )
    assert role.odds_band_breakdown


def test_edge_realization_is_diagnostic_only() -> None:
    rows, markets = _inputs()
    diagnostics = evaluate_market_value(rows, markets).source_prematch.realization_breakdown
    assert diagnostics
    assert sum(item.count for item in diagnostics) == len(rows) * 3


def test_missing_market_is_counted_not_fabricated() -> None:
    rows, markets = _inputs()
    result = evaluate_market_value(rows + (replace_row(rows[0], "missing"),), markets)
    assert result.source_prematch.missing_market_rows == 1


def replace_row(row: RawMLOOSRow, match_id: str) -> RawMLOOSRow:
    model = RawMLProbability(
        row.model.row_id + "-missing",
        match_id,
        row.model.model_version,
        row.model.feature_profile,
        row.model.prediction_as_of,
        row.model.probabilities,
    )
    return RawMLOOSRow(row.fold_id, row.competition_id, row.season_id, row.observed, model)


def test_serialization_is_deterministic_and_rows_optional() -> None:
    rows, markets = _inputs()
    result = evaluate_market_value(rows, markets)
    assert result.to_dict() == result.to_dict()
    assert "results" not in result.to_dict()["source_prematch"]
    assert "results" in result.to_dict(include_rows=True)["source_prematch"]


def test_market_engine_source_has_no_calibrator_ensemble_or_policy_dependency() -> None:
    import pitchvalue.markets.edge as edge
    import pitchvalue.markets.edge_evaluation as evaluation

    source = "\n".join(
        Path(module.__file__).read_text(encoding="utf-8").lower() for module in (edge, evaluation)
    )
    assert "calibratedmlprediction" not in source
    assert "ensembleprediction" not in source
    assert "qualityclass" not in source
    assert "kelly" not in source
