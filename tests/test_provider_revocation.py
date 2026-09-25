from unittest.mock import MagicMock, patch

import pytest

from pitchvalue.product_services.provider_revocation import (
    AppleRevocationAdapter,
    ConfigurationError,
    GoogleRevocationAdapter,
    ProviderRevocationService,
    RetryableError,
)


@pytest.fixture
def mock_connection():
    return MagicMock()


def test_apple_missing_config_fails_closed():
    with patch.dict("os.environ", clear=True):
        adapter = AppleRevocationAdapter()
        with pytest.raises(ConfigurationError):
            adapter.revoke("ACCESS_TOKEN", "token")


def test_google_missing_config_for_auth_code():
    adapter = GoogleRevocationAdapter()
    with pytest.raises(ConfigurationError, match="Google server-side exchange is not supported"):
        adapter.revoke("AUTHORIZATION_CODE", "code")


@patch("pitchvalue.product_services.provider_revocation.requests.post")
def test_apple_exchange_success(mock_post):
    with patch.dict(
        "os.environ",
        {
            "APPLE_CLIENT_ID": "1",
            "APPLE_TEAM_ID": "2",
            "APPLE_KEY_ID": "3",
            "APPLE_PRIVATE_KEY": "4",
        },
    ):
        adapter = AppleRevocationAdapter()

        # Setup mock for exchange then revoke
        mock_resp_exchange = MagicMock()
        mock_resp_exchange.status_code = 200
        mock_resp_exchange.json.return_value = {"access_token": "valid_token"}

        mock_resp_revoke = MagicMock()
        mock_resp_revoke.status_code = 200

        mock_post.side_effect = [mock_resp_exchange, mock_resp_revoke]

        adapter.revoke("AUTHORIZATION_CODE", "code")

        assert mock_post.call_count == 2
        # First call is exchange
        assert mock_post.call_args_list[0][0][0] == "https://appleid.apple.com/auth/token"
        assert mock_post.call_args_list[0][1]["data"]["grant_type"] == "authorization_code"
        assert mock_post.call_args_list[0][1]["data"]["code"] == "code"
        # Second call is revoke
        assert mock_post.call_args_list[1][0][0] == "https://appleid.apple.com/auth/revoke"
        assert mock_post.call_args_list[1][1]["data"]["token"] == "valid_token"
        assert mock_post.call_args_list[1][1]["data"]["token_type_hint"] == "access_token"


@patch("pitchvalue.product_services.provider_revocation.requests.post")
def test_apple_revoke_refresh_token(mock_post):
    with patch.dict(
        "os.environ",
        {
            "APPLE_CLIENT_ID": "1",
            "APPLE_TEAM_ID": "2",
            "APPLE_KEY_ID": "3",
            "APPLE_PRIVATE_KEY": "4",
        },
    ):
        adapter = AppleRevocationAdapter()

        mock_resp_revoke = MagicMock()
        mock_resp_revoke.status_code = 200
        mock_post.return_value = mock_resp_revoke

        adapter.revoke("REFRESH_TOKEN", "rt")

        assert mock_post.call_count == 1
        assert mock_post.call_args_list[0][0][0] == "https://appleid.apple.com/auth/revoke"
        assert mock_post.call_args_list[0][1]["data"]["token"] == "rt"
        assert mock_post.call_args_list[0][1]["data"]["token_type_hint"] == "refresh_token"


@patch("pitchvalue.product_services.provider_revocation.requests.post")
def test_apple_temporary_failure_retryable(mock_post):
    with patch.dict(
        "os.environ",
        {
            "APPLE_CLIENT_ID": "1",
            "APPLE_TEAM_ID": "2",
            "APPLE_KEY_ID": "3",
            "APPLE_PRIVATE_KEY": "4",
        },
    ):
        adapter = AppleRevocationAdapter()

        mock_resp_revoke = MagicMock()
        mock_resp_revoke.status_code = 503
        mock_post.return_value = mock_resp_revoke

        with pytest.raises(RetryableError):
            adapter.revoke("ACCESS_TOKEN", "at")


