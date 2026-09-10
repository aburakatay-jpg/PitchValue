"""Read-only extraction of one deterministic representative per canonical match."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Connection, text

from pitchvalue.markets.history.config import (
    SUPPORTED_SOURCE_FIELDS,
    VERIFIED_DOMESTIC_SOURCE_CODES,
    VERIFIED_HISTORICAL_SEASONS,
)
from pitchvalue.markets.history.contracts import (
    HistoricalOddsError,
    HistoricalSourceRow,
    SourceInventoryItem,
)


def validate_replay_consistency(connection: Connection) -> None:
    """Reject divergent source replays instead of choosing one silently."""
    mismatch = connection.execute(
        text(
            """
            SELECT match_id
            FROM football_data_canonical_lineage AS l
            JOIN football_data_staging_rows AS s
              ON s.staging_row_id = l.staging_row_id
            WHERE s.competition_source_code = ANY(:source_codes)
              AND s.season_name = ANY(:seasons)
            GROUP BY match_id
            HAVING count(DISTINCT row_hash) <> 1
            ORDER BY match_id
            LIMIT 1
            """
        ),
        {
            "source_codes": list(VERIFIED_DOMESTIC_SOURCE_CODES),
            "seasons": list(VERIFIED_HISTORICAL_SEASONS),
        },
    ).scalar_one_or_none()
    if mismatch is not None:
        raise HistoricalOddsError(f"divergent staging replays for match_id={mismatch}")


def iter_canonical_source_rows(connection: Connection) -> Iterator[HistoricalSourceRow]:
    """Yield the earliest identical replay for each canonical match in stable order."""
    rows = connection.execute(
        text(
            """
            WITH ranked AS (
                SELECT
                    l.match_id,
                    s.staging_row_id,
                    s.source_row_number,
                    s.competition_source_code,
                    s.season_name,
                    s.row_hash,
                    s.raw_row,
                    b.provider_id,
                    m.competition_id,
                    m.season_id,
                    m.kickoff_at_utc,
                    c.canonical_name AS competition_name,
                    row_number() OVER (
                        PARTITION BY l.match_id ORDER BY s.staging_row_id
                    ) AS replay_rank
                FROM football_data_canonical_lineage AS l
                JOIN football_data_staging_rows AS s
                  ON s.staging_row_id = l.staging_row_id
                JOIN import_batches AS b
                  ON b.import_batch_id = s.import_batch_id
                JOIN matches AS m ON m.match_id = l.match_id
                JOIN competitions AS c ON c.competition_id = m.competition_id
                WHERE s.parsing_status = 'parsed'
                  AND s.competition_source_code = ANY(:source_codes)
                  AND s.season_name = ANY(:seasons)
            )
            SELECT * FROM ranked WHERE replay_rank = 1
            ORDER BY kickoff_at_utc, match_id, staging_row_id
            """
        ),
        {
            "source_codes": list(VERIFIED_DOMESTIC_SOURCE_CODES),
            "seasons": list(VERIFIED_HISTORICAL_SEASONS),
        },
    ).mappings()
    for row in rows:
        raw = row["raw_row"]
        raw_values = tuple(
            sorted((str(key), None if value is None else str(value)) for key, value in raw.items())
        )
        yield HistoricalSourceRow(
            match_id=row["match_id"],
            competition_id=row["competition_id"],
            competition_name=row["competition_name"],
            season_id=row["season_id"],
            provider_id=row["provider_id"],
            staging_row_id=row["staging_row_id"],
            source_row_number=row["source_row_number"],
            source_code=row["competition_source_code"],
            season_name=row["season_name"],
            event_at=row["kickoff_at_utc"],
            source_record_hash=row["row_hash"],
            raw_values=raw_values,
        )


def replayed_source_row_count(connection: Connection) -> int:
    total, distinct_matches = connection.execute(
        text(
            """
            SELECT count(*), count(DISTINCT l.match_id)
            FROM football_data_canonical_lineage AS l
            JOIN football_data_staging_rows AS s
              ON s.staging_row_id = l.staging_row_id
            WHERE s.competition_source_code = ANY(:source_codes)
              AND s.season_name = ANY(:seasons)
            """
        ),
        {
            "source_codes": list(VERIFIED_DOMESTIC_SOURCE_CODES),
            "seasons": list(VERIFIED_HISTORICAL_SEASONS),
        },
    ).one()
    return int(total - distinct_matches)


def inventory_supported_fields(connection: Connection) -> tuple[SourceInventoryItem, ...]:
    rows = tuple(iter_canonical_source_rows(connection))
    grouped: dict[tuple[str, str, str], list[int]] = {}
    for row in rows:
        for source_field in SUPPORTED_SOURCE_FIELDS:
            counts = grouped.setdefault((row.source_code, row.season_name, source_field), [0, 0])
            value = row.value(source_field)
            counts[0 if value is not None and value.strip() else 1] += 1
    return tuple(
        SourceInventoryItem(source, season, field, counts[0], counts[1], True)
        for (source, season, field), counts in sorted(grouped.items())
    )
