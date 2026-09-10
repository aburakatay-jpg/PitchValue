"""Controlled values persisted by the canonical odds snapshot schema."""

from enum import StrEnum


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
