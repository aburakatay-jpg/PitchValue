from typing import Self

import httpx
import pytest

from pitchvalue.config import Settings
from pitchvalue.product_services.email_delivery import ResendEmailVerificationDelivery


def test_resend_delivery_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that delivery fails gracefully when missing config."""
    monkeypatch.setenv("RESEND_API_KEY", "")
    with pytest.raises(RuntimeError, match="RESEND_API_KEY is not configured"):
        delivery = ResendEmailVerificationDelivery()
        delivery.settings = Settings(database_url="postgresql://test", resend_api_key=None)
        delivery.request_verification("test@example.com", "token123")


def test_resend_delivery_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful email delivery payload."""
    delivery = ResendEmailVerificationDelivery()
    delivery.settings = Settings(
        database_url="postgresql://test",
        resend_api_key="re_test123",
        auth_email_from="auth@example.com",
        auth_verification_public_base_url="https://example.com/verify",
    )

    class MockResponse:
        def raise_for_status(self) -> None:
            pass

    class MockClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        def __enter__(self) -> Self:
            return self

        def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
            pass

        def post(self, url: str, headers: dict[str, str], json: dict[str, object]) -> MockResponse:
            assert url == "https://api.resend.com/emails"
            assert headers["Authorization"] == "Bearer re_test123"
            assert json["to"] == ["test@example.com"]
            assert isinstance(json["html"], str)
            assert "https://example.com/verify/token123" in json["html"]
            return MockResponse()

    monkeypatch.setattr("httpx.Client", MockClient)
    delivery.request_verification("test@example.com", "token123")


def test_resend_delivery_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test HTTP errors are translated to RuntimeError."""
    delivery = ResendEmailVerificationDelivery()
    delivery.settings = Settings(
        database_url="postgresql://test",
        resend_api_key="re_test123",
        auth_email_from="auth@example.com",
        auth_verification_public_base_url="https://example.com/verify",
    )

    class MockClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        def __enter__(self) -> Self:
            return self

        def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
            pass

        def post(self, url: str, headers: dict[str, str], json: dict[str, object]) -> None:
            request = httpx.Request("POST", url)
            response = httpx.Response(400, request=request)
            raise httpx.HTTPStatusError("Bad request", request=request, response=response)

    monkeypatch.setattr("httpx.Client", MockClient)
    with pytest.raises(RuntimeError, match="Resend delivery failed with status 400"):
        delivery.request_verification("test@example.com", "token123")
