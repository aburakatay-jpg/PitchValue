from __future__ import annotations

import pytest

from pitchvalue.product_services.abuse import (
    AuthAction,
    AuthRateLimited,
    InMemoryAuthLimiter,
    LimitPolicy,
)


def test_login_limiter_blocks_repeated_failures_without_storing_raw_identity() -> None:
    now = [100.0]
    limiter = InMemoryAuthLimiter({AuthAction.LOGIN: LimitPolicy(2, 60)}, clock=lambda: now[0])
    limiter.check(AuthAction.LOGIN, "127.0.0.1", "user@example.com")
    limiter.check(AuthAction.LOGIN, "127.0.0.1", "user@example.com")
    with pytest.raises(AuthRateLimited) as captured:
        limiter.check(AuthAction.LOGIN, "127.0.0.1", "user@example.com")
    assert captured.value.retry_after_seconds == 61
    assert all("user@example.com" not in key for key in limiter._attempts)


def test_success_reset_and_window_expiry_restore_access() -> None:
    now = [100.0]
    limiter = InMemoryAuthLimiter({AuthAction.LOGIN: LimitPolicy(1, 60)}, clock=lambda: now[0])
    limiter.check(AuthAction.LOGIN, "client", "identity")
    limiter.reset(AuthAction.LOGIN, "client", "identity")
    limiter.check(AuthAction.LOGIN, "client", "identity")
    now[0] = 161.0
    limiter.check(AuthAction.LOGIN, "client", "identity")


def test_registration_and_refresh_have_independent_limits() -> None:
    policies = {
        AuthAction.REGISTER: LimitPolicy(1, 60),
        AuthAction.REFRESH: LimitPolicy(1, 60),
    }
    limiter = InMemoryAuthLimiter(policies, clock=lambda: 100.0)
    limiter.check(AuthAction.REGISTER, "client")
    limiter.check(AuthAction.REFRESH, "client", "opaque-refresh-token")
    with pytest.raises(AuthRateLimited):
        limiter.check(AuthAction.REGISTER, "client")
    with pytest.raises(AuthRateLimited):
        limiter.check(AuthAction.REFRESH, "client", "opaque-refresh-token")
