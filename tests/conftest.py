import os
from datetime import UTC
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

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

# Never let test setup write to a remote database, even if its name resembles
# the local development database. Migrations in tests must share this isolation.
_test_database_url = os.environ.get("DATABASE_URL", "")
try:
    _parsed_test_url = make_url(_test_database_url)
except Exception:
    pytest.exit("Tests require a valid local PostgreSQL test database URL")
if _parsed_test_url.host not in {"localhost", "127.0.0.1", "::1"}:
    pytest.exit("Tests may only connect to a local PostgreSQL database")
if _parsed_test_url.database == "pitchvalue":
    _parsed_test_url = _parsed_test_url.set(database="pitchvalue_test")
elif _parsed_test_url.database != "pitchvalue_test":
    pytest.exit("Tests must target the dedicated pitchvalue_test database")
os.environ["DATABASE_URL"] = _parsed_test_url.render_as_string(hide_password=False)
os.environ["DATABASE_DIRECT_URL"] = os.environ["DATABASE_URL"]


@pytest.fixture(scope="session", autouse=True)
def guard_against_dev_database() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if make_url(db_url).database != "pitchvalue_test":
        pytest.exit(
            "HARD SAFETY GUARD TRIGGERED: Tests are attempting to"
            " run against the development database ('pitchvalue')."
            " Tests must target a dedicated test database."
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
                    "WHERE NOT EXISTS "
                    "(SELECT 1 FROM providers WHERE name = '5DollarFootballAPI')"
                )
            )
            # Dummy engine_run for report location and operations tests
            conn.execute(
                text(
                    "INSERT INTO engine_runs("
                    "run_id, logical_run_id, attempt_number, run_type, status,"
                    " scheduled_for, started_at, "
                    "schedule_version, fixture_horizon, model_version,"
                    " feature_profile, "
                    "orchestrator_version, policy_version, dq_version,"
                    " market_stability_version, "
                    "calibration_confidence_version, no_vig_version,"
                    " provider_contract_version) "
                    "SELECT 'test-dummy-run-id', 'test-dummy-run-id', 1,"
                    " 'SHADOW', 'RUNNING', :now, :now, "
                    "'{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}' "
                    "WHERE NOT EXISTS "
                    "(SELECT 1 FROM engine_runs WHERE run_id = 'test-dummy-run-id')"
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
                        "SELECT (SELECT provider_id FROM providers"
                        " WHERE name = '5DollarFootballAPI' LIMIT 1), "
                        "'dummy-' || :entity, 'Dummy ' || :entity,"
                        " :entity, 'UNRESOLVED', 1, 'TEST', :now, :now "
                        "WHERE NOT EXISTS (SELECT 1 FROM source_entity_references"
                        " WHERE entity_type = :entity)"
                    ),
                    {"entity": entity, "now": datetime.now(UTC)},
                )

            # Insert a dummy CURRENT_SEASON_SYNC_SUCCEEDED event to prevent STALE reasons
            _eid = "0000000000000000000000000000000000000000000000000000000000000000"
            _etype = "CURRENT_SEASON_SYNC_SUCCEEDED"
            conn.execute(
                text(
                    "INSERT INTO operational_events("
                    "event_id, event_type, event_version, occurred_at,"
                    " severity, correlation_id, source_component,"
                    " metadata, delivery_visibility, persisted_at) "
                    "SELECT :eid, :etype, 1, :occurred_at,"
                    " 'INFO', 'dummy-correlation', 'TEST',"
                    " '{}'::jsonb, 'INTERNAL', :now "
                    "WHERE NOT EXISTS (SELECT 1 FROM operational_events"
                    " WHERE event_type = :etype)"
                ),
                {
                    "now": datetime.now(UTC),
                    "occurred_at": datetime(2026, 9, 13, tzinfo=UTC),
                    "eid": _eid,
                    "etype": _etype,
                },
            )
    except Exception as e:
        print(f"Warning: Seed initialization failed (schema might not be applied yet): {e}")
        pass
