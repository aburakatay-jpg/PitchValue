"""Deterministic lifecycle operations for canonical import batch audit rows."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection, text

from pitchvalue.ingestion.football_data_uk.registry import (
    PROVIDER_BASE_URL,
    PROVIDER_NAME,
)

logger = logging.getLogger(__name__)


class BatchStateError(RuntimeError):
    """Raised when a batch transition is not valid from its current state."""


@dataclass(frozen=True)
class BatchCounters:
    """Final non-negative ingestion counts."""

    rows_read: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_rejected: int = 0


def ensure_provider(connection: Connection) -> int:
    """Idempotently ensure the one canonical football-data.co.uk provider."""
    provider_id = connection.execute(
        text(
            """
            INSERT INTO providers (
                name, provider_type, base_url, license_type, priority, active
            ) VALUES (
                :name, 'historical_csv', :base_url, NULL, 1, true
            )
            ON CONFLICT (name) DO UPDATE
            SET active = true, updated_at = now()
            RETURNING provider_id
            """
        ),
        {"name": PROVIDER_NAME, "base_url": PROVIDER_BASE_URL},
    ).scalar_one()
    assert isinstance(provider_id, int)
    return provider_id


def start_batch(connection: Connection, provider_id: int, source_identifier: str) -> int:
    """Create a running batch before a fetch or staging attempt begins."""
    batch_id = connection.execute(
        text(
            """
            INSERT INTO import_batches (
                provider_id, started_at, source_identifier, status
            ) VALUES (:provider_id, :started_at, :source_identifier, 'running')
            RETURNING import_batch_id
            """
        ),
        {
            "provider_id": provider_id,
            "started_at": datetime.now(UTC),
            "source_identifier": source_identifier,
        },
    ).scalar_one()
    assert isinstance(batch_id, int)
    logger.info("batch started: %s", batch_id)
    return batch_id


def finish_batch(
    connection: Connection,
    batch_id: int,
    status: str,
    counters: BatchCounters,
    *,
    source_hash: str | None = None,
    error_summary: str | None = None,
) -> None:
    """Finish one running batch exactly once with explicit outcome and counters."""
    if status not in {"completed", "completed_with_errors", "failed"}:
        raise ValueError(f"invalid terminal batch status: {status}")
    result = connection.execute(
        text(
            """
            UPDATE import_batches
            SET completed_at = :completed_at,
                source_hash = :source_hash,
                rows_read = :rows_read,
                rows_inserted = :rows_inserted,
                rows_updated = :rows_updated,
                rows_rejected = :rows_rejected,
                status = :status,
                error_summary = :error_summary
            WHERE import_batch_id = :batch_id AND status = 'running'
            """
        ),
        {
            "completed_at": datetime.now(UTC),
            "source_hash": source_hash,
            "rows_read": counters.rows_read,
            "rows_inserted": counters.rows_inserted,
            "rows_updated": counters.rows_updated,
            "rows_rejected": counters.rows_rejected,
            "status": status,
            "error_summary": error_summary,
            "batch_id": batch_id,
        },
    )
    if result.rowcount != 1:
        raise BatchStateError(f"batch {batch_id} is absent or no longer running")
    logger.info("batch %s: %s", status, batch_id)
