"""Secure opaque sessions and provider-neutral product identities."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from sqlalchemy import Connection, text

ACCESS_TTL = timedelta(minutes=30)
REFRESH_TTL = timedelta(days=30)
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1

_COUNTRIES_PATH = Path(__file__).parent.parent / "data" / "countries.json"
with open(_COUNTRIES_PATH) as f:
    VALID_COUNTRIES = frozenset(json.load(f))


class AuthError(ValueError):
    """Expected authentication failure without sensitive detail."""


class AccountKind(StrEnum):
    GUEST = "GUEST"
    AUTHENTICATED = "AUTHENTICATED"


@dataclass(frozen=True)
class ProductUser:
    user_id: str
    account_kind: AccountKind
    email: str | None


@dataclass(frozen=True)
class IssuedSession:
    user: ProductUser
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime


@dataclass(frozen=True)
class VerifiedExternalIdentity:
    provider: str
    subject: str
    email: str | None


class ExternalIdentityVerifier(Protocol):
    """Boundary implemented by an approved Apple or Google verifier."""

    def verify(self, provider_token: str) -> VerifiedExternalIdentity: ...


class PasswordResetDelivery(Protocol):
    """Boundary implemented by an approved email delivery provider."""

    def request_reset(self, normalized_email: str, raw_token: str) -> None: ...


class EmailVerificationDelivery(Protocol):
    """Boundary implemented by an approved email delivery provider."""

    def request_verification(self, normalized_email: str, raw_token: str) -> None: ...


class UnconfiguredAppleIdentityVerifier:
    def verify(self, provider_token: str) -> VerifiedExternalIdentity:
        del provider_token
        raise RuntimeError("Apple identity provider requires external credentials")


class UnconfiguredGoogleIdentityVerifier:
    def verify(self, provider_token: str) -> VerifiedExternalIdentity:
        del provider_token
        raise RuntimeError("Google identity provider requires external credentials")


class UnconfiguredPasswordResetDelivery:
    """Fail closed without revealing whether an email identity exists."""

    def request_reset(self, normalized_email: str, raw_token: str) -> None:
        del normalized_email, raw_token
        raise RuntimeError("password reset delivery requires external activation")


class UnconfiguredEmailVerificationDelivery:
    """Fail closed without revealing whether an email identity exists."""

    def request_verification(self, normalized_email: str, raw_token: str) -> None:
        del normalized_email, raw_token
        raise RuntimeError("email verification delivery requires external activation")


def normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized or "@" not in normalized or normalized.startswith("@"):
        raise AuthError("invalid email")
    local, domain = normalized.rsplit("@", 1)
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise AuthError("invalid email")
    return normalized


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if len(password) < 8 or len(password) > 1024:
        raise AuthError("password does not meet length requirements")
    if not any(c.isupper() for c in password):
        raise AuthError("password must contain an uppercase letter")
    if not any(c.islower() for c in password):
        raise AuthError("password must contain a lowercase letter")
    if not any(c.isdigit() for c in password):
        raise AuthError("password must contain a number")
    actual_salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=actual_salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
    )
    return "$".join(
        (
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.urlsafe_b64encode(actual_salt).decode("ascii"),
            base64.urlsafe_b64encode(derived).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_value, expected_value = encoded.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
        expected = base64.urlsafe_b64decode(expected_value.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def create_guest_session(connection: Connection, *, now: datetime | None = None) -> IssuedSession:
    issued_at = _now(now)
    user_id = str(uuid.uuid4())
    connection.execute(
        text(
            "INSERT INTO app_users (user_id,account_kind,created_at,updated_at) "
            "VALUES (:user_id,'GUEST',:now,:now)"
        ),
        {"user_id": user_id, "now": issued_at},
    )
    connection.execute(
        text(
            "INSERT INTO auth_identities "
            "(user_id,provider,provider_subject,created_at,last_verified_at) "
            "VALUES (:user_id,'GUEST',:subject,:now,:now)"
        ),
        {"user_id": user_id, "subject": secrets.token_urlsafe(24), "now": issued_at},
    )
    return _issue_session(connection, ProductUser(user_id, AccountKind.GUEST, None), issued_at)


def register_email(
    connection: Connection,
    email: str,
    password: str,
    country_code: str,
    now: datetime | None = None,
) -> tuple[IssuedSession, str]:
    issued_at = _now(now)
    normalized = normalize_email(email)

    country_code = country_code.strip().upper()
    if country_code not in VALID_COUNTRIES:
        raise AuthError("invalid country code")

    if password.casefold() == normalized:
        raise AuthError("password cannot be the same as email")
    password_hash = hash_password(password)
    user_id = str(uuid.uuid4())
    existing = connection.execute(
        text("SELECT 1 FROM auth_identities WHERE normalized_email=:email"),
        {"email": normalized},
    ).scalar_one_or_none()
    if existing is not None:
        raise AuthError("email identity already exists")
    connection.execute(
        text(
            "INSERT INTO app_users "
            "(user_id,account_kind,created_at,updated_at,country_code,age_18_acknowledged_at) "
            "VALUES (:user_id,'AUTHENTICATED',:now,:now,:country_code,:now)"
        ),
        {"user_id": user_id, "now": issued_at, "country_code": country_code},
    )
    connection.execute(
        text(
            "INSERT INTO auth_identities "
            "(user_id,provider,provider_subject,normalized_email,password_hash,"
            "created_at,last_verified_at) VALUES "
            "(:user_id,'EMAIL',:email,:email,:password_hash,:now,NULL)"
        ),
        {
            "user_id": user_id,
            "email": normalized,
            "password_hash": password_hash,
            "now": issued_at,
        },
    )

    raw_token = secrets.token_urlsafe(32)
    expires_at = issued_at + timedelta(days=1)
    connection.execute(
        text(
            "INSERT INTO auth_email_verifications (token_hash, user_id, expires_at) "
            "VALUES (:hash, :user_id, :expires)"
        ),
        {"hash": _token_hash(raw_token), "user_id": user_id, "expires": expires_at},
    )

    from pitchvalue.product_services.email_delivery import ResendEmailVerificationDelivery

    delivery_state = "VERIFICATION_EMAIL_SENT"
    try:
        ResendEmailVerificationDelivery().request_verification(normalized, raw_token)
    except RuntimeError:
        delivery_state = "VERIFICATION_DELIVERY_UNAVAILABLE"

    return _issue_session(
        connection,
        ProductUser(user_id, AccountKind.AUTHENTICATED, normalized),
        issued_at,
    ), delivery_state


def login_email(
    connection: Connection,
    email: str,
    password: str,
    *,
    now: datetime | None = None,
) -> IssuedSession:
    issued_at = _now(now)
    normalized = normalize_email(email)
    row = (
        connection.execute(
            text(
                "SELECT u.user_id,u.account_kind,i.password_hash FROM auth_identities i "
                "JOIN app_users u ON u.user_id=i.user_id "
                "WHERE i.provider='EMAIL' AND i.normalized_email=:email AND u.status='ACTIVE'"
            ),
            {"email": normalized},
        )
        .mappings()
        .one_or_none()
    )
    if row is None or not verify_password(password, str(row["password_hash"])):
        raise AuthError("invalid credentials")
    return _issue_session(
        connection,
        ProductUser(str(row["user_id"]), AccountKind(str(row["account_kind"])), normalized),
        issued_at,
    )


def authenticate_access_token(
    connection: Connection,
    token: str,
    *,
    now: datetime | None = None,
) -> ProductUser | None:
    checked_at = _now(now)
    row = (
        connection.execute(
            text(
                "SELECT u.user_id,u.account_kind,(SELECT i.normalized_email FROM auth_identities i "
                "WHERE i.user_id=u.user_id AND i.provider='EMAIL' LIMIT 1) AS normalized_email "
                "FROM auth_sessions s "
                "JOIN app_users u ON u.user_id=s.user_id "
                "WHERE s.access_token_hash=:token_hash AND s.revoked_at IS NULL "
                "AND s.access_expires_at>:now AND u.status='ACTIVE'"
            ),
            {"token_hash": _token_hash(token), "now": checked_at},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    email = None if row["normalized_email"] is None else str(row["normalized_email"])
    return ProductUser(str(row["user_id"]), AccountKind(str(row["account_kind"])), email)


def refresh_session(
    connection: Connection,
    refresh_token: str,
    *,
    now: datetime | None = None,
) -> IssuedSession:
    issued_at = _now(now)
    row = (
        connection.execute(
            text(
                "SELECT s.session_id,u.user_id,u.account_kind,"
                "(SELECT i.normalized_email FROM auth_identities i WHERE i.user_id=u.user_id "
                "AND i.provider='EMAIL' LIMIT 1) AS normalized_email "
                "FROM auth_sessions s JOIN app_users u ON u.user_id=s.user_id "
                "WHERE s.refresh_token_hash=:token_hash AND s.revoked_at IS NULL "
                "AND s.refresh_expires_at>:now AND u.status='ACTIVE'"
            ),
            {"token_hash": _token_hash(refresh_token), "now": issued_at},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise AuthError("refresh token is invalid or expired")
    email = None if row["normalized_email"] is None else str(row["normalized_email"])
    user = ProductUser(str(row["user_id"]), AccountKind(str(row["account_kind"])), email)
    session = _issue_session(connection, user, issued_at)
    connection.execute(
        text(
            "UPDATE auth_sessions SET revoked_at=:now,replaced_by_session_id=:replacement "
            "WHERE session_id=:session_id AND revoked_at IS NULL"
        ),
        {
            "now": issued_at,
            "replacement": _session_id_for_refresh(connection, session.refresh_token),
            "session_id": str(row["session_id"]),
        },
    )
    return session


def logout(connection: Connection, access_token: str, *, now: datetime | None = None) -> bool:
    result = connection.execute(
        text(
            "UPDATE auth_sessions SET revoked_at=:now "
            "WHERE access_token_hash=:token_hash AND revoked_at IS NULL"
        ),
        {"now": _now(now), "token_hash": _token_hash(access_token)},
    )
    return bool(result.rowcount)


def _issue_session(connection: Connection, user: ProductUser, issued_at: datetime) -> IssuedSession:
    session_id = str(uuid.uuid4())
    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(48)
    access_expires_at = issued_at + ACCESS_TTL
    refresh_expires_at = issued_at + REFRESH_TTL
    connection.execute(
        text(
            "INSERT INTO auth_sessions "
            "(session_id,user_id,access_token_hash,refresh_token_hash,issued_at,"
            "access_expires_at,refresh_expires_at) VALUES "
            "(:session_id,:user_id,:access_hash,:refresh_hash,:issued_at,"
            ":access_expires,:refresh_expires)"
        ),
        {
            "session_id": session_id,
            "user_id": user.user_id,
            "access_hash": _token_hash(access_token),
            "refresh_hash": _token_hash(refresh_token),
            "issued_at": issued_at,
            "access_expires": access_expires_at,
            "refresh_expires": refresh_expires_at,
        },
    )
    return IssuedSession(user, access_token, refresh_token, access_expires_at, refresh_expires_at)


def _session_id_for_refresh(connection: Connection, refresh_token: str) -> str:
    value = connection.execute(
        text("SELECT session_id FROM auth_sessions WHERE refresh_token_hash=:token_hash"),
        {"token_hash": _token_hash(refresh_token)},
    ).scalar_one()
    return str(value)


def _token_hash(value: str) -> str:
    if not value:
        raise AuthError("token is required")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise AuthError("time must be timezone-aware")
    return result


def authenticate_external(
    connection: Connection,
    provider: str,
    subject: str,
    email: str | None,
    *,
    now: datetime | None = None,
) -> IssuedSession:
    issued_at = _now(now)
    normalized = normalize_email(email) if email else None

    row = (
        connection.execute(
            text(
                "SELECT u.user_id, u.account_kind, i.normalized_email FROM auth_identities i "
                "JOIN app_users u ON u.user_id=i.user_id "
                "WHERE i.provider=:provider AND i.provider_subject=:subject"
            ),
            {"provider": provider, "subject": subject},
        )
        .mappings()
        .one_or_none()
    )

    if row is not None:
        return _issue_session(
            connection,
            ProductUser(
                str(row["user_id"]),
                AccountKind(str(row["account_kind"])),
                str(row["normalized_email"]) if row["normalized_email"] else None,
            ),
            issued_at,
        )

    if normalized:
        collision = connection.execute(
            text("SELECT 1 FROM auth_identities WHERE normalized_email=:email"),
            {"email": normalized},
        ).scalar_one_or_none()
        if collision:
            raise AuthError("EMAIL_IDENTITY_COLLISION")

    user_id = str(uuid.uuid4())
    connection.execute(
        text(
            "INSERT INTO app_users (user_id,account_kind,created_at,updated_at) "
            "VALUES (:user_id,'AUTHENTICATED',:now,:now)"
        ),
        {"user_id": user_id, "now": issued_at},
    )
    connection.execute(
        text(
            "INSERT INTO auth_identities "
            "(user_id,provider,provider_subject,normalized_email,"
            "created_at,last_verified_at) VALUES "
            "(:user_id,:provider,:subject,:email,:now,:now)"
        ),
        {
            "user_id": user_id,
            "provider": provider,
            "subject": subject,
            "email": normalized,
            "now": issued_at,
        },
    )
    return _issue_session(
        connection,
        ProductUser(user_id, AccountKind.AUTHENTICATED, normalized),
        issued_at,
    )


def request_password_reset(
    connection: Connection,
    email: str,
    *,
    now: datetime | None = None,
) -> str | None:
    issued_at = _now(now)
    normalized = normalize_email(email)

    user_id = connection.execute(
        text(
            "SELECT user_id FROM auth_identities WHERE provider='EMAIL' AND normalized_email=:email"
        ),
        {"email": normalized},
    ).scalar_one_or_none()

    if user_id is None:
        return None

    raw_token = secrets.token_urlsafe(32)
    expires_at = issued_at + timedelta(hours=1)

    connection.execute(
        text(
            "INSERT INTO auth_password_resets (token_hash, user_id, expires_at) "
            "VALUES (:hash, :user_id, :expires)"
        ),
        {"hash": _token_hash(raw_token), "user_id": str(user_id), "expires": expires_at},
    )
    return raw_token


def confirm_password_reset(
    connection: Connection,
    raw_token: str,
    new_password: str,
    *,
    now: datetime | None = None,
) -> None:
    checked_at = _now(now)
    token_hash = _token_hash(raw_token)

    row = connection.execute(
        text(
            "SELECT user_id FROM auth_password_resets "
            "WHERE token_hash=:hash AND used_at IS NULL AND expires_at > :now"
        ),
        {"hash": token_hash, "now": checked_at},
    ).scalar_one_or_none()

    if row is None:
        raise AuthError("Invalid or expired reset token")

    user_id = str(row)
    password_hash = hash_password(new_password)

    connection.execute(
        text("UPDATE auth_password_resets SET used_at=:now WHERE token_hash=:hash"),
        {"now": checked_at, "hash": token_hash},
    )

    connection.execute(
        text(
            "UPDATE auth_identities SET password_hash=:password_hash "
            "WHERE user_id=:user_id AND provider='EMAIL'"
        ),
        {"password_hash": password_hash, "user_id": user_id},
    )

    connection.execute(
        text(
            "UPDATE auth_sessions SET revoked_at=:now WHERE user_id=:user_id AND revoked_at IS NULL"
        ),
        {"now": checked_at, "user_id": user_id},
    )


def confirm_email_verification(
    connection: Connection,
    raw_token: str,
    *,
    now: datetime | None = None,
) -> None:
    checked_at = _now(now)
    token_hash = _token_hash(raw_token)

    row = connection.execute(
        text(
            "SELECT user_id FROM auth_email_verifications "
            "WHERE token_hash=:hash AND used_at IS NULL AND expires_at > :now"
        ),
        {"hash": token_hash, "now": checked_at},
    ).scalar_one_or_none()

    if row is None:
        raise AuthError("Invalid or expired verification token")

    user_id = str(row)

    connection.execute(
        text("UPDATE auth_email_verifications SET used_at=:now WHERE token_hash=:hash"),
        {"now": checked_at, "hash": token_hash},
    )

    connection.execute(
        text(
            "UPDATE auth_identities SET last_verified_at=:now "
            "WHERE user_id=:user_id AND provider='EMAIL'"
        ),
        {"now": checked_at, "user_id": user_id},
    )
