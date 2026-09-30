"""feat(auth): add CREDENTIAL_REQUIRED to provider_revocation_status

Revision ID: 4633ed520904
Revises: 27821b1f6bf0
Create Date: 2026-09-25 21:38:28.755805
"""

from collections.abc import Sequence

from alembic import op

revision: str = "4633ed520904"
down_revision: str | None = "27821b1f6bf0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE account_deletion_requests DROP CONSTRAINT "
        "account_deletion_requests_provider_status_check"
    )
    op.create_check_constraint(
        "account_deletion_requests_provider_status_check",
        "account_deletion_requests",
        "provider_revocation_status IN ('NOT_APPLICABLE', 'PENDING', 'COMPLETED', "
        "'FAILED_RETRYABLE', 'CREDENTIAL_REQUIRED')",
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE account_deletion_requests DROP CONSTRAINT "
        "account_deletion_requests_provider_status_check"
    )
    op.create_check_constraint(
        "account_deletion_requests_provider_status_check",
        "account_deletion_requests",
        "provider_revocation_status IN ('NOT_APPLICABLE', 'PENDING', 'COMPLETED', "
        "'FAILED_RETRYABLE')",
    )
