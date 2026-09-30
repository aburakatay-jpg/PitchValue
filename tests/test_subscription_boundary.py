from unittest.mock import MagicMock, patch

from pitchvalue.product_services.entitlements import Entitlement, EntitlementState


@patch("pitchvalue.product_services.account_deletion.initiate_account_deletion")
@patch("pitchvalue.product_services.entitlements.resolve_entitlement")
def test_subscription_boundary_active_apple(
    mock_resolve: MagicMock, mock_initiate: MagicMock
) -> None:
    # Simulate an active Apple subscription
    mock_resolve.return_value = Entitlement(
        state=EntitlementState.PREMIUM_ACTIVE,
        source="APPLE",
        product_identifier="com.pitchvalue.monthly",
        starts_at=None,
        ends_at=None,
        trial=False,
    )
    mock_initiate.return_value = "PROCESSING"

    from pitchvalue.api.product_models import AccountDeletionRequest
    from pitchvalue.api.routes.product_services import account_deletion
    from pitchvalue.product_services.auth import AccountKind, ProductUser

    mock_request = AccountDeletionRequest(password_or_token="token")
    mock_user = ProductUser(user_id="123", account_kind=AccountKind.AUTHENTICATED, email=None)
    mock_connection = MagicMock()

    response = account_deletion(mock_request, mock_user, mock_connection)

    assert response.deletion_state == "PROCESSING"
    assert response.has_active_store_subscription is True
    assert response.subscription_provider == "APPLE"


@patch("pitchvalue.product_services.account_deletion.initiate_account_deletion")
@patch("pitchvalue.product_services.entitlements.resolve_entitlement")
def test_subscription_boundary_none(mock_resolve: MagicMock, mock_initiate: MagicMock) -> None:
    # Simulate no subscription
    mock_resolve.return_value = Entitlement(
        state=EntitlementState.PREMIUM_INACTIVE,
        source="NONE",
        product_identifier=None,
        starts_at=None,
        ends_at=None,
        trial=False,
    )
    mock_initiate.return_value = "DELETED"

    from pitchvalue.api.product_models import AccountDeletionRequest
    from pitchvalue.api.routes.product_services import account_deletion
    from pitchvalue.product_services.auth import AccountKind, ProductUser

    mock_request = AccountDeletionRequest(password_or_token="token")
    mock_user = ProductUser(user_id="123", account_kind=AccountKind.AUTHENTICATED, email=None)
    mock_connection = MagicMock()

    response = account_deletion(mock_request, mock_user, mock_connection)

    assert response.deletion_state == "DELETED"
    assert response.has_active_store_subscription is False
    assert response.subscription_provider is None
