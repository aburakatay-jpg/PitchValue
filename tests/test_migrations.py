from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_framework_discovers_baseline() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(project_root / "alembic.ini")
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_current_head() == "ccfe1992e71e"
