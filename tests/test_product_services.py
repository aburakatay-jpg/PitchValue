from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest

from pitchvalue.prediction.contracts import MarketFamily, Selection
from pitchvalue.prediction.persistence import PersistedPrediction
from pitchvalue.product_services.assistant import (
    AssistantState,
    CouponRisk,
    CouponState,
    DeterministicTestAssistant,
    ExternalAssistantAdapter,
    build_coupon,
    explain_public_prediction,
    unsupported_prediction_request,
)
from pitchvalue.product_services.auth import (
    AuthError,
    UnconfiguredAppleIdentityVerifier,
    UnconfiguredPasswordResetDelivery,
    hash_password,
    normalize_email,
    verify_password,
)
from pitchvalue.product_services.entitlements import (
    CommerceVerificationRequest,
    ExternalCommerceVerifier,
)
from pitchvalue.product_services.settlement import (
    CanonicalResult,
    SettlementError,
    SettlementOutcome,
    settle,
)

D = Decimal


def test_email_normalization_and_scrypt_password_verification() -> None:
    assert normalize_email(" User@Example.COM ") == "user@example.com"
    encoded = hash_password("correct horse battery staple", salt=b"0123456789abcdef")
    assert encoded.startswith("scrypt$")
    assert "correct horse" not in encoded
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)


@pytest.mark.parametrize("value", ["", "missing-at", "@example.com", "a@invalid"])
def test_invalid_email_is_rejected(value: str) -> None:
    with pytest.raises(AuthError, match="invalid email"):
        normalize_email(value)


def test_external_identity_and_commerce_boundaries_fail_closed() -> None:
    with pytest.raises(RuntimeError, match="external credentials"):
        UnconfiguredAppleIdentityVerifier().verify("provider-token")
    request = CommerceVerificationRequest("APP_STORE", "tx", "annual", "ANNUAL", "receipt")
    with pytest.raises(RuntimeError, match="external activation"):
        ExternalCommerceVerifier().verify(request)
    with pytest.raises(RuntimeError, match="external activation"):
        UnconfiguredPasswordResetDelivery().request_reset("user@example.com", "dummy_token")


@pytest.mark.parametrize(
    ("home", "away", "selection", "expected"),
    [
        (2, 1, Selection.HOME, SettlementOutcome.WON),
        (1, 1, Selection.DRAW, SettlementOutcome.WON),
        (0, 1, Selection.AWAY, SettlementOutcome.WON),
        (2, 1, Selection.AWAY, SettlementOutcome.LOST),
    ],
)
def test_match_result_settlement(
    home: int, away: int, selection: Selection, expected: SettlementOutcome
) -> None:
    result = CanonicalResult("FINISHED", home, away)
    assert settle(MarketFamily.MATCH_RESULT, selection, result) is expected


@pytest.mark.parametrize(
    ("home", "away", "selection", "expected"),
    [
        (1, 1, Selection.ONE_X, SettlementOutcome.WON),
        (0, 2, Selection.X_TWO, SettlementOutcome.WON),
        (1, 0, Selection.ONE_TWO, SettlementOutcome.WON),
        (1, 1, Selection.ONE_TWO, SettlementOutcome.LOST),
    ],
)
def test_double_chance_settlement(
    home: int, away: int, selection: Selection, expected: SettlementOutcome
) -> None:
    assert (
        settle(
            MarketFamily.DOUBLE_CHANCE,
            selection,
            CanonicalResult("FINISHED", home, away),
        )
        is expected
    )


@pytest.mark.parametrize(
    ("market", "line", "home", "away", "selection", "expected"),
    [
        (MarketFamily.TOTAL_GOALS, "1.5", 1, 1, Selection.OVER, SettlementOutcome.WON),
        (MarketFamily.TOTAL_GOALS, "2.5", 1, 1, Selection.UNDER, SettlementOutcome.WON),
        (MarketFamily.HOME_TEAM_TOTAL, "0.5", 1, 0, Selection.OVER, SettlementOutcome.WON),
        (MarketFamily.HOME_TEAM_TOTAL, "1.5", 1, 0, Selection.UNDER, SettlementOutcome.WON),
        (MarketFamily.AWAY_TEAM_TOTAL, "0.5", 2, 0, Selection.UNDER, SettlementOutcome.WON),
        (MarketFamily.AWAY_TEAM_TOTAL, "1.5", 0, 2, Selection.OVER, SettlementOutcome.WON),
    ],
)
def test_goal_line_settlement(
    market: MarketFamily,
    line: str,
    home: int,
    away: int,
    selection: Selection,
    expected: SettlementOutcome,
) -> None:
    assert (
        settle(
            market,
            selection,
            CanonicalResult("FINISHED", home, away),
            line=D(line),
        )
        is expected
    )


