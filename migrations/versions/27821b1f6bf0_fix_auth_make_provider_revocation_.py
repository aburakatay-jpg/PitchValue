"""fix(auth): make provider revocation credential type explicit

Revision ID: 27821b1f6bf0
Revises: 9d88d704a4b2
Create Date: 2026-09-25 21:20:34.592894
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "27821b1f6bf0"
down_revision: str | None = "9d88d704a4b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_revocation_jobs",
        sa.Column(
            "credential_type", sa.String(), nullable=False, server_default="AUTHORIZATION_CODE"
        ),
    )
    op.alter_column("provider_revocation_jobs", "credential_type", server_default=None)
    op.alter_column(
        "provider_revocation_jobs",
        "provider_token",
        new_column_name="credential_value",
    )
    op.create_check_constraint(
        "provider_revocation_jobs_credential_type_check",
        "provider_revocation_jobs",
        "credential_type IN ('AUTHORIZATION_CODE', 'ACCESS_TOKEN', 'REFRESH_TOKEN', 'IDENTITY_TOKEN', 'UNKNOWN')",
    )


def downgrade() -> None:
    op.drop_constraint("provider_revocation_jobs_credential_type_check", "provider_revocation_jobs")
    op.alter_column(
        "provider_revocation_jobs",
        "credential_value",
        new_column_name="provider_token",
    )
    op.drop_column("provider_revocation_jobs", "credential_type")
