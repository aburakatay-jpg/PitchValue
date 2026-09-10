"""Versioned source-specific quality policy for historical prices."""

from datetime import date

from pitchvalue.markets.history.contracts import OddsQualityStatus

PINNACLE_QUALITY_BOUNDARY = date(2025, 7, 23)


def assess_source_quality(
    *, provider_name: str, bookmaker: str | None, event_date: date
) -> tuple[OddsQualityStatus, tuple[str, ...]]:
    """Return raw-observation quality without deleting or changing its price."""
    if (
        provider_name == "football-data.co.uk"
        and bookmaker == "PINNACLE"
        and event_date >= PINNACLE_QUALITY_BOUNDARY
    ):
        return OddsQualityStatus.SUSPECT, ("provider_quality_boundary", "pinnacle_post_2025_07_23")
    return OddsQualityStatus.ELIGIBLE, ()
