# ruff: noqa: E501
"""engine_data_integrity

Revision ID: 8c612d37a88b
Revises: ccfe1992e71e
Create Date: 2026-09-18 20:45:36.204684
"""

from collections.abc import Sequence

from alembic import op

revision: str = "8c612d37a88b"
down_revision: str | None = "ccfe1992e71e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Odds Snapshots Migration
    op.execute(
        """
        DROP INDEX IF EXISTS uq_live_odds_provider_market_version;
        CREATE INDEX ix_odds_snapshots_market_time
            ON odds_snapshots (provider_id, provider_market_id, normalization_version, created_at DESC)
            WHERE observation_origin = 'live_source'
              AND provider_id IS NOT NULL
              AND provider_market_id IS NOT NULL;
        """
    )

    # 2. Engine Runs Migration
    op.execute(
        """
        ALTER TABLE engine_runs ADD COLUMN logical_run_id text;
        ALTER TABLE engine_runs ADD COLUMN attempt_number integer;
        UPDATE engine_runs SET logical_run_id = run_id, attempt_number = 1;
        ALTER TABLE engine_runs ALTER COLUMN logical_run_id SET NOT NULL;
        ALTER TABLE engine_runs ALTER COLUMN attempt_number SET NOT NULL;
        ALTER TABLE engine_runs ADD CONSTRAINT uq_engine_run_logical_attempt UNIQUE (logical_run_id, attempt_number);
        """
    )

    # 3. Shadow Analysis Snapshots Migration
    op.execute(
        """
        ALTER TABLE shadow_analysis_snapshots ADD COLUMN logical_run_id text;
        UPDATE shadow_analysis_snapshots s
            SET logical_run_id = e.logical_run_id
            FROM engine_runs e
            WHERE s.run_id = e.run_id;
        """
    )
    # Check for orphans
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM shadow_analysis_snapshots WHERE logical_run_id IS NULL) THEN
                RAISE EXCEPTION 'Orphaned shadow_analysis_snapshots found during migration';
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        ALTER TABLE shadow_analysis_snapshots ALTER COLUMN logical_run_id SET NOT NULL;
        ALTER TABLE shadow_analysis_snapshots DROP CONSTRAINT uq_shadow_run_match;
        ALTER TABLE shadow_analysis_snapshots ADD CONSTRAINT uq_shadow_run_match UNIQUE (logical_run_id, match_id);
        """
    )


def downgrade() -> None:
    # Downgrade guard for shadow
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT logical_run_id
                FROM engine_runs
                GROUP BY logical_run_id
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade: multiple attempts exist for logical runs';
            END IF;
        END $$;
        """
    )

    # Downgrade shadow_analysis_snapshots
    op.execute(
        """
        ALTER TABLE shadow_analysis_snapshots DROP CONSTRAINT uq_shadow_run_match;
        ALTER TABLE shadow_analysis_snapshots ADD CONSTRAINT uq_shadow_run_match UNIQUE (run_id, match_id);
        ALTER TABLE shadow_analysis_snapshots DROP COLUMN logical_run_id;
        """
    )

    # Downgrade engine_runs
    op.execute(
        """
        ALTER TABLE engine_runs DROP CONSTRAINT uq_engine_run_logical_attempt;
        ALTER TABLE engine_runs DROP COLUMN logical_run_id;
        ALTER TABLE engine_runs DROP COLUMN attempt_number;
        """
    )

    # Downgrade guard for odds
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT provider_id, provider_market_id, normalization_version
                FROM odds_snapshots
                WHERE observation_origin = 'live_source'
                  AND provider_id IS NOT NULL
                  AND provider_market_id IS NOT NULL
                  AND normalization_version IS NOT NULL
                GROUP BY provider_id, provider_market_id, normalization_version
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade: duplicate live odds snapshots exist';
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DROP INDEX IF EXISTS ix_odds_snapshots_market_time;
        CREATE UNIQUE INDEX uq_live_odds_provider_market_version
            ON odds_snapshots (provider_id, provider_market_id, normalization_version)
            WHERE observation_origin = 'live_source'
              AND provider_id IS NOT NULL
              AND provider_market_id IS NOT NULL
              AND normalization_version IS NOT NULL;
        """
    )
