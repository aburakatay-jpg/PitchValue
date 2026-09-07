"""Explicit football-data.co.uk domestic source registry."""

from __future__ import annotations

from dataclasses import dataclass

PROVIDER_NAME = "football-data.co.uk"
PROVIDER_BASE_URL = "https://www.football-data.co.uk"
SOURCE_URL_TEMPLATE = PROVIDER_BASE_URL + "/mmz4281/{season_code}/{source_code}.csv"


@dataclass(frozen=True)
class SourceDefinition:
    """One enabled provider file mapped to canonical scope."""

    canonical_competition: str
    season_name: str
    provider: str
    source_code: str
    country_code: str
    jurisdiction_code: str
    url: str
    enabled: bool = True

    @property
    def key(self) -> str:
        """Return the stable command-line registry key."""
        return f"{self.source_code}:{self.season_name}"


_COMPETITIONS = (
    ("Premier League", "E0", "GBR", "ENG"),
    ("Ligue 1", "F1", "FRA", "FRA"),
    ("Bundesliga", "D1", "DEU", "DEU"),
    ("Süper Lig", "T1", "TUR", "TUR"),
    ("Primeira Liga", "P1", "PRT", "PRT"),
    ("La Liga", "SP1", "ESP", "ESP"),
    ("Scottish Premiership", "SC0", "GBR", "SCO"),
)
_SEASONS = (("2024/25", "2425"), ("2025/26", "2526"))

SOURCES = tuple(
    SourceDefinition(
        canonical_competition=competition,
        season_name=season_name,
        provider=PROVIDER_NAME,
        source_code=source_code,
        country_code=country_code,
        jurisdiction_code=jurisdiction_code,
        url=SOURCE_URL_TEMPLATE.format(season_code=season_code, source_code=source_code),
    )
    for competition, source_code, country_code, jurisdiction_code in _COMPETITIONS
    for season_name, season_code in _SEASONS
)


def get_source(key: str) -> SourceDefinition:
    """Resolve one enabled source by its stable key."""
    for source in SOURCES:
        if source.enabled and source.key == key:
            return source
    raise KeyError(f"Unknown or disabled source: {key}")
