"""Immutable contracts for canonical historical price observations."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class ObservationOrigin(StrEnum):
    HISTORICAL_SOURCE = "historical_source"
    LIVE_SOURCE = "live_source"


class ObservationSourceKind(StrEnum):
    BOOKMAKER = "bookmaker"
    SOURCE_AVERAGE = "source_average"
    SOURCE_MAXIMUM = "source_maximum"


class ObservationRole(StrEnum):
    OPENING = "opening"
    SOURCE_PREMATCH = "source_prematch"
    SOURCE_FINAL = "source_final"
    CLOSING = "closing"
    UNKNOWN_PREMATCH = "unknown_prematch"
    LIVE = "live"


class TimingSemantics(StrEnum):
    EXACT = "exact"
    ROLE_ONLY = "role_only"
    UNKNOWN = "unknown"


class OddsQualityStatus(StrEnum):
    ELIGIBLE = "eligible"
    SUSPECT = "suspect"
    EXCLUDED = "excluded"
    INVALID = "invalid"


class HistoricalOddsError(ValueError):
    """Raised when historical source data violates the canonical price contract."""


class HistoricalOddsDiagnosticCode(StrEnum):
    MISSING_PRICE = "MISSING_PRICE"
    MALFORMED_PRICE = "MALFORMED_PRICE"
    INVALID_PRICE = "INVALID_PRICE"
    UNSUPPORTED_SOURCE_FIELD = "UNSUPPORTED_SOURCE_FIELD"
    TIMESTAMP_UNCERTAIN = "TIMESTAMP_UNCERTAIN"
    OBSERVATION_AFTER_AS_OF = "OBSERVATION_AFTER_AS_OF"
    PROVIDER_QUALITY_BOUNDARY = "PROVIDER_QUALITY_BOUNDARY"
    PINNACLE_POST_2025_07_23 = "PINNACLE_POST_2025_07_23"
    REPLAYED_SOURCE_ROW = "REPLAYED_SOURCE_ROW"


class TemporalAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    AFTER_AS_OF = "AFTER_AS_OF"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class HistoricalOddsDiagnostic:
    code: HistoricalOddsDiagnosticCode
    source_field: str
    raw_value: str | None = None


@dataclass(frozen=True)
class HistoricalSourceRow:
    match_id: int
    competition_id: int
    competition_name: str
    season_id: int
    provider_id: int
    staging_row_id: int
    source_row_number: int
    source_code: str
    season_name: str
    event_at: datetime
    source_record_hash: str
    raw_values: tuple[tuple[str, str | None], ...]

    def value(self, source_field: str) -> str | None:
        return dict(self.raw_values).get(source_field)


@dataclass(frozen=True)
class HistoricalPriceObservation:
    match_id: int
    competition_id: int
    competition_name: str
    season_id: int
    provider_id: int
    provider_name: str
    bookmaker: str | None
    observation_source_kind: ObservationSourceKind
    market: str
    selection: str
    line: Decimal | None
    decimal_odds: Decimal
    observation_origin: ObservationOrigin
    observation_role: ObservationRole
    observed_at: datetime | None
    timing_semantics: TimingSemantics
    quality_status: OddsQualityStatus
    quality_reasons: tuple[str, ...]
    source_staging_row_id: int
    source_row_number: int
    source_code: str
    source_season: str
    source_field: str
    raw_source_value: str
    source_record_hash: str
    mapping_version: str
    normalization_version: str
    quality_policy_version: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.decimal_odds, Decimal)
            or not self.decimal_odds.is_finite()
            or self.decimal_odds <= Decimal(1)
        ):
            raise HistoricalOddsError("decimal_odds must be a finite Decimal greater than 1")
        if self.line is not None and (
            not isinstance(self.line, Decimal) or not self.line.is_finite()
        ):
            raise HistoricalOddsError("line must be a finite Decimal when supplied")
        if self.observation_source_kind is ObservationSourceKind.BOOKMAKER:
            if self.bookmaker is None or not self.bookmaker.strip():
                raise HistoricalOddsError(
                    "bookmaker source observations require bookmaker identity"
                )
        elif self.bookmaker is not None:
            raise HistoricalOddsError(
                "source aggregate observations cannot carry bookmaker identity"
            )
        if self.observed_at is not None and (
            self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None
        ):
            raise HistoricalOddsError("observed_at must be timezone-aware when supplied")
        if self.timing_semantics is TimingSemantics.EXACT and self.observed_at is None:
            raise HistoricalOddsError("exact timing requires observed_at")
        for name in (
            "provider_name",
            "market",
            "selection",
            "source_code",
            "source_season",
            "source_field",
            "raw_source_value",
            "source_record_hash",
            "mapping_version",
            "normalization_version",
            "quality_policy_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise HistoricalOddsError(f"{name} must be nonblank")
        if any(not reason.strip() for reason in self.quality_reasons):
            raise HistoricalOddsError("quality reasons must be nonblank")

    def to_dict(self) -> dict[str, Any]:
        serialized = _primitive(self)
        if not isinstance(serialized, dict):  # pragma: no cover
            raise TypeError("historical price observation must serialize to a mapping")
        return serialized


@dataclass(frozen=True)
class SourceInventoryItem:
    source_code: str
    season_name: str
    source_field: str
    present_count: int
    missing_count: int
    supported: bool


@dataclass(frozen=True)
class HistoricalOddsNormalizationSummary:
    source_rows_inspected: int
    replayed_source_rows_ignored: int
    odds_bearing_rows: int
    raw_mapped_values: int
    created_observations: int
    reused_observations: int
    missing_values: int
    malformed_values: int
    invalid_values: int
    eligible_observations: int
    suspect_observations: int
    excluded_observations: int
    lineage_observations: int
    by_source_field: tuple[tuple[str, int], ...]
    by_bookmaker: tuple[tuple[str, int], ...]
    by_market: tuple[tuple[str, int], ...]
    by_competition: tuple[tuple[str, int], ...]
    by_season: tuple[tuple[str, int], ...]
    by_observation_role: tuple[tuple[str, int], ...]
    diagnostics: tuple[HistoricalOddsDiagnostic, ...]

    @property
    def normalized_observations(self) -> int:
        return self.created_observations + self.reused_observations

    @property
    def lineage_coverage(self) -> Decimal:
        if self.normalized_observations == 0:
            return Decimal(0)
        return Decimal(self.lineage_observations) / Decimal(self.normalized_observations)

    def to_dict(self) -> dict[str, Any]:
        serialized = _primitive(self)
        if not isinstance(serialized, dict):  # pragma: no cover
            raise TypeError("normalization summary must serialize to a mapping")
        return serialized


def _primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value
