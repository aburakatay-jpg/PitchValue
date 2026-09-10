from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from pitchvalue.markets.history.config import (
    FOOTBALL_DATA_MAPPING_VERSION,
    FOOTBALL_DATA_MAPPINGS,
    FOOTBALL_DATA_QUALITY_VERSION,
    HISTORICAL_ODDS_NORMALIZATION_VERSION,
)
from pitchvalue.markets.history.contracts import (
    HistoricalOddsDiagnostic,
    HistoricalOddsDiagnosticCode,
    HistoricalOddsError,
    HistoricalPriceObservation,
    HistoricalSourceRow,
    ObservationOrigin,
    ObservationRole,
    ObservationSourceKind,
    OddsQualityStatus,
    TemporalAvailability,
    TimingSemantics,
)
from pitchvalue.markets.history.football_data import normalize_source_value
from pitchvalue.markets.history.quality import assess_source_quality
from pitchvalue.markets.history.timestamps import temporal_availability


def _row(**values: str | None) -> HistoricalSourceRow:
    return HistoricalSourceRow(
        match_id=10,
        competition_id=20,
        competition_name="Premier League",
        season_id=30,
        provider_id=40,
        staging_row_id=50,
        source_row_number=2,
        source_code="E0",
        season_name="2025/26",
        event_at=datetime(2025, 8, 16, 14, tzinfo=UTC),
        source_record_hash="a" * 64,
        raw_values=tuple(sorted(values.items())),
    )


@pytest.mark.parametrize(
    ("field", "selection", "role"),
    [
        ("B365H", "home", ObservationRole.SOURCE_PREMATCH),
        ("B365D", "draw", ObservationRole.SOURCE_PREMATCH),
        ("B365A", "away", ObservationRole.SOURCE_PREMATCH),
        ("B365CH", "home", ObservationRole.CLOSING),
        ("B365CD", "draw", ObservationRole.CLOSING),
        ("B365CA", "away", ObservationRole.CLOSING),
    ],
)
def test_verified_bet365_mapping(field: str, selection: str, role: ObservationRole) -> None:
    mapping = next(item for item in FOOTBALL_DATA_MAPPINGS if item.source_field == field)
    result = normalize_source_value(_row(**{field: "2.375"}), mapping)
    assert isinstance(result, HistoricalPriceObservation)
    assert result.bookmaker == "BET365"
    assert result.observation_source_kind is ObservationSourceKind.BOOKMAKER
    assert result.market == "match_result"
    assert result.selection == selection
    assert result.line is None
    assert result.decimal_odds == Decimal("2.375")
    assert result.observation_role is role
    assert result.timing_semantics is TimingSemantics.ROLE_ONLY
    assert result.observed_at is None
    assert result.quality_reasons == ("timestamp_uncertain",)


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (None, HistoricalOddsDiagnosticCode.MISSING_PRICE),
        ("", HistoricalOddsDiagnosticCode.MISSING_PRICE),
        ("   ", HistoricalOddsDiagnosticCode.MISSING_PRICE),
        ("abc", HistoricalOddsDiagnosticCode.MALFORMED_PRICE),
        ("NaN", HistoricalOddsDiagnosticCode.INVALID_PRICE),
        ("Infinity", HistoricalOddsDiagnosticCode.INVALID_PRICE),
        ("1", HistoricalOddsDiagnosticCode.INVALID_PRICE),
        ("0.99", HistoricalOddsDiagnosticCode.INVALID_PRICE),
        ("-2", HistoricalOddsDiagnosticCode.INVALID_PRICE),
    ],
)
def test_missing_and_invalid_prices_are_explicit(
    raw: str | None, code: HistoricalOddsDiagnosticCode
) -> None:
    result = normalize_source_value(_row(B365H=raw), FOOTBALL_DATA_MAPPINGS[0])
    assert result == HistoricalOddsDiagnostic(code, "B365H", raw)


def test_price_contract_is_immutable_and_serializes_deterministically() -> None:
    result = normalize_source_value(_row(B365H="2.10"), FOOTBALL_DATA_MAPPINGS[0])
    assert isinstance(result, HistoricalPriceObservation)
    with pytest.raises(FrozenInstanceError):
        result.bookmaker = "OTHER"  # type: ignore[misc]
    assert result.to_dict() == result.to_dict()
    assert result.to_dict()["decimal_odds"] == "2.10"


def test_source_value_is_not_rounded_or_mutated() -> None:
    row = _row(B365H="2.375")
    result = normalize_source_value(row, FOOTBALL_DATA_MAPPINGS[0])
    assert isinstance(result, HistoricalPriceObservation)
    assert result.raw_source_value == "2.375"
    assert row.value("B365H") == "2.375"


