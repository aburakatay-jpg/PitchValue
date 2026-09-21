"""seed serie_a and eredivisie competitions

Revision ID: 3af5899142ab
Revises: a21c07329c48
Create Date: 2026-09-21 19:19:48.246085
"""

from collections.abc import Sequence

from alembic import op

revision: str = "3af5899142ab"
down_revision: str | None = "a21c07329c48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Seed Serie A and Eredivisie as inactive registry competitions.

    These competitions are present in the football-data.co.uk source
    registry but were not included in the original V1 seed migration.
    They are seeded as inactive (not engine-authorized, not V1 public,
    not live-provider verified) for clean-environment reproducibility.
    """
    op.execute(
        """
        INSERT INTO competitions (
            canonical_name, country_code, jurisdiction_code,
            competition_type, gender, active
        ) VALUES
            ('Serie A', 'ITA', 'ITA', 'domestic_league', 'men', false),
            ('Eredivisie', 'NLD', 'NLD', 'domestic_league', 'men', false)
        ON CONFLICT (canonical_name, gender) DO NOTHING;
        """
    )


def downgrade() -> None:
    """Remove Serie A and Eredivisie seed records."""
    op.execute(
        """
        DELETE FROM competitions
        WHERE canonical_name IN ('Serie A', 'Eredivisie')
          AND gender = 'men'
          AND active = false;
        """
    )

