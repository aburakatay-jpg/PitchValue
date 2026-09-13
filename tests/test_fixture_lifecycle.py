from __future__ import annotations

import pytest

from pitchvalue.providers.lifecycle import CanonicalFixtureState as State
from pitchvalue.providers.lifecycle import (
    LifecycleDecision,
    evaluate_transition,
    kickoff_revision_allowed,
    model_execution_allowed,
)


@pytest.mark.parametrize(
    ("current", "incoming"),
    [
        (State.SCHEDULED, State.IN_PLAY),
        (State.SCHEDULED, State.FINISHED),
        (State.SCHEDULED, State.POSTPONED),
        (State.SCHEDULED, State.CANCELLED),
        (State.POSTPONED, State.SCHEDULED),
        (State.IN_PLAY, State.FINISHED),
    ],
)
def test_canonical_lifecycle_accepts_supported_transitions(current: State, incoming: State) -> None:
    assert evaluate_transition(current, incoming).decision is LifecycleDecision.ACCEPT


@pytest.mark.parametrize(
    ("current", "incoming"),
    [
        (State.FINISHED, State.SCHEDULED),
        (State.CANCELLED, State.SCHEDULED),
        (State.ABANDONED, State.IN_PLAY),
        (State.IN_PLAY, State.POSTPONED),
    ],
)
def test_invalid_or_contradictory_transitions_require_review(
    current: State, incoming: State
) -> None:
    transition = evaluate_transition(current, incoming)
    assert transition.decision is LifecycleDecision.REVIEW_REQUIRED
    assert transition.reason == "INVALID_LIFECYCLE_TRANSITION"


def test_final_result_correction_requires_explicit_review() -> None:
    unchanged = evaluate_transition(State.FINISHED, State.FINISHED)
    corrected = evaluate_transition(State.FINISHED, State.FINISHED, result_changed=True)
    assert unchanged.decision is LifecycleDecision.UNCHANGED
    assert corrected.decision is LifecycleDecision.REVIEW_REQUIRED
    assert corrected.reason == "RESULT_REVISION_REVIEW"


def test_kickoff_revision_and_model_execution_are_fail_closed() -> None:
    assert kickoff_revision_allowed(State.SCHEDULED)
    assert kickoff_revision_allowed(State.POSTPONED)
    assert not kickoff_revision_allowed(State.FINISHED)
    assert model_execution_allowed(State.SCHEDULED)
    for state in set(State) - {State.SCHEDULED}:
        assert not model_execution_allowed(state)
