"""SQLAlchemy Core persistence for operations and durable event delivery."""

from __future__ import annotations

import json

from sqlalchemy import Connection, text

from pitchvalue.operations.contracts import EngineRun, Quarantine
from pitchvalue.operations.events import DeliveryStatus, OperationalEvent


def persist_run(connection: Connection, run: EngineRun) -> bool:
    result = connection.execute(
        text(
            """INSERT INTO engine_runs (
                run_id, run_type, scheduled_for, started_at, finished_at, status,
                schedule_version, fixture_horizon, model_version, feature_profile,
                orchestrator_version, policy_version, dq_version, market_stability_version,
                calibration_confidence_version, no_vig_version, provider_contract_version
            ) VALUES (
                :run_id, :run_type, :scheduled_for, :started_at, :finished_at, :status,
                :schedule_version, CAST(:fixture_horizon AS jsonb), :model_version,
                :feature_profile, :orchestrator_version, :policy_version, :dq_version,
                :market_stability_version, :calibration_confidence_version, :no_vig_version,
                :provider_contract_version
            ) ON CONFLICT (run_id) DO NOTHING RETURNING run_id"""
        ),
        {
            **run.__dict__,
            "run_type": run.run_type.value,
            "status": run.status.value,
            "fixture_horizon": json.dumps(
                {
                    "timezone_name": run.fixture_horizon.timezone_name,
                    "local_dates": [item.isoformat() for item in run.fixture_horizon.local_dates],
                    "policy_version": run.fixture_horizon.policy_version,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        },
    )
    return result.scalar_one_or_none() is not None


def persist_quarantine(connection: Connection, quarantine: Quarantine) -> bool:
    result = connection.execute(
        text(
            """INSERT INTO run_quarantines (
                quarantine_id, run_id, match_id, market_family, scope, reason_code,
                occurred_at, evidence, status
            ) VALUES (
                :quarantine_id, :run_id, :match_id, :market_family, :scope, :reason_code,
                :occurred_at, CAST(:evidence AS jsonb), :status
            ) ON CONFLICT (quarantine_id) DO NOTHING RETURNING quarantine_id"""
        ),
        {
            **quarantine.__dict__,
            "scope": quarantine.scope.value,
            "status": quarantine.status.value,
            "evidence": json.dumps(
                dict(quarantine.evidence), sort_keys=True, separators=(",", ":")
            ),
        },
    )
    return result.scalar_one_or_none() is not None


def persist_event(connection: Connection, event: OperationalEvent) -> bool:
    result = connection.execute(
        text(
            """INSERT INTO operational_events (
                event_id, event_type, event_version, occurred_at, severity, run_id, match_id,
                market_family, provider_domain, correlation_id, reason_code, source_component,
                metadata, delivery_visibility
            ) VALUES (
                :event_id, :event_type, :event_version, :occurred_at, :severity, :run_id,
                :match_id, :market_family, :provider_domain, :correlation_id, :reason_code,
                :source_component, CAST(:metadata AS jsonb), :delivery_visibility
            ) ON CONFLICT (event_id) DO NOTHING RETURNING event_id"""
        ),
        {
            **event.__dict__,
            "event_type": event.event_type.value,
            "severity": event.severity.value,
            "reason_code": None if event.reason_code is None else event.reason_code.value,
            "delivery_visibility": event.delivery_visibility.value,
            "metadata": json.dumps(dict(event.metadata), sort_keys=True, separators=(",", ":")),
        },
    )
    return result.scalar_one_or_none() is not None


def record_delivery(
    connection: Connection,
    event_id: str,
    consumer: str,
    status: DeliveryStatus,
    *,
    attempt_count: int,
    failure_code: str | None = None,
) -> None:
    if not consumer.strip() or attempt_count < 0:
        raise ValueError("consumer and attempt_count are invalid")
    connection.execute(
        text(
            """INSERT INTO operational_event_deliveries (
                event_id, consumer, status, attempt_count, failure_code, updated_at
            ) VALUES (:event_id, :consumer, :status, :attempt_count, :failure_code, now())
            ON CONFLICT (event_id, consumer) DO UPDATE SET
                status = EXCLUDED.status,
                attempt_count = EXCLUDED.attempt_count,
                failure_code = EXCLUDED.failure_code,
                updated_at = now()"""
        ),
        {
            "event_id": event_id,
            "consumer": consumer,
            "status": status.value,
            "attempt_count": attempt_count,
            "failure_code": failure_code,
        },
    )
