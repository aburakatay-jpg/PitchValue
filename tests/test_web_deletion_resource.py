"""Tests for the external account deletion web resource."""

import pytest
from fastapi.testclient import TestClient

from pitchvalue.api.app import create_app
from pitchvalue.config import Settings


@pytest.fixture
def client() -> TestClient:
    app = create_app(Settings(_env_file=None, database_url="sqlite+pysqlite:///:memory:"))
    return TestClient(app)


def test_web_deletion_resource_accessible(client: TestClient) -> None:
    """The resource must be public and identify PitchValue."""
    response = client.get("/account/delete")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    content = response.text

    assert "PitchValue Account Deletion" in content
    assert "Sign In" in content


def test_web_deletion_resource_requires_auth(client: TestClient) -> None:
    """The resource must use the backend auth lifecycle."""
    content = client.get("/account/delete").text
    # JavaScript should authenticate via the backend.
    assert "fetch('/api/v1/auth/email/login'" in content


def test_web_deletion_resource_uses_backend_deletion(client: TestClient) -> None:
    """The resource must reuse the backend account deletion service."""
    content = client.get("/account/delete").text
    assert "fetch('/api/v1/auth/account-deletion'" in content

    # Must explicitly require a confirmation password/token.
    assert "password_or_token:" in content

    # Must not fake provider credentials if unavailable in web.
    assert "provider_credential: null" in content


def test_web_deletion_resource_subscription_warning(client: TestClient) -> None:
    """The resource must show the canonical subscription warning."""
    content = client.get("/account/delete").text
    assert "does not automatically cancel an App Store or Google Play subscription" in content
