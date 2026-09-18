from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.operations.contracts import Quarantine, QuarantineScope
from pitchvalue.operations.events import (
    DeliveryStatus,
    DeliveryVisibility,
    EventType,
    OperationalEvent,
    severity_for,
)
from pitchvalue.operations.repository import (
    persist_event,
    persist_quarantine,
    persist_run,
    record_delivery,
)
from test_operational_run_foundation import _run
from test_prediction_api import _clean_fixture_data
from test_prediction_repository import _request


@pytest.mark.integration
def test_run_quarantine_event_and_delivery_are_durable_and_retry_safe() -> None:
    engine = create_engine(load_settings(os.environ).database_url)
    try:
        with engine.begin() as connection:
            _clean_fixture_data(connection)
            match_id = int(_request(connection).decision.match_id)
            run = _run()
            run = persist_run(connection, run)
            assert run.attempt_number == 1
            run2 = persist_run(connection, run)
            assert run2.attempt_number == 2
            quarantine = Quarantine(
                Quarantine.deterministic_id(
                    run.run_id,
                    match_id,
                    QuarantineScope.MARKET_FAMILY,
                    "BTTS",
                    "MARKET_FAMILY_INCOMPLETE",
                ),
                run.run_id,
                match_id,
                "BTTS",
                QuarantineScope.MARKET_FAMILY,
                "MARKET_FAMILY_INCOMPLETE",
                datetime(2026, 9, 12, tzinfo=UTC),
                {"missing": "NO"},
            )
            assert persist_quarantine(connection, quarantine)
            assert not persist_quarantine(connection, quarantine)
            event_type = EventType.FIXTURE_QUARANTINED
            event = OperationalEvent(
                OperationalEvent.deterministic_id(
                    event_type, "correlation-1", "quarantine", quarantine.quarantine_id
                ),
                event_type,
                "operational_event_v1",
                datetime(2026, 9, 12, tzinfo=UTC),
                severity_for(event_type),
                "correlation-1",
                "quarantine",
                {"quarantine_id": quarantine.quarantine_id},
                DeliveryVisibility.OPERATIONS,
                run_id=run.run_id,
                match_id=match_id,
                market_family="BTTS",
            )
            assert persist_event(connection, event)
            assert not persist_event(connection, event)
            record_delivery(
                connection,
                event.event_id,
                "telegram_fake",
                DeliveryStatus.RETRYABLE_FAILURE,
                attempt_count=1,
                failure_code="DELIVERY_UNAVAILABLE",
            )
            record_delivery(
                connection,
                event.event_id,
                "telegram_fake",
                DeliveryStatus.DELIVERED,
                attempt_count=2,
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM engine_runs WHERE run_id=:run_id"),
                    {"run_id": run.run_id},
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM run_quarantines WHERE run_id=:run_id"),
                    {"run_id": run.run_id},
                ).scalar_one()
                == 1
            )
            delivery = connection.execute(
                text(
                    "SELECT status, attempt_count FROM operational_event_deliveries "
                    "WHERE event_id = :event_id"
                ),
                {"event_id": event.event_id},
            ).one()
            assert tuple(delivery) == ("DELIVERED", 2)
            connection.execute(
                text("DELETE FROM operational_event_deliveries WHERE event_id=:event_id"),
                {"event_id": event.event_id},
            )
            connection.execute(
                text("DELETE FROM operational_events WHERE event_id=:event_id"),
                {"event_id": event.event_id},
            )
            connection.execute(
                text("DELETE FROM run_quarantines WHERE run_id=:run_id"),
                {"run_id": run.run_id},
            )
            connection.execute(
                text("DELETE FROM engine_runs WHERE logical_run_id=:logical_run_id"),
                {"logical_run_id": run.logical_run_id},
            )
            _clean_fixture_data(connection)
    finally:
        engine.dispose()
