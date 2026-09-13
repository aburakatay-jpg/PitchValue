"""Provider-independent fixture lifecycle capability and transition safety."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CanonicalFixtureState(StrEnum):
    SCHEDULED = "SCHEDULED"
    IN_PLAY = "IN_PLAY"
    FINISHED = "FINISHED"
    AWARDED = "AWARDED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
    ABANDONED = "ABANDONED"


class LifecycleDecision(StrEnum):
    UNCHANGED = "UNCHANGED"
    ACCEPT = "ACCEPT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class LifecycleTransition:
    current: CanonicalFixtureState
    incoming: CanonicalFixtureState
    decision: LifecycleDecision
    reason: str


_VALID_TRANSITIONS = {
    CanonicalFixtureState.SCHEDULED: frozenset(
        {
            CanonicalFixtureState.IN_PLAY,
            CanonicalFixtureState.FINISHED,
            CanonicalFixtureState.AWARDED,
            CanonicalFixtureState.POSTPONED,
            CanonicalFixtureState.CANCELLED,
            CanonicalFixtureState.ABANDONED,
        }
    ),
    CanonicalFixtureState.IN_PLAY: frozenset(
        {CanonicalFixtureState.FINISHED, CanonicalFixtureState.ABANDONED}
    ),
    CanonicalFixtureState.POSTPONED: frozenset(
        {CanonicalFixtureState.SCHEDULED, CanonicalFixtureState.CANCELLED}
    ),
    CanonicalFixtureState.FINISHED: frozenset(),
    CanonicalFixtureState.AWARDED: frozenset(),
    CanonicalFixtureState.CANCELLED: frozenset(),
    CanonicalFixtureState.ABANDONED: frozenset(),
}


def evaluate_transition(
    current: CanonicalFixtureState,
    incoming: CanonicalFixtureState,
    *,
    result_changed: bool = False,
) -> LifecycleTransition:
    """Accept only explicit lifecycle movement; corrections remain operator-reviewed."""
    if current is incoming:
        if result_changed and current in {
            CanonicalFixtureState.FINISHED,
            CanonicalFixtureState.AWARDED,
        }:
            return LifecycleTransition(
                current, incoming, LifecycleDecision.REVIEW_REQUIRED, "RESULT_REVISION_REVIEW"
            )
        return LifecycleTransition(current, incoming, LifecycleDecision.UNCHANGED, "UNCHANGED")
    if incoming in _VALID_TRANSITIONS[current]:
        return LifecycleTransition(current, incoming, LifecycleDecision.ACCEPT, "VALID_TRANSITION")
    return LifecycleTransition(
        current, incoming, LifecycleDecision.REVIEW_REQUIRED, "INVALID_LIFECYCLE_TRANSITION"
    )


def kickoff_revision_allowed(state: CanonicalFixtureState) -> bool:
    return state in {CanonicalFixtureState.SCHEDULED, CanonicalFixtureState.POSTPONED}


def model_execution_allowed(state: CanonicalFixtureState) -> bool:
    return state is CanonicalFixtureState.SCHEDULED
