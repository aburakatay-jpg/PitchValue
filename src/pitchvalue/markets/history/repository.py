"""Canonical persistence boundary for historical price observations."""

from sqlalchemy import Connection, text

from pitchvalue.markets.history.contracts import HistoricalPriceObservation

_INSERT = text(
    """
    INSERT INTO odds_snapshots (
        match_id, provider_id, bookmaker, market, selection, line, decimal_odds,
        observed_at, observation_role, observation_origin,
        observation_source_kind, timing_semantics, quality_status,
        quality_reasons, source_staging_row_id, source_field, mapping_version,
        normalization_version, quality_policy_version
    ) VALUES (
        :match_id, :provider_id, :bookmaker, :market, :selection, :line,
        :decimal_odds, :observed_at, :observation_role, :observation_origin,
        :observation_source_kind, :timing_semantics, :quality_status,
        :quality_reasons, :source_staging_row_id, :source_field,
        :mapping_version, :normalization_version, :quality_policy_version
    )
    ON CONFLICT DO NOTHING
    RETURNING odds_snapshot_id
    """
)


def persist_historical_observation(
    connection: Connection, observation: HistoricalPriceObservation
) -> bool:
    """Atomically insert one interpretation, returning False when it already exists."""
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
            "source_field": observation.source_field,
            "mapping_version": observation.mapping_version,
            "normalization_version": observation.normalization_version,
            "quality_policy_version": observation.quality_policy_version,
        },
    )
    return result.scalar_one_or_none() is not None
