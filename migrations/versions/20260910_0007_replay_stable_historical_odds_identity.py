"""Make historical odds identity stable across ingestion replays.

Revision ID: 20260910_0007
Revises: 20260910_0006
Create Date: 2026-09-10 18:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260910_0007"
down_revision: str | None = "20260910_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Anchor historical odds uniqueness to the canonical provider source record."""
    op.execute(
        """
        CREATE UNIQUE INDEX uq_match_provider_source_record_identity
            ON match_provider_refs (provider_id, source_url, source_record_hash)
            WHERE source_url IS NOT NULL AND source_record_hash IS NOT NULL;

        ALTER TABLE odds_snapshots
            ADD COLUMN source_match_provider_ref_id bigint,
            ADD CONSTRAINT fk_odds_source_match_provider_ref
                FOREIGN KEY (source_match_provider_ref_id)
                REFERENCES match_provider_refs (match_provider_ref_id)
                ON DELETE RESTRICT;

        UPDATE odds_snapshots AS odds
        SET source_match_provider_ref_id = refs.match_provider_ref_id
        FROM football_data_staging_rows AS staging
        JOIN import_batches AS batch
          ON batch.import_batch_id = staging.import_batch_id
        JOIN match_provider_refs AS refs
          ON refs.provider_id = batch.provider_id
         AND refs.source_url = batch.source_identifier
         AND refs.source_record_hash = staging.row_hash
        WHERE odds.observation_origin = 'historical_source'
          AND odds.source_staging_row_id = staging.staging_row_id
          AND odds.match_id = refs.match_id;

        ALTER TABLE odds_snapshots
            DROP CONSTRAINT ck_odds_historical_source_complete,
            ADD CONSTRAINT ck_odds_historical_source_complete CHECK (
                observation_origin <> 'historical_source'
                OR (
                    source_staging_row_id IS NOT NULL
                    AND source_match_provider_ref_id IS NOT NULL
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

        DROP INDEX uq_odds_historical_source_identity;

        CREATE UNIQUE INDEX uq_odds_historical_source_identity
            ON odds_snapshots (
                source_match_provider_ref_id,
                source_field,
                mapping_version,
                normalization_version,
                quality_policy_version
            )
            WHERE observation_origin = 'historical_source';

        COMMENT ON COLUMN odds_snapshots.source_match_provider_ref_id IS
            'Replay-stable canonical source-record identity; staging row remains event lineage';
        """
    )


def downgrade() -> None:
    """Restore the staging-event identity used by revision 20260910_0006."""
    op.execute(
        """
        DROP INDEX uq_odds_historical_source_identity;

        CREATE UNIQUE INDEX uq_odds_historical_source_identity
            ON odds_snapshots (
                source_staging_row_id,
                source_field,
                mapping_version,
                normalization_version,
                quality_policy_version
            )
            WHERE observation_origin = 'historical_source';

        ALTER TABLE odds_snapshots
            DROP CONSTRAINT ck_odds_historical_source_complete,
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
            ),
            DROP CONSTRAINT fk_odds_source_match_provider_ref,
            DROP COLUMN source_match_provider_ref_id;

        DROP INDEX uq_match_provider_source_record_identity;
        """
    )
