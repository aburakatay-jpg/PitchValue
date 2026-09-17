import os
from datetime import UTC
from pathlib import Path

import pytest
from sqlalchemy import create_engine

# First load .env if present
env_path = Path(".env")
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            if key.strip() and key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip()

# Force environment to test
os.environ["PITCHVALUE_ENV"] = "test"

# Rewrite DATABASE_URL to target pitchvalue_test if it targets pitchvalue
if "DATABASE_URL" in os.environ:
    url = os.environ["DATABASE_URL"]
    if url.endswith("/pitchvalue"):
        # Split by / and replace the last part
        parts = url.rsplit("/", 1)
        if len(parts) == 2 and parts[1] == "pitchvalue":
            os.environ["DATABASE_URL"] = f"{parts[0]}/pitchvalue_test"


@pytest.fixture(scope="session", autouse=True)
def guard_against_dev_database() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.endswith("/pitchvalue"):
        pytest.exit(
            "HARD SAFETY GUARD TRIGGERED: Tests are attempting to run against the development database ('pitchvalue'). Tests must target a dedicated test database."
        )

    # Deterministic test seed for REFERENCE_DATA_DEPENDENCY tests
    from datetime import datetime

    from sqlalchemy import text

    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            # 5DollarFootballAPI provider for mapping review tests
            conn.execute(
                text(
                    "INSERT INTO providers(name, provider_type, priority) "
                    "SELECT '5DollarFootballAPI', 'football_data', 1 "
                    "WHERE NOT EXISTS (SELECT 1 FROM providers WHERE name = '5DollarFootballAPI')"
                )
            )
            # Dummy engine_run for report location and operations tests
            conn.execute(
                text(
                    "INSERT INTO engine_runs("
                    "run_id, run_type, status, scheduled_for, started_at, "
                    "schedule_version, fixture_horizon, model_version, feature_profile, "
                    "orchestrator_version, policy_version, dq_version, market_stability_version, "
                    "calibration_confidence_version, no_vig_version, provider_contract_version) "
                    "SELECT 'test-dummy-run-id', 'SHADOW', 'RUNNING', :now, :now, "
                    "'{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}' "
                    "WHERE NOT EXISTS (SELECT 1 FROM engine_runs WHERE run_id = 'test-dummy-run-id')"
                ),
                {"now": datetime.now(UTC)},
            )
            # Source entity references for readiness and metadata tests
            for entity in ["FIXTURE", "COMPETITION", "TEAM"]:
                conn.execute(
                    text(
                        "INSERT INTO source_entity_references("
                        "provider_id, provider_entity_id, provider_display_name, "
                        "entity_type, mapping_status, mapping_version, provenance, "
                        "first_seen_at, last_seen_at) "
                        "SELECT (SELECT provider_id FROM providers WHERE name = '5DollarFootballAPI' LIMIT 1), "
                        "'dummy-' || :entity, 'Dummy ' || :entity, :entity, 'UNRESOLVED', 1, 'TEST', :now, :now "
                        "WHERE NOT EXISTS (SELECT 1 FROM source_entity_references WHERE entity_type = :entity)"
                    ),
                    {"entity": entity, "now": datetime.now(UTC)},
                )

            # Insert a dummy CURRENT_SEASON_SYNC_SUCCEEDED event to prevent STALE reasons
            conn.execute(
                text(
                    "INSERT INTO operational_events(event_id, event_type, event_version, occurred_at, severity, correlation_id, source_component, metadata, delivery_visibility, persisted_at) "
                    "SELECT '0000000000000000000000000000000000000000000000000000000000000000', 'CURRENT_SEASON_SYNC_SUCCEEDED', 1, :occurred_at, 'INFO', 'dummy-correlation', 'TEST', '{}'::jsonb, 'INTERNAL', :now "
                    "WHERE NOT EXISTS (SELECT 1 FROM operational_events WHERE event_type = 'CURRENT_SEASON_SYNC_SUCCEEDED')"
                ),
                {"now": datetime.now(UTC), "occurred_at": datetime(2026, 9, 13, tzinfo=UTC)},
            )
    except Exception as e:
        print(f"Warning: Seed initialization failed (schema might not be applied yet): {e}")
        pass
