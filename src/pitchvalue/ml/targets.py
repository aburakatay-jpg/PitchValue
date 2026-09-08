"""Deterministic V1 target definitions and label derivation."""

from __future__ import annotations

from dataclasses import dataclass

from pitchvalue.features.contracts import MatchStatus
from pitchvalue.ml.contracts import ResolvedMatchOutcome, RowStatus, TargetDefinition, TargetScalar
from pitchvalue.prediction.contracts import MarketFamily, Selection


@dataclass(frozen=True)
class TargetDerivation:
    status: RowStatus
    value: TargetScalar | None


def derive_target(target: TargetDefinition, outcome: ResolvedMatchOutcome) -> TargetDerivation:
    if (
        outcome.status is not MatchStatus.FINISHED
        or outcome.home_goals is None
        or outcome.away_goals is None
    ):
        return TargetDerivation(RowStatus.TARGET_UNAVAILABLE, None)
    home, away = outcome.home_goals, outcome.away_goals
    value: TargetScalar
    if target.market is MarketFamily.MATCH_RESULT:
        value = Selection.HOME if home > away else Selection.AWAY if away > home else Selection.DRAW
    elif target.market is MarketFamily.BTTS:
        value = Selection.YES if home > 0 and away > 0 else Selection.NO
    elif target.market is MarketFamily.TOTAL_GOALS:
        assert target.line is not None
        value = Selection.OVER if home + away > target.line else Selection.UNDER
    elif target.market is MarketFamily.HOME_TEAM_TOTAL:
        assert target.line is not None
        value = Selection.OVER if home > target.line else Selection.UNDER
    elif target.market is MarketFamily.AWAY_TEAM_TOTAL:
        assert target.line is not None
        value = Selection.OVER if away > target.line else Selection.UNDER
    elif target.market is MarketFamily.DOUBLE_CHANCE:
        value = _double_chance(target.selection, home, away)
    else:  # pragma: no cover - target contract prevents this
        return TargetDerivation(RowStatus.INVALID_TARGET, None)
    return TargetDerivation(RowStatus.READY, value)


def _double_chance(selection: Selection | None, home: int, away: int) -> bool:
    if selection is Selection.ONE_X:
        return home >= away
    if selection is Selection.X_TWO:
        return away >= home
    return home != away
