"""feat(auth): add provider revocation jobs

Revision ID: 9d88d704a4b2
Revises: 63eaf92f52f6
Create Date: 2026-09-25 20:25:27.849354
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d88d704a4b2"
down_revision: str | None = "63eaf92f52f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_revocation_jobs",
        sa.Column("job_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_subject", sa.String(), nullable=False),
        sa.Column("provider_token", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
        sa.ForeignKeyConstraint(
            ["request_id"], ["account_deletion_requests.request_id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_provider_revocation_jobs_status",
        "provider_revocation_jobs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_table("provider_revocation_jobs")
