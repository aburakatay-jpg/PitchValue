"""Explicit, provenance-aware mirror candidates and safe fallback fetching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx

from pitchvalue.ingestion.football_data_uk.pipeline import validate_source_bytes
from pitchvalue.ingestion.football_data_uk.raw import RawArtifact, RawArtifactStore
from pitchvalue.ingestion.football_data_uk.registry import SourceDefinition

TransformationStatus = Literal["raw_equivalent", "likely_raw", "transformed", "unsupported"]


@dataclass(frozen=True)
class MirrorDefinition:
    """One reviewed mirror candidate; never an arbitrary runtime URL."""

    mirror_id: str
    display_name: str
    url_template: str
    homepage: str
    upstream_identity: str
    supported_source_codes: frozenset[str]
    supported_seasons: frozenset[str]
    enabled: bool
    transformation_status: TransformationStatus
    notes: str
    license_status: str

    def supports(self, source: SourceDefinition) -> bool:
        return (
            source.source_code in self.supported_source_codes
            and source.season_name in self.supported_seasons
        )


TARGET_CODES = frozenset({"E0", "F1", "D1", "T1", "P1", "SP1", "SC0"})
TARGET_SEASONS = frozenset({"2024/25", "2025/26"})

MIRRORS = (
    MirrorDefinition(
        mirror_id="morobang_warehouse",
        display_name="Morobang football-data-warehouse",
        url_template=("https://github.com/Morobang/football-data-warehouse/tree/main/data/bronze"),
        homepage="https://github.com/Morobang/football-data-warehouse",
        upstream_identity="football-data.co.uk",
        supported_source_codes=TARGET_CODES,
        supported_seasons=TARGET_SEASONS,
        enabled=False,
        transformation_status="likely_raw",
        notes="Documentation describes frozen raw copies, but repository contains no CSV files.",
        license_status="LICENSE REVIEW REQUIRED",
    ),
    MirrorDefinition(
        mirror_id="vibedatascience_big5",
        display_name="vibedatascience football-data.co.uk Big 5",
        url_template=(
            "https://raw.githubusercontent.com/vibedatascience/"
            "footballdatacouk_leagues_games_results_big5/refs/heads/main/"
            "footballdatacouk_leagues_games_results_2000_ytd.csv"
        ),
        homepage=("https://github.com/vibedatascience/footballdatacouk_leagues_games_results_big5"),
        upstream_identity="football-data.co.uk",
        supported_source_codes=frozenset({"E0", "F1", "D1", "SP1"}),
        supported_seasons=TARGET_SEASONS,
        enabled=False,
        transformation_status="transformed",
        notes="Combined dataset renames fields and standardizes dates; not raw-equivalent.",
        license_status="LICENSE REVIEW REQUIRED",
    ),
    MirrorDefinition(
        mirror_id="sunrick_kickme",
        display_name="sunrick/kickme archive",
        url_template="https://github.com/sunrick/kickme/tree/master/csv",
        homepage="https://github.com/sunrick/kickme",
        upstream_identity="football-data.co.uk",
        supported_source_codes=TARGET_CODES,
        supported_seasons=frozenset(),
        enabled=False,
        transformation_status="likely_raw",
        notes="Historical archive has no verified 2024/25 or 2025/26 target coverage.",
        license_status="MIT code license; dataset redistribution terms unclear",
    ),
    MirrorDefinition(
        mirror_id="xgabora_club_matches",
        display_name="xgabora Club Football Match Data",
        url_template=(
            "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data/"
            "main/data/Matches.csv"
        ),
        homepage="https://github.com/xgabora/Club-Football-Match-Data",
        upstream_identity="football-data.co.uk",
        supported_source_codes=TARGET_CODES,
        supported_seasons=TARGET_SEASONS,
        enabled=False,
        transformation_status="transformed",
        notes="Combined, renamed, normalized, team-remapped dataset with derived fields.",
        license_status="MIT repository license; upstream redistribution scope unclear",
    ),
)


def get_mirror(mirror_id: str) -> MirrorDefinition:
    """Resolve only a configured mirror ID."""
    for mirror in MIRRORS:
        if mirror.mirror_id == mirror_id:
            return mirror
    raise KeyError(f"unknown mirror: {mirror_id}")


def mirror_url(mirror: MirrorDefinition, source: SourceDefinition) -> str:
    """Build a configured URL only for an eligible raw-equivalent source pair."""
    if not mirror.enabled:
        raise ValueError(f"mirror is disabled: {mirror.mirror_id}")
    if mirror.transformation_status != "raw_equivalent":
        raise ValueError(f"mirror is not raw-equivalent: {mirror.mirror_id}")
    if mirror.upstream_identity != source.provider or not mirror.supports(source):
        raise ValueError(f"mirror does not support source: {source.key}")
    start, end = source.season_name.split("/")
    season_code = start[-2:] + end
    return mirror.url_template.format(season_code=season_code, source_code=source.source_code)


class FallbackDownloader:
    """TLS-validating downloader restricted to supplied allowlist definitions."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        mirrors: tuple[MirrorDefinition, ...] = MIRRORS,
    ) -> None:
        self._owned_client = client is None
        self.client = client or httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "PitchValue verified-mirror/0.1"},
        )
        self.mirrors = {mirror.mirror_id: mirror for mirror in mirrors}

    def close(self) -> None:
        if self._owned_client:
            self.client.close()

    def fetch(
        self,
        mirror_id: str,
        source: SourceDefinition,
        store: RawArtifactStore,
    ) -> RawArtifact:
        mirror = self.mirrors.get(mirror_id)
        if mirror is None:
            raise KeyError(f"unknown mirror: {mirror_id}")
        url = mirror_url(mirror, source)
        response = self.client.get(url)
        response.raise_for_status()
        validate_source_bytes(response.content, source)
        filename = Path(httpx.URL(url).path).name
        return store.preserve(
            response.content,
            source,
            datetime.now(UTC),
            filename,
            acquisition_mode="verified_mirror",
            mirror_url=url,
            mirror_id=mirror.mirror_id,
            mirror_name=mirror.display_name,
        )
