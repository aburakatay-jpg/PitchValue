from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock

from sqlalchemy import Connection

from pitchvalue.api.app import create_app
from pitchvalue.config import Settings
from pitchvalue.operations.release_validation import (
    ProductServiceReadinessState,
    validate_product_service_readiness,
)


def test_release_validation_can_be_imported_before_api_application() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pitchvalue.operations.release_validation import "
            "validate_product_service_readiness",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_product_service_openapi_exposes_only_intended_methods() -> None:
    app = create_app(
        Settings(database_url="postgresql+psycopg://local/test"), lambda _: MagicMock()
    )
    paths = app.openapi()["paths"]
    expected = {
        "/api/v1/auth/guest": {"post"},
        "/api/v1/auth/email/register": {"post"},
        "/api/v1/auth/email/login": {"post"},
        "/api/v1/auth/email/password-reset": {"post"},
        "/api/v1/auth/external/{provider}": {"post"},
        "/api/v1/auth/refresh": {"post"},
        "/api/v1/auth/logout": {"post"},
        "/api/v1/me": {"get"},
        "/api/v1/me/entitlement": {"get"},
        "/api/v1/commerce/catalog": {"get"},
        "/api/v1/commerce/verify": {"post"},
        "/api/v1/commerce/restore": {"post"},
        "/api/v1/me/bets": {"get", "post"},
        "/api/v1/me/bets/performance": {"get"},
        "/api/v1/me/bets/{saved_selection_id}": {"get", "delete"},
        "/api/v1/ai/best-value": {"get"},
        "/api/v1/ai/explain": {"post"},
        "/api/v1/ai/ask": {"post"},
        "/api/v1/coupon-builder": {"post"},
        "/api/v1/product-services/readiness": {"get"},
    }
    for path, methods in expected.items():
        assert path in paths
        assert set(paths[path]) == methods


def test_authorized_routes_declare_bearer_security() -> None:
    app = create_app(
        Settings(database_url="postgresql+psycopg://local/test"), lambda _: MagicMock()
    )
    paths = app.openapi()["paths"]
    for path in ("/api/v1/me", "/api/v1/me/bets", "/api/v1/ai/explain"):
        operation = paths[path]["get" if path != "/api/v1/ai/explain" else "post"]
        assert operation["security"] == [{"HTTPBearer": []}]


def test_release_readiness_distinguishes_code_and_external_activation() -> None:
    connection = MagicMock(spec=Connection)
    result = MagicMock()
    result.scalar_one.return_value = "table"
    connection.execute.return_value = result
    readiness = validate_product_service_readiness(connection)
    assert readiness.AUTH_READY is ProductServiceReadinessState.CODE_READY
    assert readiness.ENTITLEMENT_READY is ProductServiceReadinessState.CODE_READY
    assert readiness.MY_BETS_READY is ProductServiceReadinessState.CODE_READY
    assert (
        readiness.COMMERCE_ACTIVATION_READY
        is ProductServiceReadinessState.EXTERNAL_CREDENTIAL_REQUIRED
    )
    assert readiness.AI_CONTRACT_READY is ProductServiceReadinessState.EXTERNAL_CREDENTIAL_REQUIRED
    assert (
        readiness.COUPON_BUILDER_READY
        is ProductServiceReadinessState.PRODUCTION_ACTIVATION_REQUIRED
    )


def test_release_readiness_blocks_when_product_schema_is_missing() -> None:
    connection = MagicMock(spec=Connection)
    result = MagicMock()
    result.scalar_one.return_value = None
    connection.execute.return_value = result
    readiness = validate_product_service_readiness(connection)
    assert readiness.AUTH_READY is ProductServiceReadinessState.BLOCKED
    assert readiness.MY_BETS_READY is ProductServiceReadinessState.BLOCKED
    assert len(readiness.missing_tables) == 6
