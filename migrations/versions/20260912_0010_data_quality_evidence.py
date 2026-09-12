"""Add versioned provider-neutral data-quality evidence.

Revision ID: 20260912_0010
Revises: 20260912_0009
Create Date: 2026-09-12 09:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260912_0010"
down_revision: str | None = "20260912_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Preserve legacy DQ rows while adding repeatable evidence evaluations."""
    op.execute(
        """
        CREATE TABLE data_quality_evaluations (
            evaluation_id varchar(64) PRIMARY KEY CHECK (evaluation_id ~ '^[0-9a-f]{64}$'),
            match_id bigint NOT NULL REFERENCES matches (match_id) ON DELETE RESTRICT,
            run_id text REFERENCES engine_runs (run_id) ON DELETE RESTRICT,
            evaluated_at timestamptz NOT NULL,
            evidence_profile text NOT NULL CHECK (
                evidence_profile IN ('HISTORICAL_RECONSTRUCTED', 'LIVE_OPERATIONAL')
            ),
            evidence_version text NOT NULL CHECK (length(btrim(evidence_version)) > 0),
            quality_score numeric CHECK (quality_score IS NULL OR quality_score BETWEEN 0 AND 100),
            persisted_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (match_id, evaluated_at, evidence_profile, evidence_version)
        );

        CREATE TABLE data_quality_evidence (
            evaluation_id varchar(64) NOT NULL REFERENCES data_quality_evaluations (evaluation_id)
                ON DELETE RESTRICT,
            evidence_family text NOT NULL CHECK (evidence_family IN (
                'HISTORICAL_DEPTH', 'MATCH_STATISTICS_COMPLETENESS',
                'CURRENT_SEASON_FRESHNESS', 'FIXTURE_INTEGRITY',
                'ENTITY_MAPPING_INTEGRITY', 'SOURCE_PROVIDER_HEALTH'
            )),
            availability text NOT NULL CHECK (
                availability IN ('AVAILABLE', 'PARTIAL', 'UNAVAILABLE', 'HARD_FAIL')
            ),
            hard_fail boolean NOT NULL,
            reason_codes text[] NOT NULL DEFAULT ARRAY[]::text[],
            provenance jsonb NOT NULL CHECK (jsonb_typeof(provenance) = 'object'),
            observed_at timestamptz,
            PRIMARY KEY (evaluation_id, evidence_family),
            CHECK (hard_fail = (availability = 'HARD_FAIL')),
            CHECK (availability = 'AVAILABLE' OR cardinality(reason_codes) > 0)
        );

        CREATE INDEX ix_data_quality_evaluations_match_time
            ON data_quality_evaluations (match_id, evaluated_at DESC);
        """
    )


def downgrade() -> None:
    """Remove versioned evidence without touching legacy data_quality rows."""
    op.execute(
        """
        DROP TABLE data_quality_evidence;
        DROP TABLE data_quality_evaluations;
        """
    )
