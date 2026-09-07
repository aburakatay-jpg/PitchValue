"""Establish an empty migration baseline.

Revision ID: 20260907_0001
Revises:
Create Date: 2026-09-07 00:00:00
"""

from collections.abc import Sequence

revision: str = "20260907_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the no-op project baseline."""


def downgrade() -> None:
    """Remove the no-op project baseline."""
