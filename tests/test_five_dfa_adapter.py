from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from pitchvalue.providers.five_dfa.adapter import FiveDfaFreeAdapter, FiveDfaPayloadError
from pitchvalue.providers.five_dfa.client import FiveDfaClient
from pitchvalue.providers.five_dfa.config import FiveDfaConfig


def _adapter(handler: httpx.MockTransport) -> FiveDfaFreeAdapter:
    return FiveDfaFreeAdapter(
        FiveDfaClient(
            FiveDfaConfig("fake", max_safe_retries=0), client=httpx.Client(transport=handler)
        )
    )


def test_fixture_adapter_pages_without_paid_odds_include() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json={
                "success": 1,
                "data": [{"id": page}],
                "pagination": {"page": page, "has_more": page == 1},
            },
        )

    start = datetime(2026, 9, 12, tzinfo=UTC)
    rows, limits = _adapter(httpx.MockTransport(handler)).fixture_payloads(
        start_time=start, end_time=start + timedelta(hours=24), league_id="3120672213"
    )
    assert rows == ({"id": 1}, {"id": 2})
    assert len(limits) == 2
    assert all("include" not in request.url.params for request in requests)
    assert all(request.url.params["league"] == "3120672213" for request in requests)


def test_odds_adapter_uses_per_fixture_bet365_only() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"success": 1, "data": {"fixture_id": 10}})

    payload = _adapter(httpx.MockTransport(handler)).fixture_odds_payload("10")
    assert payload == {"fixture_id": 10}
    assert seen == ["https://api.5dollarfootballapi.com/v1/fixtures/10/odds?bookmakers=bet365"]


def test_adapter_rejects_unbounded_or_malformed_fixture_data() -> None:
    start = datetime(2026, 9, 12, tzinfo=UTC)
    adapter = _adapter(
        httpx.MockTransport(lambda request: httpx.Response(200, json={"success": 1, "data": {}}))
    )
    with pytest.raises(ValueError, match="24 hours"):
        adapter.fixture_payloads(start_time=start, end_time=start + timedelta(days=2))
    with pytest.raises(FiveDfaPayloadError, match="list"):
        adapter.fixture_payloads(start_time=start, end_time=start + timedelta(hours=1))
