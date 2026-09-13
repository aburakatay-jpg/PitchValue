"""Minimal HTTP adapter for documented 5DFA Free-plan endpoints."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from pitchvalue.providers.five_dfa.config import FiveDfaConfig


class ProviderErrorKind(StrEnum):
    AUTHENTICATION = "AUTHENTICATION"
    RATE_LIMIT = "RATE_LIMIT"
    UNSUPPORTED_PLAN = "UNSUPPORTED_PLAN"
    MALFORMED_PAYLOAD = "MALFORMED_PAYLOAD"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class FiveDfaError(RuntimeError):
    def __init__(
        self,
        kind: ProviderErrorKind,
        code: str,
        *,
        request_id: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(code)
        self.kind = kind
        self.code = code
        self.request_id = request_id
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class RateLimitState:
    limit: int | None
    remaining: int | None
    reset: int | None
    retry_after_seconds: int | None


@dataclass(frozen=True)
class ProviderPage:
    data: object
    request_id: str | None
    rate_limit: RateLimitState
    page: int | None = None
    per_page: int | None = None
    count: int | None = None
    has_more: bool = False


def _optional_int(headers: Mapping[str, str], name: str) -> int | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _rate_limit(headers: Mapping[str, str]) -> RateLimitState:
    return RateLimitState(
        _optional_int(headers, "x-ratelimit-limit"),
        _optional_int(headers, "x-ratelimit-remaining"),
        _optional_int(headers, "x-ratelimit-reset"),
        _optional_int(headers, "retry-after"),
    )


def _error_kind(status: int, code: str) -> ProviderErrorKind:
    if (status in {401, 403} and code != "insufficient_plan") or code in {
        "missing_api_key",
        "invalid_api_key",
    }:
        return ProviderErrorKind.AUTHENTICATION
    if status == 429 or code == "too_many_requests":
        return ProviderErrorKind.RATE_LIMIT
    if status == 403 and code == "insufficient_plan":
        return ProviderErrorKind.UNSUPPORTED_PLAN
    if status >= 500:
        return ProviderErrorKind.UNAVAILABLE
    return ProviderErrorKind.PROVIDER_ERROR


class FiveDfaClient:
    """Read-only client with injected transport and one bounded safe GET retry."""

    def __init__(
        self,
        config: FiveDfaConfig,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=config.timeout_seconds)
        self._sleep = sleep

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> FiveDfaClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def get(
        self,
        path: str,
        *,
        params: Mapping[str, str | int | float | bool | None] | None = None,
    ) -> ProviderPage:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("provider path must be absolute and host-relative")
        attempts = self.config.max_safe_retries + 1
        for attempt in range(attempts):
            try:
                response = self._client.get(
                    f"{self.config.base_url}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    timeout=self.config.timeout_seconds,
                )
            except httpx.TimeoutException as error:
                if attempt + 1 < attempts:
                    self._sleep(_backoff_seconds(attempt))
                    continue
                raise FiveDfaError(ProviderErrorKind.TIMEOUT, "provider_timeout") from error
            except httpx.HTTPError as error:
                if attempt + 1 < attempts:
                    self._sleep(_backoff_seconds(attempt))
                    continue
                raise FiveDfaError(ProviderErrorKind.UNAVAILABLE, "provider_unavailable") from error
            limits = _rate_limit(response.headers)
            try:
                body: Any = response.json()
            except ValueError as error:
                raise FiveDfaError(
                    ProviderErrorKind.MALFORMED_PAYLOAD,
                    "malformed_json",
                    request_id=response.headers.get("x-request-id"),
                ) from error
            if not isinstance(body, dict) or body.get("success") not in {0, 1}:
                raise FiveDfaError(ProviderErrorKind.MALFORMED_PAYLOAD, "invalid_envelope")
            if response.status_code >= 400 or body["success"] == 0:
                raw_error = body.get("error")
                if not isinstance(raw_error, dict):
                    raise FiveDfaError(
                        ProviderErrorKind.MALFORMED_PAYLOAD, "invalid_error_envelope"
                    )
                code = str(raw_error.get("code", "provider_error"))
                request_id = raw_error.get("request_id")
                request_id = str(request_id) if request_id is not None else None
                kind = _error_kind(response.status_code, code)
                retry_delay = _retry_delay(kind, limits, attempt)
                if attempt + 1 < attempts and retry_delay is not None:
                    self._sleep(retry_delay)
                    continue
                raise FiveDfaError(
                    kind,
                    code,
                    request_id=request_id,
                    retry_after_seconds=limits.retry_after_seconds,
                )
            if "data" not in body:
                raise FiveDfaError(ProviderErrorKind.MALFORMED_PAYLOAD, "missing_data")
            pagination = body.get("pagination") or {}
            if not isinstance(pagination, dict):
                raise FiveDfaError(ProviderErrorKind.MALFORMED_PAYLOAD, "invalid_pagination")
            return ProviderPage(
                data=body["data"],
                request_id=response.headers.get("x-request-id"),
                rate_limit=limits,
                page=_integer(pagination.get("page")),
                per_page=_integer(pagination.get("per_page")),
                count=_integer(pagination.get("count")),
                has_more=pagination.get("has_more") is True,
            )
        raise AssertionError("unreachable")

    def pages(
        self,
        path: str,
        *,
        params: Mapping[str, str | int | float | bool | None] | None = None,
    ) -> Iterator[ProviderPage]:
        """Iterate documented pages sequentially to conserve the Free quota."""
        page_number = 1
        base = dict(params or {})
        while True:
            page = self.get(path, params={**base, "page": page_number})
            yield page
            if not page.has_more:
                return
            page_number += 1


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _backoff_seconds(attempt: int) -> float:
    """Deterministic bounded backoff; jitter is intentionally absent for replayable tests."""
    return float(min(2**attempt, 10))


def _retry_delay(kind: ProviderErrorKind, limits: RateLimitState, attempt: int) -> float | None:
    if kind is ProviderErrorKind.RATE_LIMIT:
        retry_after = limits.retry_after_seconds
        if retry_after is None or retry_after < 0 or retry_after > 10:
            return None
        return float(retry_after)
    if kind is ProviderErrorKind.UNAVAILABLE:
        return _backoff_seconds(attempt)
    return None
