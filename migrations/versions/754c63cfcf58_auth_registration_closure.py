"""auth_registration_closure

Revision ID: 754c63cfcf58
Revises: 8c612d37a88b
Create Date: 2026-09-19 16:17:12.982262
"""

from collections.abc import Sequence

from alembic import op

revision: str = '754c63cfcf58'
down_revision: str | None = '8c612d37a88b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE app_users ADD COLUMN country_code varchar(2) CHECK (
            country_code IS NULL OR country_code ~ '^[A-Z]{2}$'
        );
        ALTER TABLE app_users ADD COLUMN age_18_acknowledged_at timestamptz;

        CREATE TABLE auth_email_verifications (
            token_hash varchar(64) PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
            user_id varchar(36) NOT NULL REFERENCES app_users (user_id) ON DELETE CASCADE,
            expires_at timestamptz NOT NULL,
            used_at timestamptz
        );
        CREATE INDEX ix_auth_email_verifications_valid 
            ON auth_email_verifications (token_hash) WHERE used_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE auth_email_verifications;
        ALTER TABLE app_users DROP COLUMN age_18_acknowledged_at;
        ALTER TABLE app_users DROP COLUMN country_code;
        """
    )
