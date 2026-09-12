from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_task21_is_single_new_migration_head() -> None:
    root = Path(__file__).resolve().parents[1]
    scripts = ScriptDirectory.from_config(Config(root / "alembic.ini"))
    head = scripts.get_revision("20260911_0008")
    assert head.revision == "20260911_0008"
    assert head.down_revision == "20260910_0007"


def test_prediction_schema_is_not_user_scoped() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (root / "migrations/versions/20260911_0008_prediction_snapshots.py").read_text()
    assert "CREATE TABLE prediction_snapshots" in migration
    assert "user_id" not in migration
    assert "uq_prediction_semantic_identity" in migration