@patch("pitchvalue.product_services.provider_revocation.requests.post")
def test_google_revoke_access_token(mock_post):
    adapter = GoogleRevocationAdapter()

    mock_resp_revoke = MagicMock()
    mock_resp_revoke.status_code = 200
    mock_post.return_value = mock_resp_revoke

    adapter.revoke("ACCESS_TOKEN", "at")

    assert mock_post.call_count == 1
    assert mock_post.call_args_list[0][0][0] == "https://oauth2.googleapis.com/revoke"
    assert mock_post.call_args_list[0][1]["params"]["token"] == "at"


@patch("pitchvalue.product_services.provider_revocation.requests.post")
def test_google_temporary_failure_retryable(mock_post):
    adapter = GoogleRevocationAdapter()

    mock_resp_revoke = MagicMock()
    mock_resp_revoke.status_code = 500
    mock_post.return_value = mock_resp_revoke

    with pytest.raises(RetryableError):
        adapter.revoke("ACCESS_TOKEN", "at")


def test_job_state_machine_success(mock_connection):
    service = ProviderRevocationService()

    # Mock finding a job
    job = {
        "job_id": 1,
        "request_id": 100,
        "provider": "APPLE",
        "credential_type": "ACCESS_TOKEN",
        "credential_value": "secret",
    }
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [job]

    def execute_mock(stmt, params=None):
        sql = str(stmt).upper()
        if "SELECT JOB_ID" in sql:
            return mock_result
        if "SELECT COUNT(*)" in sql:
            # Simulate no uncompleted jobs
            r = MagicMock()
            r.scalar.return_value = 0
            return r
        return MagicMock()

    mock_connection.execute.side_effect = execute_mock

    with patch(
        "pitchvalue.product_services.provider_revocation.AppleRevocationAdapter.revoke"
    ) as mock_revoke:
        service.process_pending_jobs(mock_connection)
        mock_revoke.assert_called_once_with("ACCESS_TOKEN", "secret")

    # Verify DB updates
    updates = [str(call[0][0]).upper() for call in mock_connection.execute.call_args_list]
    # Check that status was updated to COMPLETED and credential_value NULLed
    assert any("SET STATUS = 'COMPLETED'" in q and "CREDENTIAL_VALUE = NULL" in q for q in updates)
    # Check that account_deletion_requests was finalized
    assert any(
        "SET PROVIDER_REVOCATION_STATUS = 'COMPLETED', DELETION_STATE = 'DELETED'" in q
        for q in updates
    )


def test_job_state_machine_retryable(mock_connection):
    service = ProviderRevocationService()

    job = {
        "job_id": 1,
        "request_id": 100,
        "provider": "APPLE",
        "credential_type": "ACCESS_TOKEN",
        "credential_value": "secret",
    }
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [job]

    mock_connection.execute.return_value = mock_result

    with patch(
        "pitchvalue.product_services.provider_revocation.AppleRevocationAdapter.revoke"
    ) as mock_revoke:
        mock_revoke.side_effect = RetryableError("temp fail")
        service.process_pending_jobs(mock_connection)

    updates = [str(call[0][0]).upper() for call in mock_connection.execute.call_args_list]
    assert any("SET STATUS = 'FAILED_RETRYABLE'" in q for q in updates)


def test_google_auth_code_reclassifies_to_credential_required(mock_connection):
    service = ProviderRevocationService()

    job = {
        "job_id": 1,
        "request_id": 100,
        "provider": "GOOGLE",
        "credential_type": "AUTHORIZATION_CODE",
        "credential_value": "secret",
    }
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [job]

    mock_connection.execute.return_value = mock_result

    service.process_pending_jobs(mock_connection)

    updates = [str(call[0][0]).upper() for call in mock_connection.execute.call_args_list]
    # Should set job status to CREDENTIAL_REQUIRED
    assert any(
        "SET STATUS = 'CREDENTIAL_REQUIRED'" in q and "CREDENTIAL_VALUE = NULL" in q
        for q in updates
    )
    # Should also set request provider_revocation_status to CREDENTIAL_REQUIRED
    assert any("SET PROVIDER_REVOCATION_STATUS = 'CREDENTIAL_REQUIRED'" in q for q in updates)
