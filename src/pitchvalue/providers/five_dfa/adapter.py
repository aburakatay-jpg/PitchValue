"""Endpoint-specific Free adapter that keeps provider payloads out of engine code."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from pitchvalue.providers.five_dfa.client import FiveDfaClient, RateLimitState


class FiveDfaPayloadError(ValueError):
    """Raised when a successful provider envelope contains an invalid resource shape."""


class FiveDfaFreeAdapter:
    def __init__(self, client: FiveDfaClient) -> None:
        self._client = client

    def fixture_payloads(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        league_id: str | None = None,
    ) -> tuple[tuple[Mapping[str, object], ...], tuple[RateLimitState, ...]]:
        """Read a bounded UTC window without paid list-level odds expansion."""
        for name, value in (("start_time", start_time), ("end_time", end_time)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if end_time <= start_time or (end_time - start_time).total_seconds() > 86400:
            raise ValueError("fixture window must be positive and at most 24 hours")
        params: dict[str, str | int | float | bool | None] = {
            "start_time": int(start_time.timestamp()),
            "end_time": int(end_time.timestamp()),
            "per_page": 100,
        }
        if league_id is not None:
            if not league_id.strip():
                raise ValueError("league_id must be nonblank")
            params["league"] = league_id
        rows: list[Mapping[str, object]] = []
        limits: list[RateLimitState] = []
        for page in self._client.pages("/fixtures", params=params):
            if not isinstance(page.data, list) or any(
                not isinstance(item, dict) for item in page.data
            ):
                raise FiveDfaPayloadError("fixture data must be a list of objects")
            rows.extend(page.data)
            limits.append(page.rate_limit)
        return tuple(rows), tuple(limits)

    def fixture_odds_payload(self, provider_fixture_id: str) -> Mapping[str, object]:
        """Use the Free-compatible per-fixture Bet365 endpoint, never batch odds."""
        if not provider_fixture_id.strip():
            raise ValueError("provider_fixture_id must be nonblank")
        page = self._client.get(
            f"/fixtures/{provider_fixture_id}/odds",
            params={"bookmakers": "bet365"},
        )
        if not isinstance(page.data, dict):
            raise FiveDfaPayloadError("fixture odds data must be an object")
        return page.data
