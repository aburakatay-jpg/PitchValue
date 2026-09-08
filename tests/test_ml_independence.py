import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
ML = ROOT / "src" / "pitchvalue" / "ml"


def _source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(ML.glob("*.py")))


def _imports() -> set[str]:
    names: set[str] = set()
    for path in ML.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
    return names


def test_no_database_sqlalchemy_or_persistence_dependency() -> None:
    imports = _imports()
    assert not any(
        name.startswith(("sqlalchemy", "pitchvalue.db", "pitchvalue.repositories"))
        for name in imports
    )


def test_no_api_dependency() -> None:
    assert not any(name.startswith(("fastapi", "pitchvalue.api")) for name in _imports())


def test_no_dataframe_or_numeric_library_dependency() -> None:
    imports = _imports()
    assert not any(name.startswith(("pandas", "numpy", "scipy")) for name in imports)


def test_no_ml_training_library_dependency() -> None:
    imports = _imports()
    assert not any(
        name.startswith(("sklearn", "xgboost", "lightgbm", "catboost", "torch", "tensorflow"))
        for name in imports
    )


def test_no_training_scaling_encoding_or_selection_implementation() -> None:
    source = _source().lower()
    for forbidden in (
        ".fit(",
        "fit_transform",
        "standardscaler",
        "onehotencoder",
        "smote",
        "feature_importance",
    ):
        assert forbidden not in source


def test_no_calibration_ensemble_or_model_execution() -> None:
    imports = _imports()
    assert not any(
        name.startswith(("pitchvalue.models", "pitchvalue.evaluation.metrics")) for name in imports
    )


def test_no_odds_normalization_edge_roi_or_publication() -> None:
    imports = _imports()
    assert "pitchvalue.markets.implied" not in imports
    source = _source().lower()
    for forbidden in (
        "calculate_edge",
        "expected_value",
        "kelly",
        "roi",
        "bet_score",
        "evaluate_candidate",
    ):
        assert forbidden not in source


def test_no_train_test_split_implementation() -> None:
    source = _source().lower()
    for forbidden in ("train_test_split", "shuffle_split", "randomkfold", "stratifiedkfold"):
        assert forbidden not in source


def test_pure_execution_has_no_clock_randomness_or_network() -> None:
    source = _source().lower()
    for forbidden in ("datetime.now", "datetime.utcnow", "uuid4", "random.", "requests.", "httpx."):
        assert forbidden not in source


def test_public_surface_contains_contracts_builder_and_no_trainer() -> None:
    import pitchvalue.ml as ml

    assert callable(ml.build_dataset)
    assert hasattr(ml, "FeatureRecord")
    assert hasattr(ml, "TargetDefinition")
    assert not hasattr(ml, "train_model")
