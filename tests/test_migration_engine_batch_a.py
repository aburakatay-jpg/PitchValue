# ruff: noqa: E501
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


# Run this test manually or with pytest
def test_migration_engine_batch_a():
    project_root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(project_root / "alembic.ini")
    alembic_cfg.set_main_option("script_location", str(project_root / "migrations"))

    # Use test db
    db_url = os.environ.get("DATABASE_URL")
    if db_url and not db_url.endswith("_test"):
        pytest.skip("Test requires a test database.")

    engine = create_engine(db_url)

    # 0. Upgrade to head first to populate empty DB
    command.upgrade(alembic_cfg, "head")

    # 1. Migrate down to ccfe1992e71e
    command.downgrade(alembic_cfg, "ccfe1992e71e")

    # 2. Seed data
    with engine.begin() as conn:
        # Create dependencies
        conn.execute(
            text(
                "INSERT INTO teams (team_id, canonical_name, normalized_name) VALUES (1, 'Team A', 'teama') ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO teams (team_id, canonical_name, normalized_name) VALUES (2, 'Team B', 'teamb') ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO competitions (competition_id, canonical_name, competition_type) VALUES (1, 'Comp', 'domestic_league') ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO seasons (season_id, competition_id, season_name, start_year, end_year, status) VALUES (1, 1, '2026', 2026, 2026, 'active') ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            text(
                """INSERT INTO matches (
                match_id, competition_id, season_id, stage, round, matchday,
                home_team_id, away_team_id, kickoff_at_utc, status
            ) VALUES (
                1, 1, 1, 'REGULAR_SEASON', '1', 1,
                1, 2, :now, 'SCHEDULED'
            ) ON CONFLICT DO NOTHING"""
            ),
            {"now": datetime.now(UTC)},
        )
        m_id = 1

        # Ensure provider exists
        conn.execute(
            text(
                "INSERT INTO providers(name, provider_type, priority) VALUES ('TestProvider', 'football_data', 1) ON CONFLICT DO NOTHING"
            )
        )

        provider = conn.execute(text("SELECT provider_id FROM providers LIMIT 1")).fetchone()
        if not provider:
            pytest.skip("No provider found")
        p_id = provider[0]

        # clear for clean test
        conn.execute(text("DELETE FROM shadow_analysis_snapshots"))
        conn.execute(text("DELETE FROM engine_runs"))
        conn.execute(text("DELETE FROM odds_snapshots"))

        # Insert odds
        conn.execute(
            text(
                """INSERT INTO odds_snapshots (
                match_id, provider_id, bookmaker, market, selection, line, decimal_odds,
                provider_market_id, observation_role, observation_origin,
                observation_source_kind, timing_semantics, quality_status, quality_reasons,
                source_field, mapping_version, normalization_version, quality_policy_version
            ) VALUES (
                :m_id, :p_id, 'bet365', 'match_odds', 'home', NULL, 1.5,
                'provider_mkt_1', 'source_prematch', 'live_source', 'bookmaker', 'role_only', 'eligible',
                '{}', 'foo', 'map_v1', 'norm_v1', 'qual_v1'
            )"""
            ),
            {"m_id": m_id, "p_id": p_id},
        )

        # Insert engine_run
        conn.execute(
            text(
                """INSERT INTO engine_runs(
                run_id, run_type, status, scheduled_for, started_at, 
                schedule_version, fixture_horizon, model_version, feature_profile, 
                orchestrator_version, policy_version, dq_version, market_stability_version, 
                calibration_confidence_version, no_vig_version, provider_contract_version
            ) VALUES (
                'test_run_1', 'SHADOW', 'RUNNING', :now, :now, 
                'v1', '{}', 'v1', 'v1', 'v1', 'v1', 'v1', 'v1', 'v1', 'v1', 'v1'
            )"""
            ),
            {"now": datetime.now(UTC)},
        )

        # Insert shadow analysis
        conn.execute(
            text(
                """INSERT INTO shadow_analysis_snapshots(
                shadow_analysis_id, run_id, match_id, prediction_as_of, model_version, feature_version,
                raw_ml_probabilities, elo_output, poisson_output, form_output,
                agreement_output, odds_mode, dq_state, market_stability,
                calibration_confidence, bet_score, bet_score_completeness,
                publication_eligible, diagnostics, payload_hash
            ) VALUES (
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'test_run_1', :m_id, :now, 'v1', 'v1',
                '{}', '{}', '{}', '{}', '{}',
                'MARKET_REFERENCE_ONLY', '{}', '{}', '{}',
                0.0, 'COMPLETE', false, '{}', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
            )"""
            ),
            {"now": datetime.now(UTC), "m_id": m_id},
        )

    # 3. Upgrade to head
    command.upgrade(alembic_cfg, "head")

    # 4. Verify backfill
    with engine.connect() as conn:
        run = conn.execute(
            text(
                "SELECT logical_run_id, attempt_number FROM engine_runs WHERE run_id = 'test_run_1'"
            )
        ).fetchone()
        assert run[0] == "test_run_1"
        assert run[1] == 1

        shadow = conn.execute(
            text("SELECT logical_run_id FROM shadow_analysis_snapshots WHERE run_id = 'test_run_1'")
        ).fetchone()
        assert shadow[0] == "test_run_1"

        odds_idx = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE indexname = 'ix_odds_snapshots_market_time'"
            )
        ).fetchone()
        assert odds_idx is not None

    # Try downgrading to test guard
    # downgrading is safe because there are no duplicate attempts.
    command.downgrade(alembic_cfg, "ccfe1992e71e")

    # Bring back up
    command.upgrade(alembic_cfg, "head")
