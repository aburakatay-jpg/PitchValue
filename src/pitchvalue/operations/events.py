"""Stable provider-neutral operational events and delivery state."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType


class EventType(StrEnum):
    RUN_SCHEDULED = "RUN_SCHEDULED"
    RUN_STARTED = "RUN_STARTED"
    CURRENT_SEASON_SYNC_STARTED = "CURRENT_SEASON_SYNC_STARTED"
    CURRENT_SEASON_SYNC_SUCCEEDED = "CURRENT_SEASON_SYNC_SUCCEEDED"
    CURRENT_SEASON_SYNC_FAILED = "CURRENT_SEASON_SYNC_FAILED"
    FIXTURE_REFRESH_STARTED = "FIXTURE_REFRESH_STARTED"
    FIXTURE_REFRESH_SUCCEEDED = "FIXTURE_REFRESH_SUCCEEDED"
    FIXTURE_REFRESH_FAILED = "FIXTURE_REFRESH_FAILED"
    DATA_GATE_STARTED = "DATA_GATE_STARTED"
    DATA_GATE_SUCCEEDED = "DATA_GATE_SUCCEEDED"
    DATA_GATE_FAILED = "DATA_GATE_FAILED"
    FIXTURE_QUARANTINED = "FIXTURE_QUARANTINED"
    FULL_ENGINE_STARTED = "FULL_ENGINE_STARTED"
    MATCH_ANALYSIS_STARTED = "MATCH_ANALYSIS_STARTED"
    MATCH_ANALYSIS_COMPLETED = "MATCH_ANALYSIS_COMPLETED"
    MATCH_ANALYSIS_FAILED = "MATCH_ANALYSIS_FAILED"
    PERSISTENCE_STARTED = "PERSISTENCE_STARTED"
    PERSISTENCE_SUCCEEDED = "PERSISTENCE_SUCCEEDED"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    REPORT_GENERATION_STARTED = "REPORT_GENERATION_STARTED"
    REPORT_GENERATION_SUCCEEDED = "REPORT_GENERATION_SUCCEEDED"
    REPORT_ARCHIVE_FAILED = "REPORT_ARCHIVE_FAILED"
    RUN_SUCCEEDED = "RUN_SUCCEEDED"
    RUN_FAILED = "RUN_FAILED"
    READINESS_FAILED = "READINESS_FAILED"
    PROVIDER_FAILED = "PROVIDER_FAILED"
    ABNORMAL_DATA_COVERAGE = "ABNORMAL_DATA_COVERAGE"


class EventSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ReasonCode(StrEnum):
    DB_UNAVAILABLE = "DB_UNAVAILABLE"
    MIGRATION_MISMATCH = "MIGRATION_MISMATCH"
    CURRENT_SEASON_STALE = "CURRENT_SEASON_STALE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_SCHEMA_INVALID = "PROVIDER_SCHEMA_INVALID"
    ABNORMAL_COVERAGE_DROP = "ABNORMAL_COVERAGE_DROP"
    FIXTURE_MAPPING_UNRESOLVED = "FIXTURE_MAPPING_UNRESOLVED"
    FIXTURE_INVALID = "FIXTURE_INVALID"
    MARKET_FAMILY_INCOMPLETE = "MARKET_FAMILY_INCOMPLETE"
    MARKET_EVIDENCE_UNAVAILABLE = "MARKET_EVIDENCE_UNAVAILABLE"
    ODDS_STALE = "ODDS_STALE"
    PERSISTENCE_CONFLICT = "PERSISTENCE_CONFLICT"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    REPORT_ARCHIVE_FAILED = "REPORT_ARCHIVE_FAILED"
    CONFIG_VERSION_MISMATCH = "CONFIG_VERSION_MISMATCH"
    MODEL_ARTIFACT_INVALID = "MODEL_ARTIFACT_INVALID"
    LEAKAGE_VIOLATION = "LEAKAGE_VIOLATION"


class DeliveryVisibility(StrEnum):
    INTERNAL = "INTERNAL"
    OPERATIONS = "OPERATIONS"


class DeliveryStatus(StrEnum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"


_ERROR_EVENTS = frozenset(
    {
        EventType.CURRENT_SEASON_SYNC_FAILED,
        EventType.FIXTURE_REFRESH_FAILED,
        EventType.DATA_GATE_FAILED,
        EventType.MATCH_ANALYSIS_FAILED,
        EventType.PERSISTENCE_FAILED,
        EventType.REPORT_ARCHIVE_FAILED,
        EventType.RUN_FAILED,
        EventType.READINESS_FAILED,
        EventType.PROVIDER_FAILED,
    }
)
_WARNING_EVENTS = frozenset({EventType.FIXTURE_QUARANTINED, EventType.ABNORMAL_DATA_COVERAGE})


def severity_for(event_type: EventType) -> EventSeverity:
    if event_type in _ERROR_EVENTS:
        return EventSeverity.ERROR
    if event_type in _WARNING_EVENTS:
        return EventSeverity.WARNING
    return EventSeverity.INFO


@dataclass(frozen=True)
class OperationalEvent:
    event_id: str
    event_type: EventType
    event_version: str
    occurred_at: datetime
    severity: EventSeverity
    correlation_id: str
    source_component: str
    metadata: Mapping[str, str]
    delivery_visibility: DeliveryVisibility
    run_id: str | None = None
    match_id: int | None = None
    market_family: str | None = None
    provider_domain: str | None = None
    reason_code: ReasonCode | None = None

    def __post_init__(self) -> None:
        for name in ("event_id", "event_version", "correlation_id", "source_component"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be nonblank")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.severity is not severity_for(self.event_type):
            raise ValueError("severity must match the canonical event mapping")
        if self.match_id is not None and self.match_id <= 0:
            raise ValueError("match_id must be positive")
        normalized = dict(sorted(self.metadata.items()))
        if any(not key.strip() or not value.strip() for key, value in normalized.items()):
            raise ValueError("metadata keys and values must be nonblank")
        object.__setattr__(self, "metadata", MappingProxyType(normalized))

    @staticmethod
    def deterministic_id(
        event_type: EventType, correlation_id: str, source_component: str, logical_key: str
    ) -> str:
        serialized = json.dumps(
            [event_type.value, correlation_id, source_component, logical_key],
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode()).hexdigest()
