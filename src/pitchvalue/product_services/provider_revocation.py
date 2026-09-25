import logging
import os
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import requests
from sqlalchemy import Connection, text

from pitchvalue.product_services.auth import _now

logger = logging.getLogger(__name__)


class ConfigurationError(RuntimeError):
    pass


class RetryableError(RuntimeError):
    pass


class PermanentError(RuntimeError):
    pass


class AppleRevocationAdapter:
    def _get_client_secret(self) -> str:
        client_id = os.environ.get("APPLE_CLIENT_ID")
        team_id = os.environ.get("APPLE_TEAM_ID")
        key_id = os.environ.get("APPLE_KEY_ID")
        private_key = os.environ.get("APPLE_PRIVATE_KEY")

        if not (client_id and team_id and key_id and private_key):
            raise ConfigurationError("Apple configuration is missing")

        # Dynamically generate JWT client secret here
        return "mock_jwt_secret"

    def revoke(self, credential_type: str, credential_value: str) -> None:
        client_secret = self._get_client_secret()
        client_id = os.environ.get("APPLE_CLIENT_ID", "")

        if credential_type == "AUTHORIZATION_CODE":
            self._exchange_and_revoke(client_id, client_secret, credential_value)
        elif credential_type in {"ACCESS_TOKEN", "REFRESH_TOKEN"}:
            self._revoke_token(client_id, client_secret, credential_value, credential_type)
        else:
            raise PermanentError(f"Unsupported credential type for Apple: {credential_type}")

    def _exchange_and_revoke(self, client_id: str, client_secret: str, code: str) -> None:
        try:
            resp = requests.post(
                "https://appleid.apple.com/auth/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                logger.error("Apple exchange failed: %s", resp.text)
                if resp.status_code >= 500:
                    raise RetryableError("Apple server error during exchange")
                raise PermanentError("Apple exchange failed permanently")

            data = resp.json()
            access_token = data.get("access_token")
            if access_token:
                self._revoke_token(client_id, client_secret, access_token, "ACCESS_TOKEN")
        except requests.RequestException as e:
            raise RetryableError(f"Network error: {e}") from e

    def _revoke_token(
        self, client_id: str, client_secret: str, token: str, token_type: str
    ) -> None:
        token_type_hint = "access_token" if token_type == "ACCESS_TOKEN" else "refresh_token"
        try:
            resp = requests.post(
                "https://appleid.apple.com/auth/revoke",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "token": token,
                    "token_type_hint": token_type_hint,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                logger.error("Apple revoke failed: %s", resp.text)
                if resp.status_code >= 500:
                    raise RetryableError("Apple server error during revoke")
                raise PermanentError("Apple revoke failed permanently")
        except requests.RequestException as e:
            raise RetryableError(f"Network error: {e}") from e


class GoogleRevocationAdapter:
    def revoke(self, credential_type: str, credential_value: str) -> None:
        if credential_type == "AUTHORIZATION_CODE":
            # Current architecture does not support server-side exchange for Google
            raise ConfigurationError("Google server-side exchange is not supported")

        if credential_type in {"ACCESS_TOKEN", "REFRESH_TOKEN"}:
            self._revoke_token(credential_value)
        else:
            raise PermanentError(f"Unsupported credential type for Google: {credential_type}")

    def _revoke_token(self, token: str) -> None:
        try:
            resp = requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            if resp.status_code != 200:
                logger.error("Google revoke failed: %s", resp.text)
                if resp.status_code >= 500:
                    raise RetryableError("Google server error during revoke")
                raise PermanentError("Google revoke failed permanently")
        except requests.RequestException as e:
            raise RetryableError(f"Network error: {e}") from e


class ProviderRevocationService:
    def process_pending_jobs(self, connection: Connection, *, now: datetime | None = None) -> None:
        executed_at = _now(now)

        # Find PENDING or FAILED_RETRYABLE jobs
        jobs = (
            connection.execute(
                text(
                    "SELECT job_id, request_id, provider, credential_type, credential_value "
                    "FROM provider_revocation_jobs "
                    "WHERE status IN ('PENDING', 'FAILED_RETRYABLE') "
                    "FOR UPDATE SKIP LOCKED"
                )
            )
            .mappings()
            .all()
        )

        for job in jobs:
            try:
                self._process_job(connection, dict(job), executed_at)
            except Exception:
                logger.exception("Unexpected error processing revocation job %s", job["job_id"])

    def _process_job(
        self, connection: Connection, job: Mapping[str, Any], executed_at: datetime
    ) -> None:
        connection.execute(
            text(
                "UPDATE provider_revocation_jobs SET status = 'PROCESSING', "
                "attempted_at = :now WHERE job_id = :job_id"
            ),
            {"now": executed_at, "job_id": job["job_id"]},
        )

        try:
            if job["provider"] == "APPLE":
                apple_adapter = AppleRevocationAdapter()
                apple_adapter.revoke(job["credential_type"], job["credential_value"])
            elif job["provider"] == "GOOGLE":
                google_adapter = GoogleRevocationAdapter()
                google_adapter.revoke(job["credential_type"], job["credential_value"])
            else:
                raise PermanentError(f"Unsupported provider: {job['provider']}")

            # Success
            connection.execute(
                text(
                    "UPDATE provider_revocation_jobs "
                    "SET status = 'COMPLETED', completed_at = :now, credential_value = NULL "
                    "WHERE job_id = :job_id"
                ),
                {"now": executed_at, "job_id": job["job_id"]},
            )
            self._check_and_finalize_request(connection, job["request_id"], executed_at)

        except ConfigurationError:
            # Reclassify as configuration blocked or credential required if auth code for google
            if job["provider"] == "GOOGLE" and job["credential_type"] == "AUTHORIZATION_CODE":
                connection.execute(
                    text(
                        "UPDATE provider_revocation_jobs "
                        "SET status = 'CREDENTIAL_REQUIRED', credential_value = NULL "
                        "WHERE job_id = :job_id"
                    ),
                    {"job_id": job["job_id"]},
                )
                connection.execute(
                    text(
                        "UPDATE account_deletion_requests "
                        "SET provider_revocation_status = 'CREDENTIAL_REQUIRED' "
                        "WHERE request_id = :request_id"
                    ),
                    {"request_id": job["request_id"]},
                )
            else:
                connection.execute(
                    text(
                        "UPDATE provider_revocation_jobs SET status = 'CONFIGURATION_REQUIRED' "
                        "WHERE job_id = :job_id"
                    ),
                    {"job_id": job["job_id"]},
                )
        except RetryableError:
            connection.execute(
                text(
                    "UPDATE provider_revocation_jobs SET status = 'FAILED_RETRYABLE' "
                    "WHERE job_id = :job_id"
                ),
                {"job_id": job["job_id"]},
            )
        except PermanentError:
            connection.execute(
                text(
                    "UPDATE provider_revocation_jobs "
                    "SET status = 'COMPLETED', completed_at = :now, credential_value = NULL "
                    "WHERE job_id = :job_id"
                ),
                {"now": executed_at, "job_id": job["job_id"]},
            )
            self._check_and_finalize_request(connection, job["request_id"], executed_at)

    def _check_and_finalize_request(
        self, connection: Connection, request_id: int, executed_at: datetime
    ) -> None:
        # Check if all jobs for this request are completed
        uncompleted = connection.execute(
            text(
                "SELECT count(*) FROM provider_revocation_jobs "
                "WHERE request_id = :request_id AND status != 'COMPLETED' "
                "AND status != 'CREDENTIAL_REQUIRED'"
            ),
            {"request_id": request_id},
        ).scalar()

        if uncompleted == 0:
            connection.execute(
                text(
                    "UPDATE account_deletion_requests "
                    "SET provider_revocation_status = 'COMPLETED', deletion_state = 'DELETED', "
                    "completed_at = :now "
                    "WHERE request_id = :request_id AND "
                    "provider_revocation_status != 'CREDENTIAL_REQUIRED'"
                ),
                {"now": executed_at, "request_id": request_id},
            )
