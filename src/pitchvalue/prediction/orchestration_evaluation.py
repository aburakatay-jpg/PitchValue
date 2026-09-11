"""Deterministic summaries for TASK 20 policy simulations."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pitchvalue.prediction.config import DEFAULT_POLICY, PredictionPolicyConfig
from pitchvalue.prediction.contracts import QualityClass
from pitchvalue.prediction.orchestration import (
    BetScoreCompleteness,
    ComponentStatus,
    MatchDecision,
    MatchDecisionStatus,
)


@dataclass(frozen=True)
class PolicySimulationSummary:
    label: str
    matches_evaluated: int
    selections_evaluated: int
    below_edge: int
    watchlist_edge: int
    publishable_edge: int
    provisional_no_bet: int
    provisional_watchlist: int
    provisional_pick: int
    provisional_strong: int
    provisional_elite: int
    ambiguous_matches: int
    unavailable_matches: int
    publication_eligible_selections: int
    publication_eligible_matches: int
    component_available_counts: tuple[tuple[str, int], ...]
    bet_score_complete: int
    bet_score_partial: int
    bet_score_unavailable: int
    match_status_counts: tuple[tuple[str, int], ...]
    blocker_counts: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        result = _primitive(self)
        if not isinstance(result, dict):  # pragma: no cover
            raise TypeError("simulation summary must serialize to a mapping")
        return result


def summarize_policy_simulation(
    decisions: tuple[MatchDecision, ...],
    label: str,
    policy: PredictionPolicyConfig = DEFAULT_POLICY,
) -> PolicySimulationSummary:
    """Summarize decisions without interpreting them as bets or realized returns."""
    if not label.strip():
        raise ValueError("simulation label is required")
    selections = tuple(item for match in decisions for item in match.selection_decisions)
    components: Counter[str] = Counter()
    blockers: Counter[str] = Counter()
    statuses = Counter(item.status.value for item in decisions)
    completeness = Counter(item.bet_score_completeness.value for item in selections)
    classes = Counter(item.policy_decision.value for item in selections)
    for item in selections:
        for component in item.components:
            if component.status is ComponentStatus.AVAILABLE:
                components[component.name] += 1
        blockers.update(item.blockers)
    return PolicySimulationSummary(
        label,
        len(decisions),
        len(selections),
        sum(item.edge < policy.edge_watchlist_threshold for item in selections),
        sum(
            policy.edge_watchlist_threshold <= item.edge < policy.edge_publication_threshold
            for item in selections
        ),
        sum(item.edge >= policy.edge_publication_threshold for item in selections),
        classes[QualityClass.NO_BET.value],
        classes[QualityClass.WATCHLIST.value],
        classes[QualityClass.PICK.value],
        classes[QualityClass.STRONG_PICK.value],
        classes[QualityClass.ELITE_PICK.value],
        statuses[MatchDecisionStatus.MULTIPLE_POLICY_CANDIDATES.value],
        statuses[MatchDecisionStatus.UNAVAILABLE.value],
        sum(item.publication_eligible for item in selections),
        sum(item.publication_eligible for item in decisions),
        tuple(sorted(components.items())),
        completeness[BetScoreCompleteness.COMPLETE.value],
        completeness[BetScoreCompleteness.PARTIAL.value],
        completeness[BetScoreCompleteness.UNAVAILABLE.value],
        tuple(sorted(statuses.items())),
        tuple(sorted(blockers.items())),
    )


def _primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value
