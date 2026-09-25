"""legal_acceptance_evidence

Revision ID: 63eaf92f52f6
Revises: c14dc91d1459
Create Date: 2026-09-25 18:35:47.354104
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '63eaf92f52f6'
down_revision: str | None = 'c14dc91d1459'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'legal_acceptance',
        sa.Column('legal_acceptance_id', sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('app_users.user_id', ondelete='SET NULL'), nullable=True),
        sa.Column('pseudonymous_subject_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('acknowledgement_type', sa.Text(), nullable=False),
        sa.Column('document_version', sa.Text(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "acknowledgement_type IN ('AGE_18_PLUS', 'TERMS', 'FINANCIAL_RISK')",
            name='legal_acceptance_type_check'
        ),
        sa.CheckConstraint(
            "length(trim(document_version)) > 0",
            name='legal_acceptance_document_version_check'
        )
    )

    op.execute("""
        CREATE TRIGGER legal_acceptance_subject_id_trigger
        BEFORE INSERT ON legal_acceptance
        FOR EACH ROW EXECUTE FUNCTION set_pseudonymous_subject_id();
    """)

    op.create_index('ix_legal_acceptance_user', 'legal_acceptance', ['user_id'])
    op.create_index('ix_legal_acceptance_subject', 'legal_acceptance', ['pseudonymous_subject_id'])


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS legal_acceptance_subject_id_trigger ON legal_acceptance")
    op.drop_table('legal_acceptance')

