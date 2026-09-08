"""Deterministic filtering of caller-supplied history before feature computation."""

from __future__ import annotations

from dataclasses import dataclass

from pitchvalue.features.config import FeatureConfig, SeasonHistoryScope
from pitchvalue.features.contracts import (
    FeatureDiagnostics,
    FeatureValidationError,
    HistoricalMatch,
    MatchStatus,
    TargetFixture,
)


@dataclass(frozen=True)
class EligibleHistory:
    matches: tuple[HistoricalMatch, ...]
    diagnostics: FeatureDiagnostics


def select_eligible_history(
    target: TargetFixture,
    history: tuple[HistoricalMatch, ...] | list[HistoricalMatch],
    config: FeatureConfig,
) -> EligibleHistory:
    """Validate IDs and retain only ordinary finished matches known before cutoff."""
    seen_ids: set[str] = set()
    for match in history:
        if not isinstance(match, HistoricalMatch):
            raise FeatureValidationError("history entries must use HistoricalMatch")
        if match.match_id in seen_ids:
            raise FeatureValidationError(f"duplicate historical match_id: {match.match_id}")
        seen_ids.add(match.match_id)

    eligible: list[HistoricalMatch] = []
    target_ignored = 0
    future_ignored = 0
    same_time_ignored = 0
    competition_ignored = 0
    season_ignored = 0
    awarded_ignored = 0
    non_finished_ignored = 0
    allowed_seasons = {target.season_id}
    if config.season_history_scope is SeasonHistoryScope.CURRENT_AND_PREVIOUS_SEASON:
        assert config.previous_season_id is not None
        allowed_seasons.add(config.previous_season_id)

    for match in history:
        if match.match_id == target.match_id:
            if match.kickoff < target.cutoff:
                raise FeatureValidationError("target match_id appears before the feature cutoff")
            target_ignored += 1
            continue
        if match.competition_id != target.competition_id:
            competition_ignored += 1
            continue
        if match.season_id not in allowed_seasons:
            season_ignored += 1
            continue
        if match.kickoff > target.cutoff:
            future_ignored += 1
            continue
        if match.kickoff == target.cutoff:
            same_time_ignored += 1
            continue
        if match.status is MatchStatus.AWARDED:
            awarded_ignored += 1
            continue
        if match.status is not MatchStatus.FINISHED:
            non_finished_ignored += 1
            continue
        eligible.append(match)

    ordered = tuple(sorted(eligible, key=lambda item: (item.kickoff, item.match_id)))
    return EligibleHistory(
        matches=ordered,
        diagnostics=FeatureDiagnostics(
            history_rows_received=len(history),
            eligible_rows=len(ordered),
            target_rows_ignored=target_ignored,
            future_rows_ignored=future_ignored,
            same_time_rows_ignored=same_time_ignored,
            different_competition_rows_ignored=competition_ignored,
            different_season_rows_ignored=season_ignored,
            awarded_rows_ignored=awarded_ignored,
            non_finished_rows_ignored=non_finished_ignored,
        ),
    )
