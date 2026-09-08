import ast
from decimal import Decimal
from pathlib import Path

import pytest

from pitchvalue.evaluation.metrics import (
    ClassProbability,
    MetricConfig,
    MetricDiagnosticCode,
    MetricProvenance,
    MetricStatus,
    MulticlassPrediction,
    PredictionRecordStatus,
    multiclass_calibration,
)

ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "src" / "pitchvalue" / "evaluation" / "metrics"


def _row(
    home: str, draw: str, away: str, observed: str, identifier: str = "p"
) -> MulticlassPrediction:
    return MulticlassPrediction(
        identifier,
        tuple(
            ClassProbability(label, Decimal(value))
            for label, value in (("AWAY", away), ("DRAW", draw), ("HOME", home))
        ),
        observed,
    )


def test_multiclass_calibration_is_one_vs_rest_for_every_class() -> None:
    result = multiclass_calibration((_row("0.7", "0.2", "0.1", "HOME"),))
    assert [item.class_label for item in result.classes] == ["HOME", "DRAW", "AWAY"]
    assert all(item.calibration.usable_count == 1 for item in result.classes)
    assert all(item.calibration.ece is not None for item in result.classes)


@pytest.mark.parametrize(("label", "expected"), [("HOME", "1"), ("DRAW", "0"), ("AWAY", "0")])
def test_class_level_observed_frequency(label: str, expected: str) -> None:
    result = multiclass_calibration(
        (_row("0.7", "0.2", "0.1", "HOME"),), MetricConfig(bucket_edges=(Decimal(0), Decimal(1)))
    )
    class_result = next(item.calibration for item in result.classes if item.class_label == label)
    assert class_result.buckets[0].observed_frequency == Decimal(expected)


def test_macro_ece_is_mean_of_visible_class_eces() -> None:
    result = multiclass_calibration((_row("0.7", "0.2", "0.1", "HOME"),))
    values = [item.calibration.ece for item in result.classes]
    assert all(value is not None for value in values)
    assert result.macro_ece == sum(
        (value for value in values if value is not None), Decimal(0)
    ) / Decimal(3)


def test_multiclass_calibration_order_invariant() -> None:
    rows = (_row("0.7", "0.2", "0.1", "HOME", "a"), _row("0.2", "0.3", "0.5", "AWAY", "b"))
    assert (
        multiclass_calibration(rows).to_dict()
        == multiclass_calibration(tuple(reversed(rows))).to_dict()
    )


def test_invalid_multiclass_sum_is_explicit() -> None:
    result = multiclass_calibration((_row("0.4", "0.3", "0.2", "HOME"),))
    assert result.status is MetricStatus.INVALID_PROBABILITY
    assert result.classes == ()
    assert result.macro_ece is None


def test_class_domain_mismatch_is_rejected() -> None:
    binary = MulticlassPrediction(
        "binary",
        (ClassProbability("YES", Decimal("0.6")), ClassProbability("NO", Decimal("0.4"))),
        "YES",
    )
    result = multiclass_calibration((binary, _row("0.6", "0.2", "0.2", "HOME")))
    assert result.status is MetricStatus.INVALID_PROBABILITY
    assert result.diagnostics[0].code is MetricDiagnosticCode.CLASS_DOMAIN_MISMATCH


def test_missing_multiclass_prediction_is_counted() -> None:
    missing = MulticlassPrediction(
        "missing", (), None, PredictionRecordStatus.MISSING_PREDICTION, None
    )
    result = multiclass_calibration((_row("0.7", "0.2", "0.1", "HOME"), missing))
    assert (result.input_count, result.usable_count, result.excluded_count) == (2, 1, 1)


def test_empty_multiclass_calibration_is_explicit() -> None:
    result = multiclass_calibration(())
    assert result.status is MetricStatus.EMPTY_INPUT
    assert result.macro_ece is None


def test_multiclass_provenance_is_preserved_and_scoped_per_class() -> None:
    provenance = MetricProvenance("fold-1", "poisson", "v1", "comp", "season", "match_result")
    result = multiclass_calibration((_row("0.7", "0.2", "0.1", "HOME"),), provenance=provenance)
    assert result.provenance == provenance
    class_provenance = [item.calibration.provenance for item in result.classes]
    assert all(item is not None for item in class_provenance)
    assert [item.class_scope for item in class_provenance if item is not None] == [
        "HOME",
        "DRAW",
        "AWAY",
    ]


def test_serialization_is_deterministic() -> None:
    result = multiclass_calibration((_row("0.7", "0.2", "0.1", "HOME"),))
    assert result.to_dict() == result.to_dict()


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
        "pitchvalue.models.elo",
        "pitchvalue.models.form",
        "pitchvalue.models.poisson",
        "pitchvalue.models.signals",
        "sklearn",
        "xgboost",
        "lightgbm",
        "catboost",
        "numpy",
        "pandas",
        "scipy",
    ],
)
def test_metrics_package_has_no_forbidden_dependency(forbidden: str) -> None:
    assert all(name != forbidden and not name.startswith(f"{forbidden}.") for name in _imports())


@pytest.mark.parametrize(
    "term",
    [
        "isotonic",
        "platt",
        "temperature_scaling",
        "fit_calibrator",
        "train_model",
        "ensemble_weight",
        "expected_value",
        "return_on_investment",
        "kelly",
        "bet_score",
        "publication_eligible",
        "normalize_market",
        "create_engine",
        "datetime.now",
        "random.",
    ],
)
def test_metrics_package_does_not_implement_deferred_behavior(term: str) -> None:
    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in PACKAGE.glob("*.py"))
    assert term.lower() not in source
