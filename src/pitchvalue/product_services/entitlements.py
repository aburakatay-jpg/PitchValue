"""Server-authoritative entitlement and commerce verification boundaries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from sqlalchemy import Connection, text


class EntitlementState(StrEnum):
    GUEST = "GUEST"
    PREMIUM_ACTIVE = "PREMIUM_ACTIVE"
    PREMIUM_TRIAL = "PREMIUM_TRIAL"
    PREMIUM_EXPIRED = "PREMIUM_EXPIRED"
    PREMIUM_INACTIVE = "PREMIUM_INACTIVE"


class CommerceActivationState(StrEnum):
    CODE_READY = "CODE_READY"
    EXTERNAL_CREDENTIAL_REQUIRED = "EXTERNAL_CREDENTIAL_REQUIRED"


@dataclass(frozen=True)
class Entitlement:
    state: EntitlementState
    source: str
    product_identifier: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    trial: bool


@dataclass(frozen=True)
class CommerceVerificationRequest:
    provider: str
    external_transaction_id: str
    product_identifier: str
    plan: str
    verification_token: str


@dataclass(frozen=True)
class VerifiedCommerceEvidence:
    provider: str
    external_transaction_id: str
    product_identifier: str
    plan: str
    verification_state: str
    purchased_at: datetime | None
    expires_at: datetime | None
    trial_eligible: bool | None
    is_trial: bool
    payload_hash: str


class CommerceVerifier(Protocol):
    def verify(self, request: CommerceVerificationRequest) -> VerifiedCommerceEvidence: ...


class ExternalCommerceVerifier:
    """Fail-closed boundary until an approved store verifier is configured."""

    def verify(self, request: CommerceVerificationRequest) -> VerifiedCommerceEvidence:
        del request
        raise RuntimeError("commerce provider verification requires external activation")


def resolve_entitlement(
    connection: Connection,
    user_id: str,
    *,
    now: datetime | None = None,
) -> Entitlement:
    checked_at = now or datetime.now(UTC)
    row = (
        connection.execute(
            text(
                "SELECT state,source,product_identifier,starts_at,ends_at,trial "
                "FROM entitlement_evidence WHERE user_id=:user_id "
                "ORDER BY reconciled_at DESC,entitlement_evidence_id DESC LIMIT 1"
            ),
            {"user_id": user_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        account_kind = connection.execute(
            text("SELECT account_kind FROM app_users WHERE user_id=:user_id"),
            {"user_id": user_id},
        ).scalar_one_or_none()
        state = (
            EntitlementState.GUEST if account_kind == "GUEST" else EntitlementState.PREMIUM_INACTIVE
        )
        return Entitlement(state, "NONE", None, None, None, False)
    state = EntitlementState(str(row["state"]))
    ends_at = row["ends_at"]
    if (
        state in {EntitlementState.PREMIUM_ACTIVE, EntitlementState.PREMIUM_TRIAL}
        and ends_at is not None
        and ends_at <= checked_at
    ):
        state = EntitlementState.PREMIUM_EXPIRED
    return Entitlement(
        state,
        str(row["source"]),
        None if row["product_identifier"] is None else str(row["product_identifier"]),
        row["starts_at"],
        ends_at,
        bool(row["trial"]),
    )


def reconcile_verified_purchase(
    connection: Connection,
    user_id: str,
    evidence: VerifiedCommerceEvidence,
    *,
    now: datetime | None = None,
) -> bool:
    """Persist verified evidence idempotently; never trusts client premium flags."""
    received_at = now or datetime.now(UTC)
    inserted = connection.execute(
        text(
            "INSERT INTO commerce_evidence "
            "(user_id,provider,external_transaction_id,product_identifier,plan,"
            "verification_state,purchased_at,expires_at,trial_eligible,is_trial,received_at,"
            "verified_at,payload_hash) VALUES "
            "(:user_id,:provider,:external_transaction_id,:product_identifier,:plan,"
            ":verification_state,:purchased_at,:expires_at,:trial_eligible,:is_trial,:received_at,"
            ":received_at,:payload_hash) ON CONFLICT (provider,external_transaction_id) "
            "DO NOTHING RETURNING commerce_evidence_id"
        ),
        {"user_id": user_id, "received_at": received_at, **evidence.__dict__},
    ).scalar_one_or_none()
    if inserted is None:
        return False
    state = _state_for(evidence, received_at)
    external_reference = f"{evidence.provider}:{evidence.external_transaction_id}"
    entitlement_hash = _hash(
        {
            "user_id": user_id,
            "external_reference": external_reference,
            "state": state.value,
            "payload_hash": evidence.payload_hash,
        }
    )
    connection.execute(
        text(
            "INSERT INTO entitlement_evidence "
            "(user_id,state,source,product_identifier,external_reference,starts_at,ends_at,"
            "trial,auto_renewing,reconciled_at,payload_hash) VALUES "
            "(:user_id,:state,:source,:product_identifier,:external_reference,:starts_at,"
            ":ends_at,:trial,NULL,:reconciled_at,:payload_hash)"
        ),
        {
            "user_id": user_id,
            "state": state.value,
            "source": evidence.provider,
            "product_identifier": evidence.product_identifier,
            "external_reference": external_reference,
            "starts_at": evidence.purchased_at or received_at,
            "ends_at": evidence.expires_at,
            "trial": state is EntitlementState.PREMIUM_TRIAL,
            "reconciled_at": received_at,
            "payload_hash": entitlement_hash,
        },
    )
    return True


def _state_for(evidence: VerifiedCommerceEvidence, now: datetime) -> EntitlementState:
    if evidence.verification_state == "VERIFIED":
        if evidence.expires_at is not None and evidence.expires_at <= now:
            return EntitlementState.PREMIUM_EXPIRED
        return (
            EntitlementState.PREMIUM_TRIAL if evidence.is_trial else EntitlementState.PREMIUM_ACTIVE
        )
    if evidence.verification_state == "EXPIRED":
        return EntitlementState.PREMIUM_EXPIRED
    return EntitlementState.PREMIUM_INACTIVE


def _hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
