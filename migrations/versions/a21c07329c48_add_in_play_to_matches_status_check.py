"""Add IN_PLAY to matches_status_check

Revision ID: a21c07329c48
Revises: 754c63cfcf58
Create Date: 2026-09-20 19:03:04.904360
"""

from collections.abc import Sequence

from alembic import op

revision: str = 'a21c07329c48'
down_revision: str | None = '754c63cfcf58'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop existing constraint
    op.drop_constraint("matches_status_check", "matches", type_="check")
    # Recreate constraint with IN_PLAY
    op.create_check_constraint(
        "matches_status_check",
        "matches",
        "status IN ('SCHEDULED', 'IN_PLAY', 'FINISHED', 'AWARDED', 'ABANDONED', 'POSTPONED', 'CANCELLED')",
    )


def downgrade() -> None:
    # Drop constraint with IN_PLAY
    op.drop_constraint("matches_status_check", "matches", type_="check")
    # Recreate original constraint
    op.create_check_constraint(
        "matches_status_check",
        "matches",
        "status IN ('SCHEDULED', 'FINISHED', 'AWARDED', 'ABANDONED', 'POSTPONED', 'CANCELLED')",
    )

