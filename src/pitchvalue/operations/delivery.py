"""Credential-free operational delivery interfaces and deterministic fakes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pitchvalue.operations.events import OperationalEvent


class ConsumerDeliveryStatus(StrEnum):
    DELIVERED = "DELIVERED"
    UNCHANGED = "UNCHANGED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"


@dataclass(frozen=True)
class DeliveryResult:
    status: ConsumerDeliveryStatus
    identity: str
    failure_code: str | None = None


@dataclass(frozen=True)
class ReportPackage:
    run_id: str
    report_version: str
    files: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.report_version.strip():
            raise ValueError("run and report versions must be nonblank")
        if tuple(sorted(self.files)) != self.files:
            raise ValueError("report files must be canonically ordered")
        if len({name for name, _ in self.files}) != len(self.files):
            raise ValueError("report filenames must be unique")

    @property
    def fingerprint(self) -> str:
        value = json.dumps(
            [self.run_id, self.report_version, self.files],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(value.encode()).hexdigest()


class TelegramEventConsumer(Protocol):
    def deliver_group(self, events: tuple[OperationalEvent, ...]) -> DeliveryResult: ...


class RunArchiveConsumer(Protocol):
    def archive(self, report: ReportPackage) -> DeliveryResult: ...


class FakeTelegramConsumer:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.groups: list[tuple[OperationalEvent, ...]] = []

    def deliver_group(self, events: tuple[OperationalEvent, ...]) -> DeliveryResult:
        if not events:
            raise ValueError("event group must not be empty")
        identity = hashlib.sha256("|".join(item.event_id for item in events).encode()).hexdigest()
        if self.fail:
            return DeliveryResult(
                ConsumerDeliveryStatus.RETRYABLE_FAILURE,
                identity,
                "TELEGRAM_DELIVERY_FAILED",
            )
        self.groups.append(events)
        return DeliveryResult(ConsumerDeliveryStatus.DELIVERED, identity)


class FakeDriveArchive:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.archives: dict[str, str] = {}

    def archive(self, report: ReportPackage) -> DeliveryResult:
        if self.fail:
            return DeliveryResult(
                ConsumerDeliveryStatus.RETRYABLE_FAILURE,
                report.run_id,
                "REPORT_ARCHIVE_FAILED",
            )
        existing = self.archives.get(report.run_id)
        if existing is not None and existing != report.fingerprint:
            return DeliveryResult(
                ConsumerDeliveryStatus.RETRYABLE_FAILURE,
                report.run_id,
                "ARCHIVE_IDENTITY_CONFLICT",
            )
        if existing == report.fingerprint:
            return DeliveryResult(ConsumerDeliveryStatus.UNCHANGED, report.run_id)
        self.archives[report.run_id] = report.fingerprint
        return DeliveryResult(ConsumerDeliveryStatus.DELIVERED, report.run_id)
