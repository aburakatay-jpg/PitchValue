"""Persistent provider staging operations."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import Connection, text

from pitchvalue.ingestion.football_data_uk.parser import ParsedDataset
from pitchvalue.ingestion.football_data_uk.registry import SourceDefinition

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StagingResult:
    """Counts from one idempotent staging pass."""

    rows_read: int
    rows_staged: int
    rows_rejected: int
    rows_already_known: int


def stage_dataset(
    connection: Connection,
    batch_id: int,
    source: SourceDefinition,
    dataset: ParsedDataset,
) -> StagingResult:
    """Stage parsed and rejected raw rows without touching canonical football tables."""
    staged = 0
    rejected = 0
    already_known = 0
    for row in dataset.rows:
        rejection_reason = "; ".join(row.errors) if row.errors else None
        result = connection.execute(
            text(
                """
                INSERT INTO football_data_staging_rows (
                    import_batch_id, source_row_number, competition_source_code,
                    season_name, raw_row, row_hash, parsing_status, rejection_reason
                ) VALUES (
                    :batch_id, :source_row_number, :source_code,
                    :season_name, CAST(:raw_row AS jsonb), :row_hash,
                    :parsing_status, :rejection_reason
                )
                ON CONFLICT (import_batch_id, source_row_number) DO NOTHING
                """
            ),
            {
                "batch_id": batch_id,
                "source_row_number": row.source_row_number,
                "source_code": source.source_code,
                "season_name": source.season_name,
                "raw_row": json.dumps(row.raw_values, ensure_ascii=False, sort_keys=True),
                "row_hash": row.row_hash,
                "parsing_status": row.parsing_status,
                "rejection_reason": rejection_reason,
            },
        )
        if result.rowcount == 1:
            staged += 1
            rejected += int(bool(row.errors))
        else:
            already_known += 1
    logger.info(
        "rows read=%s staged=%s rejected=%s already_known=%s",
        len(dataset.rows),
        staged,
        rejected,
        already_known,
    )
    return StagingResult(len(dataset.rows), staged, rejected, already_known)
