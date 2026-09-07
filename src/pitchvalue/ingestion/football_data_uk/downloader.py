"""Network boundary for fetching raw football-data.co.uk bytes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx

from pitchvalue.ingestion.football_data_uk.raw import RawArtifact, RawArtifactStore
from pitchvalue.ingestion.football_data_uk.registry import SourceDefinition

logger = logging.getLogger(__name__)


class FootballDataDownloader:
    """Small synchronous downloader with explicit timeout and HTTP validation."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._owned_client = client is None
        self.client = client or httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "PitchValue historical-ingestion/0.1"},
        )

    def close(self) -> None:
        """Close an internally-created client."""
        if self._owned_client:
            self.client.close()

    def fetch(self, source: SourceDefinition, store: RawArtifactStore) -> RawArtifact:
        """Fetch, validate, hash, and preserve one source without parsing it."""
        logger.info("source requested: %s", source.url)
        response = self.client.get(source.url)
        response.raise_for_status()
        if not response.content:
            raise ValueError("source response was empty")
        filename = Path(httpx.URL(source.url).path).name
        return store.preserve(response.content, source, datetime.now(UTC), filename)