@pytest.mark.parametrize(
    ("home", "away", "selection", "expected"),
    [
        (1, 1, Selection.YES, SettlementOutcome.WON),
        (1, 0, Selection.NO, SettlementOutcome.WON),
        (0, 0, Selection.YES, SettlementOutcome.LOST),
    ],
)
def test_btts_settlement(
    home: int, away: int, selection: Selection, expected: SettlementOutcome
) -> None:
    assert settle(MarketFamily.BTTS, selection, CanonicalResult("FINISHED", home, away)) is expected


def test_nonfinal_and_void_settlement_rules_are_explicit() -> None:
    assert (
        settle(MarketFamily.MATCH_RESULT, Selection.HOME, CanonicalResult("SCHEDULED", None, None))
        is None
    )
    assert (
        settle(MarketFamily.MATCH_RESULT, Selection.HOME, CanonicalResult("POSTPONED", None, None))
        is None
    )
    assert (
        settle(MarketFamily.MATCH_RESULT, Selection.HOME, CanonicalResult("CANCELLED", None, None))
        is SettlementOutcome.VOID
    )
    with pytest.raises(SettlementError, match="SETTLEMENT_RULE_REVIEW_REQUIRED"):
        settle(MarketFamily.MATCH_RESULT, Selection.HOME, CanonicalResult("ABANDONED", 1, 0))


def test_result_fingerprint_detects_corrections_deterministically() -> None:
    first = CanonicalResult("FINISHED", 1, 0, "revision-1")
    replay = CanonicalResult("FINISHED", 1, 0, "revision-1")
    corrected = CanonicalResult("FINISHED", 1, 1, "revision-2")
    assert first.fingerprint == replay.fingerprint
    assert first.fingerprint != corrected.fingerprint


def _prediction(
    match_id: int,
    *,
    score: str = "80",
    edge: str = "0.05",
    public: bool = True,
) -> PersistedPrediction:
    return cast(
        PersistedPrediction,
        SimpleNamespace(
            match_id=match_id,
            market="match_result",
            selection="home",
            policy_decision="PICK",
            model_probability=D("0.55"),
            bet_score=D(score),
            edge=D(edge),
            market_observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            blockers=(),
            diagnostics=(),
            public_candidate=public,
        ),
    )


def test_ai_requires_public_context_and_external_adapter_is_fail_closed() -> None:
    available = explain_public_prediction(_prediction(1), DeterministicTestAssistant())
    assert available.state is AssistantState.AVAILABLE
    assert available.context is not None
    assert available.context.match_id == 1
    external = explain_public_prediction(_prediction(1), ExternalAssistantAdapter())
    assert external.state is AssistantState.EXTERNAL_ACTIVATION_REQUIRED
    assert external.answer is None
    assert (
        explain_public_prediction(None, DeterministicTestAssistant()).state
        is AssistantState.NO_PUBLIC_ANALYSIS
    )
    assert unsupported_prediction_request().state is AssistantState.UNSUPPORTED


@pytest.mark.parametrize("risk", list(CouponRisk))
def test_coupon_uses_eligible_unique_matches_and_never_forces_four(risk: CouponRisk) -> None:
    records = (
        _prediction(1, score="90", edge="0.02"),
        _prediction(1, score="80", edge="0.10"),
        _prediction(2, score="70", edge="0.08"),
        _prediction(3, public=False),
    )
    result = build_coupon(records, risk=risk, requested_count=4)
    assert result.state is CouponState.INSUFFICIENT_ELIGIBLE_POOL
    assert len(result.selections) == 2
    assert len({item.match_id for item in result.selections}) == 2


def test_coupon_empty_pool_and_count_bounds() -> None:
    assert build_coupon((), risk=CouponRisk.SAFE, requested_count=1).state is CouponState.EMPTY
    with pytest.raises(ValueError, match="between one and four"):
        build_coupon((), risk=CouponRisk.SAFE, requested_count=5)
