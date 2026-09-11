from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from pitchvalue.ml import (
    ML_CLASS_ORDER,
    EnsembleCandidateDecision,
    EnsembleConfig,
    EnsembleStatus,
    MLClassProbability,
    MLDatasetValidationError,
    ProbabilityModelPrediction,
    WeightEvidence,
    blend_probabilities,
    decide_ensemble_candidate,
    select_temporal_weight,
    weight_distribution,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection


def _prediction(
    family: str,
    probabilities: tuple[str, str, str],
    *,
    row_id: str = "row-1",
    match_id: str = "match-1",
    as_of: datetime | None = None,
    residual: str = "0",
    class_order: tuple[Selection, ...] = ML_CLASS_ORDER,
) -> ProbabilityModelPrediction:
    return ProbabilityModelPrediction(
        row_id,
        match_id,
        as_of or datetime(2025, 1, 2, tzinfo=UTC),
        family,
        f"{family.lower()}_v1",
        class_order,
        tuple(
            MLClassProbability(selection, Decimal(value))
            for selection, value in zip(ML_CLASS_ORDER, probabilities, strict=True)
        ),
        Decimal(residual),
    )


def _pair(index: int, observed: Selection) -> WeightEvidence:
    as_of = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index)
    return WeightEvidence(
        as_of,
        observed,
        _prediction("ML", ("0.7", "0.2", "0.1"), row_id=f"row-{index}", as_of=as_of),
        _prediction("POISSON", ("0.4", "0.3", "0.3"), row_id=f"row-{index}", as_of=as_of),
    )


def test_config_is_immutable_and_deterministic() -> None:
    config = EnsembleConfig()
    assert config.to_dict() == config.to_dict()
    with pytest.raises(FrozenInstanceError):
        config.minimum_weight_evidence = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    "values",
    [
        {"minimum_weight_evidence": 0},
        {"probability_sum_tolerance": Decimal("0")},
        {"weight_grid": (Decimal("0.5"),)},
        {"weight_grid": (Decimal("0"), Decimal("1.1"), Decimal("1"))},
        {"weight_grid": (Decimal("0"), Decimal("0.5"), Decimal("0.5"), Decimal("1"))},
    ],
)
def test_config_rejects_invalid_values(values: dict[str, object]) -> None:
    with pytest.raises(MLDatasetValidationError):
        EnsembleConfig(**values)  # type: ignore[arg-type]


def test_weight_one_is_exact_ml_and_weight_zero_exact_poisson() -> None:
    ml = _prediction("ML", ("0.6", "0.25", "0.15"))
    poisson = _prediction("POISSON", ("0.4", "0.3", "0.3"))
    through = datetime(2025, 1, 1, tzinfo=UTC)
    ml_only = blend_probabilities(
        ml, poisson, Decimal(1), evidence_support=20, evidence_through=through
    )
    poisson_only = blend_probabilities(
        ml, poisson, Decimal(0), evidence_support=20, evidence_through=through
    )
    assert ml_only.probabilities == ml.probabilities
    assert poisson_only.probabilities == poisson.probabilities


def test_blend_preserves_poisson_residual_without_hidden_normalization() -> None:
    ml = _prediction("ML", ("0.6", "0.25", "0.15"))
    poisson = _prediction("POISSON", ("0.4", "0.3", "0.2995"), residual="0.0005")
    result = blend_probabilities(
        ml,
        poisson,
        Decimal("0.5"),
        evidence_support=20,
        evidence_through=datetime(2025, 1, 1, tzinfo=UTC),
    )
    assert result.unallocated_probability_mass == Decimal("0.00025")
    assert sum((item.probability for item in result.probabilities), Decimal(0)) == Decimal(
        "0.99975"
    )


@pytest.mark.parametrize(
    "prediction",
    [
        _prediction("ML", ("-0.1", "0.5", "0.6")),
        _prediction("ML", ("NaN", "0.5", "0.5")),
        _prediction("ML", ("0.2", "0.2", "0.2")),
        _prediction(
            "ML",
            ("0.6", "0.25", "0.15"),
            class_order=(Selection.DRAW, Selection.HOME, Selection.AWAY),
        ),
    ],
)
def test_invalid_probability_vectors_are_rejected(
    prediction: ProbabilityModelPrediction,
) -> None:
    with pytest.raises(MLDatasetValidationError):
        prediction.validate(Decimal("0.001"))


