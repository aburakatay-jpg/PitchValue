"""SQLAlchemy Core persistence for operations and durable event delivery."""

from __future__ import annotations

import json

from sqlalchemy import Connection, text

from pitchvalue.operations.contracts import EngineRun, Quarantine
from pitchvalue.operations.events import DeliveryStatus, OperationalEvent


import hashlib

def _lock_key(logical_run_id: str) -> int:
    h = hashlib.sha256(logical_run_id.encode()).digest()
    return int.from_bytes(h[:8], byteorder="big", signed=True)

def persist_run(connection: Connection, run: EngineRun) -> EngineRun:
    """Persist an engine run, allocating a new attempt number and physical run_id."""
    lock_key = _lock_key(run.logical_run_id)
    connection.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
    
    # Check if a SUCCESSFUL run already exists for this logical_run_id?
    # Wait, the prompt says "Repeat After Success Policy... avoid creating duplicate semantic snapshots...
    # A new execution attempt may still exist for audit if current orchestration requires it."
    # So we always allocate a new attempt.
    
    max_attempt = connection.execute(
        text("SELECT COALESCE(MAX(attempt_number), 0) FROM engine_runs WHERE logical_run_id = :logical_run_id"),
        {"logical_run_id": run.logical_run_id}
    ).scalar_one()
    
    new_attempt = max_attempt + 1
    new_run_id = f"{run.logical_run_id}-attempt-{new_attempt}"
    
    from dataclasses import replace
    run = replace(run, run_id=new_run_id, attempt_number=new_attempt)

    result = connection.execute(
        text(
            """INSERT INTO engine_runs (
                run_id, logical_run_id, attempt_number, run_type, scheduled_for, started_at, finished_at, status,
                schedule_version, fixture_horizon, model_version, feature_profile,
                orchestrator_version, policy_version, dq_version, market_stability_version,
                calibration_confidence_version, no_vig_version, provider_contract_version
            ) VALUES (
                :run_id, :logical_run_id, :attempt_number, :run_type, :scheduled_for, :started_at, :finished_at, :status,
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
    if result.scalar_one_or_none() is None:
        raise ValueError("failed to persist run")
    return run


def persist_quarantine(connection: Connection, quarantine: Quarantine) -> bool:
    result = connection.execute(
        text(
            """INSERT INTO run_quarantines (
                quarantine_id, run_id, match_id, source_entity_ref_id,
                market_family, scope, reason_code,
                occurred_at, evidence, status
            ) VALUES (
                :quarantine_id, :run_id, :match_id, :source_entity_ref_id,
                :market_family, :scope, :reason_code,
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


def update_run_status(connection: Connection, run: EngineRun) -> None:
    """Persist a validated lifecycle transition without changing run identity."""
    changed = connection.execute(
        text(
            """UPDATE engine_runs SET started_at=:started_at, finished_at=:finished_at,
            status=:status WHERE run_id=:run_id"""
        ),
        {
            "run_id": run.run_id,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "status": run.status.value,
        },
    ).rowcount
    if changed != 1:
        raise ValueError("engine run was not found")


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
