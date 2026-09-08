from decimal import Decimal

import pytest

from pitchvalue.features.contracts import MatchStatus
from pitchvalue.ml import (
    MLDatasetValidationError,
    ResolvedMatchOutcome,
    RowStatus,
    TargetDefinition,
    TargetMode,
    derive_target,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection


def _outcome(
    home: int | None, away: int | None, status: MatchStatus = MatchStatus.FINISHED
) -> ResolvedMatchOutcome:
    return ResolvedMatchOutcome("match-1", status, home, away)


def _target(
    market: MarketFamily, *, line: str | None = None, selection: Selection | None = None
) -> TargetDefinition:
    if market is MarketFamily.MATCH_RESULT:
        return TargetDefinition(
            market, TargetMode.MULTICLASS, (Selection.HOME, Selection.DRAW, Selection.AWAY)
        )
    if market is MarketFamily.BTTS:
        return TargetDefinition(market, TargetMode.MULTICLASS, (Selection.YES, Selection.NO))
    if market is MarketFamily.DOUBLE_CHANCE:
        return TargetDefinition(market, TargetMode.BINARY, (), selection=selection)
    return TargetDefinition(
        market, TargetMode.MULTICLASS, (Selection.OVER, Selection.UNDER), Decimal(line or "1.5")
    )


@pytest.mark.parametrize(
    ("home", "away", "expected"),
    [(2, 1, Selection.HOME), (1, 1, Selection.DRAW), (0, 2, Selection.AWAY)],
)
def test_match_result_targets(home: int, away: int, expected: Selection) -> None:
    assert derive_target(_target(MarketFamily.MATCH_RESULT), _outcome(home, away)).value is expected


@pytest.mark.parametrize(
    ("home", "away", "expected"),
    [(1, 1, Selection.YES), (0, 2, Selection.NO), (2, 0, Selection.NO), (0, 0, Selection.NO)],
)
def test_btts_targets(home: int, away: int, expected: Selection) -> None:
    assert derive_target(_target(MarketFamily.BTTS), _outcome(home, away)).value is expected


@pytest.mark.parametrize(
    ("market", "line", "home", "away", "expected"),
    [
        (MarketFamily.TOTAL_GOALS, "1.5", 1, 1, Selection.OVER),
        (MarketFamily.TOTAL_GOALS, "1.5", 1, 0, Selection.UNDER),
        (MarketFamily.TOTAL_GOALS, "2.5", 2, 1, Selection.OVER),
        (MarketFamily.TOTAL_GOALS, "2.5", 1, 1, Selection.UNDER),
        (MarketFamily.HOME_TEAM_TOTAL, "0.5", 1, 0, Selection.OVER),
        (MarketFamily.HOME_TEAM_TOTAL, "0.5", 0, 3, Selection.UNDER),
        (MarketFamily.HOME_TEAM_TOTAL, "1.5", 2, 0, Selection.OVER),
        (MarketFamily.AWAY_TEAM_TOTAL, "0.5", 0, 1, Selection.OVER),
        (MarketFamily.AWAY_TEAM_TOTAL, "0.5", 3, 0, Selection.UNDER),
        (MarketFamily.AWAY_TEAM_TOTAL, "1.5", 0, 2, Selection.OVER),
    ],
)
def test_line_target_derivation(
    market: MarketFamily, line: str, home: int, away: int, expected: Selection
) -> None:
    target = _target(market, line=line)
    assert target.line == Decimal(line)
    assert derive_target(target, _outcome(home, away)).value is expected


@pytest.mark.parametrize("line", [Decimal("0.5"), Decimal("3.5")])
def test_unsupported_total_line_rejected(line: Decimal) -> None:
    with pytest.raises(MLDatasetValidationError):
        TargetDefinition(
            MarketFamily.TOTAL_GOALS, TargetMode.MULTICLASS, (Selection.OVER, Selection.UNDER), line
        )


@pytest.mark.parametrize(
    ("selection", "home", "away", "expected"),
    [
        (Selection.ONE_X, 2, 1, True),
        (Selection.ONE_X, 1, 1, True),
        (Selection.ONE_X, 0, 1, False),
        (Selection.X_TWO, 1, 2, True),
        (Selection.X_TWO, 1, 1, True),
        (Selection.X_TWO, 2, 1, False),
        (Selection.ONE_TWO, 2, 1, True),
        (Selection.ONE_TWO, 1, 2, True),
        (Selection.ONE_TWO, 1, 1, False),
    ],
)
def test_double_chance_is_binary_per_selection(
    selection: Selection, home: int, away: int, expected: bool
) -> None:
    target = _target(MarketFamily.DOUBLE_CHANCE, selection=selection)
    assert target.mode is TargetMode.BINARY
    assert target.classes == ()
    assert derive_target(target, _outcome(home, away)).value is expected


def test_double_chance_exclusive_multiclass_is_rejected() -> None:
    with pytest.raises(MLDatasetValidationError):
        TargetDefinition(
            MarketFamily.DOUBLE_CHANCE,
            TargetMode.MULTICLASS,
            (Selection.ONE_X, Selection.X_TWO, Selection.ONE_TWO),
        )


@pytest.mark.parametrize(
    "status",
    [MatchStatus.SCHEDULED, MatchStatus.AWARDED, MatchStatus.CANCELLED, MatchStatus.POSTPONED],
)
def test_nonordinary_or_unresolved_outcome_is_unavailable(status: MatchStatus) -> None:
    result = derive_target(_target(MarketFamily.MATCH_RESULT), _outcome(2, 1, status))
    assert result.status is RowStatus.TARGET_UNAVAILABLE
    assert result.value is None


def test_target_definition_serialization_is_semantic() -> None:
    data = _target(MarketFamily.MATCH_RESULT).to_dict()
    assert data["classes"] == ["home", "draw", "away"]
    assert "features" not in data


def test_outcome_rejects_negative_goals() -> None:
    with pytest.raises(MLDatasetValidationError):
        _outcome(-1, 0)
