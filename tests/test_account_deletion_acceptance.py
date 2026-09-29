"""Transactional acceptance of local deletion without live provider calls."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, create_engine, text

from pitchvalue.api.dependencies import get_connection, get_transaction
from pitchvalue.api.main import create_app
from pitchvalue.prediction.repository import persist_match_prediction
from pitchvalue.product_services import account_deletion, provider_revocation
from pitchvalue.product_services.account_deletion import initiate_account_deletion
from pitchvalue.product_services.auth import (
    AccountKind,
    AuthError,
    ProductUser,
    VerifiedExternalIdentity,
    _issue_session,
    authenticate_access_token,
    create_guest_session,
    login_email,
    refresh_session,
    register_email,
)
from pitchvalue.product_services.entitlements import (
    VerifiedCommerceEvidence,
    reconcile_verified_purchase,
)
from pitchvalue.product_services.followed_matches import follow_match
from pitchvalue.product_services.push_tokens import register_push_token
from pitchvalue.product_services.tracking import save_public_selection
from test_prediction_repository import _request


@pytest.fixture
def db() -> Iterator[Connection]:
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_email_deletion_removes_owned_state_and_allows_clean_reregistration(
    db: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pitchvalue.product_services.email_delivery.ResendEmailVerificationDelivery.request_verification",
        lambda self, email, token: None,
    )
    now = datetime.now(UTC)
    email = f"delete-{uuid.uuid4()}@example.com"
    password = "StrongPassword123!"
    first, _ = register_email(db, email, password, "US", now=now)
    first_id = first.user.user_id
    first_subject = db.execute(
        text("SELECT subject_id FROM app_users WHERE user_id=:user_id"),
        {"user_id": first_id},
    ).scalar_one()
    outsider = create_guest_session(db, now=now)

    request = _request(db, exact=True, publication_eligible=True, bet_score=Decimal("80"))
    prediction_id = persist_match_prediction(db, request).prediction_snapshot_ids[0]
    match_id = int(request.decision.match_id)
    saved = save_public_selection(db, user_id=first_id, prediction_snapshot_id=prediction_id)
    follow_match(db, first_id, match_id)
    register_push_token(db, first_id, "EXPO", f"owned-{uuid.uuid4()}")
    register_push_token(db, outsider.user.user_id, "EXPO", f"other-{uuid.uuid4()}")
    db.execute(
        text("INSERT INTO push_tokens (user_id,provider,token) VALUES (NULL,'EXPO',:token)"),
        {"token": f"unowned-{uuid.uuid4()}"},
    )
    db.execute(
        text(
            "INSERT INTO auth_password_resets (token_hash,user_id,expires_at) "
            "VALUES (:token_hash,:user_id,:expires_at)"
        ),
        {
            "token_hash": uuid.uuid4().hex * 2,
            "user_id": first_id,
            "expires_at": now + timedelta(hours=1),
        },
    )
    db.execute(
        text(
            "INSERT INTO legal_acceptance "
            "(user_id,acknowledgement_type,document_version,accepted_at) "
            "VALUES (:user_id,'TERMS','test-v1',:accepted_at)"
        ),
        {"user_id": first_id, "accepted_at": now},
    )
    commerce = VerifiedCommerceEvidence(
        provider="TEST_STORE",
        external_transaction_id=f"tx-{uuid.uuid4()}",
        product_identifier="pitchvalue.annual",
        plan="ANNUAL",
        verification_state="VERIFIED",
        purchased_at=now,
        expires_at=now + timedelta(days=365),
        trial_eligible=False,
        is_trial=False,
        payload_hash="a" * 64,
    )
    assert reconcile_verified_purchase(db, first_id, commerce, now=now)

    assert initiate_account_deletion(db, first.user, password, now=now) == "DELETED"
    assert authenticate_access_token(db, first.access_token, now=now) is None
    with pytest.raises(AuthError):
        refresh_session(db, first.refresh_token, now=now)
    with pytest.raises(AuthError):
        login_email(db, email, password, now=now)

    for table in (
        "app_users",
        "auth_identities",
        "auth_sessions",
        "auth_password_resets",
        "auth_email_verifications",
        "saved_selections",
        "followed_matches",
        "push_tokens",
    ):
        count = db.execute(
            text(f"SELECT count(*) FROM {table} WHERE user_id=:user_id"),
            {"user_id": first_id},
        ).scalar_one()
        assert count == 0, table
    assert (
        db.execute(
            text("SELECT count(*) FROM matches WHERE match_id=:id"), {"id": match_id}
        ).scalar_one()
        == 1
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM prediction_snapshots WHERE prediction_snapshot_id=:id"),
            {"id": prediction_id},
        ).scalar_one()
        == 1
    )
    assert saved.prediction_snapshot_id == prediction_id
    assert (
        db.execute(
            text("SELECT count(*) FROM push_tokens WHERE user_id=:user_id"),
            {"user_id": outsider.user.user_id},
        ).scalar_one()
        == 1
    )
    assert (
        db.execute(text("SELECT count(*) FROM push_tokens WHERE user_id IS NULL")).scalar_one() >= 1
    )

    for table in (
        "commerce_evidence",
        "entitlement_evidence",
        "legal_acceptance",
        "account_deletion_requests",
    ):
        retained = (
            db.execute(
                text(
                    f"SELECT user_id,pseudonymous_subject_id FROM {table} "
                    "WHERE pseudonymous_subject_id=:subject_id"
                ),
                {"subject_id": first_subject},
            )
            .mappings()
            .all()
        )
        assert retained, table
        assert all(row["user_id"] is None for row in retained), table

    second, _ = register_email(db, email, password, "US", now=now + timedelta(minutes=1))
    assert second.user.user_id != first_id
    second_subject = db.execute(
        text("SELECT subject_id FROM app_users WHERE user_id=:user_id"),
        {"user_id": second.user.user_id},
    ).scalar_one()
    assert second_subject != first_subject
    for table in ("saved_selections", "followed_matches", "push_tokens"):
        assert (
            db.execute(
                text(f"SELECT count(*) FROM {table} WHERE user_id=:user_id"),
                {"user_id": second.user.user_id},
            ).scalar_one()
            == 0
        )
    for table in ("commerce_evidence", "entitlement_evidence", "legal_acceptance"):
        assert (
            db.execute(
                text(f"SELECT count(*) FROM {table} WHERE user_id=:user_id"),
                {"user_id": second.user.user_id},
            ).scalar_one()
            == 0
        )


@pytest.mark.integration
def test_provider_retry_failure_does_not_restore_local_account(
    db: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    user_id = str(uuid.uuid4())
    provider_subject = f"google-{uuid.uuid4()}"
    db.execute(
        text(
            "INSERT INTO app_users (user_id,account_kind,created_at,updated_at) "
            "VALUES (:user_id,'AUTHENTICATED',:now,:now)"
        ),
        {"user_id": user_id, "now": now},
    )
    db.execute(
        text(
            "INSERT INTO auth_identities (user_id,provider,provider_subject,created_at) "
            "VALUES (:user_id,'GOOGLE',:subject,:now)"
        ),
        {"user_id": user_id, "subject": provider_subject, "now": now},
    )
    user = ProductUser(user_id, AccountKind.AUTHENTICATED, None)
    session = _issue_session(db, user, now)
    monkeypatch.setattr(
        account_deletion.UnconfiguredGoogleIdentityVerifier,
        "verify",
        lambda self, token: VerifiedExternalIdentity("GOOGLE", provider_subject, None),
    )
    assert (
        initiate_account_deletion(
            db,
            user,
            password_or_token="test-identity",
            provider_credential={"type": "ACCESS_TOKEN", "value": "test-revocation"},
            now=now,
        )
        == "PROCESSING"
    )
    assert authenticate_access_token(db, session.access_token, now=now) is None
    job = (
        db.execute(
            text(
                "SELECT job_id,request_id,provider,credential_type,credential_value "
                "FROM provider_revocation_jobs WHERE provider_subject=:subject"
            ),
            {"subject": provider_subject},
        )
        .mappings()
        .one()
    )

    def retryable_failure(self: object, credential_type: str, credential_value: str) -> None:
        del self, credential_type, credential_value
        raise provider_revocation.RetryableError("simulated provider outage")

    monkeypatch.setattr(provider_revocation.GoogleRevocationAdapter, "revoke", retryable_failure)
    provider_revocation.ProviderRevocationService()._process_job(db, job, now)
    assert (
        db.execute(
            text("SELECT status FROM provider_revocation_jobs WHERE job_id=:job_id"),
            {"job_id": job["job_id"]},
        ).scalar_one()
        == "FAILED_RETRYABLE"
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM app_users WHERE user_id=:user_id"),
            {"user_id": user_id},
        ).scalar_one()
        == 0
    )
    assert authenticate_access_token(db, session.access_token, now=now) is None


@pytest.mark.integration
def test_deletion_api_invalidates_its_previous_bearer_session(
    db: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pitchvalue.product_services.email_delivery.ResendEmailVerificationDelivery.request_verification",
        lambda self, email, token: None,
    )
    email = f"delete-api-{uuid.uuid4()}@example.com"
    session, _ = register_email(db, email, "StrongPassword123!", "US")
    app = create_app()
    app.dependency_overrides[get_connection] = lambda: db
    app.dependency_overrides[get_transaction] = lambda: db
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {session.access_token}"}
        assert client.get("/api/v1/me", headers=headers).status_code == 200
        response = client.post(
            "/api/v1/auth/account-deletion",
            headers=headers,
            json={"password_or_token": "StrongPassword123!"},
        )
        assert response.status_code == 200
        assert response.json()["deletion_state"] == "DELETED"
        assert client.get("/api/v1/me", headers=headers).status_code == 401
