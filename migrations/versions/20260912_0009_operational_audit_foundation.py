"""Add provider-neutral operational audit foundation.

Revision ID: 20260912_0009
Revises: 20260911_0008
Create Date: 2026-09-12 08:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260912_0009"
down_revision: str | None = "20260911_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create canonical run, quarantine, event, and delivery audit entities."""
    op.execute(
        """
        CREATE TABLE engine_runs (
            run_id text PRIMARY KEY CHECK (length(btrim(run_id)) > 0),
            run_type text NOT NULL CHECK (run_type IN ('FULL', 'SHADOW', 'VALIDATION')),
            scheduled_for timestamptz NOT NULL,
            started_at timestamptz,
            finished_at timestamptz,
            status text NOT NULL CHECK (status IN (
                'SCHEDULED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'PARTIAL_WITH_QUARANTINES'
            )),
            schedule_version text NOT NULL CHECK (length(btrim(schedule_version)) > 0),
            fixture_horizon jsonb NOT NULL CHECK (jsonb_typeof(fixture_horizon) = 'object'),
            model_version text NOT NULL CHECK (length(btrim(model_version)) > 0),
            feature_profile text NOT NULL CHECK (length(btrim(feature_profile)) > 0),
            orchestrator_version text NOT NULL CHECK (length(btrim(orchestrator_version)) > 0),
            policy_version text NOT NULL CHECK (length(btrim(policy_version)) > 0),
            dq_version text NOT NULL CHECK (length(btrim(dq_version)) > 0),
            market_stability_version text NOT NULL CHECK (
                length(btrim(market_stability_version)) > 0
            ),
            calibration_confidence_version text NOT NULL CHECK (
                length(btrim(calibration_confidence_version)) > 0
            ),
            no_vig_version text NOT NULL CHECK (length(btrim(no_vig_version)) > 0),
            provider_contract_version text NOT NULL CHECK (
                length(btrim(provider_contract_version)) > 0
            ),
            persisted_at timestamptz NOT NULL DEFAULT now(),
            CHECK (started_at IS NULL OR started_at >= scheduled_for),
            CHECK (finished_at IS NULL OR (started_at IS NOT NULL AND finished_at >= started_at))
        );

        CREATE TABLE run_quarantines (
            quarantine_id varchar(64) PRIMARY KEY CHECK (quarantine_id ~ '^[0-9a-f]{64}$'),
            run_id text NOT NULL REFERENCES engine_runs (run_id) ON DELETE RESTRICT,
            match_id bigint NOT NULL REFERENCES matches (match_id) ON DELETE RESTRICT,
            market_family text,
            scope text NOT NULL CHECK (scope IN ('MATCH', 'MARKET_FAMILY')),
            reason_code text NOT NULL CHECK (length(btrim(reason_code)) > 0),
            occurred_at timestamptz NOT NULL,
            evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
            status text NOT NULL CHECK (status IN ('ACTIVE', 'RESOLVED')),
            CHECK (
                (scope = 'MATCH' AND market_family IS NULL)
                OR (scope = 'MARKET_FAMILY' AND length(btrim(market_family)) > 0)
            )
        );

        CREATE TABLE operational_events (
            event_id varchar(64) PRIMARY KEY CHECK (event_id ~ '^[0-9a-f]{64}$'),
            event_type text NOT NULL CHECK (length(btrim(event_type)) > 0),
            event_version text NOT NULL CHECK (length(btrim(event_version)) > 0),
            occurred_at timestamptz NOT NULL,
            severity text NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),
            run_id text REFERENCES engine_runs (run_id) ON DELETE RESTRICT,
            match_id bigint REFERENCES matches (match_id) ON DELETE RESTRICT,
            market_family text,
            provider_domain text,
            correlation_id text NOT NULL CHECK (length(btrim(correlation_id)) > 0),
            reason_code text,
            source_component text NOT NULL CHECK (length(btrim(source_component)) > 0),
            metadata jsonb NOT NULL CHECK (jsonb_typeof(metadata) = 'object'),
            delivery_visibility text NOT NULL CHECK (
                delivery_visibility IN ('INTERNAL', 'OPERATIONS')
            ),
            persisted_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE operational_event_deliveries (
            event_id varchar(64) NOT NULL REFERENCES operational_events (event_id)
                ON DELETE RESTRICT,
            consumer text NOT NULL CHECK (length(btrim(consumer)) > 0),
            status text NOT NULL CHECK (status IN (
                'PENDING', 'DELIVERED', 'RETRYABLE_FAILURE', 'PERMANENT_FAILURE'
            )),
            attempt_count integer NOT NULL CHECK (attempt_count >= 0),
            failure_code text,
            updated_at timestamptz NOT NULL,
            PRIMARY KEY (event_id, consumer)
        );

        CREATE INDEX ix_engine_runs_scheduled_status
            ON engine_runs (scheduled_for DESC, status);
        CREATE INDEX ix_run_quarantines_run_active
            ON run_quarantines (run_id, status);
        CREATE INDEX ix_operational_events_run_time
            ON operational_events (run_id, occurred_at, event_id);
        CREATE INDEX ix_operational_deliveries_retry
            ON operational_event_deliveries (status, updated_at)
            WHERE status IN ('PENDING', 'RETRYABLE_FAILURE');
        """
    )


def downgrade() -> None:
    """Remove only provider-neutral operational audit entities."""
    op.execute(
        """
        DROP TABLE operational_event_deliveries;
        DROP TABLE operational_events;
        DROP TABLE run_quarantines;
        DROP TABLE engine_runs;
        """
    )
