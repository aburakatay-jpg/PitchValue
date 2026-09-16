from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Connection, Engine, create_engine, text

from pitchvalue.config import load_settings
from pitchvalue.prediction.repository import persist_match_prediction
from pitchvalue.product_services.auth import (
    authenticate_access_token,
    create_guest_session,
    login_email,
    logout,
    refresh_session,
    register_email,
)
from pitchvalue.product_services.entitlements import (
    EntitlementState,
    VerifiedCommerceEvidence,
    reconcile_verified_purchase,
    resolve_entitlement,
)
from pitchvalue.product_services.settlement import SettlementOutcome
from pitchvalue.product_services.tracking import (
    TrackingError,
    get_saved_selection,
    list_saved_selections,
    performance,
    remove_saved_selection,
    save_public_selection,
    settle_saved_selection,
)
from test_prediction_api import _clean_fixture_data
from test_prediction_repository import _request


@pytest.fixture(scope="session")
def product_engine() -> Engine:
    return create_engine(load_settings(os.environ).database_url)


@pytest.fixture(autouse=True)
def clean_product_data(product_engine: Engine) -> Iterator[None]:
    with product_engine.begin() as connection:
        _clean(connection)
    yield
    with product_engine.begin() as connection:
        _clean(connection)


def _clean(connection: Connection) -> None:
    connection.execute(text("DELETE FROM saved_selections"))
    connection.execute(text("DELETE FROM commerce_evidence"))
    connection.execute(text("DELETE FROM entitlement_evidence"))
    connection.execute(text("DELETE FROM auth_sessions"))
    connection.execute(text("DELETE FROM auth_identities"))
    connection.execute(text("DELETE FROM app_users"))
    _clean_fixture_data(connection)


@pytest.mark.integration
def test_guest_email_session_refresh_expiry_and_logout(product_engine: Engine) -> None:
    now = datetime(2026, 9, 16, tzinfo=UTC)
    with product_engine.begin() as connection:
        guest = create_guest_session(connection, now=now)
        email = register_email(connection, "Person@Example.com", "very secure password", now=now)
    with product_engine.begin() as connection:
        assert authenticate_access_token(connection, guest.access_token, now=now) == guest.user
        login = login_email(connection, "person@example.com", "very secure password", now=now)
        refreshed = refresh_session(connection, login.refresh_token, now=now + timedelta(minutes=1))
        assert authenticate_access_token(connection, login.access_token, now=now) is None
        assert authenticate_access_token(connection, refreshed.access_token, now=now) == email.user
        assert logout(connection, refreshed.access_token, now=now + timedelta(minutes=2))
        assert authenticate_access_token(connection, refreshed.access_token, now=now) is None


@pytest.mark.integration
def test_verified_entitlement_is_idempotent_and_client_flags_are_not_inputs(
    product_engine: Engine,
) -> None:
    now = datetime(2026, 9, 16, tzinfo=UTC)
    with product_engine.begin() as connection:
        user = create_guest_session(connection, now=now).user
    evidence = VerifiedCommerceEvidence(
        provider="TEST_STORE",
        external_transaction_id="transaction-1",
        product_identifier="pitchvalue.annual",
        plan="ANNUAL",
        verification_state="VERIFIED",
        purchased_at=now,
        expires_at=now + timedelta(days=365),
        trial_eligible=True,
        is_trial=True,
        payload_hash="a" * 64,
    )
    with product_engine.begin() as connection:
        assert reconcile_verified_purchase(connection, user.user_id, evidence, now=now)
        assert not reconcile_verified_purchase(connection, user.user_id, evidence, now=now)
        entitlement = resolve_entitlement(connection, user.user_id, now=now)
    assert entitlement.state is EntitlementState.PREMIUM_TRIAL


def _public_prediction(connection: Connection) -> tuple[str, int, int]:
    session = create_guest_session(connection).user
    request = _request(
        connection,
        exact=True,
        publication_eligible=True,
        bet_score=Decimal("80"),
    )
    result = persist_match_prediction(connection, request)
    return session.user_id, int(request.decision.match_id), result.prediction_snapshot_ids[0]


@pytest.mark.integration
def test_my_bets_enforces_ownership_and_retains_removed_history(product_engine: Engine) -> None:
    with product_engine.begin() as connection:
        owner_id, _, prediction_id = _public_prediction(connection)
        other = create_guest_session(connection).user
        saved = save_public_selection(
            connection,
            user_id=owner_id,
            prediction_snapshot_id=prediction_id,
        )
        with pytest.raises(TrackingError, match="not found"):
            get_saved_selection(connection, other.user_id, saved.saved_selection_id)
        assert not remove_saved_selection(connection, other.user_id, saved.saved_selection_id)
        assert remove_saved_selection(connection, owner_id, saved.saved_selection_id)
        count = connection.execute(
            text("SELECT count(*) FROM saved_selections WHERE saved_selection_id=:saved_id"),
            {"saved_id": saved.saved_selection_id},
        ).scalar_one()
    assert count == 1


@pytest.mark.integration
def test_finished_selection_settles_once_and_loss_remains_in_history(
    product_engine: Engine,
) -> None:
    now = datetime(2026, 9, 16, tzinfo=UTC)
    with product_engine.begin() as connection:
        user_id, match_id, prediction_id = _public_prediction(connection)
        saved = save_public_selection(
            connection,
            user_id=user_id,
            prediction_snapshot_id=prediction_id,
            saved_decimal_odds=Decimal("2.00"),
            stake=Decimal("10"),
            currency="USD",
        )
        connection.execute(
            text(
                "UPDATE matches SET status='FINISHED',home_score=0,away_score=1,result='A',"
                "updated_at=:now WHERE match_id=:match_id"
            ),
            {"now": now, "match_id": match_id},
        )
        assert settle_saved_selection(connection, saved.saved_selection_id, now=now) in {
            SettlementOutcome.WON,
            SettlementOutcome.LOST,
        }
        first = get_saved_selection(connection, user_id, saved.saved_selection_id)
        assert (
            settle_saved_selection(connection, saved.saved_selection_id, now=now) is first.outcome
        )
        history = list_saved_selections(connection, user_id, history=True)
        metrics = performance(connection, user_id)
    assert history == (first,)
    assert metrics.wins + metrics.losses == 1
    assert metrics.roi is not None


@pytest.mark.integration
def test_roi_remains_unavailable_without_complete_stake_evidence(product_engine: Engine) -> None:
    with product_engine.begin() as connection:
        user = create_guest_session(connection).user
        metrics = performance(connection, user.user_id)
    assert metrics.total_stake is None
    assert metrics.net_return is None
    assert metrics.roi is None
