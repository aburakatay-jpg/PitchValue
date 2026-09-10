"""Pure football-data source-field normalization."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from pitchvalue.markets.config import MarketMathError
from pitchvalue.markets.history.config import (
    FOOTBALL_DATA_MAPPING_VERSION,
    FOOTBALL_DATA_PROVIDER,
    FOOTBALL_DATA_QUALITY_VERSION,
    HISTORICAL_ODDS_NORMALIZATION_VERSION,
    SourceFieldMapping,
)
from pitchvalue.markets.history.contracts import (
    HistoricalOddsDiagnostic,
    HistoricalOddsDiagnosticCode,
    HistoricalPriceObservation,
    HistoricalSourceRow,
    ObservationOrigin,
)
from pitchvalue.markets.history.quality import assess_source_quality
from pitchvalue.markets.odds import validate_decimal_odds


def normalize_source_value(
    row: HistoricalSourceRow, mapping: SourceFieldMapping
) -> HistoricalPriceObservation | HistoricalOddsDiagnostic:
    raw_value = row.value(mapping.source_field)
    if raw_value is None or not raw_value.strip():
        return HistoricalOddsDiagnostic(
            HistoricalOddsDiagnosticCode.MISSING_PRICE, mapping.source_field, raw_value
        )
    try:
        price = Decimal(raw_value.strip())
    except InvalidOperation:
        return HistoricalOddsDiagnostic(
            HistoricalOddsDiagnosticCode.MALFORMED_PRICE, mapping.source_field, raw_value
        )
    try:
        validate_decimal_odds(price)
    except MarketMathError:
        return HistoricalOddsDiagnostic(
            HistoricalOddsDiagnosticCode.INVALID_PRICE, mapping.source_field, raw_value
        )
    quality_status, policy_reasons = assess_source_quality(
        provider_name=FOOTBALL_DATA_PROVIDER,
        bookmaker=mapping.bookmaker,
        event_date=row.event_at.date(),
    )
    timing_reasons = () if mapping.timing_semantics.value == "exact" else ("timestamp_uncertain",)
    return HistoricalPriceObservation(
        match_id=row.match_id,
        competition_id=row.competition_id,
        competition_name=row.competition_name,
        season_id=row.season_id,
        provider_id=row.provider_id,
        provider_name=FOOTBALL_DATA_PROVIDER,
        bookmaker=mapping.bookmaker,
        observation_source_kind=mapping.source_kind,
        market=mapping.market.value,
        selection=mapping.selection.value,
        line=None,
        decimal_odds=price,
        observation_origin=ObservationOrigin.HISTORICAL_SOURCE,
        observation_role=mapping.observation_role,
        observed_at=None,
        timing_semantics=mapping.timing_semantics,
        quality_status=quality_status,
        quality_reasons=timing_reasons + policy_reasons,
        source_staging_row_id=row.staging_row_id,
        source_row_number=row.source_row_number,
        source_code=row.source_code,
        source_season=row.season_name,
        source_field=mapping.source_field,
        raw_source_value=raw_value,
        source_record_hash=row.source_record_hash,
        mapping_version=FOOTBALL_DATA_MAPPING_VERSION,
        normalization_version=HISTORICAL_ODDS_NORMALIZATION_VERSION,
        quality_policy_version=FOOTBALL_DATA_QUALITY_VERSION,
    )
