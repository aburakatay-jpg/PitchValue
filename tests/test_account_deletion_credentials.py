from unittest.mock import MagicMock, patch

import pytest

from pitchvalue.product_services.account_deletion import (
    DeletionError,
    initiate_account_deletion,
)
from pitchvalue.product_services.auth import AccountKind, ProductUser


@pytest.fixture
def mock_connection() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_user() -> ProductUser:
    return ProductUser(user_id="user_123", account_kind=AccountKind.AUTHENTICATED, email=None)


def test_missing_credential_sets_credential_required(
    mock_connection: MagicMock, mock_user: ProductUser
) -> None:
    # Setup mock to simulate an external identity (Apple or Google)
    def execute_mock(stmt: object, params: object | None = None) -> MagicMock:
        sql = str(stmt).upper()
        mock_result = MagicMock()
        if "FROM APP_USERS" in sql:
            mock_result.mappings.return_value.one_or_none.return_value = {
                "subject_id": "sub_123",
                "account_kind": "AUTHENTICATED",
            }
        elif "FROM ACCOUNT_DELETION_REQUESTS" in sql and "SELECT DELETION_STATE" in sql:
            mock_result.scalar_one_or_none.return_value = None
        elif "FROM AUTH_IDENTITIES" in sql:
            mock_result.mappings.return_value.all.return_value = [
                {"provider": "APPLE", "provider_subject": "apple_sub_123", "password_hash": ""}
            ]
        elif "INSERT INTO ACCOUNT_DELETION_REQUESTS" in sql:
            mock_result.scalar_one.return_value = 1  # request_id
        elif "FROM PROVIDER_REVOCATION_JOBS" in sql:
            mock_result.scalar_one_or_none.return_value = None
        return mock_result

    mock_connection.execute.side_effect = execute_mock

    with patch(
        "pitchvalue.product_services.account_deletion.UnconfiguredAppleIdentityVerifier"
    ) as verifier:
        verifier().verify.return_value.subject = "apple_sub_123"
        initiate_account_deletion(
            mock_connection, mock_user, password_or_token="fake_id_token", provider_credential=None
        )

    # Verify UPDATE for CREDENTIAL_REQUIRED was called
    update_called = False
    for call in mock_connection.execute.call_args_list:
        stmt = str(call[0][0])
        if "SET provider_revocation_status = 'CREDENTIAL_REQUIRED'" in stmt:
            update_called = True
            break
    assert update_called, "Should set CREDENTIAL_REQUIRED when provider_credential is not provided"


def test_invalid_credential_type_rejected(
    mock_connection: MagicMock, mock_user: ProductUser
) -> None:
    def execute_mock(stmt: object, params: object | None = None) -> MagicMock:
        sql = str(stmt).upper()
        mock_result = MagicMock()
        if "FROM APP_USERS" in sql:
            mock_result.mappings.return_value.one_or_none.return_value = {
                "subject_id": "sub_123",
                "account_kind": "AUTHENTICATED",
            }
        elif "FROM ACCOUNT_DELETION_REQUESTS" in sql and "SELECT DELETION_STATE" in sql:
            mock_result.scalar_one_or_none.return_value = None
        elif "FROM AUTH_IDENTITIES" in sql:
            mock_result.mappings.return_value.all.return_value = [
                {"provider": "APPLE", "provider_subject": "apple_sub_123", "password_hash": ""}
            ]
        elif "INSERT INTO ACCOUNT_DELETION_REQUESTS" in sql:
            mock_result.scalar_one.return_value = 1
        elif "FROM PROVIDER_REVOCATION_JOBS" in sql:
            mock_result.scalar_one_or_none.return_value = None
        return mock_result

    mock_connection.execute.side_effect = execute_mock

    with patch(
        "pitchvalue.product_services.account_deletion.UnconfiguredAppleIdentityVerifier"
    ) as verifier:
        verifier().verify.return_value.subject = "apple_sub_123"
        with pytest.raises(DeletionError, match="Invalid provider revocation credential type"):
            initiate_account_deletion(
                mock_connection,
                mock_user,
                password_or_token="fake_id_token",
                provider_credential={"type": "IDENTITY_TOKEN", "value": "some_token"},
            )


def test_valid_credential_queued(mock_connection: MagicMock, mock_user: ProductUser) -> None:
    def execute_mock(stmt: object, params: object | None = None) -> MagicMock:
        sql = str(stmt).upper()
        mock_result = MagicMock()
        if "FROM APP_USERS" in sql:
            mock_result.mappings.return_value.one_or_none.return_value = {
                "subject_id": "sub_123",
                "account_kind": "AUTHENTICATED",
            }
        elif "FROM ACCOUNT_DELETION_REQUESTS" in sql and "SELECT DELETION_STATE" in sql:
            mock_result.scalar_one_or_none.return_value = None
        elif "FROM AUTH_IDENTITIES" in sql:
            mock_result.mappings.return_value.all.return_value = [
                {"provider": "GOOGLE", "provider_subject": "google_sub_123", "password_hash": ""}
            ]
        elif "INSERT INTO ACCOUNT_DELETION_REQUESTS" in sql:
            mock_result.scalar_one.return_value = 1
        elif "FROM PROVIDER_REVOCATION_JOBS" in sql:
            mock_result.scalar_one_or_none.return_value = None
        return mock_result

    mock_connection.execute.side_effect = execute_mock

    with patch(
        "pitchvalue.product_services.account_deletion.UnconfiguredGoogleIdentityVerifier"
    ) as verifier:
        verifier().verify.return_value.subject = "google_sub_123"
        initiate_account_deletion(
            mock_connection,
            mock_user,
            password_or_token="fake_id_token",
            provider_credential={"type": "ACCESS_TOKEN", "value": "some_access_token"},
        )

    insert_called = False
    for call in mock_connection.execute.call_args_list:
        stmt = str(call[0][0])
        params = (
            call[0][1]
            if len(call[0]) > 1
            else call[1].get("params")
            or call[1].get("parameters")
            or (call[0][1] if len(call[0]) > 1 else call[1])
        )
        if "INSERT INTO provider_revocation_jobs" in stmt:
            if params["cred_type"] == "ACCESS_TOKEN" and params["token"] == "some_access_token":
                insert_called = True
            break
    assert insert_called, (
        "Should insert provider_revocation_jobs with exact provided credential type and value"
    )
