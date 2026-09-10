"""Canonical persistence boundary for historical price observations."""

from sqlalchemy import Connection, text

from pitchvalue.markets.history.contracts import (
    HistoricalOddsError,
    HistoricalPriceObservation,
)

_INSERT = text(
    """
    INSERT INTO odds_snapshots (
        match_id, provider_id, bookmaker, market, selection, line, decimal_odds,
        observed_at, observation_role, observation_origin,
        observation_source_kind, timing_semantics, quality_status,
        quality_reasons, source_staging_row_id, source_match_provider_ref_id,
        source_field, mapping_version, normalization_version, quality_policy_version
    ) VALUES (
        :match_id, :provider_id, :bookmaker, :market, :selection, :line,
        :decimal_odds, :observed_at, :observation_role, :observation_origin,
        :observation_source_kind, :timing_semantics, :quality_status,
        :quality_reasons, :source_staging_row_id, :source_match_provider_ref_id, :source_field,
        :mapping_version, :normalization_version, :quality_policy_version
    )
    ON CONFLICT DO NOTHING
    RETURNING odds_snapshot_id
    """
)

_SOURCE_RECORD = text(
    """
    SELECT refs.match_provider_ref_id
    FROM football_data_staging_rows AS staging
    JOIN import_batches AS batch
      ON batch.import_batch_id = staging.import_batch_id
    JOIN match_provider_refs AS refs
      ON refs.match_id = :match_id
     AND refs.provider_id = batch.provider_id
     AND refs.source_url = batch.source_identifier
     AND refs.source_record_hash = staging.row_hash
    WHERE staging.staging_row_id = :source_staging_row_id
      AND batch.provider_id = :provider_id
      AND staging.row_hash = :source_record_hash
    ORDER BY refs.match_provider_ref_id
    """
)


def _stable_source_record_id(
    connection: Connection, observation: HistoricalPriceObservation
) -> int:
    values = (
        connection.execute(
            _SOURCE_RECORD,
            {
                "match_id": observation.match_id,
                "provider_id": observation.provider_id,
                "source_staging_row_id": observation.source_staging_row_id,
                "source_record_hash": observation.source_record_hash,
            },
        )
        .scalars()
        .all()
    )
    if len(values) != 1 or not isinstance(values[0], int):
        raise HistoricalOddsError(
            "historical observation must resolve exactly one canonical provider source record"
        )
    return values[0]


def persist_historical_observation(
    connection: Connection, observation: HistoricalPriceObservation
) -> bool:
    """Atomically insert one interpretation, returning False when it already exists."""
    source_match_provider_ref_id = _stable_source_record_id(connection, observation)
    result = connection.execute(
        _INSERT,
        {
            "match_id": observation.match_id,
            "provider_id": observation.provider_id,
            "bookmaker": observation.bookmaker,
            "market": observation.market,
            "selection": observation.selection,
            "line": observation.line,
            "decimal_odds": observation.decimal_odds,
            "observed_at": observation.observed_at,
            "observation_role": observation.observation_role.value,
            "observation_origin": observation.observation_origin.value,
            "observation_source_kind": observation.observation_source_kind.value,
            "timing_semantics": observation.timing_semantics.value,
            "quality_status": observation.quality_status.value,
            "quality_reasons": list(observation.quality_reasons),
            "source_staging_row_id": observation.source_staging_row_id,
            "source_match_provider_ref_id": source_match_provider_ref_id,
            "source_field": observation.source_field,
            "mapping_version": observation.mapping_version,
            "normalization_version": observation.normalization_version,
            "quality_policy_version": observation.quality_policy_version,
        },
    )
    return result.scalar_one_or_none() is not None
