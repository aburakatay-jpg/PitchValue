import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "src" / "pitchvalue" / "evaluation"


def _imports() -> set[str]:
    imported: set[str] = set()
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    return imported


@pytest.mark.parametrize(
    "forbidden",
    [
        "sqlalchemy",
        "alembic",
        "fastapi",
        "pitchvalue.api",
        "pitchvalue.models.poisson",
        "pitchvalue.models.elo",
        "pitchvalue.models.form",
        "pitchvalue.models.signals",
        "sklearn",
        "xgboost",
        "lightgbm",
        "catboost",
        "numpy",
        "pandas",
    ],
)
def test_evaluation_package_has_no_forbidden_dependency(forbidden: str) -> None:
    assert all(name != forbidden and not name.startswith(f"{forbidden}.") for name in _imports())


@pytest.mark.parametrize(
    "forbidden_term",
    [
        "brier_score",
        "log_loss",
        "expected_calibration_error",
        "return_on_investment",
        "kelly_fraction",
        "bet_score",
        "publication_eligible",
        "normalize_market",
        "create_engine",
        "datetime.now",
        "random.",
    ],
)
def test_evaluation_package_does_not_implement_deferred_behavior(forbidden_term: str) -> None:
    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in PACKAGE.glob("*.py"))
    assert forbidden_term.lower() not in source


def test_only_temporal_split_strategies_exist() -> None:
    from pitchvalue.evaluation import SplitStrategy

    assert tuple(SplitStrategy) == (SplitStrategy.EXPANDING, SplitStrategy.ROLLING)
