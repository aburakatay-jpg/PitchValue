"""account_deletion_persistence

Revision ID: c14dc91d1459
Revises: 3af5899142ab
Create Date: 2026-09-25 18:34:43.689274
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c14dc91d1459'
down_revision: str | None = '3af5899142ab'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0. Add subject_id to app_users
    op.add_column('app_users', sa.Column('subject_id', sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False))
    op.create_unique_constraint('uq_app_users_subject_id', 'app_users', ['subject_id'])

    # 1. Create account_deletion_requests
    op.create_table(
        'account_deletion_requests',
        sa.Column('request_id', sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('app_users.user_id', ondelete='SET NULL'), nullable=True),
        sa.Column('pseudonymous_subject_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deletion_state', sa.Text(), nullable=False),
        sa.Column('provider_revocation_status', sa.Text(), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.CheckConstraint(
            "deletion_state IN ('PROCESSING', 'FAILED_RETRYABLE', 'DELETED')",
            name='account_deletion_requests_state_check'
        ),
        sa.CheckConstraint(
            "provider_revocation_status IN ('NOT_APPLICABLE', 'PENDING', 'COMPLETED', 'FAILED_RETRYABLE')",
            name='account_deletion_requests_provider_status_check'
        )
    )

    op.create_index(
        'ix_account_deletion_requests_active_user',
        'account_deletion_requests',
        ['user_id'],
        unique=True,
        postgresql_where=sa.text("deletion_state != 'DELETED'")
    )

    # Trigger function for write-path compatibility
    op.execute("""
        CREATE OR REPLACE FUNCTION set_pseudonymous_subject_id()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.pseudonymous_subject_id IS NULL AND NEW.user_id IS NOT NULL THEN
                SELECT subject_id INTO NEW.pseudonymous_subject_id FROM app_users WHERE user_id = NEW.user_id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # 2. Add pseudonymous_subject_id to commerce_evidence
    op.add_column('commerce_evidence', sa.Column('pseudonymous_subject_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.execute("""
        UPDATE commerce_evidence ce
        SET pseudonymous_subject_id = au.subject_id
        FROM app_users au
        WHERE ce.user_id = au.user_id
    """)
    op.alter_column('commerce_evidence', 'pseudonymous_subject_id', nullable=False)

    op.execute("""
        CREATE TRIGGER commerce_evidence_subject_id_trigger
        BEFORE INSERT ON commerce_evidence
        FOR EACH ROW EXECUTE FUNCTION set_pseudonymous_subject_id();
    """)

    op.drop_constraint('commerce_evidence_user_id_fkey', 'commerce_evidence', type_='foreignkey')
    op.alter_column('commerce_evidence', 'user_id', nullable=True)
    op.create_foreign_key(
        'commerce_evidence_user_id_fkey',
        'commerce_evidence', 'app_users',
        ['user_id'], ['user_id'],
        ondelete='SET NULL'
    )

    # 3. Add pseudonymous_subject_id to entitlement_evidence
    op.add_column('entitlement_evidence', sa.Column('pseudonymous_subject_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.execute("""
        UPDATE entitlement_evidence ee
        SET pseudonymous_subject_id = au.subject_id
        FROM app_users au
        WHERE ee.user_id = au.user_id
    """)
    op.alter_column('entitlement_evidence', 'pseudonymous_subject_id', nullable=False)

    op.execute("""
        CREATE TRIGGER entitlement_evidence_subject_id_trigger
        BEFORE INSERT ON entitlement_evidence
        FOR EACH ROW EXECUTE FUNCTION set_pseudonymous_subject_id();
    """)

    op.drop_constraint('entitlement_evidence_user_id_fkey', 'entitlement_evidence', type_='foreignkey')
    op.alter_column('entitlement_evidence', 'user_id', nullable=True)
    op.create_foreign_key(
        'entitlement_evidence_user_id_fkey',
        'entitlement_evidence', 'app_users',
        ['user_id'], ['user_id'],
        ondelete='SET NULL'
    )

    op.create_index('ix_commerce_evidence_pseudonymous_subject', 'commerce_evidence', ['pseudonymous_subject_id'])
    op.create_index('ix_entitlement_evidence_pseudonymous_subject', 'entitlement_evidence', ['pseudonymous_subject_id'])


def downgrade() -> None:
    conn = op.get_bind()
    has_null_commerce = conn.execute(sa.text("SELECT 1 FROM commerce_evidence WHERE user_id IS NULL LIMIT 1")).scalar()
    has_null_entitlement = conn.execute(sa.text("SELECT 1 FROM entitlement_evidence WHERE user_id IS NULL LIMIT 1")).scalar()
    
    if has_null_commerce or has_null_entitlement:
        raise Exception(
            "Cannot safely downgrade migration A2: commerce_evidence or entitlement_evidence "
            "contains NULL user_id values from deleted users."
        )

    op.execute("DROP TRIGGER IF EXISTS entitlement_evidence_subject_id_trigger ON entitlement_evidence")
    op.execute("DROP TRIGGER IF EXISTS commerce_evidence_subject_id_trigger ON commerce_evidence")
    op.execute("DROP FUNCTION IF EXISTS set_pseudonymous_subject_id() CASCADE")

    op.drop_index('ix_entitlement_evidence_pseudonymous_subject', table_name='entitlement_evidence')
    op.drop_constraint('entitlement_evidence_user_id_fkey', 'entitlement_evidence', type_='foreignkey')
    op.alter_column('entitlement_evidence', 'user_id', nullable=False)
    op.create_foreign_key(
        'entitlement_evidence_user_id_fkey',
        'entitlement_evidence', 'app_users',
        ['user_id'], ['user_id'],
        ondelete='RESTRICT'
    )
    op.drop_column('entitlement_evidence', 'pseudonymous_subject_id')

    op.drop_index('ix_commerce_evidence_pseudonymous_subject', table_name='commerce_evidence')
    op.drop_constraint('commerce_evidence_user_id_fkey', 'commerce_evidence', type_='foreignkey')
    op.alter_column('commerce_evidence', 'user_id', nullable=False)
    op.create_foreign_key(
        'commerce_evidence_user_id_fkey',
        'commerce_evidence', 'app_users',
        ['user_id'], ['user_id'],
        ondelete='RESTRICT'
    )
    op.drop_column('commerce_evidence', 'pseudonymous_subject_id')

    op.drop_table('account_deletion_requests')

    op.drop_constraint('uq_app_users_subject_id', 'app_users', type_='unique')
    op.drop_column('app_users', 'subject_id')

