from __future__ import annotations

import json

import httpx
import pytest

from pitchvalue.providers.five_dfa.client import FiveDfaClient, FiveDfaError, ProviderErrorKind
from pitchvalue.providers.five_dfa.config import FiveDfaConfig


def _client(
    handler: httpx.MockTransport, *, retries: int = 0, sleeps: list[float] | None = None
) -> FiveDfaClient:
    config = FiveDfaConfig("fake-key", max_safe_retries=retries)
    return FiveDfaClient(
        config,
        client=httpx.Client(transport=handler),
        sleep=(sleeps if sleeps is not None else []).append,
    )


def test_success_and_valid_empty_are_distinct_from_failure() -> None:
    responses = iter(
        [
            httpx.Response(200, json={"success": 1, "data": [{"id": 1}]}),
            httpx.Response(200, json={"success": 1, "data": []}),
        ]
    )
    transport = httpx.MockTransport(lambda request: next(responses))
    client = _client(transport)
    assert client.get("/fixtures").data == [{"id": 1}]
    assert client.get("/fixtures").data == []


@pytest.mark.parametrize(
    ("status", "code", "kind"),
    [
        (401, "invalid_api_key", ProviderErrorKind.AUTHENTICATION),
        (403, "insufficient_plan", ProviderErrorKind.UNSUPPORTED_PLAN),
        (429, "too_many_requests", ProviderErrorKind.RATE_LIMIT),
        (503, "internal_error", ProviderErrorKind.UNAVAILABLE),
        (400, "invalid_market", ProviderErrorKind.PROVIDER_ERROR),
    ],
)
def test_provider_error_mapping(status: int, code: str, kind: ProviderErrorKind) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            status,
            json={
                "success": 0,
                "error": {"code": code, "request_id": "req_test"},
            },
            headers={"Retry-After": "7"},
        )
    )
    with pytest.raises(FiveDfaError) as caught:
        _client(transport).get("/fixtures")
    assert caught.value.kind is kind
    assert caught.value.request_id == "req_test"
    assert caught.value.retry_after_seconds == 7


def test_rate_limit_is_retried_once_using_retry_after() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                json={"success": 0, "error": {"code": "too_many_requests"}},
                headers={"Retry-After": "3"},
            )
        return httpx.Response(
            200,
            json={"success": 1, "data": []},
            headers={
                "X-RateLimit-Limit": "60",
                "X-RateLimit-Remaining": "59",
                "X-RateLimit-Reset": "1234",
                "X-Request-ID": "req_success",
            },
        )

    page = _client(httpx.MockTransport(handler), retries=1, sleeps=sleeps).get("/fixtures")
    assert calls == 2 and sleeps == [3.0]
    assert (page.rate_limit.limit, page.rate_limit.remaining, page.rate_limit.reset) == (
        60,
        59,
        1234,
    )
    assert page.request_id == "req_success"


def test_timeout_and_malformed_payload_are_not_empty_results() -> None:
    timeout = httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("x")))
    with pytest.raises(FiveDfaError) as caught:
        _client(timeout).get("/fixtures")
    assert caught.value.kind is ProviderErrorKind.TIMEOUT

    malformed = httpx.MockTransport(lambda request: httpx.Response(200, content=b"not-json"))
    with pytest.raises(FiveDfaError) as caught:
        _client(malformed).get("/fixtures")
    assert caught.value.kind is ProviderErrorKind.MALFORMED_PAYLOAD


def test_request_is_authenticated_and_pagination_is_sequential() -> None:
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page")
        seen.append((page or "", request.headers.get("authorization")))
        number = int(page or "1")
        return httpx.Response(
            200,
            json={
                "success": 1,
                "data": [number],
                "pagination": {"page": number, "per_page": 1, "count": 1, "has_more": number == 1},
            },
        )

    pages = tuple(_client(httpx.MockTransport(handler)).pages("/fixtures", params={"per_page": 1}))
    assert [page.data for page in pages] == [[1], [2]]
    assert seen == [("1", "Bearer fake-key"), ("2", "Bearer fake-key")]


def test_malformed_envelope_and_host_injection_are_rejected() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=json.dumps({"data": []}))
    )
    with pytest.raises(FiveDfaError, match="invalid_envelope"):
        _client(transport).get("/fixtures")
    with pytest.raises(ValueError, match="host-relative"):
        _client(transport).get("https://evil.example/fixtures")
