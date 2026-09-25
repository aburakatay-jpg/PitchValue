"""Account deletion lifecycle services."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, text

from pitchvalue.product_services.auth import (
    AccountKind,
    ProductUser,
    UnconfiguredAppleIdentityVerifier,
    UnconfiguredGoogleIdentityVerifier,
    _now,
    verify_password,
)


class DeletionError(ValueError):
    """Business logic errors for account deletion."""


def initiate_account_deletion(
    connection: Connection,
    user: ProductUser,
    password_or_token: str | None = None,
    *,
    now: datetime | None = None,
) -> str:
    """
    Executes the backend local account deletion sequence for the authenticated user.
    Returns the deletion state.
    """
    executed_at = _now(now)

    # 1. Fetch user metadata and active identities
    row = (
        connection.execute(
            text("SELECT subject_id, account_kind FROM app_users WHERE user_id = :user_id"),
            {"user_id": user.user_id},
        )
        .mappings()
        .one_or_none()
    )

    if row is None:
        raise DeletionError("User not found")

    subject_id = str(row["subject_id"])
    account_kind = str(row["account_kind"])

    # Ensure idempotency
    existing_request = connection.execute(
        text(
            "SELECT deletion_state FROM account_deletion_requests "
            "WHERE pseudonymous_subject_id = :subject_id "
            "ORDER BY requested_at DESC LIMIT 1"
        ),
        {"subject_id": subject_id},
    ).scalar_one_or_none()

    if existing_request == "DELETED":
        return "DELETED"

    # 2. Re-authentication
    if account_kind == AccountKind.AUTHENTICATED.value:
        identities = (
            connection.execute(
                text(
                    "SELECT provider, provider_subject, password_hash FROM auth_identities "
                    "WHERE user_id = :user_id"
                ),
                {"user_id": user.user_id},
            )
            .mappings()
            .all()
        )

        providers = {i["provider"] for i in identities}

        if not providers:
            raise DeletionError("No valid authentication method found")

        if "EMAIL" in providers:
            email_identity = next(i for i in identities if i["provider"] == "EMAIL")
            if not password_or_token:
                raise DeletionError("Password required for email authentication")
            if not verify_password(password_or_token, str(email_identity["password_hash"])):
                raise DeletionError("Invalid password")
        else:
            if not password_or_token:
                raise DeletionError("Provider token required for external authentication")

            if "APPLE" in providers:
                identity = UnconfiguredAppleIdentityVerifier().verify(password_or_token)
            elif "GOOGLE" in providers:
                identity = UnconfiguredGoogleIdentityVerifier().verify(password_or_token)
            else:
                raise DeletionError("Unsupported authentication provider")

            matched = any(
                i["provider"] in {"APPLE", "GOOGLE"} and i["provider_subject"] == identity.subject
                for i in identities
            )
            if not matched:
                raise DeletionError("Invalid provider token for this user")

    provider_status = "NOT_APPLICABLE"
    if account_kind == AccountKind.AUTHENTICATED.value and (
        "APPLE" in providers or "GOOGLE" in providers
    ):
        provider_status = "PENDING"

    # Create request
    if existing_request is None:
        connection.execute(
            text(
                "INSERT INTO account_deletion_requests "
                "(user_id, pseudonymous_subject_id, deletion_state, "
                "provider_revocation_status, requested_at) "
                "VALUES (:user_id, :subject_id, 'PROCESSING', :provider_status, :now)"
            ),
            {
                "user_id": user.user_id,
                "subject_id": subject_id,
                "provider_status": provider_status,
                "now": executed_at,
            },
        )
    else:
        connection.execute(
            text(
                "UPDATE account_deletion_requests "
                "SET deletion_state = 'PROCESSING', provider_revocation_status = :provider_status "
                "WHERE pseudonymous_subject_id = :subject_id AND deletion_state != 'DELETED'"
            ),
            {
                "subject_id": subject_id,
                "provider_status": provider_status,
            },
        )

    # 3. Session Revocation and Cleanup
    # Nullify self-references first
    connection.execute(
        text("UPDATE auth_sessions SET replaced_by_session_id = NULL WHERE user_id = :user_id"),
        {"user_id": user.user_id},
    )

    connection.execute(
        text("DELETE FROM auth_sessions WHERE user_id = :user_id"),
        {"user_id": user.user_id},
    )

    # 4. Password Resets & Email Verifications Cleanup
    connection.execute(
        text("DELETE FROM auth_password_resets WHERE user_id = :user_id"),
        {"user_id": user.user_id},
    )

    connection.execute(
        text("DELETE FROM auth_email_verifications WHERE user_id = :user_id"),
        {"user_id": user.user_id},
    )

    # 5. Saved Selections
    connection.execute(
        text("DELETE FROM saved_selections WHERE user_id = :user_id"),
        {"user_id": user.user_id},
    )

    # 6. Auth Identity Removal
    connection.execute(
        text("DELETE FROM auth_identities WHERE user_id = :user_id"),
        {"user_id": user.user_id},
    )

    # 7. Final Local Account Removal
    # (commerce_evidence, entitlement_evidence, legal_acceptance are detached by SET NULL FK)
    connection.execute(
        text("DELETE FROM app_users WHERE user_id = :user_id"),
        {"user_id": user.user_id},
    )

    # 8. Mark Deletion Success (or wait for Provider API)
    final_state = "DELETED" if provider_status == "NOT_APPLICABLE" else "PROCESSING"

    connection.execute(
        text(
            "UPDATE account_deletion_requests "
            "SET deletion_state = :state, completed_at = :now, user_id = NULL "
            "WHERE pseudonymous_subject_id = :subject_id"
        ),
        {
            "state": final_state,
            "subject_id": subject_id,
            "now": executed_at if final_state == "DELETED" else None,
        },
    )

    return final_state
