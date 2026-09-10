"""Deterministic football-data historical odds mappings and versions."""

from dataclasses import dataclass

from pitchvalue.markets.history.contracts import (
    ObservationRole,
    ObservationSourceKind,
    TimingSemantics,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection

FOOTBALL_DATA_MAPPING_VERSION = "football_data_mapping_v1"
HISTORICAL_ODDS_NORMALIZATION_VERSION = "historical_odds_normalization_v1"
FOOTBALL_DATA_QUALITY_VERSION = "football_data_quality_v1"
FOOTBALL_DATA_PROVIDER = "football-data.co.uk"
VERIFIED_DOMESTIC_SOURCE_CODES = ("D1", "E0", "F1", "P1", "SC0", "SP1", "T1")
VERIFIED_HISTORICAL_SEASONS = ("2024/25", "2025/26")


@dataclass(frozen=True)
class SourceFieldMapping:
    source_field: str
    source_kind: ObservationSourceKind
    bookmaker: str | None
    market: MarketFamily
    selection: Selection
    observation_role: ObservationRole
    timing_semantics: TimingSemantics


FOOTBALL_DATA_MAPPINGS: tuple[SourceFieldMapping, ...] = (
    SourceFieldMapping(
        "B365H",
        ObservationSourceKind.BOOKMAKER,
        "BET365",
        MarketFamily.MATCH_RESULT,
        Selection.HOME,
        ObservationRole.SOURCE_PREMATCH,
        TimingSemantics.ROLE_ONLY,
    ),
    SourceFieldMapping(
        "B365D",
        ObservationSourceKind.BOOKMAKER,
        "BET365",
        MarketFamily.MATCH_RESULT,
        Selection.DRAW,
        ObservationRole.SOURCE_PREMATCH,
        TimingSemantics.ROLE_ONLY,
    ),
    SourceFieldMapping(
        "B365A",
        ObservationSourceKind.BOOKMAKER,
        "BET365",
        MarketFamily.MATCH_RESULT,
        Selection.AWAY,
        ObservationRole.SOURCE_PREMATCH,
        TimingSemantics.ROLE_ONLY,
    ),
    SourceFieldMapping(
        "B365CH",
        ObservationSourceKind.BOOKMAKER,
        "BET365",
        MarketFamily.MATCH_RESULT,
        Selection.HOME,
        ObservationRole.CLOSING,
        TimingSemantics.ROLE_ONLY,
    ),
    SourceFieldMapping(
        "B365CD",
        ObservationSourceKind.BOOKMAKER,
        "BET365",
        MarketFamily.MATCH_RESULT,
        Selection.DRAW,
        ObservationRole.CLOSING,
        TimingSemantics.ROLE_ONLY,
    ),
    SourceFieldMapping(
        "B365CA",
        ObservationSourceKind.BOOKMAKER,
        "BET365",
        MarketFamily.MATCH_RESULT,
        Selection.AWAY,
        ObservationRole.CLOSING,
        TimingSemantics.ROLE_ONLY,
    ),
)

SUPPORTED_SOURCE_FIELDS = tuple(mapping.source_field for mapping in FOOTBALL_DATA_MAPPINGS)
