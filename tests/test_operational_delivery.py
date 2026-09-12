from __future__ import annotations

from datetime import UTC, datetime

from pitchvalue.operations.delivery import (
    ConsumerDeliveryStatus,
    FakeDriveArchive,
    FakeTelegramConsumer,
    ReportPackage,
)
from pitchvalue.operations.events import (
    DeliveryVisibility,
    EventType,
    OperationalEvent,
    severity_for,
)


def _event() -> OperationalEvent:
    event_type = EventType.RUN_FAILED
    return OperationalEvent(
        OperationalEvent.deterministic_id(event_type, "run-1", "runner", "failed"),
        event_type,
        "operational_event_v1",
        datetime(2026, 9, 12, tzinfo=UTC),
        severity_for(event_type),
        "run-1",
        "runner",
        {},
        DeliveryVisibility.OPERATIONS,
    )


def test_fake_telegram_groups_events_without_prediction_authority() -> None:
    consumer = FakeTelegramConsumer()
    result = consumer.deliver_group((_event(), _event()))
    assert result.status is ConsumerDeliveryStatus.DELIVERED
    assert len(consumer.groups) == 1


def test_telegram_failure_is_retryable_and_does_not_raise() -> None:
    consumer = FakeTelegramConsumer(fail=True)
    result = consumer.deliver_group((_event(),))
    assert result.status is ConsumerDeliveryStatus.RETRYABLE_FAILURE
    assert result.failure_code == "TELEGRAM_DELIVERY_FAILED"
    assert consumer.groups == []


def test_drive_archive_is_idempotent_by_run_id_and_content() -> None:
    archive = FakeDriveArchive()
    report = ReportPackage("run-1", "report-v1", (("report.json", "content-hash"),))
    assert archive.archive(report).status is ConsumerDeliveryStatus.DELIVERED
    assert archive.archive(report).status is ConsumerDeliveryStatus.UNCHANGED


def test_drive_failure_and_identity_conflict_are_retryable() -> None:
    report = ReportPackage("run-1", "report-v1", (("report.json", "hash-a"),))
    assert FakeDriveArchive(fail=True).archive(report).failure_code == "REPORT_ARCHIVE_FAILED"
    archive = FakeDriveArchive()
    archive.archive(report)
    conflict = ReportPackage("run-1", "report-v1", (("report.json", "hash-b"),))
    assert archive.archive(conflict).failure_code == "ARCHIVE_IDENTITY_CONFLICT"