def test_version_metadata_is_stable() -> None:
    result = normalize_source_value(_row(B365H="2.10"), FOOTBALL_DATA_MAPPINGS[0])
    assert isinstance(result, HistoricalPriceObservation)
    assert result.mapping_version == FOOTBALL_DATA_MAPPING_VERSION
    assert result.normalization_version == HISTORICAL_ODDS_NORMALIZATION_VERSION
    assert result.quality_policy_version == FOOTBALL_DATA_QUALITY_VERSION


def test_lineage_metadata_is_preserved() -> None:
    result = normalize_source_value(_row(B365H="2.10"), FOOTBALL_DATA_MAPPINGS[0])
    assert isinstance(result, HistoricalPriceObservation)
    assert result.source_staging_row_id == 50
    assert result.source_field == "B365H"
    assert result.source_record_hash == "a" * 64


def test_role_only_timing_is_not_automatically_available() -> None:
    result = normalize_source_value(_row(B365H="2.10"), FOOTBALL_DATA_MAPPINGS[0])
    assert isinstance(result, HistoricalPriceObservation)
    assert (
        temporal_availability(result, datetime(2025, 8, 16, 12, tzinfo=UTC))
        is TemporalAvailability.UNKNOWN
    )


def test_exact_quote_availability_boundaries() -> None:
    result = normalize_source_value(_row(B365H="2.10"), FOOTBALL_DATA_MAPPINGS[0])
    assert isinstance(result, HistoricalPriceObservation)
    exact = replace(
        result,
        timing_semantics=TimingSemantics.EXACT,
        observed_at=datetime(2025, 8, 16, 12, tzinfo=UTC),
    )
    assert (
        temporal_availability(exact, datetime(2025, 8, 16, 12, tzinfo=UTC))
        is TemporalAvailability.AVAILABLE
    )
    assert (
        temporal_availability(exact, datetime(2025, 8, 16, 11, tzinfo=UTC))
        is TemporalAvailability.AFTER_AS_OF
    )


def test_naive_as_of_is_rejected() -> None:
    result = normalize_source_value(_row(B365H="2.10"), FOOTBALL_DATA_MAPPINGS[0])
    assert isinstance(result, HistoricalPriceObservation)
    with pytest.raises(HistoricalOddsError, match="timezone-aware"):
        temporal_availability(result, datetime(2025, 8, 16, 12))


@pytest.mark.parametrize(
    ("event_date", "expected"),
    [
        (date(2025, 7, 22), OddsQualityStatus.ELIGIBLE),
        (date(2025, 7, 23), OddsQualityStatus.SUSPECT),
        (date(2025, 7, 24), OddsQualityStatus.SUSPECT),
    ],
)
def test_pinnacle_quality_boundary(event_date: date, expected: OddsQualityStatus) -> None:
    status, reasons = assess_source_quality(
        provider_name="football-data.co.uk", bookmaker="PINNACLE", event_date=event_date
    )
    assert status is expected
    assert bool(reasons) is (expected is OddsQualityStatus.SUSPECT)


def test_pinnacle_policy_is_source_specific() -> None:
    status, reasons = assess_source_quality(
        provider_name="another-source", bookmaker="PINNACLE", event_date=date(2025, 7, 24)
    )
    assert status is OddsQualityStatus.ELIGIBLE
    assert reasons == ()


def test_aggregate_cannot_claim_bookmaker_identity() -> None:
    result = normalize_source_value(_row(B365H="2.10"), FOOTBALL_DATA_MAPPINGS[0])
    assert isinstance(result, HistoricalPriceObservation)
    with pytest.raises(HistoricalOddsError, match="aggregate"):
        replace(
            result,
            observation_source_kind=ObservationSourceKind.SOURCE_AVERAGE,
            bookmaker="Average",
        )


def test_exact_timing_requires_timestamp() -> None:
    result = normalize_source_value(_row(B365H="2.10"), FOOTBALL_DATA_MAPPINGS[0])
    assert isinstance(result, HistoricalPriceObservation)
    with pytest.raises(HistoricalOddsError, match="requires observed_at"):
        replace(result, timing_semantics=TimingSemantics.EXACT, observed_at=None)


def test_historical_origin_and_provider_identity_are_explicit() -> None:
    result = normalize_source_value(_row(B365H="2.10"), FOOTBALL_DATA_MAPPINGS[0])
    assert isinstance(result, HistoricalPriceObservation)
    assert result.observation_origin is ObservationOrigin.HISTORICAL_SOURCE
    assert result.provider_name == "football-data.co.uk"
