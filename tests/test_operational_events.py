from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from pitchvalue.operations.events import (
    DeliveryVisibility,
    EventSeverity,
    EventType,
    OperationalEvent,
    ReasonCode,
    severity_for,
)


def _event(event_type: EventType = EventType.RUN_STARTED) -> OperationalEvent:
    return OperationalEvent(
        OperationalEvent.deterministic_id(event_type, "correlation-1", "runner", "attempt-1"),
        event_type,
        "operational_event_v1",
        datetime(2026, 9, 12, tzinfo=UTC),
        severity_for(event_type),
        "correlation-1",
        "runner",
        {"attempt": "1"},
        DeliveryVisibility.OPERATIONS,
        reason_code=(
            ReasonCode.PERSISTENCE_FAILED if event_type is EventType.PERSISTENCE_FAILED else None
        ),
    )


def test_event_identity_and_metadata_are_deterministic_and_immutable() -> None:
    first = _event()
    second = _event()
    assert first == second
    assert tuple(first.metadata) == ("attempt",)
    with pytest.raises(FrozenInstanceError):
        first.event_id = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        first.metadata["secret"] = "x"  # type: ignore[index]


def test_severity_mapping_is_stable() -> None:
    assert severity_for(EventType.RUN_STARTED) is EventSeverity.INFO
    assert severity_for(EventType.FIXTURE_QUARANTINED) is EventSeverity.WARNING
    assert severity_for(EventType.PERSISTENCE_FAILED) is EventSeverity.ERROR


def test_incorrect_severity_and_naive_time_are_rejected() -> None:
    with pytest.raises(ValueError, match="canonical event mapping"):
        replace(_event(), severity=EventSeverity.CRITICAL)
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(_event(), occurred_at=datetime(2026, 9, 12))


def test_taxonomy_contains_required_provider_neutral_events_and_reasons() -> None:
    assert {"RUN_SCHEDULED", "PROVIDER_FAILED", "REPORT_ARCHIVE_FAILED"} <= {
        item.value for item in EventType
    }
    assert {"DB_UNAVAILABLE", "LEAKAGE_VIOLATION", "PROVIDER_TIMEOUT"} <= {
        item.value for item in ReasonCode
    }
