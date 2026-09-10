from __future__ import annotations

import inspect

from pitchvalue.ml import baseline, evaluation, model, preprocessing, real_data
from pitchvalue.ml.real_data import BASELINE_FEATURE_NAMES, MATCH_RESULT_TARGET
from pitchvalue.prediction.contracts import MarketFamily, Selection


def _source() -> str:
    return "\n".join(
        inspect.getsource(module)
        for module in (baseline, evaluation, model, preprocessing, real_data)
    ).lower()


def test_default_real_feature_schema_is_football_only() -> None:
    forbidden = ("odds", "implied", "no_vig", "edge", "final_score", "result")
    assert BASELINE_FEATURE_NAMES
    assert len(BASELINE_FEATURE_NAMES) == len(set(BASELINE_FEATURE_NAMES))
    assert not any(token in name.lower() for name in BASELINE_FEATURE_NAMES for token in forbidden)


def test_real_target_is_explicit_match_result() -> None:
    assert MATCH_RESULT_TARGET.market is MarketFamily.MATCH_RESULT
    assert MATCH_RESULT_TARGET.classes == (Selection.HOME, Selection.DRAW, Selection.AWAY)


def test_no_external_ml_framework_or_dataframe_dependency() -> None:
    source = _source()
    for token in ("sklearn", "xgboost", "lightgbm", "catboost", "pandas", "numpy", "torch"):
        assert token not in source


def test_no_random_production_split_or_shuffled_kfold() -> None:
    source = _source()
    assert "train_test_split" not in source
    assert "kfold" not in source
    assert "random_split" not in source


def test_real_adapter_does_not_read_historical_odds() -> None:
    source = inspect.getsource(real_data).lower()
    assert "odds_snapshots" not in source
    assert "decimal_odds" not in source


def test_no_calibrator_ensemble_or_value_engine() -> None:
    source = _source()
    for token in (
        "isotonic",
        "platt",
        "temperature_scaling",
        "ensemble_weight",
        "kelly",
        "bet_score",
        "expected_value",
    ):
        assert token not in source


def test_no_model_artifact_persistence() -> None:
    source = _source()
    for token in ("joblib", ".pkl", "pickle.dump", "model_artifact"):
        assert token not in source
