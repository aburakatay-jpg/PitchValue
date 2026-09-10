"""Add canonical historical odds observation semantics.

Revision ID: 20260910_0006
Revises: 20260908_0005
Create Date: 2026-09-10 12:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260910_0006"
down_revision: str | None = "20260908_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Extend odds snapshots with auditable source, timing, quality, and lineage semantics."""
    op.execute(
        """
        ALTER TABLE odds_snapshots
            DROP CONSTRAINT odds_snapshots_snapshot_type_check,
            ALTER COLUMN bookmaker DROP NOT NULL;

        ALTER TABLE odds_snapshots
            RENAME COLUMN snapshot_at TO observed_at;

        ALTER TABLE odds_snapshots
            RENAME COLUMN snapshot_type TO observation_role;

        ALTER TABLE odds_snapshots
            ADD COLUMN observation_origin text NOT NULL DEFAULT 'live_source',
            ADD COLUMN observation_source_kind text NOT NULL DEFAULT 'bookmaker',
            ADD COLUMN timing_semantics text NOT NULL DEFAULT 'unknown',
            ADD COLUMN quality_status text NOT NULL DEFAULT 'eligible',
            ADD COLUMN quality_reasons text[] NOT NULL DEFAULT ARRAY[]::text[],
            ADD COLUMN source_staging_row_id bigint,
            ADD COLUMN source_field text,
            ADD COLUMN mapping_version text,
            ADD COLUMN normalization_version text,
            ADD COLUMN quality_policy_version text,
            ADD CONSTRAINT fk_odds_source_staging_row
                FOREIGN KEY (source_staging_row_id)
                REFERENCES football_data_staging_rows (staging_row_id)
                ON DELETE RESTRICT,
            ADD CONSTRAINT ck_odds_observation_origin CHECK (
                observation_origin IN ('historical_source', 'live_source')
            ),
            ADD CONSTRAINT ck_odds_observation_source_kind CHECK (
                observation_source_kind IN ('bookmaker', 'source_average', 'source_maximum')
            ),
            ADD CONSTRAINT ck_odds_observation_role CHECK (
                observation_role IN (
                    'opening',
                    'source_prematch',
                    'source_final',
                    'closing',
                    'unknown_prematch',
                    'live'
                )
            ),
            ADD CONSTRAINT ck_odds_timing_semantics CHECK (
                timing_semantics IN ('exact', 'role_only', 'unknown')
            ),
            ADD CONSTRAINT ck_odds_quality_status CHECK (
                quality_status IN ('eligible', 'suspect', 'excluded', 'invalid')
            ),
            ADD CONSTRAINT ck_odds_source_kind_bookmaker CHECK (
                (
                    observation_source_kind = 'bookmaker'
                    AND bookmaker IS NOT NULL
                    AND length(btrim(bookmaker)) > 0
                )
                OR (
                    observation_source_kind IN ('source_average', 'source_maximum')
                    AND bookmaker IS NULL
                )
            ),
            ADD CONSTRAINT ck_odds_exact_timing_has_observed_at CHECK (
                timing_semantics <> 'exact' OR observed_at IS NOT NULL
            ),
            ADD CONSTRAINT ck_odds_source_field_nonblank CHECK (
                source_field IS NULL OR length(btrim(source_field)) > 0
            ),
            ADD CONSTRAINT ck_odds_mapping_version_nonblank CHECK (
                mapping_version IS NULL OR length(btrim(mapping_version)) > 0
            ),
            ADD CONSTRAINT ck_odds_normalization_version_nonblank CHECK (
                normalization_version IS NULL OR length(btrim(normalization_version)) > 0
            ),
            ADD CONSTRAINT ck_odds_quality_policy_version_nonblank CHECK (
                quality_policy_version IS NULL OR length(btrim(quality_policy_version)) > 0
            ),
            ADD CONSTRAINT ck_odds_historical_source_complete CHECK (
                observation_origin <> 'historical_source'
                OR (
                    source_staging_row_id IS NOT NULL
                    AND source_field IS NOT NULL
                    AND length(btrim(source_field)) > 0
                    AND mapping_version IS NOT NULL
                    AND length(btrim(mapping_version)) > 0
                    AND normalization_version IS NOT NULL
                    AND length(btrim(normalization_version)) > 0
                    AND quality_policy_version IS NOT NULL
                    AND length(btrim(quality_policy_version)) > 0
                )
            );

        CREATE UNIQUE INDEX uq_odds_historical_source_identity
            ON odds_snapshots (
                source_staging_row_id,
                source_field,
                mapping_version,
                normalization_version,
                quality_policy_version
            )
            WHERE observation_origin = 'historical_source';

        COMMENT ON COLUMN odds_snapshots.observed_at IS
            'Actual source quote timestamp; never import, staging, file, or runtime time';
        COMMENT ON COLUMN odds_snapshots.observation_role IS
            'Temporal role without implying an exact timestamp';
        COMMENT ON COLUMN odds_snapshots.quality_reasons IS
            'Stable machine-readable quality reason tokens';
        COMMENT ON COLUMN odds_snapshots.source_staging_row_id IS
            'Lineage to the verified source staging row for historical observations';
        """
    )


def downgrade() -> None:
    """Restore the exact odds snapshot schema from revision 20260908_0005."""
    op.execute(
        """
        DROP INDEX uq_odds_historical_source_identity;

        ALTER TABLE odds_snapshots
            DROP CONSTRAINT ck_odds_historical_source_complete,
            DROP CONSTRAINT ck_odds_quality_policy_version_nonblank,
            DROP CONSTRAINT ck_odds_normalization_version_nonblank,
            DROP CONSTRAINT ck_odds_mapping_version_nonblank,
            DROP CONSTRAINT ck_odds_source_field_nonblank,
            DROP CONSTRAINT ck_odds_exact_timing_has_observed_at,
            DROP CONSTRAINT ck_odds_source_kind_bookmaker,
            DROP CONSTRAINT ck_odds_quality_status,
            DROP CONSTRAINT ck_odds_timing_semantics,
            DROP CONSTRAINT ck_odds_observation_role,
            DROP CONSTRAINT ck_odds_observation_source_kind,
            DROP CONSTRAINT ck_odds_observation_origin,
            DROP CONSTRAINT fk_odds_source_staging_row,
            DROP COLUMN quality_policy_version,
            DROP COLUMN normalization_version,
            DROP COLUMN mapping_version,
            DROP COLUMN source_field,
            DROP COLUMN source_staging_row_id,
            DROP COLUMN quality_reasons,
            DROP COLUMN quality_status,
            DROP COLUMN timing_semantics,
            DROP COLUMN observation_source_kind,
            DROP COLUMN observation_origin;

        ALTER TABLE odds_snapshots
            RENAME COLUMN observation_role TO snapshot_type;

        ALTER TABLE odds_snapshots
            RENAME COLUMN observed_at TO snapshot_at;

        ALTER TABLE odds_snapshots
            ALTER COLUMN bookmaker SET NOT NULL,
            ADD CONSTRAINT odds_snapshots_snapshot_type_check CHECK (
                snapshot_type IN (
                    'opening', 'morning', 'lineup', 't_minus_15', 'closing', 'unknown'
                )
            );
        """
    )
