import httpx
import pytest

from pitchvalue.config import Settings
from pitchvalue.product_services.email_delivery import ResendEmailVerificationDelivery


def test_resend_delivery_unconfigured(monkeypatch):
    """Test that delivery fails gracefully when missing config."""
    monkeypatch.setenv("RESEND_API_KEY", "")
    with pytest.raises(RuntimeError, match="RESEND_API_KEY is not configured"):
        delivery = ResendEmailVerificationDelivery()
        delivery.settings = Settings(database_url="postgresql://test", resend_api_key=None)
        delivery.request_verification("test@example.com", "token123")


def test_resend_delivery_success(monkeypatch):
    """Test successful email delivery payload."""
    delivery = ResendEmailVerificationDelivery()
    delivery.settings = Settings(
        database_url="postgresql://test",
        resend_api_key="re_test123",
        auth_email_from="auth@example.com",
        auth_verification_public_base_url="https://example.com/verify",
    )

    class MockResponse:
        def raise_for_status(self):
            pass

    class MockClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def post(self, url, headers, json):
            assert url == "https://api.resend.com/emails"
            assert headers["Authorization"] == "Bearer re_test123"
            assert "test@example.com" in json["to"]
            assert "https://example.com/verify/token123" in json["html"]
            return MockResponse()

    monkeypatch.setattr("httpx.Client", MockClient)
    delivery.request_verification("test@example.com", "token123")


def test_resend_delivery_http_error(monkeypatch):
    """Test HTTP errors are translated to RuntimeError."""
    delivery = ResendEmailVerificationDelivery()
    delivery.settings = Settings(
        database_url="postgresql://test",
        resend_api_key="re_test123",
        auth_email_from="auth@example.com",
        auth_verification_public_base_url="https://example.com/verify",
    )

    class MockErrorResponse:
        status_code = 400

    class MockClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def post(self, url, headers, json):
            raise httpx.HTTPStatusError("Bad request", request=None, response=MockErrorResponse())

    monkeypatch.setattr("httpx.Client", MockClient)
    with pytest.raises(RuntimeError, match="Resend delivery failed with status 400"):
        delivery.request_verification("test@example.com", "token123")
