"""auth_password_resets

Revision ID: ccfe1992e71e
Revises: 20260916_0012
Create Date: 2026-09-17 14:14:27.524815
"""

from collections.abc import Sequence

from alembic import op

revision: str = "ccfe1992e71e"
down_revision: str | None = "20260916_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE auth_password_resets (
            token_hash varchar(64) PRIMARY KEY,
            user_id varchar(36) NOT NULL REFERENCES app_users (user_id) ON DELETE RESTRICT,
            expires_at timestamptz NOT NULL,
            used_at timestamptz,
            CONSTRAINT ck_token_hash_shape CHECK (token_hash ~ '^[0-9a-f]{64}$')
        );
        CREATE INDEX ix_auth_password_resets_user_active
            ON auth_password_resets (user_id, expires_at DESC) WHERE used_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE auth_password_resets;")
