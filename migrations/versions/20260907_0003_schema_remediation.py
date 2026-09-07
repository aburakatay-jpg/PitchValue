"""Remediate canonical geography, score, and provider identifier semantics.

Revision ID: 20260907_0003
Revises: 20260907_0002
Create Date: 2026-09-07 02:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260907_0003"
down_revision: str | None = "20260907_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the approved canonical schema remediations."""
    op.execute(
        """
        ALTER TABLE competitions
            ADD COLUMN jurisdiction_code text,
            ADD CONSTRAINT ck_competitions_jurisdiction_code_nonblank CHECK (
                jurisdiction_code IS NULL OR length(btrim(jurisdiction_code)) > 0
            );

        UPDATE competitions
        SET
            country_code = CASE canonical_name
                WHEN 'Premier League' THEN 'GBR'
                WHEN 'Ligue 1' THEN 'FRA'
                WHEN 'Bundesliga' THEN 'DEU'
                WHEN 'Süper Lig' THEN 'TUR'
                WHEN 'Primeira Liga' THEN 'PRT'
                WHEN 'La Liga' THEN 'ESP'
                WHEN 'Scottish Premiership' THEN 'GBR'
                WHEN 'UEFA Champions League' THEN NULL
                WHEN 'UEFA Europa League' THEN NULL
                WHEN 'UEFA Conference League' THEN NULL
            END,
            jurisdiction_code = CASE canonical_name
                WHEN 'Premier League' THEN 'ENG'
                WHEN 'Ligue 1' THEN 'FRA'
                WHEN 'Bundesliga' THEN 'DEU'
                WHEN 'Süper Lig' THEN 'TUR'
                WHEN 'Primeira Liga' THEN 'PRT'
                WHEN 'La Liga' THEN 'ESP'
                WHEN 'Scottish Premiership' THEN 'SCO'
                WHEN 'UEFA Champions League' THEN 'UEFA'
                WHEN 'UEFA Europa League' THEN 'UEFA'
                WHEN 'UEFA Conference League' THEN 'UEFA'
            END
        WHERE gender = 'men'
          AND canonical_name IN (
              'Premier League',
              'Ligue 1',
              'Bundesliga',
              'Süper Lig',
              'Primeira Liga',
              'La Liga',
              'Scottish Premiership',
              'UEFA Champions League',
              'UEFA Europa League',
              'UEFA Conference League'
          );

        ALTER TABLE matches
            ADD CONSTRAINT ck_matches_finished_result_matches_score CHECK (
                status <> 'FINISHED'
                OR (result = 'H' AND home_score > away_score)
                OR (result = 'D' AND home_score = away_score)
                OR (result = 'A' AND home_score < away_score)
            );

        ALTER TABLE odds_snapshots
            ADD CONSTRAINT ck_odds_provider_market_context CHECK (
                provider_market_id IS NULL OR provider_id IS NOT NULL
            );

        ALTER TABLE competition_provider_refs
            ADD CONSTRAINT ck_competition_provider_external_id_nonblank CHECK (
                provider_competition_id IS NULL
                OR length(btrim(provider_competition_id)) > 0
            );

        ALTER TABLE team_aliases
            ADD CONSTRAINT ck_team_alias_provider_external_id_nonblank CHECK (
                provider_team_id IS NULL OR length(btrim(provider_team_id)) > 0
            );

        ALTER TABLE match_provider_refs
            ADD CONSTRAINT ck_match_provider_external_id_nonblank CHECK (
                provider_match_id IS NULL OR length(btrim(provider_match_id)) > 0
            );

        ALTER TABLE odds_snapshots
            ADD CONSTRAINT ck_odds_provider_market_id_nonblank CHECK (
                provider_market_id IS NULL OR length(btrim(provider_market_id)) > 0
            );
        """
    )


def downgrade() -> None:
    """Restore the exact schema and seed semantics of revision 20260907_0002."""
    op.execute(
        """
        ALTER TABLE odds_snapshots
            DROP CONSTRAINT ck_odds_provider_market_id_nonblank,
            DROP CONSTRAINT ck_odds_provider_market_context;

        ALTER TABLE match_provider_refs
            DROP CONSTRAINT ck_match_provider_external_id_nonblank;

        ALTER TABLE team_aliases
            DROP CONSTRAINT ck_team_alias_provider_external_id_nonblank;

        ALTER TABLE competition_provider_refs
            DROP CONSTRAINT ck_competition_provider_external_id_nonblank;

        ALTER TABLE matches
            DROP CONSTRAINT ck_matches_finished_result_matches_score;

        UPDATE competitions
        SET country_code = CASE canonical_name
            WHEN 'Premier League' THEN 'ENG'
            WHEN 'Ligue 1' THEN 'FRA'
            WHEN 'Bundesliga' THEN 'DEU'
            WHEN 'Süper Lig' THEN 'TUR'
            WHEN 'Primeira Liga' THEN 'PRT'
            WHEN 'La Liga' THEN 'ESP'
            WHEN 'Scottish Premiership' THEN 'SCO'
            WHEN 'UEFA Champions League' THEN NULL
            WHEN 'UEFA Europa League' THEN NULL
            WHEN 'UEFA Conference League' THEN NULL
        END
        WHERE gender = 'men'
          AND canonical_name IN (
              'Premier League',
              'Ligue 1',
              'Bundesliga',
              'Süper Lig',
              'Primeira Liga',
              'La Liga',
              'Scottish Premiership',
              'UEFA Champions League',
              'UEFA Europa League',
              'UEFA Conference League'
          );

        ALTER TABLE competitions
            DROP CONSTRAINT ck_competitions_jurisdiction_code_nonblank,
            DROP COLUMN jurisdiction_code;
        """
    )
