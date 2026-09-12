from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_operational_audit_is_next_provider_neutral_migration() -> None:
    root = Path(__file__).resolve().parents[1]
    scripts = ScriptDirectory.from_config(Config(root / "alembic.ini"))
    head_id = scripts.get_current_head()
    assert head_id is not None
    head = scripts.get_revision(head_id)
    assert head.revision == "20260912_0009"
    assert head.down_revision == "20260911_0008"


def test_operational_schema_has_canonical_entities_and_no_provider_identity() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (
        root / "migrations/versions/20260912_0009_operational_audit_foundation.py"
    ).read_text()
    for table in (
        "engine_runs",
        "run_quarantines",
        "operational_events",
        "operational_event_deliveries",
    ):
        assert f"CREATE TABLE {table}" in migration
    assert "sportmonks" not in migration.lower()
    assert "the_odds_api" not in migration.lower()
