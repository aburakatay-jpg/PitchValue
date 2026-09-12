"""Provider-neutral operational run and quarantine contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from types import MappingProxyType


class RunType(StrEnum):
    FULL = "FULL"
    SHADOW = "SHADOW"
    VALIDATION = "VALIDATION"


class RunStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    PARTIAL_WITH_QUARANTINES = "PARTIAL_WITH_QUARANTINES"


class QuarantineScope(StrEnum):
    MATCH = "MATCH"
    MARKET_FAMILY = "MARKET_FAMILY"


class QuarantineStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _nonblank(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must be nonblank")


def _metadata(value: Mapping[str, str]) -> Mapping[str, str]:
    normalized = dict(sorted(value.items()))
    if any(not key.strip() or not item.strip() for key, item in normalized.items()):
        raise ValueError("metadata keys and values must be nonblank")
    return MappingProxyType(normalized)


@dataclass(frozen=True)
class FixtureHorizon:
    timezone_name: str
    local_dates: tuple[date, ...]
    policy_version: str

    def __post_init__(self) -> None:
        _nonblank(self.timezone_name, "timezone_name")
        _nonblank(self.policy_version, "policy_version")
        if not self.local_dates or tuple(sorted(set(self.local_dates))) != self.local_dates:
            raise ValueError("local_dates must be nonempty, unique, and sorted")


@dataclass(frozen=True)
class EngineRun:
    run_id: str
    run_type: RunType
    scheduled_for: datetime
    started_at: datetime | None
    finished_at: datetime | None
    status: RunStatus
    schedule_version: str
    fixture_horizon: FixtureHorizon
    model_version: str
    feature_profile: str
    orchestrator_version: str
    policy_version: str
    dq_version: str
    market_stability_version: str
    calibration_confidence_version: str
    no_vig_version: str
    provider_contract_version: str

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "schedule_version",
            "model_version",
            "feature_profile",
            "orchestrator_version",
            "policy_version",
            "dq_version",
            "market_stability_version",
            "calibration_confidence_version",
            "no_vig_version",
            "provider_contract_version",
        ):
            _nonblank(getattr(self, name), name)
        _aware(self.scheduled_for, "scheduled_for")
        if self.started_at is not None:
            _aware(self.started_at, "started_at")
        if self.finished_at is not None:
            _aware(self.finished_at, "finished_at")
        if self.finished_at is not None and self.started_at is None:
            raise ValueError("finished_at requires started_at")
        if self.started_at is not None and self.started_at < self.scheduled_for:
            raise ValueError("started_at cannot precede scheduled_for")
        if (
            self.finished_at is not None
            and self.started_at is not None
            and self.finished_at < self.started_at
        ):
            raise ValueError("finished_at cannot precede started_at")


@dataclass(frozen=True)
class Quarantine:
    quarantine_id: str
    run_id: str
    match_id: int
    market_family: str | None
    scope: QuarantineScope
    reason_code: str
    occurred_at: datetime
    evidence: Mapping[str, str]
    status: QuarantineStatus = QuarantineStatus.ACTIVE

    def __post_init__(self) -> None:
        for name in ("quarantine_id", "run_id", "reason_code"):
            _nonblank(getattr(self, name), name)
        if self.match_id <= 0:
            raise ValueError("match_id must be positive")
        _aware(self.occurred_at, "occurred_at")
        if self.scope is QuarantineScope.MATCH and self.market_family is not None:
            raise ValueError("match quarantine cannot specify market_family")
        if self.scope is QuarantineScope.MARKET_FAMILY:
            if self.market_family is None:
                raise ValueError("market-family quarantine requires market_family")
            _nonblank(self.market_family, "market_family")
        object.__setattr__(self, "evidence", _metadata(self.evidence))

    @staticmethod
    def deterministic_id(
        run_id: str,
        match_id: int,
        scope: QuarantineScope,
        market: str | None,
        reason: str,
    ) -> str:
        payload = json.dumps(
            [run_id, match_id, scope.value, market, reason],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()