@pytest.mark.parametrize("field", ["row", "match", "time"])
def test_blend_rejects_misaligned_model_rows(field: str) -> None:
    ml = _prediction("ML", ("0.6", "0.25", "0.15"))
    values: dict[str, object] = {}
    if field == "row":
        values["row_id"] = "other"
    elif field == "match":
        values["match_id"] = "other"
    else:
        values["as_of"] = datetime(2025, 1, 3, tzinfo=UTC)
    poisson = _prediction("POISSON", ("0.4", "0.3", "0.3"), **values)  # type: ignore[arg-type]
    with pytest.raises(MLDatasetValidationError, match="aligned"):
        blend_probabilities(
            ml,
            poisson,
            Decimal("0.5"),
            evidence_support=20,
            evidence_through=datetime(2025, 1, 1, tzinfo=UTC),
        )


def test_blend_rejects_mismatched_target_market() -> None:
    ml = _prediction("ML", ("0.6", "0.25", "0.15"))
    poisson = replace(
        _prediction("POISSON", ("0.4", "0.3", "0.3")),
        target_market=MarketFamily.TOTAL_GOALS,
    )
    with pytest.raises(MLDatasetValidationError, match="MATCH_RESULT"):
        blend_probabilities(
            ml,
            poisson,
            Decimal("0.5"),
            evidence_support=20,
            evidence_through=datetime(2025, 1, 1, tzinfo=UTC),
        )


def test_temporal_weight_selection_requires_past_support() -> None:
    result = select_temporal_weight(
        (_pair(0, Selection.HOME),),
        datetime(2025, 2, 1, tzinfo=UTC),
        EnsembleConfig(minimum_weight_evidence=2),
    )
    assert result.status is EnsembleStatus.INSUFFICIENT_ENSEMBLE_SUPPORT


def test_same_time_or_future_weight_evidence_is_rejected() -> None:
    cutoff = datetime(2025, 1, 2, tzinfo=UTC)
    result = select_temporal_weight(
        (_pair(1, Selection.HOME),), cutoff, EnsembleConfig(minimum_weight_evidence=1)
    )
    assert result.status is EnsembleStatus.WEIGHT_SELECTION_FAILED


def test_weight_selection_is_deterministic_and_uses_only_prior_evidence() -> None:
    evidence = tuple(_pair(index, Selection.HOME) for index in range(6))
    config = EnsembleConfig(minimum_weight_evidence=3)
    cutoff = datetime(2025, 2, 1, tzinfo=UTC)
    assert select_temporal_weight(evidence, cutoff, config) == select_temporal_weight(
        tuple(reversed(evidence)), cutoff, config
    )


def test_decision_helper_permits_accept_reject_and_inconclusive() -> None:
    common = {
        "strongest_log_loss": Decimal("1"),
        "strongest_brier": Decimal("0.6"),
        "evaluated_folds": 3,
        "weights": (Decimal("0.4"), Decimal("0.6"), Decimal("0.5")),
    }
    assert (
        decide_ensemble_candidate(
            ensemble_log_loss=Decimal("0.9"),
            ensemble_brier=Decimal("0.59"),
            improved_folds=2,
            **common,
        )
        is EnsembleCandidateDecision.ACCEPT
    )
    assert (
        decide_ensemble_candidate(
            ensemble_log_loss=Decimal("1.1"),
            ensemble_brier=Decimal("0.61"),
            improved_folds=0,
            **common,
        )
        is EnsembleCandidateDecision.REJECT
    )
    assert (
        decide_ensemble_candidate(
            ensemble_log_loss=None,
            ensemble_brier=None,
            improved_folds=0,
            **common,
        )
        is EnsembleCandidateDecision.INCONCLUSIVE
    )


def test_weight_distribution_reports_boundaries() -> None:
    assert weight_distribution((Decimal(0), Decimal("0.5"), Decimal(1))) == (
        Decimal(0),
        Decimal("0.5"),
        Decimal(1),
        2,
    )


def test_ensemble_source_has_no_odds_edge_or_calibration_input() -> None:
    import pitchvalue.ml.ensemble as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    assert "odds_snapshot" not in source
    assert "bookmaker" not in source
    assert "no_vig" not in source
    assert "calibratedmlprediction" not in source
