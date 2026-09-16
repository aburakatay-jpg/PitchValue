"""Zero-cost, process-local authentication abuse controls."""

from __future__ import annotations

import hashlib
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock


class AuthAction(StrEnum):
    LOGIN = "LOGIN"
    REGISTER = "REGISTER"
    REFRESH = "REFRESH"


@dataclass(frozen=True)
class LimitPolicy:
    attempts: int
    window_seconds: int


class AuthRateLimited(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("authentication request rate limited")
        self.retry_after_seconds = max(1, retry_after_seconds)


DEFAULT_POLICIES = {
    AuthAction.LOGIN: LimitPolicy(5, 300),
    AuthAction.REGISTER: LimitPolicy(10, 3600),
    AuthAction.REFRESH: LimitPolicy(10, 300),
}
MAX_TRACKED_KEYS = 10_000


class InMemoryAuthLimiter:
    """Bound repeated abuse per process without retaining raw identifiers."""

    def __init__(
        self,
        policies: dict[AuthAction, LimitPolicy] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._policies = policies or DEFAULT_POLICIES
        self._clock = clock
        self._attempts: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, action: AuthAction, client: str, principal: str = "") -> None:
        policy = self._policies[action]
        now = self._clock()
        key = _key(action, client, principal)
        with self._lock:
            self._prune(now)
            if key not in self._attempts and len(self._attempts) >= MAX_TRACKED_KEYS:
                oldest = min(self._attempts, key=lambda item: self._attempts[item][-1])
                del self._attempts[oldest]
            attempts = self._attempts.setdefault(key, deque())
            boundary = now - policy.window_seconds
            while attempts and attempts[0] <= boundary:
                attempts.popleft()
            if len(attempts) >= policy.attempts:
                retry_after = int(policy.window_seconds - (now - attempts[0])) + 1
                raise AuthRateLimited(retry_after)
            attempts.append(now)

    def reset(self, action: AuthAction, client: str, principal: str = "") -> None:
        with self._lock:
            self._attempts.pop(_key(action, client, principal), None)

    def _prune(self, now: float) -> None:
        oldest_allowed = now - max(policy.window_seconds for policy in self._policies.values())
        for attempts in self._attempts.values():
            while attempts and attempts[0] <= oldest_allowed:
                attempts.popleft()
        empty = tuple(key for key, attempts in self._attempts.items() if not attempts)
        for key in empty:
            del self._attempts[key]


def _key(action: AuthAction, client: str, principal: str) -> str:
    payload = "\x1f".join((action.value, client.strip(), principal.strip()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
